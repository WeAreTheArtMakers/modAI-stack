import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import DateTime, create_engine, inspect, text

from app.models.database import Base


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0009_document_archive.py"
)


def _migration():
    spec = importlib.util.spec_from_file_location(
        "migration_0009_document_archive",
        MIGRATION_PATH,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_document_archived_at_is_optional_timezone_aware_and_indexed():
    documents = Base.metadata.tables["documents"]

    assert "archived_at" in documents.c
    assert documents.c.archived_at.nullable is True
    assert isinstance(documents.c.archived_at.type, DateTime)
    assert documents.c.archived_at.type.timezone is True
    assert documents.c.archived_at.server_default is None

    index_names = {
        index.name
        for index in documents.indexes
        if index.name
    }

    assert "ix_documents_archived_at" in index_names


def test_archive_migration_follows_assistant_preferences_on_one_branch():
    migration = _migration()

    assert migration.revision == "0009_document_archive"
    assert migration.down_revision == "0008_assistant_preferences"

    scripts = ScriptDirectory(str(MIGRATION_PATH.parents[1]))
    heads = scripts.get_heads()

    assert len(heads) == 1
    assert "0009_document_archive" in {
        script.revision
        for script in scripts.walk_revisions("base", heads[0])
    }


def test_archive_migration_leaves_existing_documents_live_and_downgrades():
    migration = _migration()
    engine = create_engine("sqlite:///:memory:")

    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE documents ("
                "id INTEGER PRIMARY KEY, "
                "filename VARCHAR(255) NOT NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO documents (id, filename) VALUES "
                "(1, 'destek-v2.md'), (2, 'destek-v3.md')"
            )
        )

        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        inspector = inspect(connection)
        columns = {
            column["name"]: column
            for column in inspector.get_columns("documents")
        }

        assert columns["archived_at"]["nullable"] is True
        assert "ix_documents_archived_at" in {
            index["name"]
            for index in inspector.get_indexes("documents")
        }
        # No existing document becomes archived by the migration.
        assert connection.execute(
            text("SELECT id, archived_at FROM documents ORDER BY id")
        ).all() == [(1, None), (2, None)]

        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()

        inspector = inspect(connection)

        assert "archived_at" not in {
            column["name"]
            for column in inspector.get_columns("documents")
        }
        assert "ix_documents_archived_at" not in {
            index["name"]
            for index in inspector.get_indexes("documents")
        }
        assert connection.execute(
            text("SELECT id, filename FROM documents ORDER BY id")
        ).all() == [(1, "destek-v2.md"), (2, "destek-v3.md")]

    engine.dispose()
