"""Script generation: Claude-written scripts, or offline conversion of raw text."""

from __future__ import annotations

import json
import os
import re

from .models import Scene, Script, VISUAL_FOOTAGE, VISUAL_PHOTO

DEFAULT_MODEL = os.environ.get("VIDEOPIPELINE_MODEL", "claude-sonnet-5")
WORDS_PER_MINUTE = 145  # comfortable narration pace

STOPWORDS = frozenset(
    "a an and are as at be but by for from has have if in into is it its of on or "
    "so than that the their then there these they this to was were what when where "
    "which while who will with you your we our i he she his her not no yes can".split()
)

_PROMPT = """Write a narration script for a short {style} video about: {topic}

Target length: about {word_target} words total (~{duration} seconds when read aloud).

Break it into 4-10 scenes. Each scene is one narrated beat paired with one visual.
For each scene choose:
- "narration": 1-3 spoken sentences (plain text, no stage directions)
- "keywords": 2-4 short stock-search terms describing the visual
- "visual": "footage" for stock video, or "photo" for a still image / archival
  photograph (prefer "photo" for historical or specific-subject moments)

Respond with ONLY a JSON object, no other text:
{{"title": "...", "description": "one-sentence video description", "scenes": [{{"narration": "...", "keywords": ["..."], "visual": "footage"}}]}}"""


def generate_script(topic: str, duration: int = 60, style: str = "documentary", model: str = DEFAULT_MODEL) -> Script:
    """Generate a scene-by-scene script with Claude. Requires ANTHROPIC_API_KEY."""
    try:
        import anthropic
    except ImportError as e:
        raise RuntimeError("anthropic package not installed — run: pip install -r requirements.txt") from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Either export it to generate scripts with Claude, "
            "or supply your own script with --script script.json / --text narration.txt"
        )

    client = anthropic.Anthropic()
    word_target = max(60, round(duration * WORDS_PER_MINUTE / 60))
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        messages=[{"role": "user", "content": _PROMPT.format(
            topic=topic, style=style, duration=duration, word_target=word_target)}],
    )
    return Script.from_dict(_parse_json_reply(response.content[0].text))


def _parse_json_reply(text: str) -> dict:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise ValueError(f"model reply contained no JSON object:\n{text[:400]}")
        text = text[start:end + 1]
    return json.loads(text)


def script_from_text(text: str, title: str = "Untitled") -> Script:
    """Offline fallback: turn prewritten narration into scenes (one per paragraph,
    splitting long paragraphs), with naive keyword extraction for asset search."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        raise ValueError("input text is empty")

    scenes: list[Scene] = []
    for para in paragraphs:
        para = " ".join(para.split())
        for chunk in _split_long(para, max_words=60):
            scenes.append(Scene(narration=chunk, keywords=_keywords(chunk), visual=VISUAL_FOOTAGE))
    # Alternate in some photo scenes so Ken Burns gets exercised on mixed material.
    for i in range(1, len(scenes), 3):
        scenes[i].visual = VISUAL_PHOTO
    return Script(title=title, scenes=scenes)


def _split_long(paragraph: str, max_words: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    chunks, current = [], ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate.split()) > max_words:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _keywords(sentence: str, count: int = 3) -> list[str]:
    tokens = re.findall(r"[A-Za-z][A-Za-z'-]+", sentence.lower())
    candidates = [t for t in tokens if t not in STOPWORDS and len(t) > 3]
    seen: list[str] = []
    for t in sorted(candidates, key=len, reverse=True):
        if t not in seen:
            seen.append(t)
        if len(seen) == count:
            break
    return seen or tokens[:count]
