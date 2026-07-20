"""Build an SRT caption track from per-scene word timings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .tts import Word

MAX_CUE_CHARS = 42
MAX_CUE_SECONDS = 5.0
WORD_GAP_BREAK = 0.7  # a pause this long starts a new cue


@dataclass
class Cue:
    start: float
    end: float
    text: str


def build_cues(scene_words: list[tuple[float, list[Word]]]) -> list[Cue]:
    """Group words into readable cues.

    `scene_words` pairs each scene's start offset on the final timeline with
    that scene's word timings (which are relative to the scene's own audio).
    """
    cues: list[Cue] = []
    for offset, words in scene_words:
        current: list[Word] = []

        def flush() -> None:
            if current:
                cues.append(Cue(
                    start=offset + current[0].start,
                    end=offset + current[-1].end,
                    text=" ".join(w.text for w in current),
                ))
                current.clear()

        for word in words:
            if current:
                length = len(" ".join(w.text for w in current)) + 1 + len(word.text)
                span = word.end - current[0].start
                gap = word.start - current[-1].end
                if length > MAX_CUE_CHARS or span > MAX_CUE_SECONDS or gap > WORD_GAP_BREAK:
                    flush()
            current.append(word)
            if word.text.rstrip('"”’)').endswith((".", "!", "?")) and len(" ".join(w.text for w in current)) >= 12:
                flush()
        flush()

    # Linger slightly for readability, without overlapping the next cue.
    for i, cue in enumerate(cues):
        limit = cues[i + 1].start if i + 1 < len(cues) else cue.end + 0.5
        cue.end = min(cue.end + 0.4, limit)
    return cues


def write_srt(cues: list[Cue], path: Path) -> None:
    lines = []
    for i, cue in enumerate(cues, start=1):
        lines.append(str(i))
        lines.append(f"{_timestamp(cue.start)} --> {_timestamp(cue.end)}")
        lines.append(cue.text)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _timestamp(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
