# CLAUDE.md

Guidance for AI assistants (and humans) working in this repository.

## What this is

**Companion** is a small AI chat assistant powered by the Claude API. It ships
in two interchangeable front-ends that share the same conversation state:

- **`companion.py`** — a terminal/CLI chat app (uses `rich` for formatting when
  available, degrades gracefully to plain text).
- **`app.py`** — a Flask web app that serves a single-page chat UI with
  **streaming** responses over Server-Sent Events (SSE).

Both store conversation history in the same JSON file, so a chat started in the
CLI can be resumed in the web UI and vice-versa.

## Project layout

```
.
├── companion.py        # CLI entrypoint (rich UI, /commands, blocking responses)
├── app.py              # Flask web server (SSE streaming, /history, /clear, /chat)
├── requirements.txt    # anthropic, rich, flask
├── templates/
│   └── index.html      # Web UI markup (chat layout, input form)
└── static/
    ├── app.js          # Front-end: SSE streaming, minimal markdown renderer
    └── style.css       # Web UI styling
```

There is no package, build step, test suite, or CI configuration. It is a
flat, dependency-light Python project.

## Running

Both apps require the `ANTHROPIC_API_KEY` environment variable and exit early
if it is unset.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

python companion.py        # CLI
python app.py              # Web UI at http://localhost:5000
```

### CLI commands (`companion.py`)
- `/clear` — wipe conversation history
- `/history` — print stored messages
- `/quit` — exit (Ctrl-C / Ctrl-D also exit and save)

### Web routes (`app.py`)
- `GET /` — serves the chat page
- `GET /history` — returns stored messages as JSON
- `POST /clear` — clears history
- `POST /chat` — accepts `{"message": "..."}`, streams the reply as SSE
  (`data: {"text": ...}` chunks, then `data: {"done": true}`; errors as
  `data: {"error": ...}`)

## Key conventions & shared contracts

These details are duplicated across `companion.py` and `app.py`. **When you
change one, change the other to match** unless there is a deliberate reason not
to.

- **Model**: `MODEL = "claude-sonnet-4-6"` — defined identically in both files.
  Use the latest, most capable Claude model when updating; keep the two
  constants in sync.
- **System prompt**: the `SYSTEM_PROMPT` string (the "Companion" persona) is
  copied verbatim in both files. Edit both.
- **History file**: `~/.companion_history.json` (`HISTORY_FILE`). A flat JSON
  list of `{"role": "user"|"assistant", "content": str}` messages — the exact
  shape the Anthropic Messages API expects, so it is passed straight through as
  the `messages` argument.
- **History trimming**: `MAX_HISTORY = 50` message *pairs*; `load_history` and
  `save_history` keep only the last `MAX_HISTORY * 2` entries.
- **`max_tokens`**: `1024` per response in both apps.
- **Error handling**: API calls are wrapped to catch `anthropic.APIError`. The
  CLI pops the failed user message off history so it is not persisted; the web
  app emits an SSE `error` event.

### CLI specifics
- `rich` is optional. Code guards every use behind `HAS_RICH`; keep both the
  rich and plain-text branches working when editing output.

### Web specifics
- The web app uses `client.messages.stream(...)` and iterates
  `stream.text_stream`; the CLI uses the blocking `client.messages.create(...)`.
- SSE responses set `Cache-Control: no-cache` and `X-Accel-Buffering: no` to
  prevent proxy buffering — keep these if you touch the streaming response.
- `static/app.js` contains a hand-rolled minimal markdown renderer
  (`renderMarkdown`) supporting bold, inline code, fenced code blocks, and list
  items. There is no markdown library; extend this function for new formatting.
- User content is HTML-escaped (`escapeHtml`) before insertion; assistant
  content is rendered through `renderMarkdown` (which also escapes). Preserve
  this escaping to avoid XSS.

## Coding style

- Python 3 with type hints and module docstrings; standard library + the three
  pinned dependencies only. Match the existing concise, function-first style.
- Keep the two entrypoints free of heavy frameworks or new dependencies unless
  the change clearly warrants it.

## Git workflow

- Default branch work happens on feature branches (e.g. `claude/...`).
- Commit with clear, descriptive messages; push with
  `git push -u origin <branch-name>` and open a draft PR for the pushed branch
  if one does not already exist.
