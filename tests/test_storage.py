import asyncio
from pathlib import Path
from uuid import uuid4

from simpleconvbot.storage import LocalTemporaryStorage


def test_workspace_is_job_scoped_and_cleanup_removes_it(tmp_path: Path) -> None:
    async def scenario() -> None:
        job_id = uuid4()
        storage = LocalTemporaryStorage(tmp_path)

        workspace = await storage.ensure_workspace(job_id)
        assert workspace == tmp_path / str(job_id)
        assert workspace.is_dir()

        marker = workspace / "marker.txt"
        marker.write_text("test", encoding="utf-8")

        await storage.cleanup_workspace(job_id)
        assert not workspace.exists()

    asyncio.run(scenario())
