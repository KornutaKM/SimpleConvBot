from __future__ import annotations

import json
import math
import shutil
import subprocess
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class MediaErrorCode(StrEnum):
    TOOLCHAIN_UNAVAILABLE = "media_toolchain_unavailable"
    INPUT_TOO_LARGE = "media_input_too_large"
    CORRUPT_INPUT = "media_corrupt_input"
    UNSUPPORTED_CONTAINER = "media_unsupported_container"
    UNSUPPORTED_CODEC = "media_unsupported_codec"
    UNSUPPORTED_STREAMS = "media_unsupported_streams"
    DURATION_LIMIT_EXCEEDED = "media_duration_limit_exceeded"
    RESOLUTION_LIMIT_EXCEEDED = "media_resolution_limit_exceeded"
    INVALID_OPERATION = "media_invalid_operation"
    TIMEOUT = "media_timeout"
    OUTPUT_TOO_LARGE = "media_output_too_large"
    OUTPUT_VALIDATION_FAILED = "media_output_validation_failed"
    PROCESSING_FAILED = "media_processing_failed"


class MediaEngineError(RuntimeError):
    def __init__(self, code: MediaErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class AudioOutputFormat(StrEnum):
    MP3 = "mp3"
    M4A = "m4a"
    WAV = "wav"


class VideoCompressionPreset(StrEnum):
    HIGH_QUALITY = "high_quality"
    BALANCED = "balanced"
    SMALL = "small"


@dataclass(frozen=True, slots=True)
class MediaPolicy:
    max_input_bytes: int = 20 * 1024 * 1024
    max_output_bytes: int = 45 * 1024 * 1024
    max_duration_seconds: float = 600.0
    max_video_width: int = 3840
    max_video_height: int = 2160
    max_video_pixels: int = 8_294_400
    max_streams: int = 8
    max_gif_duration_seconds: float = 10.0
    max_gif_width: int = 640
    probe_timeout_seconds: float = 10.0
    conversion_timeout_seconds: float = 60.0
    max_process_output_bytes: int = 1024 * 1024

    def __post_init__(self) -> None:
        for name, value in (
            ("max_input_bytes", self.max_input_bytes),
            ("max_output_bytes", self.max_output_bytes),
            ("max_duration_seconds", self.max_duration_seconds),
            ("max_video_width", self.max_video_width),
            ("max_video_height", self.max_video_height),
            ("max_video_pixels", self.max_video_pixels),
            ("max_streams", self.max_streams),
            ("max_gif_duration_seconds", self.max_gif_duration_seconds),
            ("max_gif_width", self.max_gif_width),
            ("probe_timeout_seconds", self.probe_timeout_seconds),
            ("conversion_timeout_seconds", self.conversion_timeout_seconds),
            ("max_process_output_bytes", self.max_process_output_bytes),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be greater than zero")


@dataclass(frozen=True, slots=True)
class AudioStreamInfo:
    codec_name: str
    sample_rate: int | None
    channels: int | None


@dataclass(frozen=True, slots=True)
class VideoStreamInfo:
    codec_name: str
    width: int
    height: int


@dataclass(frozen=True, slots=True)
class MediaInfo:
    container_formats: tuple[str, ...]
    duration_seconds: float
    byte_size: int
    audio_streams: tuple[AudioStreamInfo, ...]
    video_streams: tuple[VideoStreamInfo, ...]


@dataclass(frozen=True, slots=True)
class MediaToolchain:
    ffmpeg: Path
    ffprobe: Path

    @classmethod
    def discover(cls) -> MediaToolchain:
        ffmpeg = shutil.which("ffmpeg")
        ffprobe = shutil.which("ffprobe")
        if ffmpeg is None or ffprobe is None:
            raise MediaEngineError(
                MediaErrorCode.TOOLCHAIN_UNAVAILABLE,
                "ffmpeg and ffprobe are required",
            )
        return cls(ffmpeg=Path(ffmpeg).resolve(), ffprobe=Path(ffprobe).resolve())


@dataclass(frozen=True, slots=True)
class _ProcessResult:
    returncode: int
    stdout: str
    stderr: str


class _BoundedProcessRunner:
    def __init__(self, max_output_bytes: int) -> None:
        self._max_output_bytes = max_output_bytes

    def run(self, argv: tuple[str, ...], *, timeout_seconds: float) -> _ProcessResult:
        safe_env = {
            "LANG": "C",
            "LC_ALL": "C",
            "AV_LOG_FORCE_NOCOLOR": "1",
        }
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            shell=False,
            env=safe_env,
            close_fds=True,
        )
        try:
            stdout, stderr = process.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            process.kill()
            process.communicate()
            raise MediaEngineError(
                MediaErrorCode.TIMEOUT,
                "media process exceeded its hard timeout",
            ) from exc

        if len(stdout.encode("utf-8")) + len(stderr.encode("utf-8")) > self._max_output_bytes:
            raise MediaEngineError(
                MediaErrorCode.PROCESSING_FAILED,
                "media process diagnostic output exceeded limit",
            )
        return _ProcessResult(process.returncode, stdout, stderr)


_ALLOWED_CONTAINERS = frozenset(
    {
        "aac",
        "avi",
        "flac",
        "gif",
        "matroska",
        "m4a",
        "mj2",
        "mov",
        "mp3",
        "mp4",
        "ogg",
        "wav",
        "webm",
        "3g2",
        "3gp",
    }
)
_ALLOWED_AUDIO_CODECS = frozenset(
    {
        "aac",
        "alac",
        "flac",
        "mp3",
        "opus",
        "pcm_f32le",
        "pcm_s16le",
        "pcm_s24le",
        "pcm_s32le",
        "vorbis",
    }
)
_ALLOWED_VIDEO_CODECS = frozenset({"av1", "h264", "hevc", "mpeg4", "theora", "vp8", "vp9", "gif"})


class MediaEngine:
    def __init__(
        self,
        policy: MediaPolicy | None = None,
        toolchain: MediaToolchain | None = None,
    ) -> None:
        self._policy = policy or MediaPolicy()
        self._toolchain = toolchain or MediaToolchain.discover()
        self._runner = _BoundedProcessRunner(self._policy.max_process_output_bytes)

    def inspect(self, source: Path) -> MediaInfo:
        return self._probe(source, max_bytes=self._policy.max_input_bytes)

    def convert_audio(
        self,
        source: Path,
        destination: Path,
        target: AudioOutputFormat,
    ) -> MediaInfo:
        source_info = self.inspect(source)
        self._require_audio(source_info)

        if target is AudioOutputFormat.MP3:
            media_args = ("-vn", "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3")
            expected_container = "mp3"
            expected_codec = "mp3"
        elif target is AudioOutputFormat.M4A:
            media_args = (
                "-vn",
                "-map",
                "0:a:0",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                "-f",
                "ipod",
            )
            expected_container = "m4a"
            expected_codec = "aac"
        elif target is AudioOutputFormat.WAV:
            media_args = ("-vn", "-map", "0:a:0", "-c:a", "pcm_s16le", "-f", "wav")
            expected_container = "wav"
            expected_codec = "pcm_s16le"
        else:
            raise MediaEngineError(MediaErrorCode.INVALID_OPERATION, "unsupported audio target")

        output = self._transcode(source, destination, media_args)
        try:
            info = self._probe(output, max_bytes=self._policy.max_output_bytes)
            self._validate_audio_output(info, expected_container, expected_codec)
            return info
        except MediaEngineError:
            self._remove_output(output)
            raise

    def video_to_mp3(self, source: Path, destination: Path) -> MediaInfo:
        source_info = self.inspect(source)
        self._require_video(source_info)
        self._require_audio(source_info)
        output = self._transcode(
            source,
            destination,
            ("-vn", "-map", "0:a:0", "-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3"),
        )
        try:
            info = self._probe(output, max_bytes=self._policy.max_output_bytes)
            self._validate_audio_output(info, "mp3", "mp3")
            return info
        except MediaEngineError:
            self._remove_output(output)
            raise

    def mute_video(self, source: Path, destination: Path) -> MediaInfo:
        source_info = self.inspect(source)
        self._require_video(source_info)
        output = self._transcode(
            source,
            destination,
            (
                "-map",
                "0:v:0",
                "-an",
                "-c:v",
                "mpeg4",
                "-q:v",
                "5",
                "-pix_fmt",
                "yuv420p",
                "-f",
                "mp4",
            ),
        )
        try:
            info = self._probe(output, max_bytes=self._policy.max_output_bytes)
            self._validate_mp4_video(info, allow_audio=False)
            return info
        except MediaEngineError:
            self._remove_output(output)
            raise

    def video_to_gif(self, source: Path, destination: Path) -> MediaInfo:
        source_info = self.inspect(source)
        video = self._require_video(source_info)
        if source_info.duration_seconds > self._policy.max_gif_duration_seconds:
            raise MediaEngineError(
                MediaErrorCode.DURATION_LIMIT_EXCEEDED,
                "video is too long for GIF conversion",
            )

        width = min(video.width, self._policy.max_gif_width)
        height = max(2, round(video.height * width / video.width))
        if height % 2:
            height += 1

        output = self._transcode(
            source,
            destination,
            (
                "-map",
                "0:v:0",
                "-an",
                "-vf",
                f"scale={width}:{height}:flags=lanczos,fps=10",
                "-loop",
                "0",
                "-f",
                "gif",
            ),
        )
        try:
            info = self._probe(output, max_bytes=self._policy.max_output_bytes)
            if "gif" not in info.container_formats or not info.video_streams:
                raise MediaEngineError(
                    MediaErrorCode.OUTPUT_VALIDATION_FAILED,
                    "GIF output validation failed",
                )
            return info
        except MediaEngineError:
            self._remove_output(output)
            raise

    def compress_video(
        self,
        source: Path,
        destination: Path,
        preset: VideoCompressionPreset = VideoCompressionPreset.BALANCED,
    ) -> MediaInfo:
        source_info = self.inspect(source)
        self._require_video(source_info)
        qscale = {
            VideoCompressionPreset.HIGH_QUALITY: "2",
            VideoCompressionPreset.BALANCED: "5",
            VideoCompressionPreset.SMALL: "8",
        }[preset]
        output = self._transcode(
            source,
            destination,
            (
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "mpeg4",
                "-q:v",
                qscale,
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-f",
                "mp4",
            ),
        )
        try:
            info = self._probe(output, max_bytes=self._policy.max_output_bytes)
            self._validate_mp4_video(info, allow_audio=True)
            return info
        except MediaEngineError:
            self._remove_output(output)
            raise

    def _transcode(
        self,
        source: Path,
        destination: Path,
        media_args: tuple[str, ...],
    ) -> Path:
        if source.resolve() == destination.resolve():
            raise MediaEngineError(
                MediaErrorCode.INVALID_OPERATION,
                "input and output paths must be different",
            )

        partial = _partial_path(destination)
        destination.unlink(missing_ok=True)
        partial.unlink(missing_ok=True)
        partial.parent.mkdir(parents=True, exist_ok=True)

        argv = (
            str(self._toolchain.ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-protocol_whitelist",
            "file",
            "-i",
            str(source.resolve()),
            "-map_metadata",
            "-1",
            "-map_chapters",
            "-1",
            *media_args,
            str(partial.resolve()),
        )
        try:
            result = self._runner.run(
                argv,
                timeout_seconds=self._policy.conversion_timeout_seconds,
            )
            if result.returncode != 0:
                raise MediaEngineError(
                    MediaErrorCode.PROCESSING_FAILED,
                    "FFmpeg conversion failed",
                )
            self._check_output_size(partial)
            partial.replace(destination)
            return destination
        except MediaEngineError:
            partial.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise
        except Exception as exc:
            partial.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            raise MediaEngineError(
                MediaErrorCode.PROCESSING_FAILED,
                "media conversion failed",
            ) from exc

    def _probe(self, source: Path, *, max_bytes: int) -> MediaInfo:
        try:
            byte_size = source.stat().st_size
        except OSError as exc:
            raise MediaEngineError(
                MediaErrorCode.CORRUPT_INPUT,
                "media file is not readable",
            ) from exc
        if byte_size > max_bytes:
            raise MediaEngineError(
                MediaErrorCode.INPUT_TOO_LARGE,
                "media file exceeds configured byte limit",
            )

        argv = (
            str(self._toolchain.ffprobe),
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
            "-show_entries",
            (
                "format=format_name,duration:"
                "stream=index,codec_type,codec_name,width,height,duration,sample_rate,channels"
            ),
            "-of",
            "json=compact=1:string_validation=fail",
            "-i",
            str(source.resolve()),
        )
        result = self._runner.run(argv, timeout_seconds=self._policy.probe_timeout_seconds)
        if result.returncode != 0:
            raise MediaEngineError(
                MediaErrorCode.CORRUPT_INPUT,
                "ffprobe rejected the media file",
            )

        try:
            payload = json.loads(result.stdout)
            info = self._parse_probe_payload(payload, byte_size=byte_size)
        except MediaEngineError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise MediaEngineError(
                MediaErrorCode.CORRUPT_INPUT,
                "ffprobe returned invalid metadata",
            ) from exc
        return info

    def _parse_probe_payload(self, payload: dict[str, Any], *, byte_size: int) -> MediaInfo:
        format_data = payload.get("format")
        streams_data = payload.get("streams")
        if not isinstance(format_data, dict) or not isinstance(streams_data, list):
            raise MediaEngineError(
                MediaErrorCode.CORRUPT_INPUT,
                "media metadata is incomplete",
            )
        if len(streams_data) > self._policy.max_streams:
            raise MediaEngineError(
                MediaErrorCode.UNSUPPORTED_STREAMS,
                "media contains too many streams",
            )

        format_name = format_data.get("format_name")
        if not isinstance(format_name, str) or not format_name:
            raise MediaEngineError(
                MediaErrorCode.UNSUPPORTED_CONTAINER,
                "media container could not be identified",
            )
        containers = tuple(part.strip() for part in format_name.split(",") if part.strip())
        if not containers or any(item not in _ALLOWED_CONTAINERS for item in containers):
            raise MediaEngineError(
                MediaErrorCode.UNSUPPORTED_CONTAINER,
                "media container is outside the MVP allowlist",
            )

        audio_streams: list[AudioStreamInfo] = []
        video_streams: list[VideoStreamInfo] = []
        duration_candidates: list[float] = []

        format_duration = _optional_float(format_data.get("duration"))
        if format_duration is not None:
            duration_candidates.append(format_duration)

        for raw_stream in streams_data:
            if not isinstance(raw_stream, dict):
                raise MediaEngineError(
                    MediaErrorCode.CORRUPT_INPUT,
                    "media stream metadata is invalid",
                )
            stream_duration = _optional_float(raw_stream.get("duration"))
            if stream_duration is not None:
                duration_candidates.append(stream_duration)

            codec_type = raw_stream.get("codec_type")
            codec_name = raw_stream.get("codec_name")
            if not isinstance(codec_name, str) or not codec_name:
                continue

            if codec_type == "audio":
                if codec_name not in _ALLOWED_AUDIO_CODECS:
                    raise MediaEngineError(
                        MediaErrorCode.UNSUPPORTED_CODEC,
                        "audio codec is outside the MVP allowlist",
                    )
                audio_streams.append(
                    AudioStreamInfo(
                        codec_name=codec_name,
                        sample_rate=_optional_int(raw_stream.get("sample_rate")),
                        channels=_optional_int(raw_stream.get("channels")),
                    )
                )
            elif codec_type == "video":
                if codec_name not in _ALLOWED_VIDEO_CODECS:
                    raise MediaEngineError(
                        MediaErrorCode.UNSUPPORTED_CODEC,
                        "video codec is outside the MVP allowlist",
                    )
                width = _required_positive_int(raw_stream.get("width"))
                height = _required_positive_int(raw_stream.get("height"))
                if (
                    width > self._policy.max_video_width
                    or height > self._policy.max_video_height
                    or width * height > self._policy.max_video_pixels
                ):
                    raise MediaEngineError(
                        MediaErrorCode.RESOLUTION_LIMIT_EXCEEDED,
                        "video resolution exceeds configured limits",
                    )
                video_streams.append(VideoStreamInfo(codec_name, width, height))

        if not audio_streams and not video_streams:
            raise MediaEngineError(
                MediaErrorCode.UNSUPPORTED_STREAMS,
                "media has no supported audio or video streams",
            )

        duration = max(duration_candidates, default=0.0)
        if not math.isfinite(duration) or duration <= 0:
            raise MediaEngineError(
                MediaErrorCode.CORRUPT_INPUT,
                "media duration is missing or invalid",
            )
        if duration > self._policy.max_duration_seconds:
            raise MediaEngineError(
                MediaErrorCode.DURATION_LIMIT_EXCEEDED,
                "media duration exceeds configured limit",
            )

        return MediaInfo(
            container_formats=containers,
            duration_seconds=duration,
            byte_size=byte_size,
            audio_streams=tuple(audio_streams),
            video_streams=tuple(video_streams),
        )

    def _require_audio(self, info: MediaInfo) -> AudioStreamInfo:
        if not info.audio_streams:
            raise MediaEngineError(
                MediaErrorCode.UNSUPPORTED_STREAMS,
                "operation requires an audio stream",
            )
        return info.audio_streams[0]

    def _require_video(self, info: MediaInfo) -> VideoStreamInfo:
        if not info.video_streams:
            raise MediaEngineError(
                MediaErrorCode.UNSUPPORTED_STREAMS,
                "operation requires a video stream",
            )
        return info.video_streams[0]

    def _validate_audio_output(
        self,
        info: MediaInfo,
        expected_container: str,
        expected_codec: str,
    ) -> None:
        if (
            expected_container not in info.container_formats
            or len(info.audio_streams) != 1
            or info.audio_streams[0].codec_name != expected_codec
            or info.video_streams
        ):
            raise MediaEngineError(
                MediaErrorCode.OUTPUT_VALIDATION_FAILED,
                "audio output does not match the requested contract",
            )

    def _validate_mp4_video(self, info: MediaInfo, *, allow_audio: bool) -> None:
        if "mp4" not in info.container_formats or not info.video_streams:
            raise MediaEngineError(
                MediaErrorCode.OUTPUT_VALIDATION_FAILED,
                "video output is not a valid MP4",
            )
        if info.video_streams[0].codec_name != "mpeg4":
            raise MediaEngineError(
                MediaErrorCode.OUTPUT_VALIDATION_FAILED,
                "video output codec does not match the requested contract",
            )
        if not allow_audio and info.audio_streams:
            raise MediaEngineError(
                MediaErrorCode.OUTPUT_VALIDATION_FAILED,
                "muted video output still contains audio",
            )
        if allow_audio and any(stream.codec_name != "aac" for stream in info.audio_streams):
            raise MediaEngineError(
                MediaErrorCode.OUTPUT_VALIDATION_FAILED,
                "compressed video audio codec is unexpected",
            )

    def _check_output_size(self, output: Path) -> None:
        try:
            size = output.stat().st_size
        except OSError as exc:
            raise MediaEngineError(
                MediaErrorCode.OUTPUT_VALIDATION_FAILED,
                "media output is not readable",
            ) from exc
        if size > self._policy.max_output_bytes:
            raise MediaEngineError(
                MediaErrorCode.OUTPUT_TOO_LARGE,
                "media output exceeds configured byte limit",
            )

    @staticmethod
    def _remove_output(path: Path) -> None:
        path.unlink(missing_ok=True)


def _partial_path(destination: Path) -> Path:
    suffix = destination.suffix
    return destination.with_name(f".{destination.stem}.partial{suffix}")


def _optional_float(value: object) -> float | None:
    if value is None or value == "N/A":
        return None
    parsed = float(value)
    if not math.isfinite(parsed) or parsed < 0:
        return None
    return parsed


def _optional_int(value: object) -> int | None:
    if value is None or value == "N/A":
        return None
    parsed = int(value)
    return parsed if parsed >= 0 else None


def _required_positive_int(value: object) -> int:
    parsed = _optional_int(value)
    if parsed is None or parsed <= 0:
        raise MediaEngineError(
            MediaErrorCode.CORRUPT_INPUT,
            "video dimensions are missing or invalid",
        )
    return parsed
