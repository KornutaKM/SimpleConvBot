from __future__ import annotations

import base64
from pathlib import Path

import pytest
from PIL import Image

from simpleconvbot.image_engine import (
    CompressionPreset,
    ImageEngine,
    ImageEngineError,
    ImageErrorCode,
    ImageFormat,
    ImageOutputFormat,
    ImagePolicy,
    ImageTransform,
    ResizeSpec,
)

FIXTURES = Path(__file__).parent / "fixtures" / "images"


def _save_rgb(path: Path, image_format: str = "PNG", size: tuple[int, int] = (80, 40)) -> None:
    with Image.new("RGB", size, (10, 100, 200)) as image:
        image.save(path, format=image_format)


def _fixture(name: str) -> bytes:
    encoded = (FIXTURES / name).read_text(encoding="ascii")
    return base64.b64decode(encoded)


def test_inspection_uses_content_not_filename_extension(tmp_path: Path) -> None:
    source = tmp_path / "pretends-to-be-jpeg.jpg"
    _save_rgb(source, image_format="PNG")

    info = ImageEngine().inspect(source)

    assert info.image_format is ImageFormat.PNG
    assert (info.width, info.height) == (80, 40)


def test_corrupt_input_has_stable_error_code(tmp_path: Path) -> None:
    source = tmp_path / "broken.png"
    source.write_bytes(_fixture("malformed_png.b64"))

    with pytest.raises(ImageEngineError) as captured:
        ImageEngine().inspect(source)

    assert captured.value.code is ImageErrorCode.CORRUPT_INPUT


def test_input_byte_limit_is_checked_before_decode(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    _save_rgb(source)
    engine = ImageEngine(
        ImagePolicy(
            max_input_bytes=1,
            max_width=100,
            max_height=100,
            max_pixels=10_000,
            max_output_bytes=1024 * 1024,
        )
    )

    with pytest.raises(ImageEngineError) as captured:
        engine.inspect(source)

    assert captured.value.code is ImageErrorCode.INPUT_TOO_LARGE


def test_oversized_header_maps_decoder_bomb_to_stable_error(tmp_path: Path) -> None:
    source = tmp_path / "huge.png"
    source.write_bytes(_fixture("oversized_header_png.b64"))

    with pytest.raises(ImageEngineError) as captured:
        ImageEngine().inspect(source)

    assert captured.value.code is ImageErrorCode.PIXELS_EXCEEDED


def test_dimensions_are_rejected_before_transform(tmp_path: Path) -> None:
    source = tmp_path / "wide.png"
    _save_rgb(source, size=(64, 16))
    engine = ImageEngine(
        ImagePolicy(
            max_input_bytes=1024 * 1024,
            max_width=32,
            max_height=32,
            max_pixels=1024,
            max_output_bytes=1024 * 1024,
        )
    )

    with pytest.raises(ImageEngineError) as captured:
        engine.inspect(source)

    assert captured.value.code is ImageErrorCode.DIMENSIONS_EXCEEDED


def test_rgba_to_jpeg_flattens_transparency_on_white(tmp_path: Path) -> None:
    source = tmp_path / "source.bin"
    output = tmp_path / "result.bin"
    with Image.new("RGBA", (20, 10), (255, 0, 0, 0)) as image:
        image.save(source, format="PNG")

    result = ImageEngine().transform(
        source,
        output,
        ImageTransform(ImageOutputFormat.JPEG, CompressionPreset.BEST),
    )

    assert result.output_info.image_format is ImageFormat.JPEG
    assert result.output_info.mode == "RGB"
    with Image.open(output) as image:
        pixel = image.getpixel((0, 0))
    assert isinstance(pixel, tuple)
    assert min(pixel) >= 245


def test_resize_percent_preserves_aspect_ratio(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "result.webp"
    _save_rgb(source, size=(100, 50))

    result = ImageEngine().transform(
        source,
        output,
        ImageTransform(
            ImageOutputFormat.WEBP,
            resize=ResizeSpec(percent=50),
        ),
    )

    assert (result.output_info.width, result.output_info.height) == (50, 25)
    assert result.output_info.image_format is ImageFormat.WEBP


def test_resize_box_preserves_aspect_ratio(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "result.png"
    _save_rgb(source, size=(200, 100))

    result = ImageEngine().transform(
        source,
        output,
        ImageTransform(
            ImageOutputFormat.PNG,
            resize=ResizeSpec(width=60, height=60),
        ),
    )

    assert (result.output_info.width, result.output_info.height) == (60, 30)


def test_resize_target_is_bounded_by_policy(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "result.png"
    _save_rgb(source, size=(20, 20))
    engine = ImageEngine(
        ImagePolicy(
            max_input_bytes=1024 * 1024,
            max_width=100,
            max_height=100,
            max_pixels=10_000,
            max_output_bytes=1024 * 1024,
        )
    )

    with pytest.raises(ImageEngineError) as captured:
        engine.transform(
            source,
            output,
            ImageTransform(
                ImageOutputFormat.PNG,
                resize=ResizeSpec(width=101),
            ),
        )

    assert captured.value.code is ImageErrorCode.DIMENSIONS_EXCEEDED
    assert not output.exists()


def test_animated_webp_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "animated.webp"
    first = Image.new("RGB", (20, 20), "red")
    second = Image.new("RGB", (20, 20), "blue")
    try:
        first.save(
            source,
            format="WEBP",
            save_all=True,
            append_images=[second],
            duration=100,
            loop=0,
        )
    finally:
        first.close()
        second.close()

    with pytest.raises(ImageEngineError) as captured:
        ImageEngine().inspect(source)

    assert captured.value.code is ImageErrorCode.MULTI_FRAME_UNSUPPORTED


def test_heif_content_converts_to_jpeg(tmp_path: Path) -> None:
    source = tmp_path / "phone-photo.dat"
    output = tmp_path / "phone-photo.jpg"
    _save_rgb(source, image_format="HEIF", size=(32, 24))

    result = ImageEngine().transform(
        source,
        output,
        ImageTransform(ImageOutputFormat.JPEG),
    )

    assert result.input_info.image_format is ImageFormat.HEIF
    assert result.output_info.image_format is ImageFormat.JPEG
    assert (result.output_info.width, result.output_info.height) == (32, 24)


def test_output_size_limit_removes_output(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "result.png"
    _save_rgb(source, size=(20, 20))
    engine = ImageEngine(
        ImagePolicy(
            max_input_bytes=1024 * 1024,
            max_width=100,
            max_height=100,
            max_pixels=10_000,
            max_output_bytes=1,
        )
    )

    with pytest.raises(ImageEngineError) as captured:
        engine.transform(source, output, ImageTransform(ImageOutputFormat.PNG))

    assert captured.value.code is ImageErrorCode.OUTPUT_TOO_LARGE
    assert not output.exists()


@pytest.mark.parametrize(
    "target_format",
    [
        ImageOutputFormat.JPEG,
        ImageOutputFormat.PNG,
        ImageOutputFormat.WEBP,
    ],
)
def test_every_advertised_output_is_content_validated(
    tmp_path: Path,
    target_format: ImageOutputFormat,
) -> None:
    source = tmp_path / "input.bin"
    output = tmp_path / "output.bin"
    _save_rgb(source, size=(23, 17))

    result = ImageEngine().transform(
        source,
        output,
        ImageTransform(target_format=target_format),
    )

    assert result.output_info.image_format.value == target_format.value
    assert (result.output_info.width, result.output_info.height) == (23, 17)


@pytest.mark.parametrize(
    "spec",
    [
        ResizeSpec(width=10),
        ResizeSpec(height=10),
        ResizeSpec(width=10, height=20),
        ResizeSpec(percent=50),
    ],
)
def test_resize_specs_are_valid(spec: ResizeSpec) -> None:
    width, height = spec.resolve(100, 50)

    assert width > 0
    assert height > 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"width": 0},
        {"height": -1},
        {"percent": 0},
        {"width": 10, "percent": 50},
    ],
)
def test_invalid_resize_specs_fail(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        ResizeSpec(**kwargs)
