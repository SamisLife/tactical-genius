"""LangChain tools that wrap the data layer. Docstrings are the agent's instructions for when to use each tool."""

import os
import requests
from langchain_core.tools import tool

from ..data.client import (
    _get,
    search_team,
    get_live_matches,
    get_match_details,
    get_team_recent_form,
    get_team_squad,
    get_head_to_head,
    get_standings,
)


@tool
def find_team(name: str) -> str:
    """
    Search for a team by name and get their ID. Always call this first when the user
    mentions a team by name (e.g. "Real Madrid", "Arsenal") and you don't already have
    their numeric team ID. The ID is required by fetch_team_form, fetch_squad, etc.
    """
    data = search_team(name)
    if "error" in data:
        return f"Error: {data['error']}"
    if not data["teams"]:
        return f"No teams found matching '{name}'. Try a shorter or different spelling."

    lines = [f"Found {data['count']} team(s) matching '{name}':\n"]
    for t in data["teams"]:
        comps = ", ".join(t["competitions"]) or "none listed"
        lines.append(f"  id={t['id']:6}  {t['name']:35}  ({t['area']})  competitions: {comps}")
    return "\n".join(lines)


@tool
def fetch_live_matches() -> str:
    """
    Get all currently live matches. Call this first when the user asks about an ongoing match
    or wants to know what games are happening right now. Returns match IDs you'll need for other tools.
    """
    data = get_live_matches()
    if "error" in data:
        return f"Error: {data['error']}"
    if not data["matches"]:
        return "No matches are live right now."

    lines = [f"Found {data['count']} live match(es):\n"]
    for m in data["matches"]:
        score = m["score"]
        s = f"{score['home']}-{score['away']}" if score["home"] is not None else "vs"
        lines.append(
            f"  [{m['id']}] {m['home_team']} {s} {m['away_team']}"
            f"  |  {m['competition']}"
            f"  |  status: {m['status']}"
        )
    return "\n".join(lines)


@tool
def fetch_match_stats(match_id: int) -> str:
    """
    Get detailed info for a specific match: score, half-time score, competition stage,
    referee, and a head-to-head summary if available. Use this after fetch_live_matches
    to dig into a specific game. match_id comes from fetch_live_matches output.
    """
    data = get_match_details(match_id)
    if "error" in data:
        return f"Error: {data['error']}"

    score = data["score"]
    lines = [
        f"{data['home_team']} vs {data['away_team']}",
        f"Competition: {data['competition']} | Stage: {data['stage']} | Matchday: {data['matchday']}",
        f"Score: {score['home']}-{score['away']} (HT: {score['half_time_home']}-{score['half_time_away']})",
        f"Status: {data['status']}" + (f" | Minute: {data['minute']}" if data.get("minute") else ""),
        f"Referees: {', '.join(data['referees']) or 'unknown'}",
    ]

    h2h = data.get("head_to_head_summary")
    if h2h:
        lines.append(
            f"H2H (last {h2h['number_of_matches']} meetings): "
            f"{data['home_team']} {h2h['home_team_wins']}W / "
            f"{h2h['draws']}D / "
            f"{h2h['away_team_wins']}W {data['away_team']} | "
            f"{h2h['total_goals']} total goals"
        )

    return "\n".join(lines)


@tool
def fetch_team_form(team_id: int, last_n: int = 5) -> str:
    """
    Get a team's results from their last N matches — form string (e.g. WWDLW), scores,
    opponents, and goal stats. Use this to understand momentum, defensive fragility,
    or attacking patterns before making tactical recommendations.
    """
    data = get_team_recent_form(team_id, last_n)
    if "error" in data:
        return f"Error: {data['error']}"

    s = data["summary"]
    lines = [
        f"{data['team_name']} — last {len(data['matches'])} matches",
        f"Form: {data['form_string']}  |  {s['wins']}W {s['draws']}D {s['losses']}L  |  {s['points']} pts",
        f"Goals: {s['goals_scored']} scored / {s['goals_conceded']} conceded  |  {s['clean_sheets']} clean sheet(s)",
        "",
    ]
    for m in data["matches"]:
        lines.append(f"  {m['date']}  {m['location']:4}  {m['result']}  {m['score']:5}  vs {m['opponent']}  ({m['competition']})")

    return "\n".join(lines)


@tool
def fetch_squad(team_id: int) -> str:
    """
    Get the full squad for a team grouped by position (GK, DEF, MID, ATT), including
    player IDs, nationalities, and ages. Use this when evaluating substitution options
    or understanding squad depth. Player IDs here can be passed to fetch_player_history.
    """
    data = get_team_squad(team_id)
    if "error" in data:
        return f"Error: {data['error']}"

    coach = data["coach"]
    lines = [
        f"{data['team_name']} (founded {data['founded']}) — {data['squad_count']} players",
        f"Coach: {coach['name']} ({coach['nationality']})",
        f"Venue: {data['venue']}",
        "",
    ]

    pos_map = {
        "goalkeepers": "GK",
        "defenders": "DEF",
        "midfielders": "MID",
        "attackers": "ATT",
    }
    for key, label in pos_map.items():
        players = data["squad_by_position"].get(key, [])
        if not players:
            continue
        lines.append(f"[{label}]")
        for p in players:
            dob = p.get("date_of_birth", "")
            age = _age_from_dob(dob)
            num = f"#{p['shirt_number']}" if p.get("shirt_number") else "   "
            lines.append(f"  {num:4} id={p['id']:7}  {p['name']:30}  {p['nationality']:20}  age {age}")
        lines.append("")

    return "\n".join(lines)


@tool
def fetch_player_history(player_id: int) -> str:
    """
    Get a player's recent match appearances and performance context. Use this when
    you need to understand a specific player's workload or form — pass the player ID
    from fetch_squad. Note: the free API tier returns match history but not detailed
    per-match stats like goals/assists.
    """
    raw = _get(f"/persons/{player_id}/matches", params={"limit": 10}, cache_ttl=300)
    if "error" in raw:
        return f"Error: {raw['error']}"

    person = raw.get("person", {})
    matches = raw.get("matches", [])

    if not person and not matches:
        return f"No data found for player ID {player_id}."

    lines = [
        f"{person.get('name', 'Unknown')} — {person.get('position', 'N/A')} — {person.get('nationality', 'N/A')}",
        f"Recent appearances ({len(matches)}):",
        "",
    ]
    for m in matches[:10]:
        home = m.get("homeTeam", {}).get("name", "?")
        away = m.get("awayTeam", {}).get("name", "?")
        score_ft = m.get("score", {}).get("fullTime", {})
        score_str = f"{score_ft.get('home')}-{score_ft.get('away')}"
        lines.append(f"  {m.get('utcDate','')[:10]}  {home} {score_str} {away}  ({m.get('competition',{}).get('name','')})")

    return "\n".join(lines)


@tool
def fetch_head_to_head(team1_id: int, team2_id: int) -> str:
    """
    Get historical results between two teams. Use this to understand which side
    has the psychological edge, typical scorelines, and recent trends in this matchup.
    """
    data = get_head_to_head(team1_id, team2_id)
    if "error" in data:
        return f"Error: {data['error']}"

    lines = [
        f"{data['team1']} vs {data['team2']} — last {data['total_meetings']} meetings",
        f"{data['team1']}: {data['team1_wins']}W  |  Draws: {data['draws']}  |  {data['team2']}: {data['team2_wins']}W",
        f"Goals: {data['team1']} {data['team1_goals']} — {data['team2_goals']} {data['team2']}",
        "",
    ]
    for m in data["matches"]:
        lines.append(f"  {m['date']}  {m['home_team']} {m['score']} {m['away_team']}  → {m['winner']}  ({m['competition']})")

    return "\n".join(lines)


@tool
def compare_players(player1_name: str, team1_id: int, player2_name: str, team2_id: int) -> str:
    """
    Compare two players side by side using squad data — position, age, nationality.
    Useful when choosing between a starting player and a substitute, or comparing
    a player from each team at the same position. Names are case-insensitive partial matches.
    """
    squad1 = get_team_squad(team1_id)
    squad2 = get_team_squad(team2_id)

    if "error" in squad1:
        return f"Error fetching team {team1_id}: {squad1['error']}"
    if "error" in squad2:
        return f"Error fetching team {team2_id}: {squad2['error']}"

    p1 = _find_player(squad1, player1_name)
    p2 = _find_player(squad2, player2_name)

    if not p1:
        return f"Could not find '{player1_name}' in {squad1['team_name']}'s squad."
    if not p2:
        return f"Could not find '{player2_name}' in {squad2['team_name']}'s squad."

    age1 = _age_from_dob(p1.get("date_of_birth", ""))
    age2 = _age_from_dob(p2.get("date_of_birth", ""))

    lines = [
        f"Player comparison:",
        f"  {'Name':25} {p1['name']:30} {p2['name']}",
        f"  {'Team':25} {squad1['team_name']:30} {squad2['team_name']}",
        f"  {'Position':25} {p1.get('position','?'):30} {p2.get('position','?')}",
        f"  {'Nationality':25} {p1.get('nationality','?'):30} {p2.get('nationality','?')}",
        f"  {'Age':25} {str(age1):30} {str(age2)}",
        f"  {'Shirt number':25} {str(p1.get('shirt_number','?')):30} {str(p2.get('shirt_number','?'))}",
        f"  {'Player ID':25} {str(p1.get('id','?')):30} {str(p2.get('id','?'))}",
    ]
    return "\n".join(lines)


@tool
def fetch_standings(competition_id: str) -> str:
    """
    Get the current league table for a competition. Use this to understand the stakes —
    title race, European spots, relegation battles — which should inform how aggressive
    or defensive a team's tactics should be. Common IDs: PL, CL, BL1, SA, PD, FL1.
    """
    data = get_standings(competition_id)
    if "error" in data:
        return f"Error: {data['error']}"

    lines = [
        f"{data['competition']} — {data['season']}/{int(data['season'])+1} standings",
        f"{'Pos':3} {'Team':28} {'P':3} {'W':3} {'D':3} {'L':3} {'GF':4} {'GA':4} {'GD':4} {'Pts':4} {'Form'}",
        "-" * 80,
    ]
    for row in data["standings"]:
        lines.append(
            f"{row['position']:3} {(row['team'] or '?'):28} "
            f"{row['played']:3} {row['won']:3} {row['drawn']:3} {row['lost']:3} "
            f"{row['goals_for']:4} {row['goals_against']:4} {row['goal_difference']:+4} "
            f"{row['points']:4}  {row['form'] or ''}"
        )

    return "\n".join(lines)


# exposed list for the agent
all_tools = [
    find_team,
    fetch_live_matches,
    fetch_match_stats,
    fetch_team_form,
    fetch_squad,
    fetch_player_history,
    fetch_head_to_head,
    compare_players,
    fetch_standings,
]


def _find_player(squad_data: dict, name: str) -> dict | None:
    name_lower = name.lower()
    for group in squad_data["squad_by_position"].values():
        for p in group:
            if name_lower in (p.get("name") or "").lower():
                return p
    return None


def _age_from_dob(dob: str) -> int | str:
    if not dob:
        return "?"
    try:
        from datetime import date
        born = date.fromisoformat(dob)
        today = date.today()
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    except Exception:
        return "?"
