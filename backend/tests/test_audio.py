import shutil
import struct
import subprocess

import pytest

from app.services.audio import AudioConversionError, to_wav_16k_mono

ffmpeg_required = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
)


def make_webm_opus(duration_sec: float = 0.5) -> bytes:
    """ffmpeg でテスト用の WebM/Opus（440Hzサイン波）を生成する。"""
    proc = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration_sec}",
            "-c:a", "libopus", "-b:a", "32k", "-f", "webm", "pipe:1",
        ],
        capture_output=True,
        check=True,
    )
    return proc.stdout


def parse_wav_fmt(wav: bytes) -> tuple[int, int, int]:
    """fmt チャンクから (channels, sample_rate, bits_per_sample) を返す。

    ffmpeg の pipe 出力は RIFF サイズが確定しないため、wave モジュールではなく
    ヘッダを直接読む。
    """
    assert wav[0:4] == b"RIFF" and wav[8:12] == b"WAVE"
    pos = 12
    while pos + 8 <= len(wav):
        chunk_id = wav[pos : pos + 4]
        (chunk_size,) = struct.unpack("<I", wav[pos + 4 : pos + 8])
        if chunk_id == b"fmt ":
            channels, sample_rate = struct.unpack("<HI", wav[pos + 10 : pos + 16])
            (bits,) = struct.unpack("<H", wav[pos + 22 : pos + 24])
            return channels, sample_rate, bits
        pos += 8 + chunk_size + (chunk_size % 2)
    raise AssertionError("fmt chunk not found")


@ffmpeg_required
def test_webm_opus_converts_to_wav_16k_mono() -> None:
    wav = to_wav_16k_mono(make_webm_opus())
    channels, sample_rate, bits = parse_wav_fmt(wav)
    assert channels == 1
    assert sample_rate == 16000
    assert bits == 16
    # 0.5秒 × 16kHz × 2byte ≒ 16000byte のデータが含まれるはず。
    assert len(wav) > 8000


@ffmpeg_required
def test_garbage_bytes_raise_conversion_error() -> None:
    with pytest.raises(AudioConversionError):
        to_wav_16k_mono(b"this is not audio at all")


@ffmpeg_required
def test_empty_bytes_raise_conversion_error() -> None:
    with pytest.raises(AudioConversionError):
        to_wav_16k_mono(b"")
