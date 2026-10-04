"""Interactive, first-install-only platform administrator bootstrap."""

import asyncio
from getpass import getpass

from pydantic import ValidationError
from sqlalchemy import func, select, text

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.database import User
from app.models.schemas import RegisterRequest
from app.services.audit import record_audit_event
from app.services.invitations import normalize_email


async def bootstrap_admin(email: str, password: str) -> User:
    normalized = normalize_email(email)
    try:
        validated = RegisterRequest(email=normalized, password=password)
    except ValidationError as exc:
        field = "email" if any(item["loc"][0] == "email" for item in exc.errors()) else "password"
        raise ValueError(f"Invalid {field} for platform administrator") from None

    async with SessionLocal() as db:
        # An empty table cannot be row-locked. Serialize first installation on
        # PostgreSQL so two operators cannot create two first administrators.
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            await db.execute(text("SELECT pg_advisory_xact_lock(836457311)"))
        if await db.scalar(select(User.id).where(User.role == "admin").limit(1)) is not None:
            raise ValueError("A platform administrator already exists; bootstrap is refused")
        if await db.scalar(select(User.id).where(func.lower(User.email) == validated.email)) is not None:
            raise ValueError("Account already exists; bootstrap never promotes an existing user")
        account = User(email=validated.email, password_hash=hash_password(password), role="admin")
        db.add(account)
        await db.flush()
        record_audit_event(db, action="bootstrap_admin_created", resource_type="user",
                           resource_id=account.id, actor_user_id=account.id)
        await db.commit()
        return account


def main() -> None:
    email = input("First platform admin email: ").strip()
    password = getpass("New platform admin password: ")
    confirmation = getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match; no account was created")
    try:
        account = asyncio.run(bootstrap_admin(email, password))
    except ValueError as exc:
        raise SystemExit(f"Bootstrap refused: {exc}") from None
    print(f"Platform administrator created: {account.email}")


if __name__ == "__main__":
    main()
