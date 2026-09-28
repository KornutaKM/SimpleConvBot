from __future__ import annotations

import shutil
from asyncio import to_thread
from pathlib import Path
from uuid import UUID


class LocalTemporaryStorage:
    def __init__(self, root: Path) -> None:
        self._root = root

    async def ensure_workspace(self, job_id: UUID) -> Path:
        path = self._root / str(job_id)
        await to_thread(path.mkdir, parents=True, exist_ok=True)
        return path

    async def cleanup_workspace(self, job_id: UUID) -> None:
        path = self._root / str(job_id)
        await to_thread(shutil.rmtree, path, ignore_errors=True)
