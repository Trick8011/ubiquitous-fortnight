#!/usr/bin/env python3
"""Web interface for Companion — streaming chat powered by Claude."""

import json
import os
import sys
from pathlib import Path

try:
    import anthropic
    from flask import Flask, Response, jsonify, render_template, request, stream_with_context
except ImportError:
    print("Missing dependencies. Run: pip install -r requirements.txt")
    sys.exit(1)

HISTORY_FILE = Path.home() / ".companion_history.json"
MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 50

SYSTEM_PROMPT = """You are Companion, a warm, thoughtful, and engaging conversational AI.
You are curious, supportive, and genuinely interested in the person you're talking with.
You remember what's been said in the conversation and build on it naturally.
You are honest, direct, and never sycophantic. You speak like a real person — no corporate-speak.
When you don't know something, you say so. When you have opinions, you share them.
Keep responses concise unless depth is clearly needed."""

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


def load_history() -> list[dict]:
    if HISTORY_FILE.exists():
        try:
            data = json.loads(HISTORY_FILE.read_text())
            return data[-MAX_HISTORY * 2:]
        except (json.JSONDecodeError, KeyError):
            return []
    return []


def save_history(messages: list[dict]) -> None:
    HISTORY_FILE.write_text(json.dumps(messages[-MAX_HISTORY * 2:], indent=2))


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/history")
def history():
    return jsonify(load_history())


@app.route("/clear", methods=["POST"])
def clear():
    save_history([])
    return jsonify({"ok": True})


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_message = (data or {}).get("message", "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    messages = load_history()
    messages.append({"role": "user", "content": user_message})

    def generate():
        full_reply = ""
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    full_reply += text
                    yield f"data: {json.dumps({'text': text})}\n\n"
        except anthropic.APIError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        messages.append({"role": "assistant", "content": full_reply})
        save_history(messages)
        yield f"data: {json.dumps({'done': True})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


if __name__ == "__main__":
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)
    print("Companion running at http://localhost:5000")
    app.run(debug=False, port=5000)
