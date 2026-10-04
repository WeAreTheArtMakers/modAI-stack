import sqlite3

import pytest
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError

from app.models.database import Base


EXPECTED_TABLES = {
    "index_generations",
    "workspace_retrieval_assignments",
    "document_index_events",
    "index_generation_items",
    "index_generation_event_receipts",
}


def test_generation_schema_is_present_in_metadata():
    assert EXPECTED_TABLES.issubset(Base.metadata.tables)

    documents = Base.metadata.tables["documents"]

    assert "source_revision" in documents.c
    assert documents.c.source_revision.nullable is False

    assert "deleted_at" in documents.c
    assert documents.c.deleted_at.nullable is True


def test_source_events_and_generation_items_survive_document_row_deletion_design():
    events = Base.metadata.tables["document_index_events"]
    items = Base.metadata.tables["index_generation_items"]

    event_fk_targets = {
        fk.target_fullname
        for fk in events.c.document_id.foreign_keys
    }
    item_fk_targets = {
        fk.target_fullname
        for fk in items.c.document_id.foreign_keys
    }

    assert "documents.id" not in event_fk_targets
    assert "documents.id" not in item_fk_targets


def test_assignment_has_same_workspace_generation_foreign_key():
    assignments = Base.metadata.tables[
        "workspace_retrieval_assignments"
    ]

    composite_targets = {
        tuple(
            element.target_fullname
            for element in constraint.elements
        )
        for constraint in assignments.foreign_key_constraints
    }

    assert (
        "index_generations.workspace_id",
        "index_generations.id",
    ) in composite_targets


def test_generation_contract_identity_fields_are_required():
    generations = Base.metadata.tables["index_generations"]

    for column_name in (
        "profile_id",
        "profile_version",
        "space_json",
        "space_sha256",
        "materialization_json",
        "materialization_sha256",
        "qdrant_collection",
        "state",
    ):
        assert generations.c[column_name].nullable is False


def test_assignment_does_not_auto_create_verified_generation():
    assignments = Base.metadata.tables[
        "workspace_retrieval_assignments"
    ]

    assert assignments.c.active_generation_id.nullable is True
    assert assignments.c.serving_mode.default.arg == "legacy"


def _sqlite_engine():
    engine = create_engine("sqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        del connection_record
        if isinstance(dbapi_connection, sqlite3.Connection):
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def test_schema_creates_cleanly_on_sqlite():
    engine = _sqlite_engine()
    Base.metadata.create_all(engine)

    names = set(inspect(engine).get_table_names())

    assert EXPECTED_TABLES.issubset(names)


def test_assignment_rejects_generation_from_another_workspace():
    engine = _sqlite_engine()
    Base.metadata.create_all(engine)

    organizations = Base.metadata.tables["organizations"]
    workspaces = Base.metadata.tables["workspaces"]
    generations = Base.metadata.tables["index_generations"]
    assignments = Base.metadata.tables[
        "workspace_retrieval_assignments"
    ]

    with engine.begin() as conn:
        conn.execute(
            organizations.insert(),
            [
                {"id": 1, "name": "Org", "slug": "org"},
            ],
        )
        conn.execute(
            workspaces.insert(),
            [
                {
                    "id": 1,
                    "organization_id": 1,
                    "name": "One",
                    "slug": "one",
                },
                {
                    "id": 2,
                    "organization_id": 1,
                    "name": "Two",
                    "slug": "two",
                },
            ],
        )
        conn.execute(
            generations.insert(),
            {
                "id": "00000000-0000-0000-0000-000000000002",
                "workspace_id": 2,
                "generation_number": 1,
                "profile_id": "test-profile",
                "profile_version": 1,
                "space_json": {"schema_version": 1},
                "space_sha256": "a" * 64,
                "materialization_json": {"schema_version": 1},
                "materialization_sha256": "b" * 64,
                "qdrant_collection": "modai_space_test",
                "state": "planned",
            },
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                assignments.insert(),
                {
                    "workspace_id": 1,
                    "serving_mode": "generation",
                    "active_generation_id": (
                        "00000000-0000-0000-0000-000000000002"
                    ),
                    "assignment_epoch": 1,
                },
            )


def test_legacy_assignment_cannot_point_to_generation():
    engine = _sqlite_engine()
    Base.metadata.create_all(engine)

    organizations = Base.metadata.tables["organizations"]
    workspaces = Base.metadata.tables["workspaces"]
    generations = Base.metadata.tables["index_generations"]
    assignments = Base.metadata.tables[
        "workspace_retrieval_assignments"
    ]

    generation_id = "00000000-0000-0000-0000-000000000001"

    with engine.begin() as conn:
        conn.execute(
            organizations.insert(),
            {"id": 1, "name": "Org", "slug": "org"},
        )
        conn.execute(
            workspaces.insert(),
            {
                "id": 1,
                "organization_id": 1,
                "name": "One",
                "slug": "one",
            },
        )
        conn.execute(
            generations.insert(),
            {
                "id": generation_id,
                "workspace_id": 1,
                "generation_number": 1,
                "profile_id": "test-profile",
                "profile_version": 1,
                "space_json": {"schema_version": 1},
                "space_sha256": "a" * 64,
                "materialization_json": {"schema_version": 1},
                "materialization_sha256": "b" * 64,
                "qdrant_collection": "modai_space_test",
                "state": "planned",
            },
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(
                assignments.insert(),
                {
                    "workspace_id": 1,
                    "serving_mode": "legacy",
                    "active_generation_id": generation_id,
                    "assignment_epoch": 0,
                },
            )


def test_document_source_revision_has_positive_database_invariant():
    documents = Base.metadata.tables["documents"]

    constraint_names = {
        constraint.name
        for constraint in documents.constraints
        if constraint.name
    }

    assert "ck_documents_source_revision" in constraint_names


def test_document_deleted_at_index_matches_migration_metadata():
    documents = Base.metadata.tables["documents"]

    index_names = {
        index.name
        for index in documents.indexes
        if index.name
    }

    assert "ix_documents_deleted_at" in index_names


def test_active_ready_generation_can_coexist_with_replacement_candidate():
    engine = _sqlite_engine()
    Base.metadata.create_all(engine)

    organizations = Base.metadata.tables["organizations"]
    workspaces = Base.metadata.tables["workspaces"]
    generations = Base.metadata.tables["index_generations"]
    assignments = Base.metadata.tables[
        "workspace_retrieval_assignments"
    ]

    active_id = "00000000-0000-0000-0000-000000000001"
    candidate_id = "00000000-0000-0000-0000-000000000002"

    base = {
        "workspace_id": 1,
        "profile_id": "test-profile",
        "profile_version": 1,
        "space_json": {"schema_version": 1},
        "materialization_json": {"schema_version": 1},
        "qdrant_collection": "modai_space_test",
    }

    with engine.begin() as conn:
        conn.execute(
            organizations.insert(),
            {
                "id": 1,
                "name": "Org",
                "slug": "org",
            },
        )

        conn.execute(
            workspaces.insert(),
            {
                "id": 1,
                "organization_id": 1,
                "name": "Workspace",
                "slug": "workspace",
            },
        )

        # Persisted state is "ready"; active role comes from assignment.
        conn.execute(
            generations.insert(),
            {
                **base,
                "id": active_id,
                "generation_number": 1,
                "space_sha256": "a" * 64,
                "materialization_sha256": "b" * 64,
                "state": "ready",
            },
        )

        conn.execute(
            assignments.insert(),
            {
                "workspace_id": 1,
                "serving_mode": "generation",
                "active_generation_id": active_id,
                "assignment_epoch": 1,
            },
        )

        # Replacement candidate must be able to exist beside the
        # currently serving generation.
        conn.execute(
            generations.insert(),
            {
                **base,
                "id": candidate_id,
                "generation_number": 2,
                "space_sha256": "c" * 64,
                "materialization_sha256": "d" * 64,
                "state": "planned",
            },
        )

        rows = conn.execute(
            generations.select().where(
                generations.c.workspace_id == 1
            )
        ).all()

    assert len(rows) == 2
