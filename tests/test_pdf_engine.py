from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader, PdfWriter

from simpleconvbot.pdf_engine import (
    PageRange,
    PageSelection,
    PdfEngine,
    PdfEngineError,
    PdfErrorCode,
    PdfPolicy,
)


def _make_pdf(path: Path, sizes: tuple[tuple[float, float], ...]) -> None:
    writer = PdfWriter()
    try:
        for width, height in sizes:
            writer.add_blank_page(width=width, height=height)
        with path.open("wb") as stream:
            writer.write(stream)
    finally:
        writer.close()


def test_inspect_uses_pdf_content_not_extension(tmp_path: Path) -> None:
    source = tmp_path / "document.txt"
    _make_pdf(source, ((200, 300), (300, 400)))

    info = PdfEngine().inspect(source)

    assert info.page_count == 2
    assert info.byte_size == source.stat().st_size
    assert info.version.startswith("%PDF-")


def test_corrupt_pdf_returns_stable_error(tmp_path: Path) -> None:
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.7\nnot actually a PDF")

    with pytest.raises(PdfEngineError) as captured:
        PdfEngine().inspect(source)

    assert captured.value.code is PdfErrorCode.CORRUPT_INPUT


def test_encrypted_pdf_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "encrypted.pdf"
    writer = PdfWriter()
    try:
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secret")
        with source.open("wb") as stream:
            writer.write(stream)
    finally:
        writer.close()

    with pytest.raises(PdfEngineError) as captured:
        PdfEngine().inspect(source)

    assert captured.value.code is PdfErrorCode.ENCRYPTED_UNSUPPORTED


def test_page_count_limit_is_enforced(tmp_path: Path) -> None:
    source = tmp_path / "pages.pdf"
    _make_pdf(source, ((100, 100), (100, 100)))
    engine = PdfEngine(PdfPolicy(max_pages=1))

    with pytest.raises(PdfEngineError) as captured:
        engine.inspect(source)

    assert captured.value.code is PdfErrorCode.PAGE_LIMIT_EXCEEDED


def test_page_dimensions_are_bounded(tmp_path: Path) -> None:
    source = tmp_path / "huge-page.pdf"
    _make_pdf(source, ((500, 100),))
    engine = PdfEngine(PdfPolicy(max_page_width_points=400))

    with pytest.raises(PdfEngineError) as captured:
        engine.inspect(source)

    assert captured.value.code is PdfErrorCode.PAGE_DIMENSIONS_EXCEEDED


def test_page_selection_is_typed_bounded_and_ordered() -> None:
    selection = PageSelection((PageRange(2, 3), PageRange(1, 1)))

    assert selection.resolve(total_pages=3, max_selected_pages=3) == (1, 2, 0)


def test_page_selection_rejects_duplicates() -> None:
    selection = PageSelection((PageRange(1, 2), PageRange(2, 2)))

    with pytest.raises(PdfEngineError) as captured:
        selection.resolve(total_pages=3, max_selected_pages=3)

    assert captured.value.code is PdfErrorCode.INVALID_SELECTION


def test_page_selection_rejects_out_of_range_without_expanding() -> None:
    selection = PageSelection((PageRange(1, 1_000_000),))

    with pytest.raises(PdfEngineError) as captured:
        selection.resolve(total_pages=10, max_selected_pages=10)

    assert captured.value.code is PdfErrorCode.INVALID_SELECTION


def test_merge_preserves_source_order_and_validates_output(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    output = tmp_path / "merged.pdf"
    _make_pdf(first, ((100, 200),))
    _make_pdf(second, ((300, 400),))

    info = PdfEngine().merge((first, second), output)

    assert info.page_count == 2
    reader = PdfReader(output, strict=True)
    try:
        widths = tuple(float(page.mediabox.width) for page in reader.pages)
    finally:
        reader.close()
    assert widths == (100.0, 300.0)
    assert not (tmp_path / ".merged.pdf.partial").exists()


def test_extract_pages_preserves_explicit_selection_order(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "extract.pdf"
    _make_pdf(source, ((100, 100), (200, 100), (300, 100)))

    info = PdfEngine().extract_pages(
        source,
        output,
        PageSelection((PageRange(3, 3), PageRange(1, 1))),
    )

    assert info.page_count == 2
    reader = PdfReader(output, strict=True)
    try:
        widths = tuple(float(page.mediabox.width) for page in reader.pages)
    finally:
        reader.close()
    assert widths == (300.0, 100.0)


def test_pdf_to_images_renders_and_validates_every_page(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output_dir = tmp_path / "pages"
    _make_pdf(source, ((72, 72), (144, 72)))

    result = PdfEngine().render_pages(source, output_dir)

    assert len(result.output_paths) == 2
    with Image.open(result.output_paths[0]) as first:
        assert first.format == "PNG"
        assert first.size == (144, 144)
    with Image.open(result.output_paths[1]) as second:
        assert second.format == "PNG"
        assert second.size == (288, 144)
    assert not tuple(output_dir.glob("*.partial.png"))


def test_pdf_render_rejects_pixel_bomb_before_render(tmp_path: Path) -> None:
    source = tmp_path / "large-canvas.pdf"
    _make_pdf(source, ((1000, 1000),))
    engine = PdfEngine(
        PdfPolicy(
            max_page_width_points=2000,
            max_page_height_points=2000,
            max_render_pixels_per_page=1_000_000,
        )
    )

    with pytest.raises(PdfEngineError) as captured:
        engine.render_pages(source, tmp_path / "pages")

    assert captured.value.code is PdfErrorCode.RENDER_LIMIT_EXCEEDED


def test_images_to_pdf_is_deterministic_and_validated(tmp_path: Path) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.jpg"
    output = tmp_path / "images.pdf"
    Image.new("RGB", (30, 20), "red").save(first, format="PNG")
    Image.new("RGB", (40, 25), "blue").save(second, format="JPEG")

    info = PdfEngine().images_to_pdf((first, second), output)

    assert info.page_count == 2
    assert output.exists()
    assert not (tmp_path / ".images.pdf.partial").exists()


def test_output_limit_removes_partial_and_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    output = tmp_path / "output.pdf"
    _make_pdf(source, ((100, 100),))
    engine = PdfEngine(PdfPolicy(max_output_bytes=1))

    with pytest.raises(PdfEngineError) as captured:
        engine.extract_pages(
            source,
            output,
            PageSelection((PageRange(1, 1),)),
        )

    assert captured.value.code is PdfErrorCode.OUTPUT_TOO_LARGE
    assert not output.exists()
    assert not (tmp_path / ".output.pdf.partial").exists()


def test_aggregate_merge_byte_limit_is_enforced(tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    _make_pdf(first, ((100, 100),))
    _make_pdf(second, ((100, 100),))
    combined = first.stat().st_size + second.stat().st_size
    engine = PdfEngine(PdfPolicy(max_aggregate_input_bytes=combined - 1))

    with pytest.raises(PdfEngineError) as captured:
        engine.merge((first, second), tmp_path / "merged.pdf")

    assert captured.value.code is PdfErrorCode.AGGREGATE_TOO_LARGE
