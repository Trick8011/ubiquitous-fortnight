"""Data model for video scripts."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

VISUAL_FOOTAGE = "footage"  # stock video clip
VISUAL_PHOTO = "photo"      # still image, animated with a Ken Burns move


@dataclass
class Scene:
    """One narrated beat of the video, paired with a visual."""

    narration: str
    keywords: list[str] = field(default_factory=list)
    visual: str = VISUAL_FOOTAGE
    asset: str | None = None  # optional local path or URL overriding asset search

    def __post_init__(self) -> None:
        if self.visual not in (VISUAL_FOOTAGE, VISUAL_PHOTO):
            raise ValueError(f"scene visual must be '{VISUAL_FOOTAGE}' or '{VISUAL_PHOTO}', got {self.visual!r}")
        if not self.narration.strip():
            raise ValueError("scene narration must not be empty")


@dataclass
class Script:
    title: str
    description: str = ""
    scenes: list[Scene] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "Script":
        scenes = [
            Scene(
                narration=s["narration"],
                keywords=list(s.get("keywords", [])),
                visual=s.get("visual", VISUAL_FOOTAGE),
                asset=s.get("asset"),
            )
            for s in data.get("scenes", [])
        ]
        if not scenes:
            raise ValueError("script has no scenes")
        return cls(title=data.get("title", "Untitled"), description=data.get("description", ""), scenes=scenes)

    @classmethod
    def load(cls, path: str | Path) -> "Script":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False) + "\n")

    @property
    def word_count(self) -> int:
        return sum(len(s.narration.split()) for s in self.scenes)
