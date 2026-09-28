from __future__ import annotations

import math
from copy import copy
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image, ImageOps
from pypdf import PdfReader, PdfWriter

from simpleconvbot.image_engine import ImageEngine, ImageEngineError, ImagePolicy


class PdfErrorCode(StrEnum):
    INPUT_TOO_LARGE = "pdf_input_too_large"
    AGGREGATE_TOO_LARGE = "pdf_aggregate_too_large"
    CORRUPT_INPUT = "pdf_corrupt_input"
    ENCRYPTED_UNSUPPORTED = "pdf_encrypted_unsupported"
    PAGE_LIMIT_EXCEEDED = "pdf_page_limit_exceeded"
    PAGE_DIMENSIONS_EXCEEDED = "pdf_page_dimensions_exceeded"
    INVALID_SELECTION = "pdf_invalid_selection"
    IMAGE_INPUT_INVALID = "pdf_image_input_invalid"
    RENDER_LIMIT_EXCEEDED = "pdf_render_limit_exceeded"
    OUTPUT_TOO_LARGE = "pdf_output_too_large"
    OUTPUT_VALIDATION_FAILED = "pdf_output_validation_failed"
    PROCESSING_FAILED = "pdf_processing_failed"


class PdfEngineError(RuntimeError):
    def __init__(self, code: PdfErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PdfPolicy:
    max_input_bytes: int = 20 * 1024 * 1024
    max_aggregate_input_bytes: int = 40 * 1024 * 1024
    max_output_bytes: int = 45 * 1024 * 1024
    max_pages: int = 200
    max_selected_pages: int = 100
    max_image_inputs: int = 20
    max_page_width_points: int = 20_000
    max_page_height_points: int = 20_000
    render_dpi: int = 144
    max_render_pixels_per_page: int = 25_000_000
    max_rendered_page_bytes: int = 20 * 1024 * 1024
    max_rendered_total_bytes: int = 45 * 1024 * 1024
    root_object_recovery_limit: int = 2_000

    def __post_init__(self) -> None:
        for name, value in (
            ("max_input_bytes", self.max_input_bytes),
            ("max_aggregate_input_bytes", self.max_aggregate_input_bytes),
            ("max_output_bytes", self.max_output_bytes),
            ("max_pages", self.max_pages),
            ("max_selected_pages", self.max_selected_pages),
            ("max_image_inputs", self.max_image_inputs),
            ("max_page_width_points", self.max_page_width_points),
            ("max_page_height_points", self.max_page_height_points),
            ("render_dpi", self.render_dpi),
            ("max_render_pixels_per_page", self.max_render_pixels_per_page),
            ("max_rendered_page_bytes", self.max_rendered_page_bytes),
            ("max_rendered_total_bytes", self.max_rendered_total_bytes),
            ("root_object_recovery_limit", self.root_object_recovery_limit),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")


@dataclass(frozen=True, slots=True)
class PdfInfo:
    page_count: int
    byte_size: int
    version: str


@dataclass(frozen=True, slots=True)
class PageRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start <= 0 or self.end <= 0:
            raise ValueError("PDF page numbers are 1-based and must be positive")
        if self.end < self.start:
            raise ValueError("page range end must be greater than or equal to start")


@dataclass(frozen=True, slots=True)
class PageSelection:
    ranges: tuple[PageRange, ...]

    def __post_init__(self) -> None:
        if not self.ranges:
            raise ValueError("page selection must not be empty")

    def resolve(self, *, total_pages: int, max_selected_pages: int) -> tuple[int, ...]:
        if total_pages <= 0:
            raise PdfEngineError(PdfErrorCode.CORRUPT_INPUT, "PDF contains no pages")

        selected_count = 0
        for page_range in self.ranges:
            if page_range.end > total_pages:
                raise PdfEngineError(
                    PdfErrorCode.INVALID_SELECTION,
                    "page selection exceeds document page count",
                )
            selected_count += page_range.end - page_range.start + 1
            if selected_count > max_selected_pages:
                raise PdfEngineError(
                    PdfErrorCode.INVALID_SELECTION,
                    "page selection exceeds configured page limit",
                )

        resolved: list[int] = []
        seen: set[int] = set()
        for page_range in self.ranges:
            for page_number in range(page_range.start, page_range.end + 1):
                zero_based = page_number - 1
                if zero_based in seen:
                    raise PdfEngineError(
                        PdfErrorCode.INVALID_SELECTION,
                        "page selection contains duplicates",
                    )
                seen.add(zero_based)
                resolved.append(zero_based)
        return tuple(resolved)


@dataclass(frozen=True, slots=True)
class RenderedPages:
    input_info: PdfInfo
    output_paths: tuple[Path, ...]


class PdfEngine:
    def __init__(self, policy: PdfPolicy | None = None) -> None:
        self._policy = policy or PdfPolicy()
        self._rendered_image_validator = ImageEngine(
            ImagePolicy(
                max_input_bytes=self._policy.max_rendered_page_bytes,
                max_width=20_000,
                max_height=20_000,
                max_pixels=self._policy.max_render_pixels_per_page,
                max_output_bytes=self._policy.max_rendered_page_bytes,
            )
        )

    def inspect(self, source: Path) -> PdfInfo:
        return self._inspect_pdf(source, max_bytes=self._policy.max_input_bytes)

    def render_pages(
        self,
        source: Path,
        output_dir: Path,
        selection: PageSelection | None = None,
    ) -> RenderedPages:
        input_info = self.inspect(source)
        indices = (
            tuple(range(input_info.page_count))
            if selection is None
            else selection.resolve(
                total_pages=input_info.page_count,
                max_selected_pages=self._policy.max_selected_pages,
            )
        )
        if len(indices) > self._policy.max_selected_pages:
            raise PdfEngineError(
                PdfErrorCode.INVALID_SELECTION,
                "render page count exceeds configured page limit",
            )

        output_dir.mkdir(parents=True, exist_ok=True)
        generated_paths: list[Path] = []
        final_paths: list[Path] = []
        total_output_bytes = 0

        try:
            document = pdfium.PdfDocument(str(source))
            try:
                if len(document) != input_info.page_count:
                    raise PdfEngineError(
                        PdfErrorCode.CORRUPT_INPUT,
                        "PDF parsers disagree on page count",
                    )

                scale = self._policy.render_dpi / 72.0
                for output_number, page_index in enumerate(indices, start=1):
                    page = document[page_index]
                    try:
                        width_points, height_points = page.get_size()
                        width_px = max(1, math.ceil(width_points * scale))
                        height_px = max(1, math.ceil(height_points * scale))
                        if width_px * height_px > self._policy.max_render_pixels_per_page:
                            raise PdfEngineError(
                                PdfErrorCode.RENDER_LIMIT_EXCEEDED,
                                "rendered page would exceed pixel limit",
                            )

                        final = output_dir / f"page-{output_number:04d}.png"
                        partial = output_dir / f".page-{output_number:04d}.partial.png"
                        final.unlink(missing_ok=True)
                        partial.unlink(missing_ok=True)
                        generated_paths.extend((partial, final))

                        bitmap = page.render(
                            scale=scale,
                            rotation=0,
                            may_draw_forms=False,
                            draw_annots=False,
                            limit_image_cache=True,
                            rev_byteorder=True,
                        )
                        try:
                            rendered = bitmap.to_pil()
                            try:
                                rendered.save(partial, format="PNG", optimize=True)
                            finally:
                                rendered.close()
                        finally:
                            bitmap.close()

                        self._rendered_image_validator.inspect(partial)
                        page_bytes = partial.stat().st_size
                        total_output_bytes += page_bytes
                        if total_output_bytes > self._policy.max_rendered_total_bytes:
                            raise PdfEngineError(
                                PdfErrorCode.OUTPUT_TOO_LARGE,
                                "rendered page set exceeds aggregate byte limit",
                            )
                        partial.replace(final)
                        final_paths.append(final)
                    finally:
                        page.close()
            finally:
                document.close()
        except PdfEngineError:
            _cleanup_paths(tuple(generated_paths))
            raise
        except Exception as exc:
            _cleanup_paths(tuple(generated_paths))
            raise PdfEngineError(
                PdfErrorCode.PROCESSING_FAILED,
                "PDF rendering failed",
            ) from exc

        return RenderedPages(input_info=input_info, output_paths=tuple(final_paths))

    def merge(self, sources: tuple[Path, ...], destination: Path) -> PdfInfo:
        if not sources:
            raise PdfEngineError(PdfErrorCode.CORRUPT_INPUT, "merge requires at least one PDF")
        infos = self._inspect_many(sources)
        expected_pages = sum(info.page_count for info in infos)
        return self._compose_pdf(
            sources=sources,
            destination=destination,
            selected_pages=None,
            expected_pages=expected_pages,
        )

    def extract_pages(
        self,
        source: Path,
        destination: Path,
        selection: PageSelection,
    ) -> PdfInfo:
        info = self.inspect(source)
        indices = selection.resolve(
            total_pages=info.page_count,
            max_selected_pages=self._policy.max_selected_pages,
        )
        return self._compose_pdf(
            sources=(source,),
            destination=destination,
            selected_pages=indices,
            expected_pages=len(indices),
        )

    def images_to_pdf(self, sources: tuple[Path, ...], destination: Path) -> PdfInfo:
        if not sources:
            raise PdfEngineError(
                PdfErrorCode.IMAGE_INPUT_INVALID,
                "image-to-PDF requires at least one image",
            )
        if len(sources) > self._policy.max_image_inputs:
            raise PdfEngineError(
                PdfErrorCode.PAGE_LIMIT_EXCEEDED,
                "too many image inputs",
            )

        total_bytes = 0
        images: list[Image.Image] = []
        partial = _partial_path(destination)
        destination.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)

        try:
            for source in sources:
                try:
                    info = ImageEngine().inspect(source)
                except ImageEngineError as exc:
                    raise PdfEngineError(
                        PdfErrorCode.IMAGE_INPUT_INVALID,
                        f"invalid image input: {exc.code.value}",
                    ) from exc

                total_bytes += info.byte_size
                if total_bytes > self._policy.max_aggregate_input_bytes:
                    raise PdfEngineError(
                        PdfErrorCode.AGGREGATE_TOO_LARGE,
                        "image inputs exceed aggregate byte limit",
                    )

                with Image.open(source) as opened:
                    normalized = ImageOps.exif_transpose(opened)
                    if normalized is opened:
                        normalized = opened.copy()
                    try:
                        images.append(_flatten_for_pdf(normalized))
                    finally:
                        normalized.close()

            first, *rest = images
            partial.parent.mkdir(parents=True, exist_ok=True)
            first.save(
                partial,
                format="PDF",
                save_all=True,
                append_images=rest,
                resolution=float(self._policy.render_dpi),
            )
            self._check_output_size(partial)
            self._validate_output(partial, expected_pages=len(images))
            partial.replace(destination)
            return self._validate_output(destination, expected_pages=len(images))
        except PdfEngineError:
            destination.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
            raise
        except Exception as exc:
            destination.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
            raise PdfEngineError(
                PdfErrorCode.PROCESSING_FAILED,
                "image-to-PDF conversion failed",
            ) from exc
        finally:
            for image in images:
                image.close()

    def _inspect_many(self, sources: tuple[Path, ...]) -> tuple[PdfInfo, ...]:
        total_bytes = 0
        total_pages = 0
        infos: list[PdfInfo] = []

        for source in sources:
            info = self.inspect(source)
            total_bytes += info.byte_size
            total_pages += info.page_count
            if total_bytes > self._policy.max_aggregate_input_bytes:
                raise PdfEngineError(
                    PdfErrorCode.AGGREGATE_TOO_LARGE,
                    "PDF inputs exceed aggregate byte limit",
                )
            if total_pages > self._policy.max_pages:
                raise PdfEngineError(
                    PdfErrorCode.PAGE_LIMIT_EXCEEDED,
                    "PDF inputs exceed aggregate page limit",
                )
            infos.append(info)
        return tuple(infos)

    def _compose_pdf(
        self,
        *,
        sources: tuple[Path, ...],
        destination: Path,
        selected_pages: tuple[int, ...] | None,
        expected_pages: int,
    ) -> PdfInfo:
        if expected_pages <= 0 or expected_pages > self._policy.max_pages:
            raise PdfEngineError(
                PdfErrorCode.PAGE_LIMIT_EXCEEDED,
                "output page count exceeds configured limit",
            )

        partial = _partial_path(destination)
        destination.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
        writer = PdfWriter()

        try:
            for source_index, source in enumerate(sources):
                reader = self._open_reader(source, max_bytes=self._policy.max_input_bytes)
                try:
                    indices = (
                        selected_pages
                        if selected_pages is not None and source_index == 0
                        else tuple(range(len(reader.pages)))
                    )
                    for page_index in indices:
                        page = copy(reader.pages[page_index])
                        page.pop("/Annots", None)
                        page.pop("/AA", None)
                        page.pop("/Metadata", None)
                        writer.add_page(page)
                finally:
                    reader.close()

            writer.add_metadata({})
            partial.parent.mkdir(parents=True, exist_ok=True)
            with partial.open("wb") as stream:
                writer.write(stream)

            self._check_output_size(partial)
            self._validate_output(partial, expected_pages=expected_pages)
            partial.replace(destination)
            return self._validate_output(destination, expected_pages=expected_pages)
        except PdfEngineError:
            destination.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
            raise
        except Exception as exc:
            destination.unlink(missing_ok=True)
            partial.unlink(missing_ok=True)
            raise PdfEngineError(
                PdfErrorCode.PROCESSING_FAILED,
                "PDF composition failed",
            ) from exc
        finally:
            writer.close()

    def _inspect_pdf(self, source: Path, *, max_bytes: int) -> PdfInfo:
        reader = self._open_reader(source, max_bytes=max_bytes)
        try:
            page_count = len(reader.pages)
            if page_count <= 0:
                raise PdfEngineError(PdfErrorCode.CORRUPT_INPUT, "PDF contains no pages")
            if page_count > self._policy.max_pages:
                raise PdfEngineError(
                    PdfErrorCode.PAGE_LIMIT_EXCEEDED,
                    "PDF exceeds configured page limit",
                )

            for page in reader.pages:
                width = abs(float(page.mediabox.width))
                height = abs(float(page.mediabox.height))
                if (
                    width <= 0
                    or height <= 0
                    or width > self._policy.max_page_width_points
                    or height > self._policy.max_page_height_points
                ):
                    raise PdfEngineError(
                        PdfErrorCode.PAGE_DIMENSIONS_EXCEEDED,
                        "PDF page dimensions exceed configured limits",
                    )

            byte_size = source.stat().st_size
            version = reader.pdf_header
        except PdfEngineError:
            raise
        except Exception as exc:
            raise PdfEngineError(
                PdfErrorCode.CORRUPT_INPUT,
                "PDF structure could not be inspected",
            ) from exc
        finally:
            reader.close()

        try:
            document = pdfium.PdfDocument(str(source))
            try:
                if len(document) != page_count:
                    raise PdfEngineError(
                        PdfErrorCode.CORRUPT_INPUT,
                        "PDF parsers disagree on page count",
                    )
            finally:
                document.close()
        except PdfEngineError:
            raise
        except Exception as exc:
            raise PdfEngineError(
                PdfErrorCode.CORRUPT_INPUT,
                "PDFium rejected the document",
            ) from exc

        return PdfInfo(page_count=page_count, byte_size=byte_size, version=version)

    def _open_reader(self, source: Path, *, max_bytes: int) -> PdfReader:
        try:
            byte_size = source.stat().st_size
        except OSError as exc:
            raise PdfEngineError(
                PdfErrorCode.CORRUPT_INPUT,
                "PDF file is not readable",
            ) from exc
        if byte_size > max_bytes:
            raise PdfEngineError(
                PdfErrorCode.INPUT_TOO_LARGE,
                "PDF file exceeds configured byte limit",
            )

        try:
            reader = PdfReader(
                source,
                strict=True,
                root_object_recovery_limit=self._policy.root_object_recovery_limit,
            )
        except Exception as exc:
            raise PdfEngineError(
                PdfErrorCode.CORRUPT_INPUT,
                "file is not a readable PDF",
            ) from exc

        if reader.is_encrypted:
            reader.close()
            raise PdfEngineError(
                PdfErrorCode.ENCRYPTED_UNSUPPORTED,
                "encrypted PDFs are not supported",
            )
        return reader

    def _check_output_size(self, path: Path) -> None:
        try:
            byte_size = path.stat().st_size
        except OSError as exc:
            raise PdfEngineError(
                PdfErrorCode.OUTPUT_VALIDATION_FAILED,
                "PDF output is not readable",
            ) from exc
        if byte_size > self._policy.max_output_bytes:
            raise PdfEngineError(
                PdfErrorCode.OUTPUT_TOO_LARGE,
                "PDF output exceeds configured byte limit",
            )

    def _validate_output(self, path: Path, *, expected_pages: int) -> PdfInfo:
        try:
            info = self._inspect_pdf(path, max_bytes=self._policy.max_output_bytes)
        except PdfEngineError as exc:
            if exc.code is PdfErrorCode.INPUT_TOO_LARGE:
                raise PdfEngineError(
                    PdfErrorCode.OUTPUT_TOO_LARGE,
                    "PDF output exceeds configured byte limit",
                ) from exc
            raise PdfEngineError(
                PdfErrorCode.OUTPUT_VALIDATION_FAILED,
                f"PDF output failed validation: {exc.code.value}",
            ) from exc
        if info.page_count != expected_pages:
            raise PdfEngineError(
                PdfErrorCode.OUTPUT_VALIDATION_FAILED,
                "PDF output page count does not match expected count",
            )
        return info


def _partial_path(destination: Path) -> Path:
    return destination.with_name(f".{destination.name}.partial")


def _cleanup_paths(paths: tuple[Path, ...]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def _flatten_for_pdf(image: Image.Image) -> Image.Image:
    rgba = image.convert("RGBA")
    try:
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    finally:
        rgba.close()
