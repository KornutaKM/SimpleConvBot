import json
import logging
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID, uuid4

import pytest

from simpleconvbot.jobs import JobSnapshot, JobState
from simpleconvbot.sessions import (
    CollectionSessionSnapshot,
    SessionFileNotFound,
    SessionFileSnapshot,
    SessionKind,
    SessionState,
)
from simpleconvbot.telegram_sessions import (
    _emit_download,
    _last_session_file_id,
    parse_session_callback,
)
from simpleconvbot.telemetry import OperationOutcome


def test_session_callback_parser_is_closed_and_uuid_bound() -> None:
    session_id = uuid4()

    assert parse_session_callback(f"sess:add:{session_id}") == ("add", session_id)
    assert parse_session_callback(f"sess:remove:{session_id}") == ("remove", session_id)
    assert parse_session_callback(f"sess:done:{session_id}") == ("done", session_id)
    assert parse_session_callback(f"sess:cancel:{session_id}") == ("cancel", session_id)


def test_session_callback_parser_rejects_free_form_values() -> None:
    assert parse_session_callback(None) is None
    assert parse_session_callback("sess:done:not-a-uuid") is None
    assert parse_session_callback(f"sess:delete:{UUID(int=0)}") is None
    assert parse_session_callback("ui:pdf:merge") is None


def test_collection_validation_telemetry_records_only_input_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    now = datetime.now(UTC)
    job = JobSnapshot(
        job_id=uuid4(),
        idempotency_key="test",
        operation_id="pdf.merge",
        operation_version=1,
        user_id=101,
        chat_id=202,
        source_message_id=303,
        state=JobState.VALIDATING,
        created_at=now,
        updated_at=now,
    )

    with caplog.at_level(logging.INFO, logger="simpleconvbot.telegram_sessions"):
        _emit_download(
            job,
            monotonic(),
            OperationOutcome.SUCCESS,
            3,
        )

    payload = json.loads(caplog.messages[-1])
    assert payload["event"] == "operation_stage"
    assert payload["operation_id"] == "pdf.merge"
    assert payload["stage"] == "validation"
    assert payload["outcome"] == "success"
    assert payload["count"] == 3
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in ("user_id", "chat_id", "source_message_id", "filename"):
        assert forbidden not in serialized


def test_last_session_file_selection_uses_highest_persisted_position() -> None:
    now = datetime.now(UTC)
    first = SessionFileSnapshot(uuid4(), 10, "A", 100, 1)
    last = SessionFileSnapshot(uuid4(), 30, "C", 300, 7)
    middle = SessionFileSnapshot(uuid4(), 20, "B", 200, 4)
    snapshot = CollectionSessionSnapshot(
        session_id=uuid4(),
        kind=SessionKind.PDF_MERGE,
        state=SessionState.COLLECTING,
        owner_user_id=1,
        chat_id=2,
        expires_at=now,
        file_count=3,
        total_bytes=600,
        files=(last, first, middle),
        created_at=now,
        updated_at=now,
    )

    assert _last_session_file_id(snapshot) == last.file_id


def test_last_session_file_selection_rejects_empty_collection() -> None:
    now = datetime.now(UTC)
    snapshot = CollectionSessionSnapshot(
        session_id=uuid4(),
        kind=SessionKind.IMAGES_TO_PDF,
        state=SessionState.COLLECTING,
        owner_user_id=1,
        chat_id=2,
        expires_at=now,
        file_count=0,
        total_bytes=0,
        files=(),
        created_at=now,
        updated_at=now,
    )

    with pytest.raises(SessionFileNotFound):
        _last_session_file_id(snapshot)
