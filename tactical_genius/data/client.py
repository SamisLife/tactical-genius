"""football-data.org v4 API wrapper. Errors always return {"error": "..."} so the agent can keep going."""

import os
import time
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

_BASE = "https://api.football-data.org/v4"
_HEADERS = {"X-Auth-Token": os.getenv("FOOTBALL_DATA_API_KEY", "")}

_cache: dict[str, tuple[float, Any]] = {}
_CACHE_TTL = 60  # seconds


def _get(path: str, params: dict | None = None, cache_ttl: int = _CACHE_TTL) -> dict:
    cache_key = path + str(sorted((params or {}).items()))
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if time.time() - ts < cache_ttl:
            return data

    try:
        resp = requests.get(f"{_BASE}{path}", headers=_HEADERS, params=params or {}, timeout=10)
    except requests.exceptions.RequestException as exc:
        return {"error": f"Network error: {exc}"}

    if resp.status_code == 429:
        return {"error": "Rate limit hit — wait a minute and retry."}
    if resp.status_code == 403:
        return {"error": "Bad or missing FOOTBALL_DATA_API_KEY."}
    if resp.status_code == 404:
        return {"error": f"Not found: {path}"}
    if not resp.ok:
        return {"error": f"API error {resp.status_code}: {resp.text[:200]}"}

    data = resp.json()
    _cache[cache_key] = (time.time(), data)
    return data


def search_team(name: str, limit: int = 5) -> dict:
    """Search for a team by name. Returns best matches sorted by name similarity."""
    raw = _get("/teams", params={"name": name}, cache_ttl=3600)
    if "error" in raw:
        return raw

    query = name.lower().strip()

    def score(t: dict) -> int:
        n = (t.get("name") or "").lower()
        sn = (t.get("shortName") or "").lower()
        if n == query or sn == query:
            return 3
        if n.startswith(query) or sn.startswith(query):
            return 2
        return 1

    teams = sorted(raw.get("teams", []), key=score, reverse=True)[:limit]
    return {
        "count": len(teams),
        "teams": [
            {
                "id": t.get("id"),
                "name": t.get("name"),
                "short_name": t.get("shortName"),
                "tla": t.get("tla"),
                "area": t.get("area", {}).get("name"),
                "competitions": [c.get("name") for c in t.get("runningCompetitions", [])],
            }
            for t in teams
        ],
    }


def get_live_matches() -> dict:
    """All currently live matches."""
    raw = _get("/matches", params={"status": "LIVE"})
    if "error" in raw:
        return raw
    return {"count": len(raw.get("matches", [])), "matches": [_slim_match(m) for m in raw.get("matches", [])]}


def get_match_details(match_id: int) -> dict:
    """Score, lineups, referees, and H2H summary for a specific match."""
    raw = _get(f"/matches/{match_id}", cache_ttl=30)
    if "error" in raw:
        return raw

    m = raw
    result = {
        "id": m.get("id"),
        "competition": m.get("competition", {}).get("name", "Unknown"),
        "competition_id": m.get("competition", {}).get("id"),
        "season": m.get("season", {}).get("startDate", "")[:4],
        "utc_date": m.get("utcDate"),
        "status": m.get("status"),
        "matchday": m.get("matchday"),
        "stage": m.get("stage"),
        "group": m.get("group"),
        "home_team": m.get("homeTeam", {}).get("name"),
        "home_team_id": m.get("homeTeam", {}).get("id"),
        "away_team": m.get("awayTeam", {}).get("name"),
        "away_team_id": m.get("awayTeam", {}).get("id"),
        "score": {
            "home": m.get("score", {}).get("fullTime", {}).get("home"),
            "away": m.get("score", {}).get("fullTime", {}).get("away"),
            "half_time_home": m.get("score", {}).get("halfTime", {}).get("home"),
            "half_time_away": m.get("score", {}).get("halfTime", {}).get("away"),
            "winner": m.get("score", {}).get("winner"),
        },
        "minute": _extract_minute(m),
        "referees": [r.get("name") for r in m.get("referees", [])],
        "odds": m.get("odds"),
    }

    h2h_raw = raw.get("head2Head", {})
    if h2h_raw:
        result["head_to_head_summary"] = {
            "number_of_matches": h2h_raw.get("numberOfMatches"),
            "total_goals": h2h_raw.get("totalGoals"),
            "home_team_wins": h2h_raw.get("homeTeam", {}).get("wins"),
            "away_team_wins": h2h_raw.get("awayTeam", {}).get("wins"),
            "draws": h2h_raw.get("homeTeam", {}).get("draws"),
        }

    return result


def get_team_recent_form(team_id: int, last_n: int = 5) -> dict:
    """Last N finished matches for a team, with a form string like WWDLW."""
    # fetch double to account for cup games and gaps
    raw = _get(f"/teams/{team_id}/matches", params={"status": "FINISHED", "limit": max(last_n * 2, 10)})
    if "error" in raw:
        return raw

    team_name = ""
    results = []
    for m in raw.get("matches", [])[::-1]:  # API returns oldest first
        home_id = m.get("homeTeam", {}).get("id")
        home_score = m.get("score", {}).get("fullTime", {}).get("home", 0) or 0
        away_score = m.get("score", {}).get("fullTime", {}).get("away", 0) or 0

        if home_id == team_id:
            team_name = m.get("homeTeam", {}).get("name", "")
            team_goals, opp_goals = home_score, away_score
            opponent = m.get("awayTeam", {}).get("name", "Unknown")
            location = "HOME"
        else:
            team_name = m.get("awayTeam", {}).get("name", "")
            team_goals, opp_goals = away_score, home_score
            opponent = m.get("homeTeam", {}).get("name", "Unknown")
            location = "AWAY"

        result = "W" if team_goals > opp_goals else ("L" if team_goals < opp_goals else "D")

        results.append({
            "date": m.get("utcDate", "")[:10],
            "competition": m.get("competition", {}).get("name", ""),
            "opponent": opponent,
            "location": location,
            "score": f"{team_goals}-{opp_goals}",
            "result": result,
            "match_id": m.get("id"),
        })
        if len(results) == last_n:
            break

    wins = sum(1 for r in results if r["result"] == "W")
    draws = sum(1 for r in results if r["result"] == "D")
    losses = sum(1 for r in results if r["result"] == "L")
    goals_scored = sum(int(r["score"].split("-")[0]) for r in results)
    goals_conceded = sum(int(r["score"].split("-")[1]) for r in results)

    return {
        "team_id": team_id,
        "team_name": team_name,
        "form_string": "".join(r["result"] for r in reversed(results)),
        "matches": results,
        "summary": {
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_scored": goals_scored,
            "goals_conceded": goals_conceded,
            "clean_sheets": sum(1 for r in results if int(r["score"].split("-")[1]) == 0),
            "points": wins * 3 + draws,
        },
    }


def get_team_squad(team_id: int) -> dict:
    """Full squad grouped by position, plus coach info."""
    raw = _get(f"/teams/{team_id}", cache_ttl=3600)
    if "error" in raw:
        return raw

    coach = raw.get("coach", {})
    squad = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "position": p.get("position"),
            "nationality": p.get("nationality"),
            "date_of_birth": p.get("dateOfBirth", "")[:10],
            "shirt_number": p.get("shirtNumber"),
        }
        for p in raw.get("squad", [])
    ]

    return {
        "team_id": team_id,
        "team_name": raw.get("name"),
        "short_name": raw.get("shortName"),
        "crest": raw.get("crest"),
        "venue": raw.get("venue"),
        "founded": raw.get("founded"),
        "coach": {"name": coach.get("name"), "nationality": coach.get("nationality")},
        "squad_by_position": {
            "goalkeepers": [p for p in squad if p["position"] == "Goalkeeper"],
            "defenders": [p for p in squad if p["position"] == "Defence"],
            "midfielders": [p for p in squad if p["position"] == "Midfield"],
            "attackers": [p for p in squad if p["position"] in ("Offence", "Attack", "Forward")],
        },
        "squad_count": len(squad),
    }


def get_head_to_head(team1_id: int, team2_id: int, limit: int = 10) -> dict:
    """Historical matchups between two teams, built by cross-referencing both teams' match histories."""
    raw1 = _get(f"/teams/{team1_id}/matches", params={"status": "FINISHED", "limit": 50})
    raw2 = _get(f"/teams/{team2_id}/matches", params={"status": "FINISHED", "limit": 50})

    if "error" in raw1:
        return raw1
    if "error" in raw2:
        return raw2

    team2_match_ids = {m.get("id") for m in raw2.get("matches", [])}
    team1_name = ""
    team2_name = ""
    h2h_matches = []

    for m in raw1.get("matches", []):
        if m.get("id") not in team2_match_ids:
            continue

        home_id = m.get("homeTeam", {}).get("id")
        home_name = m.get("homeTeam", {}).get("name", "")
        away_name = m.get("awayTeam", {}).get("name", "")
        home_goals = m.get("score", {}).get("fullTime", {}).get("home", 0) or 0
        away_goals = m.get("score", {}).get("fullTime", {}).get("away", 0) or 0

        if home_id == team1_id:
            team1_name, team2_name = home_name, away_name
        else:
            team1_name, team2_name = away_name, home_name

        winner_raw = m.get("score", {}).get("winner")
        winner = home_name if winner_raw == "HOME_TEAM" else (away_name if winner_raw == "AWAY_TEAM" else "Draw")

        h2h_matches.append({
            "date": m.get("utcDate", "")[:10],
            "competition": m.get("competition", {}).get("name", ""),
            "home_team": home_name,
            "away_team": away_name,
            "score": f"{home_goals}-{away_goals}",
            "winner": winner,
            "match_id": m.get("id"),
        })
        if len(h2h_matches) == limit:
            break

    if not h2h_matches:
        return {"error": f"No H2H matches found in the last 50 games for team {team1_id} and team {team2_id}."}

    t1_wins = sum(1 for m in h2h_matches if m["winner"] == team1_name)
    t2_wins = sum(1 for m in h2h_matches if m["winner"] == team2_name)

    t1_total_goals, t2_total_goals = 0, 0
    for m in h2h_matches:
        hg, ag = int(m["score"].split("-")[0]), int(m["score"].split("-")[1])
        if m["home_team"] == team1_name:
            t1_total_goals += hg
            t2_total_goals += ag
        else:
            t1_total_goals += ag
            t2_total_goals += hg

    return {
        "team1": team1_name or str(team1_id),
        "team2": team2_name or str(team2_id),
        "total_meetings": len(h2h_matches),
        "team1_wins": t1_wins,
        "team2_wins": t2_wins,
        "draws": len(h2h_matches) - t1_wins - t2_wins,
        "team1_goals": t1_total_goals,
        "team2_goals": t2_total_goals,
        "matches": h2h_matches,
    }


def get_standings(competition_id: str | int) -> dict:
    """
    League table for a competition.

    Common IDs: PL (Premier League), CL (Champions League), BL1 (Bundesliga),
    SA (Serie A), PD (La Liga), FL1 (Ligue 1)
    """
    raw = _get(f"/competitions/{competition_id}/standings", cache_ttl=300)
    if "error" in raw:
        return raw

    entries = []
    for table in raw.get("standings", []):
        if table.get("type") != "TOTAL":
            continue
        for row in table.get("table", []):
            entries.append({
                "position": row.get("position"),
                "team": row.get("team", {}).get("name"),
                "team_id": row.get("team", {}).get("id"),
                "played": row.get("playedGames"),
                "won": row.get("won"),
                "drawn": row.get("draw"),
                "lost": row.get("lost"),
                "goals_for": row.get("goalsFor"),
                "goals_against": row.get("goalsAgainst"),
                "goal_difference": row.get("goalDifference"),
                "points": row.get("points"),
                "form": row.get("form"),
            })
        break  # only need TOTAL, not HOME/AWAY splits

    return {
        "competition": raw.get("competition", {}).get("name"),
        "competition_id": competition_id,
        "season": raw.get("season", {}).get("startDate", "")[:4],
        "standings": entries,
    }


def _slim_match(m: dict) -> dict:
    return {
        "id": m.get("id"),
        "competition": m.get("competition", {}).get("name", "Unknown"),
        "competition_id": m.get("competition", {}).get("id"),
        "home_team": m.get("homeTeam", {}).get("name"),
        "home_team_id": m.get("homeTeam", {}).get("id"),
        "away_team": m.get("awayTeam", {}).get("name"),
        "away_team_id": m.get("awayTeam", {}).get("id"),
        "score": {
            "home": m.get("score", {}).get("fullTime", {}).get("home"),
            "away": m.get("score", {}).get("fullTime", {}).get("away"),
        },
        "minute": _extract_minute(m),
        "status": m.get("status"),
        "utc_date": m.get("utcDate"),
    }


def _extract_minute(m: dict) -> int | None:
    for key in ("minute", "currentPeriodStartedAt"):
        if m.get(key):
            return m.get(key)
    return None
