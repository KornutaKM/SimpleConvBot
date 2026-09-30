from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass

_MACHINE_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True, slots=True)
class RuntimeIdentity:
    provider: str
    git_commit: str | None = None
    deployment_id: str | None = None
    service_id: str | None = None
    replica_id: str | None = None
    region: str | None = None

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> RuntimeIdentity:
        railway_markers = (
            values.get("RAILWAY_DEPLOYMENT_ID"),
            values.get("RAILWAY_SERVICE_ID"),
            values.get("RAILWAY_REPLICA_ID"),
        )
        provider = "railway" if any(_optional(value) for value in railway_markers) else "local"
        git_commit = _optional(values.get("RAILWAY_GIT_COMMIT_SHA"))
        if git_commit is not None and _COMMIT.fullmatch(git_commit) is None:
            raise ValueError("RAILWAY_GIT_COMMIT_SHA must be a full lowercase commit SHA")

        deployment_id = _machine("RAILWAY_DEPLOYMENT_ID", values.get("RAILWAY_DEPLOYMENT_ID"))
        service_id = _machine("RAILWAY_SERVICE_ID", values.get("RAILWAY_SERVICE_ID"))
        replica_id = _machine("RAILWAY_REPLICA_ID", values.get("RAILWAY_REPLICA_ID"))
        region = _machine("RAILWAY_REPLICA_REGION", values.get("RAILWAY_REPLICA_REGION"))
        return cls(
            provider=provider,
            git_commit=git_commit,
            deployment_id=deployment_id,
            service_id=service_id,
            replica_id=replica_id,
            region=region,
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"provider": self.provider}
        for key, value in (
            ("git_commit", self.git_commit),
            ("deployment_id", self.deployment_id),
            ("service_id", self.service_id),
            ("replica_id", self.replica_id),
            ("region", self.region),
        ):
            if value is not None:
                payload[key] = value
        return payload


def emit_runtime_identity(logger: logging.Logger, identity: RuntimeIdentity) -> None:
    _emit(logger, {"event": "runtime_identity", **identity.to_payload()})


def emit_runtime_lifecycle(
    logger: logging.Logger,
    *,
    event: str,
    outcome: str | None = None,
) -> None:
    if event not in {"runtime_lease", "runtime_ready", "polling_start"}:
        raise ValueError("unsupported runtime lifecycle event")
    payload: dict[str, object] = {"event": event}
    if outcome is not None:
        if outcome not in {"acquired", "released", "lost"}:
            raise ValueError("unsupported runtime lifecycle outcome")
        payload["outcome"] = outcome
    _emit(logger, payload)


def _emit(logger: logging.Logger, payload: dict[str, object]) -> None:
    logger.info(
        json.dumps(
            payload,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def _optional(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _machine(name: str, raw: str | None) -> str | None:
    value = _optional(raw)
    if value is None:
        return None
    if _MACHINE_ID.fullmatch(value) is None:
        raise ValueError(f"{name} must be a bounded machine identifier")
    return value
