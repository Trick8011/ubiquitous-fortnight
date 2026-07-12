# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Companion — an AI chat assistant powered by Claude, with two independent entry points that share the same persona and conversation history:

- `companion.py` — terminal chat app (Rich-based UI with a plain-text fallback if `rich` isn't installed)
- `app.py` — Flask web app with streaming responses (SSE), served with `templates/index.html` and `static/` (vanilla JS, no build step)

## Commands

```bash
pip install -r requirements.txt   # anthropic, rich, flask

export ANTHROPIC_API_KEY=...      # required by both apps; they exit at startup without it

python companion.py               # CLI chat
python app.py                     # web UI at http://localhost:5000
```

There are no tests, linters, or build tooling configured.

## Architecture

Both apps are deliberately parallel implementations, not a shared module. They duplicate the same constants and helpers: `MODEL`, `MAX_HISTORY`, `SYSTEM_PROMPT`, `load_history()`, `save_history()`. **When changing any of these (e.g. the model or the persona), change both `companion.py` and `app.py` to keep them in sync.**

### Shared conversation history

Both apps read/write `~/.companion_history.json` — a flat JSON list of `{"role", "content"}` messages in Anthropic Messages API format. History is truncated to the last `MAX_HISTORY * 2` entries (50 message pairs) on both load and save, so a CLI conversation resumes in the web UI and vice versa.

### CLI (`companion.py`)

Single-file loop: read input → call `client.messages.create()` (non-streaming) → render reply → save history. Slash commands (`/clear`, `/history`, `/quit`) are handled in `handle_command()` before anything reaches the API. On an `anthropic.APIError`, the failed user message is popped from history so a retry doesn't double it. All output goes through `HAS_RICH` branches — keep both the Rich and plain-text paths working when touching UI code.

### Web app (`app.py` + `static/app.js`)

- `POST /chat` streams the reply as server-sent events. Each event is a `data: {json}` line carrying one of `{"text": chunk}`, `{"error": msg}`, or `{"done": true}`. History is saved server-side only after the full reply finishes streaming.
- `GET /history` and `POST /clear` round out the API; the frontend keeps no state of its own beyond the DOM.
- `static/app.js` parses the SSE stream manually via `fetch` + `ReadableStream` (not `EventSource`, since the endpoint is a POST) and renders assistant messages with its own minimal markdown renderer (`renderMarkdown`: bold, inline code, fenced code blocks, lists). User content is always HTML-escaped.
