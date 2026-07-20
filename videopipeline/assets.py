"""Resolve each scene to a visual asset.

Resolution order per scene:
1. An explicit `asset` on the scene (local path or URL).
2. A file in --assets-dir whose name matches one of the scene's keywords.
3. Pexels stock search (videos and photos) if PEXELS_API_KEY is set — free key
   from https://www.pexels.com/api/.
4. Openverse (keyless, openly-licensed images — good for archival photos).
5. A generated gradient placeholder card, so the pipeline always completes.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from .ffutil import run
from .models import Scene, VISUAL_FOOTAGE

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}
USER_AGENT = "videopipeline/0.1 (https://github.com/trick8011/ubiquitous-fortnight)"

PLACEHOLDER_PALETTES = [
    ("0x16324f", "0x3c6e71"),
    ("0x3a2d4d", "0x845ec2"),
    ("0x1f3b2c", "0x5c8d76"),
    ("0x4d2d2d", "0xb0603c"),
    ("0x2d3a4d", "0x6c8ebf"),
]


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def resolve_scene_asset(scene: Scene, index: int, cache_dir: Path, assets_dir: Path | None = None,
                        size: tuple[int, int] = (1920, 1080)) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    query = " ".join(scene.keywords) or scene.narration.split(".")[0]

    if scene.asset:
        if scene.asset.startswith(("http://", "https://")):
            path = _download(scene.asset, cache_dir)
            if path:
                return path
            print(f"  warning: could not download {scene.asset}; trying other sources", file=sys.stderr)
        else:
            path = Path(scene.asset).expanduser()
            if path.exists():
                return path
            print(f"  warning: asset {scene.asset} not found; trying other sources", file=sys.stderr)

    if assets_dir:
        path = _match_local(scene, assets_dir)
        if path:
            return path

    if os.environ.get("PEXELS_API_KEY"):
        path = _search_pexels(query, scene.visual, cache_dir)
        if path:
            return path

    path = _search_openverse(query, cache_dir)
    if path:
        return path

    print(f"  note: no asset found for scene {index + 1} ({query!r}); using generated placeholder", file=sys.stderr)
    return _placeholder(query, index, cache_dir, size)


def _match_local(scene: Scene, assets_dir: Path) -> Path | None:
    files = [p for p in sorted(assets_dir.rglob("*")) if p.suffix.lower() in VIDEO_EXTS | IMAGE_EXTS]
    prefer_video = scene.visual == VISUAL_FOOTAGE
    matches = [
        p for p in files
        if any(k.lower().replace(" ", "") in p.stem.lower().replace(" ", "").replace("_", "").replace("-", "")
               for k in scene.keywords)
    ]
    if not matches:
        return None
    matches.sort(key=lambda p: is_video(p) != prefer_video)  # preferred media type first
    return matches[0]


def _http_json(url: str, headers: dict[str, str] | None = None) -> dict | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"  warning: request to {urllib.parse.urlparse(url).netloc} failed: {e}", file=sys.stderr)
        return None


def _download(url: str, cache_dir: Path, suffix: str | None = None) -> Path | None:
    if suffix is None:
        suffix = Path(urllib.parse.urlparse(url).path).suffix or ".bin"
    dest = cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:16] + suffix)
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=120) as resp, open(dest, "wb") as f:
            while chunk := resp.read(1 << 16):
                f.write(chunk)
        return dest
    except Exception as e:
        print(f"  warning: download failed ({e})", file=sys.stderr)
        dest.unlink(missing_ok=True)
        return None


def _search_pexels(query: str, visual: str, cache_dir: Path) -> Path | None:
    headers = {"Authorization": os.environ["PEXELS_API_KEY"]}
    encoded = urllib.parse.quote(query)

    if visual == VISUAL_FOOTAGE:
        data = _http_json(f"https://api.pexels.com/videos/search?query={encoded}&per_page=3&orientation=landscape", headers)
        for video in (data or {}).get("videos", []):
            files = [f for f in video.get("video_files", []) if f.get("link") and f.get("width")]
            if not files:
                continue
            best = min(files, key=lambda f: abs(f["width"] - 1920))
            path = _download(best["link"], cache_dir, suffix=".mp4")
            if path:
                return path
        # fall through to a photo if no usable footage

    data = _http_json(f"https://api.pexels.com/v1/search?query={encoded}&per_page=3&orientation=landscape", headers)
    for photo in (data or {}).get("photos", []):
        url = photo.get("src", {}).get("large2x") or photo.get("src", {}).get("original")
        if url:
            path = _download(url, cache_dir, suffix=".jpg")
            if path:
                return path
    return None


def _search_openverse(query: str, cache_dir: Path) -> Path | None:
    encoded = urllib.parse.quote(query)
    data = _http_json(
        f"https://api.openverse.org/v1/images/?q={encoded}&page_size=3&license_type=commercial&aspect_ratio=wide"
    )
    for result in (data or {}).get("results", []):
        url = result.get("url")
        if url:
            path = _download(url, cache_dir)
            if path and path.suffix.lower() in IMAGE_EXTS:
                return path
            if path:
                path.unlink(missing_ok=True)
    return None


def _placeholder(label: str, index: int, cache_dir: Path, size: tuple[int, int]) -> Path:
    w, h = size
    c0, c1 = PLACEHOLDER_PALETTES[index % len(PLACEHOLDER_PALETTES)]
    dest = cache_dir / f"placeholder_{index:02d}.png"
    text = label.replace("\\", "").replace("'", "").replace(":", " ")[:48]
    base = ["ffmpeg", "-f", "lavfi", "-i", f"gradients=s={w * 2}x{h * 2}:c0={c0}:c1={c1}:n=2", "-frames:v", "1"]
    try:
        run(base[:-2] + ["-vf", f"drawtext=text='{text}':fontcolor=white@0.85:fontsize={h // 12}"
                               f":x=(w-text_w)/2:y=(h-text_h)/2", "-frames:v", "1", str(dest)])
    except Exception:
        run(base + [str(dest)])  # no fontconfig — plain gradient
    return dest
