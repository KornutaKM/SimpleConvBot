import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from simpleconvbot.storage import (
    LocalTemporaryStorage,
    StorageErrorCode,
    StorageSecurityError,
)


def test_workspace_is_job_scoped_and_cleanup_removes_it(tmp_path: Path) -> None:
    async def scenario() -> None:
        job_id = uuid4()
        storage = LocalTemporaryStorage(tmp_path)

        workspace = await storage.ensure_workspace(job_id)
        assert workspace == tmp_path.resolve() / str(job_id)
        assert workspace.is_dir()

        marker = workspace / "marker.txt"
        marker.write_text("test", encoding="utf-8")

        await storage.cleanup_workspace(job_id)
        assert not workspace.exists()

    asyncio.run(scenario())


def test_internal_filename_rejects_path_traversal(tmp_path: Path) -> None:
    async def scenario() -> None:
        storage = LocalTemporaryStorage(tmp_path)
        job_id = uuid4()
        await storage.ensure_workspace(job_id)

        for value in ("../escape", "/absolute", ".", "..", "nested/file.bin"):
            with pytest.raises(StorageSecurityError) as captured:
                await storage.workspace_file(job_id, value)
            assert captured.value.code is StorageErrorCode.INVALID_INTERNAL_NAME

    asyncio.run(scenario())


def test_workspace_symlink_is_fail_closed(tmp_path: Path) -> None:
    async def scenario() -> None:
        job_id = uuid4()
        storage = LocalTemporaryStorage(tmp_path)
        target = tmp_path / "outside"
        target.mkdir()
        os.symlink(target, tmp_path / str(job_id), target_is_directory=True)

        with pytest.raises(StorageSecurityError) as captured:
            await storage.ensure_workspace(job_id)

        assert captured.value.code is StorageErrorCode.WORKSPACE_TAMPERED

    asyncio.run(scenario())


def test_workspace_quota_detects_existing_oversize(tmp_path: Path) -> None:
    async def scenario() -> None:
        job_id = uuid4()
        storage = LocalTemporaryStorage(tmp_path, max_workspace_bytes=10)
        workspace = await storage.ensure_workspace(job_id)
        (workspace / "payload.bin").write_bytes(b"x" * 11)

        with pytest.raises(StorageSecurityError) as captured:
            await storage.workspace_usage(job_id)

        assert captured.value.code is StorageErrorCode.QUOTA_EXCEEDED

    asyncio.run(scenario())


def test_reaper_removes_only_expired_uuid_workspaces(tmp_path: Path) -> None:
    async def scenario() -> None:
        storage = LocalTemporaryStorage(tmp_path)
        old_id = uuid4()
        fresh_id = uuid4()
        old = await storage.ensure_workspace(old_id)
        fresh = await storage.ensure_workspace(fresh_id)
        unknown = tmp_path / "do-not-delete"
        unknown.mkdir()

        now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
        old_time = (now - timedelta(hours=2)).timestamp()
        fresh_time = (now - timedelta(minutes=5)).timestamp()
        os.utime(old, (old_time, old_time))
        os.utime(fresh, (fresh_time, fresh_time))

        report = await storage.reap_expired(ttl_seconds=3600, now=now)

        assert report.deleted == 1
        assert report.skipped == 2
        assert not old.exists()
        assert fresh.exists()
        assert unknown.exists()

    asyncio.run(scenario())
