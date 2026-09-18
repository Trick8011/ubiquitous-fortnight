"""FFmpeg assembly: per-scene clips (Ken Burns for photos, scale/crop/loop for
footage), concatenation, narration mux, caption burn-in, upload-ready MP4."""

from __future__ import annotations

from pathlib import Path

from .ffutil import run
from .tts import SceneAudio

# Uniform intermediate encode so scene clips concat with -c copy.
CLIP_ENCODE = ["-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p"]

CAPTION_STYLE = (
    "FontName=DejaVu Sans,Bold=1,FontSize=17,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00101010,BorderStyle=1,Outline=2,Shadow=1,MarginV=32"
)

# Ken Burns moves, cycled across photo scenes. `p` sweeps 0→1 over the clip.
_KEN_BURNS = [
    {"z": "1+0.18*{p}", "x": "(iw-iw/zoom)/2", "y": "(ih-ih/zoom)/2"},          # slow zoom in
    {"z": "1.18-0.18*{p}", "x": "(iw-iw/zoom)/2", "y": "(ih-ih/zoom)/2"},       # slow zoom out
    {"z": "1.12", "x": "(iw-iw/zoom)*{p}", "y": "(ih-ih/zoom)/2"},              # pan left → right
    {"z": "1.12", "x": "(iw-iw/zoom)*(1-{p})", "y": "(ih-ih/zoom)/3"},          # pan right → left
]


def round_to_frames(seconds: float, fps: int) -> float:
    """Snap a duration up to a whole frame count so audio and video stay aligned."""
    import math
    return math.ceil(seconds * fps - 1e-6) / fps


def build_photo_clip(image: Path, duration: float, out: Path, size: tuple[int, int], fps: int, variant: int) -> Path:
    """Animate a still image with a Ken Burns move for `duration` seconds."""
    w, h = size
    frames = max(2, round(duration * fps))
    move = _KEN_BURNS[variant % len(_KEN_BURNS)]
    p = f"on/{frames - 1}"
    # Pre-scale to 2x output size: zoompan samples on integer pixels, so a roomy
    # source keeps the move smooth instead of jittering.
    filters = (
        f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
        f"zoompan=z='{move['z'].format(p=p)}':x='{move['x'].format(p=p)}':y='{move['y'].format(p=p)}'"
        f":d={frames}:s={w}x{h}:fps={fps},setsar=1"
    )
    run(["ffmpeg", "-i", str(image), "-vf", filters, "-frames:v", str(frames), *CLIP_ENCODE, str(out)])
    return out


def build_video_clip(video: Path, duration: float, out: Path, size: tuple[int, int], fps: int) -> Path:
    """Cut stock footage to `duration`, looping if the source is shorter, and
    normalize to the output size/framerate (cover-crop, audio stripped)."""
    w, h = size
    filters = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps},setsar=1"
    run([
        "ffmpeg", "-stream_loop", "-1", "-i", str(video),
        "-vf", filters, "-t", f"{duration:.6f}", *CLIP_ENCODE, str(out),
    ])
    return out


def concat_clips(clips: list[Path], out: Path, workdir: Path) -> Path:
    list_file = workdir / "concat_video.txt"
    list_file.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(out)])
    return out


def build_narration(audios: list[SceneAudio], scene_durations: list[float], out: Path, workdir: Path) -> Path:
    """Pad each scene's narration to its clip duration, then join them."""
    padded: list[Path] = []
    for i, (audio, duration) in enumerate(zip(audios, scene_durations)):
        p = workdir / f"narration_{i:02d}.wav"
        run(["ffmpeg", "-i", str(audio.path), "-af", "apad", "-t", f"{duration:.6f}", "-c:a", "pcm_s16le", str(p)])
        padded.append(p)
    list_file = workdir / "concat_audio.txt"
    list_file.write_text("".join(f"file '{p.resolve()}'\n" for p in padded))
    run(["ffmpeg", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c:a", "pcm_s16le", str(out)])
    return out


def render_final(visual: Path, narration: Path, out: Path, workdir: Path,
                 srt: Path | None = None, captions: str = "burn",
                 music: Path | None = None, music_volume: float = 0.15) -> Path:
    """Mux everything into an upload-ready MP4 (H.264 + AAC, faststart)."""
    # All inputs first — ffmpeg applies any option between -i flags to the next input.
    cmd = ["ffmpeg", "-i", str(visual.resolve()), "-i", str(narration.resolve())]
    music_index = srt_index = None
    if music:
        cmd += ["-stream_loop", "-1", "-i", str(music.resolve())]
        music_index = 2
    if srt and captions == "soft":
        srt_index = 3 if music else 2
        cmd += ["-i", str(srt.resolve())]

    filters: list[str] = []
    if srt and captions == "burn":
        # Run from the workdir with a bare filename to sidestep filter-path escaping.
        filters.append(f"[0:v]subtitles={srt.name}:force_style='{CAPTION_STYLE}'[vout]")
        cmd += ["-map", "[vout]"]
        video_codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p"]
    else:
        cmd += ["-map", "0:v"]
        video_codec = ["-c:v", "copy"]

    if music:
        filters.append(f"[{music_index}:a]volume={music_volume}[mus];"
                       f"[1:a][mus]amix=inputs=2:duration=first:normalize=0[aout]")
        cmd += ["-map", "[aout]"]
    else:
        cmd += ["-map", "1:a"]

    if filters:
        cmd += ["-filter_complex", ";".join(filters)]
    cmd += video_codec + ["-c:a", "aac", "-b:a", "192k"]
    if srt_index is not None:
        cmd += ["-map", f"{srt_index}:s", "-c:s", "mov_text", "-metadata:s:s:0", "language=eng"]

    cmd += ["-movflags", "+faststart", "-shortest", str(out.resolve())]
    run(cmd, cwd=workdir)
    return out
