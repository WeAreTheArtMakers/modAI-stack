"""Explicit, local-only bootstrap for platform-level administration."""
import argparse
import asyncio
from getpass import getpass

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.database import User
from app.services.audit import record_audit_event


async def promote_platform_admin(email: str, *, create: bool = False, password: str | None = None) -> tuple[User, bool]:
    """Promote an existing account, or explicitly create the first platform admin."""
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("An email address is required")
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == normalized_email))
        created = False
        if user is None:
            if not create:
                raise ValueError("No user exists with that email; re-run with --create to create one explicitly")
            if not password:
                raise ValueError("A password is required when creating a platform admin")
            user = User(email=normalized_email, password_hash=hash_password(password), role="admin")
            db.add(user)
            created = True
        else:
            user.role = "admin"
        record_audit_event(db, action="platform_admin_promotion", resource_type="user", actor_user_id=user.id if not created else None, resource_id=user.id or normalized_email, metadata={"created": created})
        await db.commit()
        await db.refresh(user)
        return user, created


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or promote a local platform administrator.")
    parser.add_argument("--email", help="Existing user email, or the email to create with --create")
    parser.add_argument("--create", action="store_true", help="Explicitly create the user when it does not exist")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    email = args.email or input("Platform admin email: ").strip()
    password = None
    if args.create:
        password = getpass("New platform admin password: ")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords do not match; no account was created")
    try:
        user, created = asyncio.run(promote_platform_admin(email, create=args.create, password=password))
    except ValueError as exc:
        raise SystemExit(f"Platform admin bootstrap failed: {exc}") from exc
    action = "created and promoted" if created else "promoted"
    print(f"Platform administrator {action}: {user.email}")


if __name__ == "__main__":
    main()
