import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from aiogram import Bot
from PIL import Image
from pypdf import PdfReader, PdfWriter

from simpleconvbot.image_engine import CompressionPreset, ImageEngine, ImageOutputFormat
from simpleconvbot.jobs import JobSnapshot, JobState
from simpleconvbot.localization import UserErrorCode
from simpleconvbot.media_engine import MediaEngine, VideoCompressionPreset
from simpleconvbot.media_operations import MEDIA_OPERATIONS
from simpleconvbot.metrics import MetricsRegistry
from simpleconvbot.operations import OperationDefinition
from simpleconvbot.pdf_engine import PdfEngineError, PdfErrorCode
from simpleconvbot.ports import ExecutionResult, LocalizedDeliveryText
from simpleconvbot.redis_security import RedisUpdateRateLimiter
from simpleconvbot.services import JobService
from simpleconvbot.storage import (
    LocalTemporaryStorage,
    StorageErrorCode,
    StorageSecurityError,
)
from simpleconvbot.telegram_execution import (
    TELEGRAM_CLOUD_DOWNLOAD_MAX_BYTES,
    TelegramDelivery,
    TelegramExecutionGateway,
    TelegramFile,
    TelegramImageExecutor,
    TelegramPdfExecutor,
    UserFacingError,
    _execute_media,
    _image_transform_request,
    audio_operation,
    image_operation,
    pdf_operation,
    telegram_download_error_code,
    video_operation,
)
from simpleconvbot.telemetry import OperationStage


def test_callback_mappings_are_explicit_and_closed() -> None:
    assert image_operation("ui:image:png") == "image.to_png"
    assert image_operation("ui:image:compress") is None
    assert image_operation("ui:image:compress:best") == "image.compress_best"
    assert image_operation("ui:image:compress:balanced") == "image.compress_balanced"
    assert image_operation("ui:image:compress:smallest") == "image.compress_smallest"
    assert image_operation("ui:image:resize") is None
    assert image_operation("ui:image:resize:25") == "image.resize_25"
    assert image_operation("ui:image:resize:50") == "image.resize_50"
    assert image_operation("ui:image:resize:720") == "image.resize_720"
    assert image_operation("ui:image:resize:1080") == "image.resize_1080"
    assert pdf_operation("ui:pdf:jpg") == "pdf.to_jpeg_images"
    assert pdf_operation("ui:pdf:png") == "pdf.to_images"
    assert pdf_operation("ui:pdf:split") == "pdf.extract_pages"
    assert pdf_operation("ui:pdf:info") == "pdf.info"
    assert audio_operation("ui:audio:mp3") == "audio.to_mp3"
    assert audio_operation("ui:audio:anything") is None
    assert video_operation("ui:video:gif") == "video.to_gif"
    assert video_operation("ui:video:compress") is None
    assert video_operation("ui:video:compress:best") == "video.compress_best"
    assert video_operation("ui:video:compress:balanced") == "video.compress_balanced"
    assert video_operation("ui:video:compress:smallest") == "video.compress_smallest"
    assert video_operation("ui:video:anything") is None
    assert image_operation(None) is None





class _RecordingMediaEngine:
    def __init__(self) -> None:
        self.preset: VideoCompressionPreset | None = None

    def compress_video(
        self,
        source: Path,
        destination: Path,
        preset: VideoCompressionPreset,
    ) -> None:
        del source, destination
        self.preset = preset


@pytest.mark.parametrize(
    ("operation_id", "preset"),
    [
        ("video.compress_best", VideoCompressionPreset.HIGH_QUALITY),
        ("video.compress_balanced", VideoCompressionPreset.BALANCED),
        ("video.compress_smallest", VideoCompressionPreset.SMALL),
        ("video.compress", VideoCompressionPreset.BALANCED),
    ],
)
def test_video_compression_operation_selects_exact_preset(
    tmp_path: Path,
    operation_id: str,
    preset: VideoCompressionPreset,
) -> None:
    engine = _RecordingMediaEngine()

    asyncio.run(
        _execute_media(
            cast(MediaEngine, engine),
            tmp_path / "input.mp4",
            tmp_path / "result.mp4",
            operation_id,
        )
    )

    assert engine.preset is preset


def test_video_compression_registry_keeps_legacy_and_preset_identities() -> None:
    operation_ids = {operation.operation_id for operation in MEDIA_OPERATIONS}

    assert {
        "video.compress",
        "video.compress_best",
        "video.compress_balanced",
        "video.compress_smallest",
    } <= operation_ids


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


@pytest.mark.parametrize(
    ("operation_id", "preset"),
    [
        ("image.compress_best", CompressionPreset.BEST),
        ("image.compress_balanced", CompressionPreset.BALANCED),
        ("image.compress_smallest", CompressionPreset.SMALLEST),
    ],
)
def test_image_compression_operation_selects_exact_preset(
    tmp_path: Path,
    operation_id: str,
    preset: CompressionPreset,
) -> None:
    source = tmp_path / "input.jpg"
    Image.new("RGB", (32, 16), "red").save(source, format="JPEG")

    request = asyncio.run(_image_transform_request(ImageEngine(), source, operation_id))

    assert request.target_format is ImageOutputFormat.JPEG
    assert request.compression is preset
    assert request.resize is None


def test_image_executor_compression_preserves_png_format(tmp_path: Path) -> None:
    asyncio.run(_image_executor_compression_preserves_png_format(tmp_path))


async def _image_executor_compression_preserves_png_format(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("image.compress_balanced")
    source = await storage.workspace_file(job.job_id, "input")
    Image.new("RGBA", (64, 32), (255, 0, 0, 128)).save(source, format="PNG")

    result = await TelegramImageExecutor(storage).execute(
        job,
        OperationDefinition("image.compress_balanced", 1, "image"),
        await storage.ensure_workspace(job.job_id),
    )

    assert Path(result.output_ref).name == "result.png"
    with Image.open(result.output_ref) as compressed:
        assert compressed.format == "PNG"
        assert compressed.size == (64, 32)


def test_legacy_image_compress_identity_keeps_historical_webp_behavior(tmp_path: Path) -> None:
    asyncio.run(_legacy_image_compress_identity_keeps_historical_webp_behavior(tmp_path))


async def _legacy_image_compress_identity_keeps_historical_webp_behavior(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("image.compress")
    source = await storage.workspace_file(job.job_id, "input")
    Image.new("RGB", (32, 16), "blue").save(source, format="JPEG")

    result = await TelegramImageExecutor(storage).execute(
        job,
        OperationDefinition("image.compress", 1, "image"),
        await storage.ensure_workspace(job.job_id),
    )

    assert Path(result.output_ref).name == "result.webp"
    with Image.open(result.output_ref) as compressed:
        assert compressed.format == "WEBP"


def test_image_executor_compression_heif_returns_jpeg(tmp_path: Path) -> None:
    asyncio.run(_image_executor_compression_heif_returns_jpeg(tmp_path))


async def _image_executor_compression_heif_returns_jpeg(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("image.compress_smallest")
    source = await storage.workspace_file(job.job_id, "input")
    Image.new("RGB", (40, 20), "purple").save(source, format="HEIF")

    result = await TelegramImageExecutor(storage).execute(
        job,
        OperationDefinition("image.compress_smallest", 1, "image"),
        await storage.ensure_workspace(job.job_id),
    )

    assert Path(result.output_ref).name == "result.jpg"
    with Image.open(result.output_ref) as compressed:
        assert compressed.format == "JPEG"


def test_image_executor_resize_percent_preserves_source_format(tmp_path: Path) -> None:
    asyncio.run(_image_executor_resize_percent_preserves_source_format(tmp_path))


async def _image_executor_resize_percent_preserves_source_format(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("image.resize_50")
    source = await storage.workspace_file(job.job_id, "input")
    Image.new("RGB", (400, 200), "red").save(source, format="PNG")

    result = await TelegramImageExecutor(storage).execute(
        job,
        OperationDefinition("image.resize_50", 1, "image"),
        await storage.ensure_workspace(job.job_id),
    )

    assert Path(result.output_ref).name == "result.png"
    with Image.open(result.output_ref) as resized:
        assert resized.format == "PNG"
        assert resized.size == (200, 100)


def test_image_executor_resize_box_does_not_upscale(tmp_path: Path) -> None:
    asyncio.run(_image_executor_resize_box_does_not_upscale(tmp_path))


async def _image_executor_resize_box_does_not_upscale(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("image.resize_720")
    source = await storage.workspace_file(job.job_id, "input")
    Image.new("RGB", (320, 160), "blue").save(source, format="JPEG")

    result = await TelegramImageExecutor(storage).execute(
        job,
        OperationDefinition("image.resize_720", 1, "image"),
        await storage.ensure_workspace(job.job_id),
    )

    assert Path(result.output_ref).name == "result.jpg"
    with Image.open(result.output_ref) as resized:
        assert resized.format == "JPEG"
        assert resized.size == (320, 160)


def test_image_executor_resize_box_downscales_long_side(tmp_path: Path) -> None:
    asyncio.run(_image_executor_resize_box_downscales_long_side(tmp_path))


async def _image_executor_resize_box_downscales_long_side(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("image.resize_720")
    source = await storage.workspace_file(job.job_id, "input")
    Image.new("RGB", (1440, 720), "green").save(source, format="WEBP")

    result = await TelegramImageExecutor(storage).execute(
        job,
        OperationDefinition("image.resize_720", 1, "image"),
        await storage.ensure_workspace(job.job_id),
    )

    assert Path(result.output_ref).name == "result.webp"
    with Image.open(result.output_ref) as resized:
        assert resized.format == "WEBP"
        assert resized.size == (720, 360)


def test_image_executor_resize_heif_returns_jpeg(tmp_path: Path) -> None:
    asyncio.run(_image_executor_resize_heif_returns_jpeg(tmp_path))


async def _image_executor_resize_heif_returns_jpeg(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("image.resize_25")
    source = await storage.workspace_file(job.job_id, "input")
    Image.new("RGB", (80, 40), "purple").save(source, format="HEIF")

    result = await TelegramImageExecutor(storage).execute(
        job,
        OperationDefinition("image.resize_25", 1, "image"),
        await storage.ensure_workspace(job.job_id),
    )

    assert Path(result.output_ref).name == "result.jpg"
    with Image.open(result.output_ref) as resized:
        assert resized.format == "JPEG"
        assert resized.size == (20, 10)


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


def test_pdf_executor_returns_localized_info_without_output_file(tmp_path: Path) -> None:
    asyncio.run(_pdf_executor_returns_localized_info_without_output_file(tmp_path))


async def _pdf_executor_returns_localized_info_without_output_file(tmp_path: Path) -> None:
    storage = LocalTemporaryStorage(tmp_path / "jobs")
    job = _job("pdf.info")
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
        OperationDefinition("pdf.info", 1, "pdf"),
        await storage.ensure_workspace(job.job_id),
    )

    assert result.output_refs == ()
    assert result.delivery_text is not None
    assert "Страниц: 2" in result.delivery_text.ru
    assert "Pages: 2" in result.delivery_text.en
    assert "Version:" in result.delivery_text.en


def test_execution_result_rejects_ambiguous_delivery_modes() -> None:
    localized = LocalizedDeliveryText(ru="готово", en="done")
    with pytest.raises(ValueError):
        ExecutionResult()
    with pytest.raises(ValueError):
        ExecutionResult(output_ref="result.bin", delivery_text=localized)
    with pytest.raises(ValueError):
        ExecutionResult(additional_output_refs=("extra.bin",), delivery_text=localized)


def test_telegram_delivery_sends_text_result_as_message() -> None:
    asyncio.run(_telegram_delivery_sends_text_result_as_message())


async def _telegram_delivery_sends_text_result_as_message() -> None:
    class RecordingBot:
        def __init__(self) -> None:
            self.messages: list[tuple[int, str]] = []

        async def send_message(self, chat_id: int, text: str) -> None:
            self.messages.append((chat_id, text))

    bot = RecordingBot()
    delivery = TelegramDelivery(cast(Bot, bot))
    job = _job("pdf.info")
    result = ExecutionResult(
        delivery_text=LocalizedDeliveryText(
            ru="PDF информация",
            en="PDF information",
        )
    )

    await delivery.deliver(job, result)

    assert bot.messages == [(job.chat_id, "PDF информация")]


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


def test_single_file_download_rejects_cloud_transport_oversize_before_provider_io(
    tmp_path: Path,
) -> None:
    asyncio.run(_single_file_download_rejects_cloud_transport_oversize_before_provider_io(tmp_path))


async def _single_file_download_rejects_cloud_transport_oversize_before_provider_io(
    tmp_path: Path,
) -> None:
    root = tmp_path / "jobs"
    storage = LocalTemporaryStorage(
        root,
        max_workspace_bytes=4 * TELEGRAM_CLOUD_DOWNLOAD_MAX_BYTES,
    )
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
            TelegramFile(
                file_id="provider-ref",
                file_size=TELEGRAM_CLOUD_DOWNLOAD_MAX_BYTES + 1,
            ),
        )

    assert caught.value.code == UserErrorCode.TELEGRAM_INPUT_TOO_LARGE.value
    assert not (root / str(job.job_id)).exists()
