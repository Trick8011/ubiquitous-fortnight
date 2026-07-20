"""Thin helpers around the ffmpeg/ffprobe CLIs."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise FFmpegError(f"{tool} not found on PATH — install FFmpeg (e.g. `apt install ffmpeg`)")


def run(args: list[str], cwd: Path | None = None) -> None:
    """Run an ffmpeg command, raising with the tail of stderr on failure."""
    proc = subprocess.run(
        [args[0], "-hide_banner", "-y", *args[1:]],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-12:])
        raise FFmpegError(f"command failed: {' '.join(args)}\n{tail}")


def probe_duration(path: str | Path) -> float:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0 or not proc.stdout.strip():
        raise FFmpegError(f"ffprobe failed for {path}: {proc.stderr.strip()[-300:]}")
    return float(proc.stdout.strip())


def to_wav(src: str | Path, dst: str | Path, sample_rate: int = 48000) -> None:
    """Normalize any audio file to stereo PCM WAV so clips concat cleanly."""
    run(["ffmpeg", "-i", str(src), "-ar", str(sample_rate), "-ac", "2", "-c:a", "pcm_s16le", str(dst)])
