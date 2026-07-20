#!/usr/bin/env python3
"""Web interface for Companion — streaming chat powered by Claude.

Stateless server: conversation history lives in the browser (localStorage)
and is sent with each request, so the app works on serverless hosts like
Vercel where there is no persistent filesystem.
"""

import json
import os
import sys

try:
    import anthropic
    from flask import Flask, Response, jsonify, render_template, request, stream_with_context
except ImportError:
    print("Missing dependencies. Run: pip install -r requirements.txt")
    sys.exit(1)

MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 50  # message pairs accepted per request
MAX_MESSAGE_CHARS = 8000

SYSTEM_PROMPT = """You are Companion, a warm, thoughtful, and engaging conversational AI.
You are curious, supportive, and genuinely interested in the person you're talking with.
You remember what's been said in the conversation and build on it naturally.
You are honest, direct, and never sycophantic. You speak like a real person — no corporate-speak.
When you don't know something, you say so. When you have opinions, you share them.
Keep responses concise unless depth is clearly needed."""

app = Flask(__name__)
client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


def sanitize_history(raw) -> list[dict]:
    """Validate client-supplied history into alternating Anthropic messages."""
    if not isinstance(raw, list):
        return []
    messages = []
    for item in raw[-MAX_HISTORY * 2:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, str) or not content.strip():
            continue
        if messages and messages[-1]["role"] == role:
            continue  # the API requires alternating roles
        messages.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    if messages and messages[0]["role"] != "user":
        messages.pop(0)
    if messages and messages[-1]["role"] == "user":
        messages.pop()  # the new user message is appended by /chat
    return messages


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()
    if not user_message:
        return jsonify({"error": "Empty message"}), 400

    messages = sanitize_history(data.get("history"))
    messages.append({"role": "user", "content": user_message[:MAX_MESSAGE_CHARS]})

    def generate():
        try:
            with client.messages.stream(
                model=MODEL,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=messages,
            ) as stream:
                for text in stream.text_stream:
                    yield f"data: {json.dumps({'text': text})}\n\n"
        except Exception as e:  # surface SDK/config errors as an SSE event, not a dead stream
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

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
