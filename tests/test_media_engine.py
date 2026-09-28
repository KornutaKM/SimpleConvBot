from __future__ import annotations

import math
import struct
import subprocess
import sys
import wave
from pathlib import Path

import pytest

from simpleconvbot.media_engine import (
    AudioOutputFormat,
    MediaEngine,
    MediaEngineError,
    MediaErrorCode,
    MediaPolicy,
    MediaToolchain,
    VideoCompressionPreset,
    _BoundedProcessRunner,
)


def _tool(name: str) -> str:
    toolchain = MediaToolchain.discover()
    if name == "ffmpeg":
        return str(toolchain.ffmpeg)
    if name == "ffprobe":
        return str(toolchain.ffprobe)
    raise AssertionError(f"unknown media test tool: {name}")


def _make_wav(path: Path, duration: float = 0.25, frequency: float = 440.0) -> None:
    sample_rate = 8000
    frame_count = int(sample_rate * duration)
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        for index in range(frame_count):
            value = int(12000 * math.sin(2 * math.pi * frequency * index / sample_rate))
            output.writeframesraw(struct.pack("<h", value))


def _make_video(path: Path, *, size: str = "160x120", duration: float = 0.5) -> None:
    subprocess.run(
        [
            _tool("ffmpeg"),
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=blue:s={size}:r=10:d={duration}",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-shortest",
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-c:a",
            "aac",
            str(path),
        ],
        check=True,
        stdin=subprocess.DEVNULL,
    )


def test_media_toolchain_is_available() -> None:
    toolchain = MediaToolchain.discover()

    assert toolchain.ffmpeg.is_absolute()
    assert toolchain.ffprobe.is_absolute()


def test_probe_reads_bounded_audio_metadata(tmp_path: Path) -> None:
    source = tmp_path / "tone.bin"
    _make_wav(source)

    info = MediaEngine().inspect(source)

    assert "wav" in info.container_formats
    assert info.audio_streams[0].codec_name == "pcm_s16le"
    assert not info.video_streams
    assert 0 < info.duration_seconds < 1


@pytest.mark.parametrize(
    ("target", "suffix", "container", "codec"),
    [
        (AudioOutputFormat.MP3, ".mp3", "mp3", "mp3"),
        (AudioOutputFormat.M4A, ".m4a", "m4a", "aac"),
        (AudioOutputFormat.WAV, ".wav", "wav", "pcm_s16le"),
    ],
)
def test_audio_conversions_are_probed_after_encoding(
    tmp_path: Path,
    target: AudioOutputFormat,
    suffix: str,
    container: str,
    codec: str,
) -> None:
    source = tmp_path / "tone.wav"
    destination = tmp_path / f"out{suffix}"
    _make_wav(source)

    info = MediaEngine().convert_audio(source, destination, target)

    assert container in info.container_formats
    assert info.audio_streams[0].codec_name == codec
    assert not info.video_streams
    assert destination.exists()
    assert not tuple(tmp_path.glob("*.partial.*"))


def test_video_to_mp3_requires_video_and_validates_output(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "audio.mp3"
    _make_video(source)

    info = MediaEngine().video_to_mp3(source, destination)

    assert "mp3" in info.container_formats
    assert info.audio_streams[0].codec_name == "mp3"
    assert not info.video_streams


def test_mute_video_removes_audio(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "muted.mp4"
    _make_video(source)

    info = MediaEngine().mute_video(source, destination)

    assert "mp4" in info.container_formats
    assert info.video_streams[0].codec_name == "mpeg4"
    assert not info.audio_streams


def test_video_to_gif_is_bounded_and_validated(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / "preview.gif"
    _make_video(source, size="320x180")

    info = MediaEngine().video_to_gif(source, destination)

    assert "gif" in info.container_formats
    assert info.video_streams[0].codec_name == "gif"
    assert info.video_streams[0].width <= 640
    assert not info.audio_streams


@pytest.mark.parametrize(
    "preset",
    [
        VideoCompressionPreset.HIGH_QUALITY,
        VideoCompressionPreset.BALANCED,
        VideoCompressionPreset.SMALL,
    ],
)
def test_video_compression_presets_have_fixed_validated_outputs(
    tmp_path: Path,
    preset: VideoCompressionPreset,
) -> None:
    source = tmp_path / "source.mp4"
    destination = tmp_path / f"{preset.value}.mp4"
    _make_video(source)

    info = MediaEngine().compress_video(source, destination, preset)

    assert "mp4" in info.container_formats
    assert info.video_streams[0].codec_name == "mpeg4"
    assert all(stream.codec_name == "aac" for stream in info.audio_streams)


def test_corrupt_input_fails_predictably(tmp_path: Path) -> None:
    source = tmp_path / "broken.mp4"
    source.write_bytes(b"not a media container")

    with pytest.raises(MediaEngineError) as captured:
        MediaEngine().inspect(source)

    assert captured.value.code is MediaErrorCode.CORRUPT_INPUT


def test_unsupported_container_fails_predictably(tmp_path: Path) -> None:
    source = tmp_path / "still.png"
    from PIL import Image

    Image.new("RGB", (10, 10), "red").save(source, format="PNG")

    with pytest.raises(MediaEngineError) as captured:
        MediaEngine().inspect(source)

    assert captured.value.code is MediaErrorCode.UNSUPPORTED_CONTAINER


def test_duration_limit_is_enforced(tmp_path: Path) -> None:
    source = tmp_path / "tone.wav"
    _make_wav(source, duration=0.25)
    engine = MediaEngine(MediaPolicy(max_duration_seconds=0.1))

    with pytest.raises(MediaEngineError) as captured:
        engine.inspect(source)

    assert captured.value.code is MediaErrorCode.DURATION_LIMIT_EXCEEDED


def test_resolution_limit_is_enforced(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _make_video(source, size="160x120")
    engine = MediaEngine(
        MediaPolicy(
            max_video_width=100,
            max_video_height=100,
            max_video_pixels=10_000,
        )
    )

    with pytest.raises(MediaEngineError) as captured:
        engine.inspect(source)

    assert captured.value.code is MediaErrorCode.RESOLUTION_LIMIT_EXCEEDED


def test_gif_duration_limit_rejects_long_video(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    _make_video(source, duration=0.5)
    engine = MediaEngine(MediaPolicy(max_gif_duration_seconds=0.1))

    with pytest.raises(MediaEngineError) as captured:
        engine.video_to_gif(source, tmp_path / "preview.gif")

    assert captured.value.code is MediaErrorCode.DURATION_LIMIT_EXCEEDED


class RejectingOutputMediaEngine(MediaEngine):
    def _validate_audio_output(
        self,
        info: object,
        expected_container: str,
        expected_codec: str,
    ) -> None:
        del info, expected_container, expected_codec
        raise MediaEngineError(
            MediaErrorCode.OUTPUT_VALIDATION_FAILED,
            "synthetic output contract rejection",
        )


def test_post_validation_failure_removes_final_output(tmp_path: Path) -> None:
    source = tmp_path / "tone.wav"
    destination = tmp_path / "out.mp3"
    _make_wav(source)

    with pytest.raises(MediaEngineError) as captured:
        RejectingOutputMediaEngine().convert_audio(
            source,
            destination,
            AudioOutputFormat.MP3,
        )

    assert captured.value.code is MediaErrorCode.OUTPUT_VALIDATION_FAILED
    assert not destination.exists()


def test_output_size_limit_cleans_partial_and_final(tmp_path: Path) -> None:
    source = tmp_path / "tone.wav"
    destination = tmp_path / "out.mp3"
    _make_wav(source)
    engine = MediaEngine(MediaPolicy(max_output_bytes=1))

    with pytest.raises(MediaEngineError) as captured:
        engine.convert_audio(source, destination, AudioOutputFormat.MP3)

    assert captured.value.code is MediaErrorCode.OUTPUT_TOO_LARGE
    assert not destination.exists()
    assert not (tmp_path / ".out.partial.mp3").exists()


def test_hard_timeout_kills_and_waits_for_process() -> None:
    runner = _BoundedProcessRunner(max_output_bytes=1024)

    with pytest.raises(MediaEngineError) as captured:
        runner.run(
            (sys.executable, "-c", "import time; time.sleep(2)"),
            timeout_seconds=0.05,
        )

    assert captured.value.code is MediaErrorCode.TIMEOUT
