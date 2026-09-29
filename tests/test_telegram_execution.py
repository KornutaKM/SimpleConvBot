import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image

from simpleconvbot.jobs import JobSnapshot, JobState
from simpleconvbot.operations import OperationDefinition
from simpleconvbot.storage import LocalTemporaryStorage
from simpleconvbot.telegram_execution import TelegramImageExecutor, image_operation


def test_image_callback_mapping_is_explicit_and_closed() -> None:
    assert image_operation("ui:image:png") == "image.to_png"
    assert image_operation("ui:image:resize") is None
    assert image_operation(None) is None


def test_image_executor_uses_workspace_input_and_validates_output(tmp_path: Path) -> None:
    asyncio.run(_image_executor_uses_workspace_input_and_validates_output(tmp_path))


async def _image_executor_uses_workspace_input_and_validates_output(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("image.to_png")
    source = await storage.workspace_file(job.job_id, "input")
    Image.new("RGB", (16, 8), "red").save(source, format="JPEG")

    result = await TelegramImageExecutor(storage).execute(
        job,
        OperationDefinition("image.to_png", 1, "image"),
        await storage.ensure_workspace(job.job_id),
    )

    assert Path(result.output_ref).name == "result.png"
    with Image.open(result.output_ref) as converted:
        assert converted.format == "PNG"
        assert converted.size == (16, 8)


def _job(operation_id: str) -> JobSnapshot:
    now = datetime.now(UTC)
    return JobSnapshot(
        job_id=uuid4(),
        idempotency_key="test",
        operation_id=operation_id,
        operation_version=1,
        user_id=1,
        chat_id=2,
        source_message_id=3,
        state=JobState.PROCESSING,
        created_at=now,
        updated_at=now,
    )
