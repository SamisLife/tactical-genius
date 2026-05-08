"""Quick smoke test for the data layer. Run after adding your API key to .env."""

import json
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from tactical_genius.data import (
    get_live_matches,
    get_match_details,
    get_team_recent_form,
    get_team_squad,
    get_head_to_head,
    get_standings,
)

console = Console()

ARSENAL_ID = 57
CHELSEA_ID = 61
PREMIER_LEAGUE_ID = "PL"


def pretty(label: str, data: dict) -> None:
    syntax = Syntax(json.dumps(data, indent=2, default=str), "json", theme="monokai", word_wrap=True)
    console.print(Panel(syntax, title=f"[bold cyan]{label}[/bold cyan]", expand=False))


def run_test(label: str, fn, *args, **kwargs):
    console.rule(f"[bold green]{label}")
    try:
        result = fn(*args, **kwargs)
        pretty(label, result)
        if "error" in result:
            console.print("[yellow]  ⚠  got an error (see above)[/yellow]")
        else:
            console.print("[green]  ✓  ok[/green]")
        return result
    except Exception as exc:
        console.print(f"[red]  ✗  {exc}[/red]")
        return {}


def main():
    console.print(Panel("[bold white]Tactical Genius — data layer smoke test[/bold white]", style="bold blue"))

    live = run_test("get_live_matches", get_live_matches)

    if live.get("matches"):
        first_id = live["matches"][0]["id"]
        run_test(f"get_match_details({first_id})", get_match_details, first_id)
    else:
        console.print("[dim]  no live matches right now, skipping get_match_details[/dim]")

    run_test("get_team_recent_form (Arsenal, last 5)", get_team_recent_form, ARSENAL_ID, 5)
    run_test("get_team_squad (Chelsea)", get_team_squad, CHELSEA_ID)
    run_test("get_head_to_head (Arsenal vs Chelsea)", get_head_to_head, ARSENAL_ID, CHELSEA_ID)
    run_test(f"get_standings ({PREMIER_LEAGUE_ID})", get_standings, PREMIER_LEAGUE_ID)

    console.rule("[bold green]done")


if __name__ == "__main__":
    main()
