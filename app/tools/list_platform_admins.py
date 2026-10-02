"""List platform administrators without exposing credentials or token material."""
import asyncio

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.database import User


async def list_platform_admins() -> list[str]:
    async with SessionLocal() as db:
        return list((await db.scalars(select(User.email).where(User.role == "admin").order_by(User.email))).all())


def main() -> None:
    admins = asyncio.run(list_platform_admins())
    if not admins:
        print("No platform administrators found")
        return
    print("Platform administrators:")
    for email in admins:
        print(f"- {email}")


if __name__ == "__main__":
    main()
