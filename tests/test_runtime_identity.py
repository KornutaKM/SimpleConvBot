from __future__ import annotations

import json
import logging

import pytest

from simpleconvbot.runtime_identity import (
    RuntimeIdentity,
    emit_runtime_identity,
    emit_runtime_lifecycle,
)


def test_local_runtime_identity_is_bounded() -> None:
    identity = RuntimeIdentity.from_mapping({})

    assert identity.to_payload() == {"provider": "local"}


def test_railway_runtime_identity_uses_only_machine_fields() -> None:
    commit = "a" * 40
    identity = RuntimeIdentity.from_mapping(
        {
            "RAILWAY_GIT_COMMIT_SHA": commit,
            "RAILWAY_DEPLOYMENT_ID": "deploy-123",
            "RAILWAY_SERVICE_ID": "service-123",
            "RAILWAY_REPLICA_ID": "replica-123",
            "RAILWAY_REPLICA_REGION": "europe-west4",
            "RAILWAY_PROJECT_NAME": "not-emitted",
        }
    )

    assert identity.to_payload() == {
        "provider": "railway",
        "git_commit": commit,
        "deployment_id": "deploy-123",
        "service_id": "service-123",
        "replica_id": "replica-123",
        "region": "europe-west4",
    }


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RAILWAY_GIT_COMMIT_SHA", "short"),
        ("RAILWAY_DEPLOYMENT_ID", "contains spaces"),
        ("RAILWAY_REPLICA_ID", "https://secret.invalid"),
    ],
)
def test_runtime_identity_rejects_unbounded_values(name: str, value: str) -> None:
    with pytest.raises(ValueError):
        RuntimeIdentity.from_mapping({name: value})


def test_runtime_identity_and_lifecycle_are_structured_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("test.runtime.identity")
    caplog.set_level(logging.INFO, logger=logger.name)
    identity = RuntimeIdentity.from_mapping(
        {
            "RAILWAY_GIT_COMMIT_SHA": "b" * 40,
            "RAILWAY_DEPLOYMENT_ID": "deploy-456",
        }
    )

    emit_runtime_identity(logger, identity)
    emit_runtime_lifecycle(logger, event="runtime_lease", outcome="acquired")
    emit_runtime_lifecycle(logger, event="runtime_ready")
    emit_runtime_lifecycle(logger, event="polling_start")

    payloads = [json.loads(record.message) for record in caplog.records]
    assert payloads[0]["event"] == "runtime_identity"
    assert payloads[0]["deployment_id"] == "deploy-456"
    assert payloads[1] == {"event": "runtime_lease", "outcome": "acquired"}
    assert payloads[2] == {"event": "runtime_ready"}
    assert payloads[3] == {"event": "polling_start"}
