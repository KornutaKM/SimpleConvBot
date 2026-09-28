import pytest

from simpleconvbot.jobs import JobAdmissionPolicy


def test_job_admission_policy_defaults_are_bounded() -> None:
    policy = JobAdmissionPolicy()

    assert policy.max_active_per_user == 3
    assert policy.max_active_global == 32


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_active_per_user": 0},
        {"max_active_global": 0},
        {"max_active_per_user": 4, "max_active_global": 3},
    ],
)
def test_job_admission_policy_rejects_invalid_limits(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        JobAdmissionPolicy(**kwargs)
