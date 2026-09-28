from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener(thumbnails=False)


class ImageFormat(StrEnum):
    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"
    HEIF = "HEIF"


class ImageOutputFormat(StrEnum):
    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"


class CompressionPreset(StrEnum):
    BEST = "best"
    BALANCED = "balanced"
    SMALLEST = "smallest"


class ImageErrorCode(StrEnum):
    UNSUPPORTED_TYPE = "unsupported_type"
    CORRUPT_INPUT = "corrupt_input"
    DIMENSIONS_EXCEEDED = "dimensions_exceeded"
    PIXELS_EXCEEDED = "pixels_exceeded"
    MULTI_FRAME_UNSUPPORTED = "multi_frame_unsupported"
    INVALID_PARAMETERS = "invalid_parameters"
    OUTPUT_TOO_LARGE = "output_too_large"
    OUTPUT_VALIDATION_FAILED = "output_validation_failed"


class ImageEngineError(RuntimeError):
    def __init__(self, code: ImageErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ImagePolicy:
    max_width: int = 16_384
    max_height: int = 16_384
    max_pixels: int = 40_000_000
    max_output_bytes: int = 45 * 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("max_width", self.max_width),
            ("max_height", self.max_height),
            ("max_pixels", self.max_pixels),
            ("max_output_bytes", self.max_output_bytes),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")


@dataclass(frozen=True, slots=True)
class ImageInfo:
    image_format: ImageFormat
    width: int
    height: int
    mode: str
    has_alpha: bool
    byte_size: int

    @property
    def pixels(self) -> int:
        return self.width * self.height


@dataclass(frozen=True, slots=True)
class ResizeSpec:
    width: int | None = None
    height: int | None = None
    percent: int | None = None

    def __post_init__(self) -> None:
        values = (self.width, self.height, self.percent)
        if all(value is None for value in values):
            raise ValueError("resize requires width, height, or percent")
        if self.percent is not None and (self.width is not None or self.height is not None):
            raise ValueError("percent cannot be combined with width/height")
        for name, value in (
            ("width", self.width),
            ("height", self.height),
            ("percent", self.percent),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be greater than zero")

    def resolve(self, source_width: int, source_height: int) -> tuple[int, int]:
        if self.percent is not None:
            width = max(1, round(source_width * self.percent / 100))
            height = max(1, round(source_height * self.percent / 100))
            return width, height

        if self.width is not None and self.height is not None:
            ratio = min(self.width / source_width, self.height / source_height)
            return max(1, round(source_width * ratio)), max(1, round(source_height * ratio))

        if self.width is not None:
            ratio = self.width / source_width
            return self.width, max(1, round(source_height * ratio))

        if self.height is None:
            raise AssertionError("ResizeSpec validation guarantees a height")
        ratio = self.height / source_height
        return max(1, round(source_width * ratio)), self.height


@dataclass(frozen=True, slots=True)
class ImageTransform:
    target_format: ImageOutputFormat
    compression: CompressionPreset = CompressionPreset.BALANCED
    resize: ResizeSpec | None = None


@dataclass(frozen=True, slots=True)
class ImageTransformResult:
    input_info: ImageInfo
    output_info: ImageInfo
    output_path: Path


class ImageEngine:
    def __init__(self, policy: ImagePolicy | None = None) -> None:
        self._policy = policy or ImagePolicy()

    def inspect(self, source: Path) -> ImageInfo:
        image = self._load_checked(source)
        try:
            return _info(source, image)
        finally:
            image.close()

    def transform(
        self,
        source: Path,
        destination: Path,
        request: ImageTransform,
    ) -> ImageTransformResult:
        if source.resolve() == destination.resolve():
            raise ImageEngineError(
                ImageErrorCode.INVALID_PARAMETERS,
                "input and output paths must be different",
            )

        image = self._load_checked(source)
        try:
            input_info = _info(source, image)
            normalized = ImageOps.exif_transpose(image)
            if normalized is image:
                normalized = image.copy()

            try:
                transformed = self._resize(normalized, request.resize)
            finally:
                normalized.close()

            try:
                prepared = _prepare_for_output(transformed, request.target_format)
            finally:
                transformed.close()

            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                save_kwargs = _save_kwargs(request.target_format, request.compression)
                prepared.save(destination, format=request.target_format.value, **save_kwargs)
            except (OSError, ValueError) as exc:
                destination.unlink(missing_ok=True)
                raise ImageEngineError(
                    ImageErrorCode.OUTPUT_VALIDATION_FAILED,
                    "image output could not be encoded",
                ) from exc
            finally:
                prepared.close()

            if destination.stat().st_size > self._policy.max_output_bytes:
                destination.unlink(missing_ok=True)
                raise ImageEngineError(
                    ImageErrorCode.OUTPUT_TOO_LARGE,
                    "image output exceeds configured byte limit",
                )

            output_info = self._validate_output(destination, request.target_format)
            return ImageTransformResult(
                input_info=input_info,
                output_info=output_info,
                output_path=destination,
            )
        except Exception:
            if destination.exists():
                destination.unlink(missing_ok=True)
            raise
        finally:
            image.close()

    def _load_checked(self, source: Path) -> Image.Image:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image = Image.open(source)
        except Image.DecompressionBombWarning as exc:
            raise ImageEngineError(
                ImageErrorCode.PIXELS_EXCEEDED,
                "image exceeds decoder safety limits",
            ) from exc
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ImageEngineError(
                ImageErrorCode.CORRUPT_INPUT,
                "file is not a supported readable image",
            ) from exc

        try:
            image_format = _parse_input_format(image.format)
            del image_format
            width, height = image.size
            self._validate_dimensions(width, height)

            if getattr(image, "n_frames", 1) != 1:
                raise ImageEngineError(
                    ImageErrorCode.MULTI_FRAME_UNSUPPORTED,
                    "multi-frame images are not supported in the MVP",
                )

            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                image.load()
        except ImageEngineError:
            image.close()
            raise
        except Image.DecompressionBombWarning as exc:
            image.close()
            raise ImageEngineError(
                ImageErrorCode.PIXELS_EXCEEDED,
                "image exceeds decoder safety limits",
            ) from exc
        except (OSError, ValueError) as exc:
            image.close()
            raise ImageEngineError(
                ImageErrorCode.CORRUPT_INPUT,
                "image could not be decoded",
            ) from exc

        return image

    def _validate_dimensions(self, width: int, height: int) -> None:
        if width <= 0 or height <= 0:
            raise ImageEngineError(
                ImageErrorCode.CORRUPT_INPUT,
                "image has invalid dimensions",
            )
        if width > self._policy.max_width or height > self._policy.max_height:
            raise ImageEngineError(
                ImageErrorCode.DIMENSIONS_EXCEEDED,
                "image dimensions exceed configured limits",
            )
        if width * height > self._policy.max_pixels:
            raise ImageEngineError(
                ImageErrorCode.PIXELS_EXCEEDED,
                "image pixel count exceeds configured limit",
            )

    def _resize(self, image: Image.Image, resize: ResizeSpec | None) -> Image.Image:
        if resize is None:
            return image.copy()

        width, height = resize.resolve(*image.size)
        self._validate_dimensions(width, height)
        if (width, height) == image.size:
            return image.copy()
        return image.resize((width, height), Image.Resampling.LANCZOS)

    def _validate_output(
        self,
        destination: Path,
        expected_format: ImageOutputFormat,
    ) -> ImageInfo:
        try:
            with Image.open(destination) as output:
                actual_format = _parse_input_format(output.format)
                if actual_format.value != expected_format.value:
                    raise ImageEngineError(
                        ImageErrorCode.OUTPUT_VALIDATION_FAILED,
                        "encoded output format does not match the requested format",
                    )
                self._validate_dimensions(*output.size)
                output.verify()

            return self.inspect(destination)
        except ImageEngineError:
            destination.unlink(missing_ok=True)
            raise
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            destination.unlink(missing_ok=True)
            raise ImageEngineError(
                ImageErrorCode.OUTPUT_VALIDATION_FAILED,
                "encoded output failed validation",
            ) from exc


def _parse_input_format(raw: str | None) -> ImageFormat:
    if raw is None:
        raise ImageEngineError(
            ImageErrorCode.UNSUPPORTED_TYPE,
            "image format could not be determined from file content",
        )
    try:
        return ImageFormat(raw.upper())
    except ValueError as exc:
        raise ImageEngineError(
            ImageErrorCode.UNSUPPORTED_TYPE,
            f"unsupported image format: {raw}",
        ) from exc


def _has_alpha(image: Image.Image) -> bool:
    return image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info)


def _info(source: Path, image: Image.Image) -> ImageInfo:
    return ImageInfo(
        image_format=_parse_input_format(image.format),
        width=image.width,
        height=image.height,
        mode=image.mode,
        has_alpha=_has_alpha(image),
        byte_size=source.stat().st_size,
    )


def _prepare_for_output(
    image: Image.Image,
    target_format: ImageOutputFormat,
) -> Image.Image:
    if target_format is ImageOutputFormat.JPEG:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        rgba.close()
        return background

    if target_format is ImageOutputFormat.PNG:
        if _has_alpha(image):
            return image.convert("RGBA")
        return image.convert("RGB")

    if target_format is ImageOutputFormat.WEBP:
        if _has_alpha(image):
            return image.convert("RGBA")
        return image.convert("RGB")

    raise ImageEngineError(
        ImageErrorCode.INVALID_PARAMETERS,
        f"unsupported output format: {target_format}",
    )


def _save_kwargs(
    target_format: ImageOutputFormat,
    preset: CompressionPreset,
) -> dict[str, Any]:
    if target_format is ImageOutputFormat.JPEG:
        quality = {
            CompressionPreset.BEST: 92,
            CompressionPreset.BALANCED: 82,
            CompressionPreset.SMALLEST: 70,
        }[preset]
        return {
            "quality": quality,
            "optimize": True,
            "progressive": True,
            "exif": b"",
        }

    if target_format is ImageOutputFormat.WEBP:
        quality = {
            CompressionPreset.BEST: 92,
            CompressionPreset.BALANCED: 82,
            CompressionPreset.SMALLEST: 70,
        }[preset]
        return {"quality": quality, "method": 4, "exif": b"", "xmp": b""}

    if target_format is ImageOutputFormat.PNG:
        compress_level = {
            CompressionPreset.BEST: 6,
            CompressionPreset.BALANCED: 8,
            CompressionPreset.SMALLEST: 9,
        }[preset]
        return {"compress_level": compress_level, "optimize": True}

    raise ImageEngineError(
        ImageErrorCode.INVALID_PARAMETERS,
        f"unsupported output format: {target_format}",
    )
