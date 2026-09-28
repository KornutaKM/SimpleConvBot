from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from simpleconvbot.maintenance import RetentionSweepService
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.postgres import (
    PostgresCollectionSessionRepository,
    create_schema,
    drop_schema,
    make_engine,
    make_session_factory,
)
from simpleconvbot.sessions import SessionKind, SessionNotFound, SessionState
from simpleconvbot.storage import LocalTemporaryStorage


@pytest.mark.integration
def test_retention_sweep_removes_only_expired_alpha_state(tmp_path: Path) -> None:
    asyncio.run(_retention_sweep_removes_only_expired_alpha_state(tmp_path))


async def _retention_sweep_removes_only_expired_alpha_state(tmp_path: Path) -> None:
    engine = make_engine(os.environ["DATABASE_URL"])
    sessions = make_session_factory(engine)
    repository = PostgresCollectionSessionRepository(sessions)
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    metrics = MetricsRegistry()

    now = datetime(2026, 9, 29, 0, 0, tzinfo=UTC)
    expired_created_at = now - timedelta(hours=2)

    stale_job_id = uuid4()
    fresh_job_id = uuid4()

    try:
        await drop_schema(engine)
        await create_schema(engine)

        expired_session = await repository.create(
            kind=SessionKind.PDF_MERGE,
            owner_user_id=10,
            chat_id=20,
            now=expired_created_at,
        )
        fresh_session = await repository.create(
            kind=SessionKind.IMAGES_TO_PDF,
            owner_user_id=11,
            chat_id=21,
            now=now,
        )

        stale_workspace = await storage.ensure_workspace(stale_job_id)
        fresh_workspace = await storage.ensure_workspace(fresh_job_id)
        (stale_workspace / "payload.bin").write_bytes(b"stale")
        (fresh_workspace / "payload.bin").write_bytes(b"fresh")

        stale_timestamp = (now - timedelta(hours=2)).timestamp()
        fresh_timestamp = (now - timedelta(minutes=5)).timestamp()
        os.utime(stale_workspace, (stale_timestamp, stale_timestamp))
        os.utime(fresh_workspace, (fresh_timestamp, fresh_timestamp))

        service = RetentionSweepService(
            workspace_reaper=storage,
            session_reaper=repository,
            metrics=metrics,
            workspace_ttl_seconds=3600,
        )
        result = await service.sweep(now=now)

        assert result.workspaces_deleted == 1
        assert result.workspaces_failed == 0
        assert result.sessions_deleted == 1
        assert result.deleted_total == 2

        assert not stale_workspace.exists()
        assert fresh_workspace.exists()

        with pytest.raises(SessionNotFound):
            await repository.get_owned(
                expired_session.session_id,
                owner_user_id=10,
                chat_id=20,
            )

        preserved = await repository.get_owned(
            fresh_session.session_id,
            owner_user_id=11,
            chat_id=21,
        )
        assert preserved.state is SessionState.COLLECTING

        cleanup = metrics.snapshot().cleanup
        assert cleanup.attempts == 1
        assert cleanup.deleted == 2
        assert cleanup.failed == 0
    finally:
        await engine.dispose()
