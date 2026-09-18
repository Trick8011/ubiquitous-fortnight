"""Free text-to-speech with word-level timing.

Engines:
- ``edge``   — Microsoft Edge neural voices via the edge-tts package. Free, no API
               key, high quality, and streams WordBoundary events we use for captions.
               Requires network access.
- ``espeak`` — espeak-ng CLI. Fully offline, robotic but dependable. Word timings
               are estimated proportionally from the measured audio duration.
- ``auto``   — try edge, fall back to espeak with a warning.
"""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .ffutil import probe_duration, to_wav

DEFAULT_VOICE = "en-US-GuyNeural"
ESPEAK_DEFAULT_VOICE = "en-us"


@dataclass
class Word:
    text: str
    start: float  # seconds from start of this scene's audio
    end: float


@dataclass
class SceneAudio:
    path: Path  # 48 kHz stereo WAV
    duration: float
    words: list[Word] = field(default_factory=list)


class TTSError(RuntimeError):
    pass


def synthesize(text: str, out_path: Path, engine: str = "auto", voice: str = DEFAULT_VOICE) -> SceneAudio:
    """Synthesize `text` to a WAV at `out_path` and return timing metadata."""
    text = " ".join(text.split())
    if engine == "edge":
        return _synthesize_edge(text, out_path, voice)
    if engine == "espeak":
        return _synthesize_espeak(text, out_path)
    if engine == "auto":
        try:
            return _synthesize_edge(text, out_path, voice)
        except Exception as e:  # network/service failures — fall back offline
            print(f"  warning: edge-tts unavailable ({type(e).__name__}: {e}); falling back to espeak-ng", file=sys.stderr)
            return _synthesize_espeak(text, out_path)
    raise TTSError(f"unknown TTS engine {engine!r} (expected edge, espeak, or auto)")


def _synthesize_edge(text: str, out_path: Path, voice: str) -> SceneAudio:
    try:
        import edge_tts
    except ImportError as e:
        raise TTSError("edge-tts is not installed — run: pip install edge-tts") from e

    mp3_path = out_path.with_suffix(".mp3")
    words: list[Word] = []

    async def _run() -> None:
        communicate = edge_tts.Communicate(text, voice)
        with open(mp3_path, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / 1e7  # 100-ns ticks → seconds
                    words.append(Word(text=chunk["text"], start=start, end=start + chunk["duration"] / 1e7))

    asyncio.run(_run())
    if not mp3_path.exists() or mp3_path.stat().st_size == 0:
        raise TTSError("edge-tts produced no audio")

    to_wav(mp3_path, out_path)
    mp3_path.unlink()
    return SceneAudio(path=out_path, duration=probe_duration(out_path), words=words)


def _synthesize_espeak(text: str, out_path: Path, voice: str = ESPEAK_DEFAULT_VOICE, wpm: int = 160) -> SceneAudio:
    if shutil.which("espeak-ng") is None:
        raise TTSError("espeak-ng not found on PATH — install it (e.g. `apt install espeak-ng`) or use --tts edge")

    raw_path = out_path.with_suffix(".espeak.wav")
    proc = subprocess.run(
        ["espeak-ng", "-v", voice, "-s", str(wpm), "-w", str(raw_path), text],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if proc.returncode != 0:
        raise TTSError(f"espeak-ng failed: {proc.stderr.strip()[-300:]}")

    to_wav(raw_path, out_path)
    raw_path.unlink()
    duration = probe_duration(out_path)
    return SceneAudio(path=out_path, duration=duration, words=_estimate_words(text, duration))


def _estimate_words(text: str, duration: float) -> list[Word]:
    """Spread word timings across the audio proportionally to word length."""
    tokens = text.split()
    if not tokens:
        return []
    weights = [len(t) + 2 for t in tokens]  # +2 approximates inter-word pause
    total = sum(weights)
    words, t = [], 0.0
    for token, w in zip(tokens, weights):
        span = duration * w / total
        words.append(Word(text=token, start=t, end=t + span))
        t += span
    return words


def list_edge_voices() -> list[str]:
    """Return available edge-tts voice short names."""
    try:
        import edge_tts
    except ImportError as e:
        raise TTSError("edge-tts is not installed — run: pip install edge-tts") from e
    voices = asyncio.run(edge_tts.list_voices())
    return sorted(v["ShortName"] for v in voices)
