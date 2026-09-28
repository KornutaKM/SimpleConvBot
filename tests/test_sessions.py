from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from simpleconvbot.sessions import (
    CollectionSessionSnapshot,
    SessionClosed,
    SessionFileInput,
    SessionFileSnapshot,
    SessionKind,
    SessionPolicy,
    SessionState,
    finalization_plan,
)


def test_session_kind_maps_to_fixed_operation_identity() -> None:
    assert SessionKind.IMAGES_TO_PDF.operation_id == "pdf.from_images"
    assert SessionKind.PDF_MERGE.operation_id == "pdf.merge"


def test_session_policy_has_bounded_positive_defaults() -> None:
    policy = SessionPolicy()

    assert policy.max_files == 20
    assert policy.max_aggregate_bytes == 40 * 1024 * 1024
    assert policy.ttl.total_seconds() == 3600


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_files": 0},
        {"max_aggregate_bytes": 0},
        {"ttl_seconds": 0},
    ],
)
def test_session_policy_rejects_non_positive_limits(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        SessionPolicy(**kwargs)


def test_session_file_input_rejects_invalid_identity_and_size() -> None:
    with pytest.raises(ValueError):
        SessionFileInput(source_message_id=0, object_ref="ref", byte_size=1)
    with pytest.raises(ValueError):
        SessionFileInput(source_message_id=1, object_ref="", byte_size=1)
    with pytest.raises(ValueError):
        SessionFileInput(source_message_id=1, object_ref="ref", byte_size=0)


def test_finalization_plan_preserves_persisted_position_order() -> None:
    now = datetime(2026, 9, 28, tzinfo=UTC)
    later = SessionFileSnapshot(uuid4(), 20, "second", 2, 2)
    earlier = SessionFileSnapshot(uuid4(), 10, "first", 1, 1)
    snapshot = CollectionSessionSnapshot(
        session_id=uuid4(),
        kind=SessionKind.PDF_MERGE,
        state=SessionState.FINALIZED,
        owner_user_id=1,
        chat_id=2,
        expires_at=now,
        file_count=2,
        total_bytes=3,
        files=(later, earlier),
        created_at=now,
        updated_at=now,
    )

    plan = finalization_plan(snapshot)

    assert plan.operation_id == "pdf.merge"
    assert plan.ordered_input_refs == ("first", "second")


def test_non_finalized_session_has_no_execution_plan() -> None:
    now = datetime(2026, 9, 28, tzinfo=UTC)
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

    with pytest.raises(SessionClosed):
        finalization_plan(snapshot)
