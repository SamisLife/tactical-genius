"""
Interactive agent test. Type a query and watch the reasoning unfold in real time.
Conversation memory persists across turns — try follow-up questions.
Type 'quit' to exit, 'reset' to start a fresh thread.
"""

import uuid
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.rule import Rule

from tactical_genius.agent import stream_query

console = Console()

EXAMPLES = [
    "What matches are live right now?",
    "Analyze Arsenal's recent form and suggest tactical improvements",
    "Look at the Premier League standings and identify who's in a relegation battle",
]


def run():
    console.print(Panel("[bold white]Tactical Genius — agent test[/bold white]\n"
                        "[dim]Memory persists across turns. Type 'reset' for a new thread, 'quit' to exit.[/dim]",
                        style="bold blue"))

    console.print("\n[dim]Example queries:[/dim]")
    for ex in EXAMPLES:
        console.print(f"  [dim]→ {ex}[/dim]")
    console.print()

    thread_id = str(uuid.uuid4())

    while True:
        try:
            query = console.input("[bold cyan]You:[/bold cyan] ").strip()
        except (KeyboardInterrupt, EOFError):
            break

        if not query:
            continue
        if query.lower() == "quit":
            break
        if query.lower() == "reset":
            thread_id = str(uuid.uuid4())
            console.print("[dim]  memory cleared — new session started[/dim]\n")
            continue

        console.print()
        answer_parts = []

        try:
            for event in stream_query(query, thread_id=thread_id):
                if event["type"] == "tool_call":
                    args_str = ", ".join(f"{k}={v}" for k, v in event["args"].items())
                    console.print(f"  [dim]🔧 {event['name']}({args_str})[/dim]")

                elif event["type"] == "tool_result":
                    # just show first line so it doesn't flood the terminal
                    first_line = event["content"].split("\n")[0][:80]
                    console.print(f"  [dim]   ↳ {first_line}...[/dim]")

                elif event["type"] == "answer":
                    answer_parts.append(event["content"])

        except Exception as exc:
            console.print(f"[red]Agent error: {exc}[/red]")
            continue

        if answer_parts:
            console.print()
            console.print(Panel(Markdown("\n".join(answer_parts)), title="[bold green]Tactical Genius[/bold green]", border_style="green"))

        console.print()


if __name__ == "__main__":
    run()
