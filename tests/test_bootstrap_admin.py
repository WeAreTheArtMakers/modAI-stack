import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.security import verify_password
from app.models.database import AuditEvent, Base, Membership, Organization, User
from app.tools import bootstrap_admin, check_compose_env


@pytest.mark.asyncio
async def test_first_platform_admin_is_created_once_with_hashed_password_and_audit(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(bootstrap_admin, "SessionLocal", maker)
    account = await bootstrap_admin.bootstrap_admin("  FIRST.ADMIN@EXAMPLE.COM  ", "chosen-long-password")
    assert account.email == "first.admin@example.com" and account.role == "admin"
    assert account.password_hash != "chosen-long-password"
    assert verify_password("chosen-long-password", account.password_hash)
    async with maker() as db:
        assert len(list((await db.scalars(select(User))).all())) == 1
        assert list((await db.scalars(select(Organization))).all()) == []
        assert list((await db.scalars(select(Membership))).all()) == []
        event = await db.scalar(select(AuditEvent).where(AuditEvent.action == "bootstrap_admin_created"))
        assert event is not None and "chosen-long-password" not in str(event.metadata_json)
    with pytest.raises(ValueError, match="already exists"):
        await bootstrap_admin.bootstrap_admin("second@example.com", "another-long-password")
    await engine.dispose()


@pytest.mark.asyncio
async def test_bootstrap_rejects_existing_user_invalid_email_and_weak_password(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(bootstrap_admin, "SessionLocal", maker)
    async with maker() as db:
        db.add(User(email="Existing@Example.com", password_hash="unchanged", role="user"))
        await db.commit()
    for email, password, expected in (
        ("bad-email", "long-enough-password", "email"),
        ("new@example.com", "weak", "password"),
        ("existing@example.com", "long-enough-password", "never promotes"),
    ):
        with pytest.raises(ValueError, match=expected):
            await bootstrap_admin.bootstrap_admin(email, password)
    async with maker() as db:
        user = await db.scalar(select(User).where(User.email == "Existing@Example.com"))
        assert user.role == "user" and user.password_hash == "unchanged"
    await engine.dispose()


def test_bootstrap_cli_prompts_securely_and_never_echoes_password(monkeypatch, capsys):
    class Account:
        email = "first@example.com"

    seen = []
    monkeypatch.setattr("builtins.input", lambda _prompt: "FIRST@example.com")
    monkeypatch.setattr(bootstrap_admin, "getpass", lambda _prompt: "secret-sentinel-password")
    def fake_run(coroutine):
        seen.append(coroutine)
        coroutine.close()
        return Account()
    monkeypatch.setattr(bootstrap_admin.asyncio, "run", fake_run)
    bootstrap_admin.main()
    output = capsys.readouterr().out
    assert len(seen) == 1 and "first@example.com" in output
    assert "secret-sentinel-password" not in output


def test_compose_environment_checker_reports_presence_without_values(tmp_path, monkeypatch, capsys):
    for key in check_compose_env.REQUIRED:
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / ".env"
    path.write_text("POSTGRES_DB=test_db\nPOSTGRES_USER=test_user\nPOSTGRES_PASSWORD=secret-sentinel\n")
    assert all(check_compose_env.check_compose_env(path).values())
    monkeypatch.chdir(tmp_path)
    check_compose_env.main()
    output = capsys.readouterr().out
    assert "POSTGRES_PASSWORD: SET" in output
    assert "secret-sentinel" not in output
