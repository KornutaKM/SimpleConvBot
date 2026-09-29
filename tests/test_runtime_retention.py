from __future__ import annotations

import asyncio
from datetime import datetime

import pytest

from simpleconvbot.maintenance import RetentionSweepResult, RetentionSweepService
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.runtime import _require_complete_initial_retention, _run_retention
from simpleconvbot.storage import CleanupReport


class FakeWorkspaceReaper:
    def __init__(self) -> None:
        self.calls = 0

    async def reap_expired(
        self,
        *,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> CleanupReport:
        del ttl_seconds, now
        self.calls += 1
        return CleanupReport(
            scanned=1,
            deleted=1,
            skipped=0,
            tampered=0,
            failed=0,
        )


class StopAfterSessionReaper:
    def __init__(self, stop: asyncio.Event) -> None:
        self._stop = stop
        self.calls = 0

    async def reap_expired(self, *, now: datetime | None = None) -> int:
        del now
        self.calls += 1
        self._stop.set()
        return 1


def test_periodic_retention_sweeps_and_stops_cleanly() -> None:
    async def scenario() -> None:
        stop = asyncio.Event()
        workspace = FakeWorkspaceReaper()
        sessions = StopAfterSessionReaper(stop)
        service = RetentionSweepService(
            workspace_reaper=workspace,
            session_reaper=sessions,
            metrics=MetricsRegistry(),
            workspace_ttl_seconds=60,
        )

        await _run_retention(service, stop, interval_seconds=0.001)

        assert workspace.calls == 1
        assert sessions.calls == 1

    asyncio.run(scenario())


def test_initial_retention_gate_rejects_partial_cleanup_failure() -> None:
    result = RetentionSweepResult(
        workspaces_scanned=2,
        workspaces_deleted=1,
        workspaces_failed=1,
        sessions_deleted=0,
    )

    with pytest.raises(RuntimeError, match="initial retention sweep"):
        _require_complete_initial_retention(result)


def test_initial_retention_gate_accepts_complete_cleanup() -> None:
    result = RetentionSweepResult(
        workspaces_scanned=2,
        workspaces_deleted=2,
        workspaces_failed=0,
        sessions_deleted=1,
    )

    _require_complete_initial_retention(result)
