import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from aiogram import Bot
from PIL import Image
from pypdf import PdfReader, PdfWriter

from simpleconvbot.jobs import JobSnapshot, JobState
from simpleconvbot.localization import UserErrorCode
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.operations import OperationDefinition
from simpleconvbot.pdf_engine import PdfEngineError, PdfErrorCode
from simpleconvbot.redis_security import RedisUpdateRateLimiter
from simpleconvbot.services import JobService
from simpleconvbot.storage import (
    LocalTemporaryStorage,
    StorageErrorCode,
    StorageSecurityError,
)
from simpleconvbot.telegram_execution import (
    TelegramExecutionGateway,
    TelegramFile,
    TelegramImageExecutor,
    TelegramPdfExecutor,
    UserFacingError,
    audio_operation,
    image_operation,
    pdf_operation,
    telegram_download_error_code,
    video_operation,
)
from simpleconvbot.telemetry import OperationStage


def test_callback_mappings_are_explicit_and_closed() -> None:
    assert image_operation("ui:image:png") == "image.to_png"
    assert image_operation("ui:image:resize") is None
    assert pdf_operation("ui:pdf:jpg") == "pdf.to_jpeg_images"
    assert pdf_operation("ui:pdf:png") == "pdf.to_images"
    assert pdf_operation("ui:pdf:split") == "pdf.extract_pages"
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


def test_pdf_executor_returns_all_rendered_jpeg_pages(tmp_path: Path) -> None:
    asyncio.run(_pdf_executor_returns_all_rendered_jpeg_pages(tmp_path))


async def _pdf_executor_returns_all_rendered_jpeg_pages(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("pdf.to_jpeg_images")
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
        OperationDefinition("pdf.to_jpeg_images", 1, "pdf"),
        await storage.ensure_workspace(job.job_id),
    )

    assert tuple(Path(value).name for value in result.output_refs) == (
        "page-0001.jpg",
        "page-0002.jpg",
    )
    for output in result.output_refs:
        with Image.open(output) as rendered:
            assert rendered.format == "JPEG"


def test_pdf_executor_splits_pdf_into_one_document_per_page(tmp_path: Path) -> None:
    asyncio.run(_pdf_executor_splits_pdf_into_one_document_per_page(tmp_path))


async def _pdf_executor_splits_pdf_into_one_document_per_page(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("pdf.extract_pages")
    source = await storage.workspace_file(job.job_id, "input")
    writer = PdfWriter()
    try:
        writer.add_blank_page(width=72, height=72)
        writer.add_blank_page(width=144, height=72)
        writer.add_blank_page(width=216, height=72)
        with source.open("wb") as stream:
            writer.write(stream)
    finally:
        writer.close()

    result = await TelegramPdfExecutor(storage).execute(
        job,
        OperationDefinition("pdf.extract_pages", 1, "pdf"),
        await storage.ensure_workspace(job.job_id),
    )

    assert tuple(Path(value).name for value in result.output_refs) == (
        "page-0001.pdf",
        "page-0002.pdf",
        "page-0003.pdf",
    )
    widths: list[float] = []
    for output in result.output_refs:
        reader = PdfReader(output, strict=True)
        try:
            assert len(reader.pages) == 1
            widths.append(float(reader.pages[0].mediabox.width))
        finally:
            reader.close()
    assert widths == [72.0, 144.0, 216.0]


def test_pdf_executor_rejects_split_fanout_above_telegram_limit(tmp_path: Path) -> None:
    asyncio.run(_pdf_executor_rejects_split_fanout_above_telegram_limit(tmp_path))


async def _pdf_executor_rejects_split_fanout_above_telegram_limit(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("pdf.extract_pages")
    source = await storage.workspace_file(job.job_id, "input")
    writer = PdfWriter()
    try:
        for _ in range(21):
            writer.add_blank_page(width=72, height=72)
        with source.open("wb") as stream:
            writer.write(stream)
    finally:
        writer.close()

    with pytest.raises(PdfEngineError) as captured:
        await TelegramPdfExecutor(storage).execute(
            job,
            OperationDefinition("pdf.extract_pages", 1, "pdf"),
            await storage.ensure_workspace(job.job_id),
        )

    assert captured.value.code is PdfErrorCode.PAGE_LIMIT_EXCEEDED


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


def test_pdf_executor_creates_pdf_from_ordered_images(tmp_path: Path) -> None:
    asyncio.run(_pdf_executor_creates_pdf_from_ordered_images(tmp_path))


async def _pdf_executor_creates_pdf_from_ordered_images(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("pdf.from_images")
    workspace = await storage.ensure_workspace(job.job_id)
    first = await storage.workspace_file(job.job_id, "input-0001")
    second = await storage.workspace_file(job.job_id, "input-0002")
    Image.new("RGB", (20, 10), "red").save(first, format="PNG")
    Image.new("RGB", (30, 15), "blue").save(second, format="JPEG")

    result = await TelegramPdfExecutor(storage).execute(
        job,
        OperationDefinition("pdf.from_images", 1, "pdf"),
        workspace,
    )

    output = Path(result.output_ref)
    assert output.name == "result.pdf"
    reader = PdfReader(output, strict=True)
    try:
        assert len(reader.pages) == 2
    finally:
        reader.close()


def test_pdf_executor_merges_pdfs_in_persisted_input_order(tmp_path: Path) -> None:
    asyncio.run(_pdf_executor_merges_pdfs_in_persisted_input_order(tmp_path))


async def _pdf_executor_merges_pdfs_in_persisted_input_order(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("pdf.merge")
    workspace = await storage.ensure_workspace(job.job_id)
    first = await storage.workspace_file(job.job_id, "input-0001")
    second = await storage.workspace_file(job.job_id, "input-0002")

    for path, width in ((first, 100), (second, 200)):
        writer = PdfWriter()
        try:
            writer.add_blank_page(width=width, height=100)
            with path.open("wb") as stream:
                writer.write(stream)
        finally:
            writer.close()

    result = await TelegramPdfExecutor(storage).execute(
        job,
        OperationDefinition("pdf.merge", 1, "pdf"),
        workspace,
    )

    reader = PdfReader(result.output_ref, strict=True)
    try:
        widths = tuple(float(page.mediabox.width) for page in reader.pages)
    finally:
        reader.close()
    assert widths == (100.0, 200.0)


def test_pdf_executor_rejects_non_contiguous_collection_inputs(tmp_path: Path) -> None:
    asyncio.run(_pdf_executor_rejects_non_contiguous_collection_inputs(tmp_path))


async def _pdf_executor_rejects_non_contiguous_collection_inputs(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("pdf.merge")
    workspace = await storage.ensure_workspace(job.job_id)
    source = await storage.workspace_file(job.job_id, "input-0002")
    writer = PdfWriter()
    try:
        writer.add_blank_page(width=100, height=100)
        with source.open("wb") as stream:
            writer.write(stream)
    finally:
        writer.close()

    with pytest.raises(UserFacingError):
        await TelegramPdfExecutor(storage).execute(
            job,
            OperationDefinition("pdf.merge", 1, "pdf"),
            workspace,
        )


def test_image_executor_records_aggregate_worker_metric(tmp_path: Path) -> None:
    asyncio.run(_image_executor_records_aggregate_worker_metric(tmp_path))


async def _image_executor_records_aggregate_worker_metric(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    metrics = MetricsRegistry()
    job = _job("image.to_png")
    source = await storage.workspace_file(job.job_id, "input")
    Image.new("RGB", (8, 8), "blue").save(source, format="JPEG")

    await TelegramImageExecutor(storage, metrics=metrics).execute(
        job,
        OperationDefinition("image.to_png", 1, "image"),
        await storage.ensure_workspace(job.job_id),
    )

    snapshot = metrics.snapshot()
    worker_metrics = [
        item
        for item in snapshot.operations
        if item.operation_id == "image.to_png" and item.stage is OperationStage.WORKER
    ]
    assert len(worker_metrics) == 1
    assert worker_metrics[0].total == 1
    assert worker_metrics[0].succeeded == 1
    assert worker_metrics[0].failed == 0


def test_download_error_mapping_preserves_bounded_storage_identity() -> None:
    quota = StorageSecurityError(
        StorageErrorCode.QUOTA_EXCEEDED,
        "workspace quota exceeded",
    )
    tampered = StorageSecurityError(
        StorageErrorCode.WORKSPACE_TAMPERED,
        "workspace tampered",
    )

    assert telegram_download_error_code(quota) == UserErrorCode.TELEGRAM_INPUT_TOO_LARGE.value
    assert telegram_download_error_code(tampered) == StorageErrorCode.WORKSPACE_TAMPERED.value
    assert (
        telegram_download_error_code(RuntimeError("provider unavailable"))
        == UserErrorCode.TELEGRAM_DOWNLOAD_FAILED.value
    )


def test_single_file_download_rejects_known_oversize_before_provider_io(
    tmp_path: Path,
) -> None:
    asyncio.run(_single_file_download_rejects_known_oversize_before_provider_io(tmp_path))


async def _single_file_download_rejects_known_oversize_before_provider_io(
    tmp_path: Path,
) -> None:
    root = tmp_path / "jobs"
    storage = LocalTemporaryStorage(root, max_workspace_bytes=10)
    gateway = TelegramExecutionGateway(
        bot=cast(Bot, object()),
        jobs=cast(JobService, object()),
        storage=storage,
        rate_limiter=cast(RedisUpdateRateLimiter, object()),
    )
    job = _job("image.to_png")

    with pytest.raises(UserFacingError) as caught:
        await gateway._download(
            job,
            TelegramFile(file_id="provider-ref", file_size=11),
        )

    assert caught.value.code == UserErrorCode.TELEGRAM_INPUT_TOO_LARGE.value
    assert not (root / str(job.job_id)).exists()
