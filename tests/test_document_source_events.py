from types import SimpleNamespace

import pytest

from app.models.database import DocumentIndexEvent
from app.services.document_source_events import (
    ACTIVE_VERSION_PUBLISHED,
    SOURCE_STAGED,
    add_document_source_event,
    advance_document_source_revision,
    lock_document_source,
)


class FakeDb:
    def __init__(self):
        self.added = []

    def add(self, item):
        self.added.append(item)


def document(**overrides):
    values = {
        "id": 7,
        "organization_id": 2,
        "workspace_id": 3,
        "knowledge_base_id": 4,
        "source_revision": 1,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_initial_staged_event_uses_existing_revision_one():
    db = FakeDb()
    doc = document()

    event = add_document_source_event(
        db,
        document=doc,
        operation=SOURCE_STAGED,
        document_version=1,
        content_hash="a" * 64,
    )

    assert isinstance(event, DocumentIndexEvent)
    assert event.document_id == 7
    assert event.source_revision == 1
    assert event.operation == SOURCE_STAGED
    assert event.document_version == 1
    assert event.content_hash == "a" * 64
    assert db.added == [event]


def test_revision_advances_before_replacement_event():
    db = FakeDb()
    doc = document(source_revision=4)

    assert advance_document_source_revision(doc) == 5

    event = add_document_source_event(
        db,
        document=doc,
        operation=SOURCE_STAGED,
        document_version=3,
        content_hash="b" * 64,
    )

    assert event.source_revision == 5


def test_publication_event_uses_advanced_revision():
    db = FakeDb()
    doc = document(source_revision=8)

    advance_document_source_revision(doc)

    event = add_document_source_event(
        db,
        document=doc,
        operation=ACTIVE_VERSION_PUBLISHED,
        document_version=4,
        content_hash="c" * 64,
    )

    assert event.source_revision == 9
    assert event.operation == ACTIVE_VERSION_PUBLISHED


@pytest.mark.parametrize(
    "missing",
    (
        "organization_id",
        "workspace_id",
        "knowledge_base_id",
    ),
)
def test_event_scope_fails_closed_when_tenant_scope_is_missing(missing):
    db = FakeDb()
    doc = document(**{missing: None})

    with pytest.raises(
        ValueError,
        match="requires organization, workspace",
    ):
        add_document_source_event(
            db,
            document=doc,
            operation=SOURCE_STAGED,
            document_version=1,
            content_hash="d" * 64,
        )

    assert db.added == []


def test_revision_cannot_advance_from_invalid_value():
    doc = document(source_revision=0)

    with pytest.raises(
        ValueError,
        match="source revision must be positive",
    ):
        advance_document_source_revision(doc)


@pytest.mark.asyncio
async def test_lock_document_source_refreshes_existing_orm_state():
    doc = document()

    class CaptureDb:
        def __init__(self):
            self.statement = None

        async def scalar(self, statement):
            self.statement = statement
            return doc

    db = CaptureDb()

    result = await lock_document_source(db, doc.id)

    assert result is doc
    assert (
        db.statement.get_execution_options()
        .get("populate_existing")
        is True
    )
