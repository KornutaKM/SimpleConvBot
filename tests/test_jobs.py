import pytest

from simpleconvbot.jobs import InvalidTransition, JobState, can_transition, ensure_transition


def test_happy_path_transitions_are_allowed() -> None:
    path = (
        (JobState.RECEIVED, JobState.VALIDATING),
        (JobState.VALIDATING, JobState.QUEUED),
        (JobState.QUEUED, JobState.PROCESSING),
        (JobState.PROCESSING, JobState.UPLOADING),
        (JobState.UPLOADING, JobState.COMPLETED),
    )

    for current, target in path:
        assert can_transition(current, target)
        ensure_transition(current, target)


def test_terminal_state_cannot_transition() -> None:
    with pytest.raises(InvalidTransition):
        ensure_transition(JobState.COMPLETED, JobState.PROCESSING)


def test_skipping_state_is_rejected() -> None:
    with pytest.raises(InvalidTransition):
        ensure_transition(JobState.QUEUED, JobState.COMPLETED)
