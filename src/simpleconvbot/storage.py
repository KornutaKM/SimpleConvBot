from __future__ import annotations

import os
import re
import shutil
from asyncio import to_thread
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from uuid import UUID

_INTERNAL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class StorageErrorCode(StrEnum):
    INVALID_INTERNAL_NAME = "storage_invalid_internal_name"
    ROOT_SYMLINK = "storage_root_symlink"
    WORKSPACE_TAMPERED = "storage_workspace_tampered"
    UNSUPPORTED_ENTRY = "storage_unsupported_entry"
    QUOTA_EXCEEDED = "storage_quota_exceeded"
    CLEANUP_FAILED = "storage_cleanup_failed"


class StorageSecurityError(RuntimeError):
    def __init__(self, code: StorageErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class CleanupReport:
    scanned: int
    deleted: int
    skipped: int
    tampered: int
    failed: int


class LocalTemporaryStorage:
    def __init__(
        self,
        root: Path,
        *,
        max_workspace_bytes: int = 64 * 1024 * 1024,
    ) -> None:
        if max_workspace_bytes <= 0:
            raise ValueError("max_workspace_bytes must be greater than zero")
        self._root = root.expanduser()
        self._max_workspace_bytes = max_workspace_bytes
        self._resolved_root: Path | None = None

    async def ensure_workspace(self, job_id: UUID) -> Path:
        return await to_thread(self._ensure_workspace_sync, job_id)

    async def cleanup_workspace(self, job_id: UUID) -> None:
        await to_thread(self._cleanup_workspace_sync, job_id)

    async def workspace_file(self, job_id: UUID, internal_name: str) -> Path:
        return await to_thread(self._workspace_file_sync, job_id, internal_name)

    async def workspace_usage(self, job_id: UUID) -> int:
        return await to_thread(self._workspace_usage_sync, job_id)

    async def enforce_quota(self, job_id: UUID, *, additional_bytes: int = 0) -> int:
        if additional_bytes < 0:
            raise ValueError("additional_bytes must not be negative")
        used = await self.workspace_usage(job_id)
        projected = used + additional_bytes
        if projected > self._max_workspace_bytes:
            raise StorageSecurityError(
                StorageErrorCode.QUOTA_EXCEEDED,
                "workspace byte quota would be exceeded",
            )
        return used

    async def reap_expired(
        self,
        *,
        ttl_seconds: int,
        now: datetime | None = None,
    ) -> CleanupReport:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be greater than zero")
        current = now or datetime.now(UTC)
        return await to_thread(self._reap_expired_sync, ttl_seconds, current)

    def _prepare_root(self) -> Path:
        self._root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if self._root.is_symlink():
            raise StorageSecurityError(
                StorageErrorCode.ROOT_SYMLINK,
                "temporary storage root must not be a symlink",
            )
        resolved = self._root.resolve(strict=True)
        if self._resolved_root is None:
            self._resolved_root = resolved
        elif resolved != self._resolved_root:
            raise StorageSecurityError(
                StorageErrorCode.ROOT_SYMLINK,
                "temporary storage root identity changed",
            )
        try:
            resolved.chmod(0o700)
        except OSError:
            # Some mounted filesystems may not support chmod. The identity
            # checks above still apply; deployment permissions are verified
            # independently by the container security self-test.
            pass
        return resolved

    def _workspace_path(self, job_id: UUID) -> Path:
        return self._prepare_root() / str(job_id)

    def _ensure_workspace_sync(self, job_id: UUID) -> Path:
        path = self._workspace_path(job_id)
        if os.path.lexists(path) and path.is_symlink():
            raise StorageSecurityError(
                StorageErrorCode.WORKSPACE_TAMPERED,
                "job workspace must not be a symlink",
            )
        path.mkdir(mode=0o700, parents=False, exist_ok=True)
        if not path.is_dir() or path.is_symlink():
            raise StorageSecurityError(
                StorageErrorCode.WORKSPACE_TAMPERED,
                "job workspace is not a real directory",
            )
        try:
            path.chmod(0o700)
        except OSError:
            pass
        return path

    def _workspace_file_sync(self, job_id: UUID, internal_name: str) -> Path:
        if (
            internal_name in {".", ".."}
            or not _INTERNAL_NAME.fullmatch(internal_name)
            or Path(internal_name).name != internal_name
        ):
            raise StorageSecurityError(
                StorageErrorCode.INVALID_INTERNAL_NAME,
                "workspace filenames must be generated bounded basenames",
            )
        workspace = self._ensure_workspace_sync(job_id)
        candidate = workspace / internal_name
        if os.path.lexists(candidate) and candidate.is_symlink():
            raise StorageSecurityError(
                StorageErrorCode.WORKSPACE_TAMPERED,
                "workspace file must not be a symlink",
            )
        if candidate.parent.resolve(strict=True) != workspace.resolve(strict=True):
            raise StorageSecurityError(
                StorageErrorCode.WORKSPACE_TAMPERED,
                "workspace file escaped the job directory",
            )
        return candidate

    def _workspace_usage_sync(self, job_id: UUID) -> int:
        workspace = self._ensure_workspace_sync(job_id)
        total = 0
        for root, directories, files in os.walk(workspace, followlinks=False):
            root_path = Path(root)
            for name in directories:
                path = root_path / name
                if path.is_symlink():
                    raise StorageSecurityError(
                        StorageErrorCode.WORKSPACE_TAMPERED,
                        "symlinked directories are forbidden in job workspaces",
                    )
            for name in files:
                path = root_path / name
                if path.is_symlink():
                    raise StorageSecurityError(
                        StorageErrorCode.WORKSPACE_TAMPERED,
                        "symlinked files are forbidden in job workspaces",
                    )
                stat = path.stat(follow_symlinks=False)
                if not path.is_file():
                    raise StorageSecurityError(
                        StorageErrorCode.UNSUPPORTED_ENTRY,
                        "only regular files are allowed in job workspaces",
                    )
                total += stat.st_size
                if total > self._max_workspace_bytes:
                    raise StorageSecurityError(
                        StorageErrorCode.QUOTA_EXCEEDED,
                        "workspace byte quota exceeded",
                    )
        return total

    def _cleanup_workspace_sync(self, job_id: UUID) -> None:
        path = self._workspace_path(job_id)
        if not os.path.lexists(path):
            return
        if path.is_symlink():
            path.unlink()
            raise StorageSecurityError(
                StorageErrorCode.WORKSPACE_TAMPERED,
                "tampered workspace symlink was removed",
            )
        try:
            shutil.rmtree(path)
        except OSError as exc:
            raise StorageSecurityError(
                StorageErrorCode.CLEANUP_FAILED,
                "job workspace cleanup failed",
            ) from exc

    def _reap_expired_sync(self, ttl_seconds: int, now: datetime) -> CleanupReport:
        root = self._prepare_root()
        cutoff = now.timestamp() - ttl_seconds
        scanned = deleted = skipped = tampered = failed = 0

        for entry in root.iterdir():
            scanned += 1
            if entry.is_symlink():
                try:
                    entry.unlink()
                    deleted += 1
                    tampered += 1
                except OSError:
                    failed += 1
                continue

            try:
                job_id = UUID(entry.name)
            except ValueError:
                skipped += 1
                continue

            if not entry.is_dir():
                skipped += 1
                continue

            try:
                modified = entry.stat(follow_symlinks=False).st_mtime
            except OSError:
                failed += 1
                continue
            if modified > cutoff:
                skipped += 1
                continue

            try:
                self._cleanup_workspace_sync(job_id)
                deleted += 1
            except StorageSecurityError:
                failed += 1

        return CleanupReport(
            scanned=scanned,
            deleted=deleted,
            skipped=skipped,
            tampered=tampered,
            failed=failed,
        )
