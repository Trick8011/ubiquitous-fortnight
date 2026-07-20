"""CLI for the video assembly pipeline.

Examples:
    # Generate a script with Claude, narrate it, and assemble a video
    python -m videopipeline --topic "The history of lighthouses" -o lighthouses.mp4

    # Use a prewritten script (JSON) or plain narration text — no API key needed
    python -m videopipeline --script examples/lighthouses.json -o out.mp4
    python -m videopipeline --text narration.txt --title "My Video" -o out.mp4
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import script_gen, tts, upload
from .models import Script
from .pipeline import PipelineOptions, run_pipeline


def parse_resolution(value: str) -> tuple[int, int]:
    try:
        w, h = value.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected WIDTHxHEIGHT, got {value!r}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="videopipeline",
        description="Script → free TTS → FFmpeg assembly → upload-ready MP4.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--topic", help="generate the script with Claude (needs ANTHROPIC_API_KEY)")
    source.add_argument("--script", type=Path, help="use an existing script JSON file")
    source.add_argument("--text", type=Path, help="build the script from a plain-text narration file")

    parser.add_argument("-o", "--out", type=Path, default=Path("output.mp4"), help="output MP4 path")
    parser.add_argument("--duration", type=int, default=60, help="target length in seconds (with --topic)")
    parser.add_argument("--style", default="documentary", help="script tone (with --topic)")
    parser.add_argument("--title", default="Untitled", help="video title (with --text)")
    parser.add_argument("--save-script", type=Path, help="also write the script JSON here")

    parser.add_argument("--tts", choices=["auto", "edge", "espeak"], default="auto", help="TTS engine")
    parser.add_argument("--voice", default=tts.DEFAULT_VOICE, help="edge-tts voice name")
    parser.add_argument("--list-voices", action="store_true", help="list edge-tts voices and exit")

    parser.add_argument("--resolution", type=parse_resolution, default=(1920, 1080), metavar="WxH")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--captions", choices=["burn", "soft", "none"], default="burn",
                        help="burn into video, mux as a soft track, or skip")
    parser.add_argument("--assets-dir", type=Path, help="folder of local footage/photos matched by scene keywords")
    parser.add_argument("--music", type=Path, help="background music file, looped and mixed under narration")
    parser.add_argument("--music-volume", type=float, default=0.15)
    parser.add_argument("--work-dir", type=Path, help="keep intermediate files here instead of a temp dir")
    parser.add_argument("-q", "--quiet", action="store_true")

    yt = parser.add_argument_group("YouTube upload (optional)")
    yt.add_argument("--upload", action="store_true",
                    help="upload the finished MP4 to YouTube (needs OAuth setup, see README)")
    yt.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private",
                    help="privacy of the uploaded video")
    yt.add_argument("--yt-tags", default="", help="comma-separated tags for the uploaded video")
    yt.add_argument("--yt-category", default=upload.DEFAULT_CATEGORY, help="YouTube category id")
    yt.add_argument("--client-secrets", type=Path, help="OAuth client_secret.json path")
    yt.add_argument("--token-file", type=Path, help="cached OAuth token path")

    args = parser.parse_args(argv)

    if args.list_voices:
        for name in tts.list_edge_voices():
            print(name)
        return 0

    try:
        if args.script:
            script = Script.load(args.script)
        elif args.text:
            script = script_gen.script_from_text(args.text.read_text(), title=args.title)
        elif args.topic:
            print(f"Generating script for {args.topic!r} with Claude...")
            script = script_gen.generate_script(args.topic, duration=args.duration, style=args.style)
        else:
            parser.error("one of --topic, --script, or --text is required")

        if args.save_script:
            script.save(args.save_script)

        options = PipelineOptions(
            output=args.out,
            size=args.resolution,
            fps=args.fps,
            tts_engine=args.tts,
            voice=args.voice,
            captions=args.captions,
            assets_dir=args.assets_dir,
            music=args.music,
            music_volume=args.music_volume,
            work_dir=args.work_dir,
            verbose=not args.quiet,
        )
        output = run_pipeline(script, options)

        if args.upload:
            srt = output.with_suffix(".srt")
            url = upload.upload_video(output, upload.UploadOptions(
                title=script.title,
                description=script.description,
                tags=[t.strip() for t in args.yt_tags.split(",") if t.strip()],
                category=args.yt_category,
                privacy=args.privacy,
                captions_srt=srt if srt.exists() else None,
                client_secrets=args.client_secrets,
                token_file=args.token_file,
                verbose=not args.quiet,
            ))
            print(url)
        return 0
    except (RuntimeError, ValueError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
