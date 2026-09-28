from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.storage import CleanupReport


class WorkspaceReaper(Protocol):
    async def reap_expired(
        self,
        *,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> CleanupReport: ...


class SessionReaper(Protocol):
    async def reap_expired(self, *, now: datetime | None = None) -> int: ...


@dataclass(frozen=True, slots=True)
class RetentionSweepResult:
    workspaces_scanned: int
    workspaces_deleted: int
    workspaces_failed: int
    sessions_deleted: int

    @property
    def deleted_total(self) -> int:
        return self.workspaces_deleted + self.sessions_deleted


class RetentionSweepService:
    def __init__(
        self,
        *,
        workspace_reaper: WorkspaceReaper,
        session_reaper: SessionReaper,
        metrics: MetricsRegistry,
        workspace_ttl_seconds: int,
    ) -> None:
        if workspace_ttl_seconds <= 0:
            raise ValueError("workspace_ttl_seconds must be greater than zero")
        self._workspace_reaper = workspace_reaper
        self._session_reaper = session_reaper
        self._metrics = metrics
        self._workspace_ttl_seconds = workspace_ttl_seconds

    async def sweep(self, *, now: datetime | None = None) -> RetentionSweepResult:
        current = now or datetime.now(UTC)

        try:
            workspaces = await self._workspace_reaper.reap_expired(
                ttl_seconds=self._workspace_ttl_seconds,
                now=current,
            )
        except Exception:
            self._metrics.record_cleanup(failed=1)
            raise

        try:
            sessions_deleted = await self._session_reaper.reap_expired(now=current)
        except Exception:
            self._metrics.record_cleanup(
                deleted=workspaces.deleted,
                failed=workspaces.failed + 1,
            )
            raise

        self._metrics.record_cleanup(
            deleted=workspaces.deleted + sessions_deleted,
            failed=workspaces.failed,
        )
        return RetentionSweepResult(
            workspaces_scanned=workspaces.scanned,
            workspaces_deleted=workspaces.deleted,
            workspaces_failed=workspaces.failed,
            sessions_deleted=sessions_deleted,
        )
