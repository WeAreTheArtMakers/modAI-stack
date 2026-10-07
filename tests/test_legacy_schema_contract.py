import sqlite3

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError

from app.models.database import Base


def _engine():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(connection, _record):
        if isinstance(connection, sqlite3.Connection):
            connection.execute("PRAGMA foreign_keys=ON")

    return engine


def test_legacy_required_timestamps_and_workspace_indexes_match_metadata():
    expected_not_null = {
        "users": ("created_at",),
        "organizations": ("created_at",),
        "documents": ("created_at",),
        "document_versions": ("created_at",),
        "index_jobs": ("created_at", "updated_at"),
    }

    for table_name, columns in expected_not_null.items():
        table = Base.metadata.tables[table_name]
        assert all(table.c[column].nullable is False for column in columns)

    knowledge_bases = Base.metadata.tables["knowledge_bases"]
    assert "uq_knowledge_bases_workspace_slug" in {
        constraint.name for constraint in knowledge_bases.constraints
    }

    engine = _engine()
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    assert {
        "ix_documents_content_hash",
        "ix_documents_knowledge_base_id",
        "ix_documents_organization_id",
        "ix_documents_workspace_id",
        "ix_document_versions_content_hash",
        "ix_knowledge_bases_workspace_id",
        "ix_memberships_organization_id",
        "ix_memberships_workspace_id",
    }.issubset({index["name"] for index in inspector.get_indexes("documents")}
               | {index["name"] for index in inspector.get_indexes("document_versions")}
               | {index["name"] for index in inspector.get_indexes("knowledge_bases")}
               | {index["name"] for index in inspector.get_indexes("memberships")})


def test_knowledge_base_slugs_are_unique_per_workspace_not_globally():
    engine = _engine()
    Base.metadata.create_all(engine)
    organizations = Base.metadata.tables["organizations"]
    workspaces = Base.metadata.tables["workspaces"]
    knowledge_bases = Base.metadata.tables["knowledge_bases"]

    with engine.begin() as connection:
        connection.execute(
            organizations.insert(),
            [
                {"id": 1, "name": "One", "slug": "one"},
                {"id": 2, "name": "Two", "slug": "two"},
            ],
        )
        connection.execute(
            workspaces.insert(),
            [
                {"id": 1, "organization_id": 1, "name": "One", "slug": "one"},
                {"id": 2, "organization_id": 2, "name": "Two", "slug": "two"},
            ],
        )
        connection.execute(
            knowledge_bases.insert(),
            [
                {"workspace_id": 1, "name": "Docs", "slug": "docs"},
                {"workspace_id": 2, "name": "Docs", "slug": "docs"},
            ],
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                knowledge_bases.insert(),
                {"workspace_id": 1, "name": "Duplicate", "slug": "docs"},
            )
