"""音声変換サービス。

MediaRecorder の既定出力は WebM/Opus で、Azure Speech は受け付けない。
サーバ側で ffmpeg により WAV(16kHz mono, PCM s16le) へ変換してから渡す（CLAUDE.md 地雷）。
"""

import subprocess

FFMPEG_TIMEOUT_SEC = 30


class AudioConversionError(Exception):
    """アップロード音声を WAV に変換できなかった（壊れたファイル・非対応形式など）。"""


def build_ffmpeg_command() -> list[str]:
    # 入力はコンテナ自動判定（WebM/Opus 以外に OGG/M4A 等が来ても許容する）。
    return [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-ac", "1",
        "-ar", "16000",
        "-acodec", "pcm_s16le",
        "-f", "wav",
        "pipe:1",
    ]


def to_wav_16k_mono(data: bytes) -> bytes:
    """音声バイト列を WAV 16kHz mono に変換して返す。失敗時は AudioConversionError。"""
    try:
        proc = subprocess.run(
            build_ffmpeg_command(),
            input=data,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT_SEC,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AudioConversionError("ffmpeg が見つかりません。インストールしてください。") from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioConversionError("音声変換がタイムアウトしました。") from exc
    if proc.returncode != 0 or not proc.stdout:
        detail = proc.stderr.decode(errors="replace").strip()[:300]
        raise AudioConversionError(detail or "ffmpeg での変換に失敗しました。")
    return proc.stdout
