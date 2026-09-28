from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from simpleconvbot.maintenance import RetentionSweepService
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.storage import CleanupReport


class FakeWorkspaceReaper:
    def __init__(self, report: CleanupReport | None = None, error: Exception | None = None) -> None:
        self.report = report or CleanupReport(0, 0, 0, 0, 0)
        self.error = error
        self.calls: list[tuple[int, datetime]] = []

    async def reap_expired(
        self,
        *,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> CleanupReport:
        assert now is not None
        self.calls.append((ttl_seconds, now))
        if self.error is not None:
            raise self.error
        return self.report


class FakeSessionReaper:
    def __init__(self, deleted: int = 0, error: Exception | None = None) -> None:
        self.deleted = deleted
        self.error = error
        self.calls: list[datetime] = []

    async def reap_expired(self, *, now: datetime | None = None) -> int:
        assert now is not None
        self.calls.append(now)
        if self.error is not None:
            raise self.error
        return self.deleted


def test_retention_sweep_aggregates_cleanup_evidence() -> None:
    async def scenario() -> None:
        now = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
        workspace_reaper = FakeWorkspaceReaper(
            CleanupReport(
                scanned=5,
                deleted=2,
                skipped=2,
                tampered=1,
                failed=1,
            )
        )
        session_reaper = FakeSessionReaper(deleted=3)
        metrics = MetricsRegistry()
        service = RetentionSweepService(
            workspace_reaper=workspace_reaper,
            session_reaper=session_reaper,
            metrics=metrics,
            workspace_ttl_seconds=3600,
        )

        result = await service.sweep(now=now)

        assert result.workspaces_scanned == 5
        assert result.workspaces_deleted == 2
        assert result.workspaces_failed == 1
        assert result.sessions_deleted == 3
        assert result.deleted_total == 5
        assert workspace_reaper.calls == [(3600, now)]
        assert session_reaper.calls == [now]

        cleanup = metrics.snapshot().cleanup
        assert cleanup.attempts == 1
        assert cleanup.deleted == 5
        assert cleanup.failed == 1

    asyncio.run(scenario())


def test_workspace_reaper_failure_is_visible_and_propagated() -> None:
    async def scenario() -> None:
        metrics = MetricsRegistry()
        service = RetentionSweepService(
            workspace_reaper=FakeWorkspaceReaper(error=RuntimeError("workspace failure")),
            session_reaper=FakeSessionReaper(),
            metrics=metrics,
            workspace_ttl_seconds=60,
        )

        with pytest.raises(RuntimeError, match="workspace failure"):
            await service.sweep()

        cleanup = metrics.snapshot().cleanup
        assert cleanup.attempts == 1
        assert cleanup.deleted == 0
        assert cleanup.failed == 1

    asyncio.run(scenario())


def test_session_reaper_failure_preserves_completed_workspace_evidence() -> None:
    async def scenario() -> None:
        metrics = MetricsRegistry()
        service = RetentionSweepService(
            workspace_reaper=FakeWorkspaceReaper(CleanupReport(2, 2, 0, 0, 0)),
            session_reaper=FakeSessionReaper(error=RuntimeError("session failure")),
            metrics=metrics,
            workspace_ttl_seconds=60,
        )

        with pytest.raises(RuntimeError, match="session failure"):
            await service.sweep()

        cleanup = metrics.snapshot().cleanup
        assert cleanup.attempts == 1
        assert cleanup.deleted == 2
        assert cleanup.failed == 1

    asyncio.run(scenario())


def test_retention_ttl_must_be_positive() -> None:
    with pytest.raises(ValueError, match="workspace_ttl_seconds"):
        RetentionSweepService(
            workspace_reaper=FakeWorkspaceReaper(),
            session_reaper=FakeSessionReaper(),
            metrics=MetricsRegistry(),
            workspace_ttl_seconds=0,
        )
