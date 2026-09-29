import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image
from pypdf import PdfWriter

from simpleconvbot.jobs import JobSnapshot, JobState
from simpleconvbot.operations import OperationDefinition
from simpleconvbot.storage import LocalTemporaryStorage
from simpleconvbot.telegram_execution import (
    TelegramImageExecutor,
    TelegramPdfExecutor,
    audio_operation,
    image_operation,
    pdf_operation,
    video_operation,
)


def test_callback_mappings_are_explicit_and_closed() -> None:
    assert image_operation("ui:image:png") == "image.to_png"
    assert image_operation("ui:image:resize") is None
    assert pdf_operation("ui:pdf:png") == "pdf.to_images"
    assert pdf_operation("ui:pdf:split") is None
    assert audio_operation("ui:audio:mp3") == "audio.to_mp3"
    assert audio_operation("ui:audio:anything") is None
    assert video_operation("ui:video:gif") == "video.to_gif"
    assert video_operation("ui:video:anything") is None
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
    assert result.output_refs == (result.output_ref,)
    with Image.open(result.output_ref) as converted:
        assert converted.format == "PNG"
        assert converted.size == (16, 8)


def test_pdf_executor_returns_all_rendered_pages(tmp_path: Path) -> None:
    asyncio.run(_pdf_executor_returns_all_rendered_pages(tmp_path))


async def _pdf_executor_returns_all_rendered_pages(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("pdf.to_images")
    source = await storage.workspace_file(job.job_id, "input")
    writer = PdfWriter()
    try:
        writer.add_blank_page(width=72, height=72)
        writer.add_blank_page(width=144, height=72)
        with source.open("wb") as stream:
            writer.write(stream)
    finally:
        writer.close()

    result = await TelegramPdfExecutor(storage).execute(
        job,
        OperationDefinition("pdf.to_images", 1, "pdf"),
        await storage.ensure_workspace(job.job_id),
    )

    assert len(result.output_refs) == 2
    assert tuple(Path(value).name for value in result.output_refs) == (
        "page-0001.png",
        "page-0002.png",
    )
    for output in result.output_refs:
        with Image.open(output) as rendered:
            assert rendered.format == "PNG"


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
