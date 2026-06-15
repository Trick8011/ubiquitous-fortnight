#!/usr/bin/env python3
"""AI Chat Companion — a conversational assistant powered by Claude."""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import anthropic
except ImportError:
    print("Missing dependency. Run: pip install -r requirements.txt")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.text import Text
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

HISTORY_FILE = Path.home() / ".companion_history.json"
MODEL = "claude-sonnet-4-6"
MAX_HISTORY = 50  # message pairs kept in memory

SYSTEM_PROMPT = """You are Companion, a warm, thoughtful, and engaging conversational AI.
You are curious, supportive, and genuinely interested in the person you're talking with.
You remember what's been said in the conversation and build on it naturally.
You are honest, direct, and never sycophantic. You speak like a real person — no corporate-speak.
When you don't know something, you say so. When you have opinions, you share them.
Keep responses concise unless depth is clearly needed."""

console = Console() if HAS_RICH else None


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


def print_message(role: str, content: str) -> None:
    if HAS_RICH:
        if role == "assistant":
            console.print(Panel(Markdown(content), border_style="blue", title="[bold blue]Companion[/]", title_align="left"))
        else:
            console.print(Panel(content, border_style="green", title="[bold green]You[/]", title_align="left"))
    else:
        label = "Companion" if role == "assistant" else "You"
        print(f"\n[{label}]\n{content}\n")


def print_header() -> None:
    if HAS_RICH:
        console.print(Panel(
            "[bold blue]Companion[/bold blue] — your AI chat partner\n"
            "[dim]Commands: /clear · /history · /quit[/dim]",
            border_style="blue"
        ))
    else:
        print("=== Companion — your AI chat partner ===")
        print("Commands: /clear · /history · /quit\n")


def handle_command(cmd: str, messages: list[dict]) -> tuple[bool, list[dict]]:
    """Returns (should_continue, updated_messages)."""
    cmd = cmd.strip().lower()
    if cmd == "/quit":
        if HAS_RICH:
            console.print("[dim]Goodbye.[/dim]")
        else:
            print("Goodbye.")
        return False, messages
    elif cmd == "/clear":
        messages = []
        save_history(messages)
        if HAS_RICH:
            console.print("[dim]Conversation cleared.[/dim]")
        else:
            print("Conversation cleared.")
    elif cmd == "/history":
        if not messages:
            if HAS_RICH:
                console.print("[dim]No history yet.[/dim]")
            else:
                print("No history yet.")
        else:
            if HAS_RICH:
                console.print(f"[dim]{len(messages)} messages in history[/dim]")
            for msg in messages:
                print_message(msg["role"], msg["content"])
    else:
        if HAS_RICH:
            console.print(f"[yellow]Unknown command: {cmd}[/yellow]")
        else:
            print(f"Unknown command: {cmd}")
    return True, messages


def chat(client: anthropic.Anthropic, messages: list[dict], user_input: str) -> str:
    messages.append({"role": "user", "content": user_input})
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=messages,
    )
    reply = response.content[0].text
    messages.append({"role": "assistant", "content": reply})
    return reply


def get_input(prompt: str = "You") -> str:
    if HAS_RICH:
        return Prompt.ask(f"[bold green]{prompt}[/bold green]")
    else:
        return input(f"{prompt}: ").strip()


def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: ANTHROPIC_API_KEY environment variable not set.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)
    messages = load_history()

    print_header()

    if messages:
        if HAS_RICH:
            console.print(f"[dim]Resuming conversation ({len(messages)} messages)[/dim]\n")
        else:
            print(f"Resuming conversation ({len(messages)} messages)\n")

    while True:
        try:
            user_input = get_input()
        except (KeyboardInterrupt, EOFError):
            if HAS_RICH:
                console.print("\n[dim]Goodbye.[/dim]")
            else:
                print("\nGoodbye.")
            save_history(messages)
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            should_continue, messages = handle_command(user_input, messages)
            if not should_continue:
                save_history(messages)
                break
            continue

        try:
            if HAS_RICH:
                with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                    reply = chat(client, messages, user_input)
            else:
                print("...")
                reply = chat(client, messages, user_input)
        except anthropic.APIError as e:
            if HAS_RICH:
                console.print(f"[red]API error: {e}[/red]")
            else:
                print(f"API error: {e}")
            messages.pop()  # remove the failed user message
            continue

        print_message("assistant", reply)
        save_history(messages)


if __name__ == "__main__":
    main()
