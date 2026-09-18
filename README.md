# ubiquitous-fortnight

Two small AI apps:

- **Companion** — a Claude-powered chat companion (`companion.py` CLI, `app.py` web UI).
- **videopipeline** — an automated video assembly pipeline: script → free TTS → FFmpeg → upload-ready MP4.

## videopipeline

Turns a topic (or your own narration) into a finished, captioned video:

1. **Script generation** — Claude writes a scene-by-scene script (narration + stock-search
   keywords + visual type per scene), or you supply a script JSON / plain-text narration.
2. **Free TTS** — [edge-tts](https://pypi.org/project/edge-tts/) neural voices (free, no key)
   with word-level timestamps; falls back to offline `espeak-ng` when there's no network.
3. **Visual sourcing** — per scene: your local assets folder → Pexels stock search
   (free `PEXELS_API_KEY`) → Openverse openly-licensed images (keyless) → generated
   placeholder card, so a render always completes.
4. **FFmpeg assembly** — stock footage is cover-cropped/looped to each scene's narration;
   still photos get Ken Burns moves (alternating zoom/pan via `zoompan`); scenes are
   concatenated, narration and optional background music are mixed in, and captions
   (built from the TTS word timings) are burned in or muxed as a soft track.
5. **Output** — H.264 + AAC MP4, `yuv420p`, `+faststart` — ready to upload to
   YouTube et al., with a sidecar `.srt` next to it.
6. **YouTube upload (optional)** — `--upload` pushes the finished MP4 to YouTube via
   the Data API v3 (resumable, with retry), using the script's title/description and
   attaching the sidecar `.srt` as an English caption track.

### Setup

```bash
pip install -r requirements.txt
apt install ffmpeg            # required
apt install espeak-ng         # optional offline TTS fallback
export ANTHROPIC_API_KEY=...  # only needed for --topic script generation
export PEXELS_API_KEY=...     # optional, enables stock footage/photo search
```

### Usage

```bash
# Everything automated: Claude writes the script, edge-tts narrates, FFmpeg assembles
python -m videopipeline --topic "The history of lighthouses" --duration 60 -o lighthouses.mp4

# From your own script JSON (see examples/lighthouses.json) — no Anthropic key needed
python -m videopipeline --script examples/lighthouses.json -o out.mp4

# From plain-text narration (one paragraph per scene)
python -m videopipeline --text narration.txt --title "My Video" -o out.mp4

# Use your own footage/photos, matched to scenes by keyword in the filename
python -m videopipeline --script examples/lighthouses.json --assets-dir ./my_media -o out.mp4

# Fully offline: espeak narration + local assets (or generated placeholders)
python -m videopipeline --text narration.txt --tts espeak -o out.mp4

# Render and upload to YouTube in one go (private by default)
python -m videopipeline --topic "The history of lighthouses" -o out.mp4 --upload --privacy unlisted

# Upload an already-rendered MP4
python -m videopipeline.upload out.mp4 --title "My Video" --srt out.srt --privacy unlisted
```

Useful flags: `--voice` (see `--list-voices`), `--captions burn|soft|none`,
`--music file.mp3 --music-volume 0.15`, `--resolution 1280x720`, `--fps`,
`--save-script script.json` (edit it, re-run with `--script`), and
`--work-dir dir` to keep intermediates for inspection.

### Script JSON format

```json
{
  "title": "Keepers of the Coast",
  "description": "One-sentence description.",
  "scenes": [
    {
      "narration": "Spoken text for this scene.",
      "keywords": ["lighthouse", "storm"],
      "visual": "footage",
      "asset": "optional/local/file.mp4 (or URL) to skip asset search"
    }
  ]
}
```

`visual` is `"footage"` (stock video) or `"photo"` (still image, animated with Ken Burns).

### YouTube upload setup

Uploading needs the Google API client libraries and a one-time OAuth setup:

```bash
pip install google-api-python-client google-auth-oauthlib
```

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project,
   enable the **YouTube Data API v3**, and create an **OAuth client ID** of type
   *Desktop app* (configure the consent screen and add your account as a test user).
2. Download the client secret JSON to `~/.videopipeline/client_secret.json`
   (or point `--client-secrets` / `YT_CLIENT_SECRETS` at it).
3. The first `--upload` prints a Google consent URL; open it, approve, and the token
   is cached at `~/.videopipeline/token.json` (`--token-file` / `YT_TOKEN_FILE`) and
   refreshed automatically afterwards.

Uploads default to **private** so nothing goes public by accident — pass
`--privacy unlisted` or `--privacy public` to change that. New/unverified API
projects may cap daily uploads and can mark uploads private until the app is
verified by Google.

## Companion

```bash
export ANTHROPIC_API_KEY=...
python companion.py   # terminal chat
python app.py         # web UI at http://localhost:5000
```
