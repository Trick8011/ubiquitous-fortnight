# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Companion — an AI chat assistant powered by Claude, with two independent entry points that share the same persona and conversation history:

- `companion.py` — terminal chat app (Rich-based UI with a plain-text fallback if `rich` isn't installed)
- `app.py` — Flask web app with streaming responses (SSE), served with `templates/index.html` and `static/` (vanilla JS, no build step); deployable to Vercel via `vercel.json` + `api/index.py`

## Commands

```bash
pip install -r requirements.txt   # anthropic, rich, flask

export ANTHROPIC_API_KEY=...      # required by both apps; they exit at startup without it

python companion.py               # CLI chat
python app.py                     # web UI at http://localhost:5000
```

There are no tests, linters, or build tooling configured.

## Architecture

Both apps are deliberately parallel implementations, not a shared module. They duplicate the same constants — `MODEL` (currently `claude-sonnet-4-6`), `MAX_HISTORY`, `SYSTEM_PROMPT` — and the same `max_tokens=1024` in the API call. **When changing any of these (e.g. the model or the persona), change both `companion.py` and `app.py` to keep them in sync.**

The two apps store history differently:

- CLI: server-side file `~/.companion_history.json` — a flat JSON list of `{"role", "content"}` messages in Anthropic Messages API format, truncated to `MAX_HISTORY * 2` entries on load and save.
- Web: client-side `localStorage` (key `companion_history` in `static/app.js`, capped at `MAX_STORED_MESSAGES = 100`); the Flask server is stateless so it can run on serverless hosts.

### CLI (`companion.py`)

Single-file loop: read input → call `client.messages.create()` (non-streaming) → render reply → save history. Slash commands (`/clear`, `/history`, `/quit`) are handled in `handle_command()` before anything reaches the API. On an `anthropic.APIError`, the failed user message is popped from history so a retry doesn't double it. All output goes through `HAS_RICH` branches — keep both the Rich and plain-text paths working when touching UI code.

### Web app (`app.py` + `static/app.js`)

- `POST /chat` is the only API endpoint. The request body is `{"message": str, "history": [{"role", "content"}, ...]}`; the server validates history with `sanitize_history()` before calling the API: role whitelist, enforced user/assistant alternation, per-message cap of `MAX_MESSAGE_CHARS` (8000), and it drops a leading assistant message or a trailing user message (the new user message is appended separately by `/chat`). The reply streams back as server-sent events — each a `data: {json}` line carrying one of `{"text": chunk}`, `{"error": msg}`, or `{"done": true}`.
- `static/app.js` owns history: it loads from and saves to `localStorage`, appending the user/assistant pair only after a stream completes without error. It parses the SSE stream manually via `fetch` + `ReadableStream` (not `EventSource`, since the endpoint is a POST) and renders assistant messages with its own minimal markdown renderer (`renderMarkdown`: bold, inline code, fenced code blocks, lists). User content is always HTML-escaped.

### Vercel deployment

`vercel.json` rewrites every path to `api/index.py`, which imports the Flask app from the repo root as the WSGI entry point. The `ANTHROPIC_API_KEY` environment variable must be set in the Vercel project settings. Because the server is stateless, no other infrastructure is needed; if the platform buffers the response instead of streaming, the frontend still works — it renders whatever chunks arrive.
