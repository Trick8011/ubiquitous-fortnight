"""Orchestrates the stages: script → TTS → assets → assembly → final MP4."""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import assemble, assets, captions, tts
from .ffutil import require_ffmpeg
from .models import Script, VISUAL_PHOTO

SCENE_TAIL_GAP = 0.5  # seconds of breathing room after each scene's narration


@dataclass
class PipelineOptions:
    output: Path = Path("output.mp4")
    size: tuple[int, int] = (1920, 1080)
    fps: int = 30
    tts_engine: str = "auto"
    voice: str = tts.DEFAULT_VOICE
    captions: str = "burn"  # burn | soft | none
    assets_dir: Path | None = None
    music: Path | None = None
    music_volume: float = 0.15
    work_dir: Path | None = None  # kept for inspection when set; else a temp dir
    verbose: bool = True


def run_pipeline(script: Script, options: PipelineOptions) -> Path:
    require_ffmpeg()
    say = print if options.verbose else (lambda *a, **k: None)

    if options.work_dir:
        workdir = options.work_dir
        workdir.mkdir(parents=True, exist_ok=True)
        cleanup = False
    else:
        workdir = Path(tempfile.mkdtemp(prefix="videopipeline_"))
        cleanup = True

    try:
        n = len(script.scenes)
        say(f"Script: {script.title!r} — {n} scenes, {script.word_count} words")

        say(f"[1/4] Synthesizing narration ({options.tts_engine})...")
        audios: list[tts.SceneAudio] = []
        for i, scene in enumerate(script.scenes):
            audio = tts.synthesize(scene.narration, workdir / f"scene_{i:02d}.wav",
                                   engine=options.tts_engine, voice=options.voice)
            audios.append(audio)
            say(f"  scene {i + 1}/{n}: {audio.duration:.1f}s")

        scene_durations = [
            assemble.round_to_frames(a.duration + SCENE_TAIL_GAP, options.fps) for a in audios
        ]

        say("[2/4] Resolving visuals...")
        clips: list[Path] = []
        photo_variant = 0
        for i, (scene, duration) in enumerate(zip(script.scenes, scene_durations)):
            asset = assets.resolve_scene_asset(scene, i, workdir / "assets",
                                               assets_dir=options.assets_dir, size=options.size)
            clip = workdir / f"clip_{i:02d}.mp4"
            if assets.is_video(asset):
                assemble.build_video_clip(asset, duration, clip, options.size, options.fps)
                kind = "footage"
            else:
                assemble.build_photo_clip(asset, duration, clip, options.size, options.fps, photo_variant)
                photo_variant += 1
                kind = "photo + Ken Burns"
            clips.append(clip)
            say(f"  scene {i + 1}/{n}: {asset.name} ({kind})")

        say("[3/4] Assembling timeline...")
        visual = assemble.concat_clips(clips, workdir / "visual.mp4", workdir)
        narration = assemble.build_narration(audios, scene_durations, workdir / "narration.wav", workdir)

        srt_path: Path | None = None
        if options.captions != "none":
            offsets, t = [], 0.0
            for duration in scene_durations:
                offsets.append(t)
                t += duration
            cues = captions.build_cues([(off, a.words) for off, a in zip(offsets, audios)])
            srt_path = workdir / "captions.srt"
            captions.write_srt(cues, srt_path)

        say("[4/4] Rendering final MP4...")
        options.output.parent.mkdir(parents=True, exist_ok=True)
        assemble.render_final(visual, narration, options.output, workdir,
                              srt=srt_path, captions=options.captions,
                              music=options.music, music_volume=options.music_volume)

        if srt_path and options.captions == "burn":
            shutil.copy(srt_path, options.output.with_suffix(".srt"))  # sidecar for upload platforms

        total = sum(scene_durations)
        say(f"Done: {options.output} ({total:.1f}s, {options.size[0]}x{options.size[1]}@{options.fps}fps)")
        return options.output
    finally:
        if cleanup:
            shutil.rmtree(workdir, ignore_errors=True)
