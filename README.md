# Tactical Genius

An AI agent that acts as a soccer co-manager. Give it a team name, ask it to analyze a match, and it autonomously figures out what data to pull, calls the right APIs, and comes back with tactical recommendations, substitutions, formation changes, pressing adjustments. Backed by actual numbers.

---

## What it actually does

You type something like *"analyze Real Madrid's last 5 matches and suggest a formation change"*. The agent decides on its own to:

1. Look up Real Madrid's team ID
2. Fetch their recent match results
3. Pull the current La Liga standings to understand what's at stake
4. Optionally check squad depth before recommending a specific change

The agent decides what to look up, in what order, and when it has enough information to make a call.

```
You: analyze arsenal's last 5 matches and suggest a formation change

  🔧 find_team(name=Arsenal)
     ↳ Found 1 team(s) matching 'Arsenal'...
  🔧 fetch_team_form(team_id=57, last_n=5)
     ↳ Arsenal — last 5 matches...
  🔧 fetch_standings(competition_id=PL)
     ↳ Premier League — 2024/2025 standings...
  🔧 fetch_squad(team_id=57)
     ↳ Arsenal FC (founded 1886) — 28 players...

╭─────────────────── Tactical Genius ───────────────────╮
│ Based on Arsenal's recent form (WDWLW) and their       │
│ current 2nd place position, here's what I'd change...  │
╰────────────────────────────────────────────────────────╯
```

---

## Stack

- **[LangGraph](https://github.com/langchain-ai/langgraph)** — the agent loop (ReAct pattern)
- **[Google Gemini](https://ai.google.dev/)** — the reasoning model (`gemini-2.5-flash` by default)
- **[football-data.org](https://www.football-data.org/)** — match data, standings, squad info (free tier)
- **[Rich](https://github.com/Textualize/rich)** — terminal UI

---

## Setup

You need two free API keys before anything works.

**football-data.org** — register at [football-data.org/client/register](https://www.football-data.org/client/register). Free tier gives you 10 requests/minute and covers the major leagues (PL, La Liga, Bundesliga, Serie A, Ligue 1, Champions League).

**Google AI (Gemini)** — get a key at [aistudio.google.com](https://aistudio.google.com/app/apikey).

```bash
git clone <repo>
cd tactical-genius

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux

pip install -e .

cp .env.example .env
# open .env and add your two API keys
```

---

## Running it

```bash
# test the data layer first (no Gemini needed)
python test_data_layer.py

# run the agent
python test_agent.py
```

Type `reset` to clear memory and start a new session. Type `quit` to exit.

---

## Project structure

```
tactical_genius/
├── data/
│   └── client.py      # football-data.org API wrapper with caching
├── tools/
│   └── football.py    # LangChain tools the agent can call
└── agent/
    └── brain.py       # LangGraph ReAct loop + Gemini
```

The data layer and the tools are deliberately separate. The data layer is plain Python functions that return dicts - easy to test and swap out. The tools layer wraps those into LangChain `@tool` functions with docstrings that tell the agent *when* to use each one.

---

## Known limitations

**Tool calls are sequential.** The ReAct loop calls one tool at a time and waits for each result before deciding the next step. A full analysis that needs form + squad + standings + H2H runs those fetches one by one, usually 10–20 seconds end to end. LangGraph supports parallel tool calls when the LLM emits multiple at once, but getting Gemini to do that consistently is an open problem.

**Player stats aren't in the free API.** football-data.org's free tier gives you match results and squad profiles, not per-match stats like goals or assists. When the agent recommends specific players, those names come from Gemini's training knowledge rather than a verified API call. It flags this when asked directly, but the attribution isn't always obvious in the answer.

**Long sessions get slower.** Every tool result gets added to the conversation thread permanently. After 10–15 turns the model is processing 40,000+ tokens per request, which compounds latency. There's no summarisation or trimming in place yet.

---

## Available tools

| Tool | What it does |
|------|-------------|
| `find_team` | Resolves a team name to an ID. Hits a local lookup table for ~80 major clubs before falling back to the API. |
| `fetch_live_matches` | Returns all currently live matches with scores and match IDs. |
| `fetch_match_stats` | Score, half-time score, stage, referees, and H2H summary for a specific match. |
| `fetch_team_form` | Last N results with a form string (WWDLW), goal stats, and per-match breakdown. |
| `fetch_squad` | Full squad grouped by position, with player IDs, ages, and nationalities. |
| `fetch_player_history` | Recent match appearances for a player (ID from `fetch_squad`). |
| `fetch_head_to_head` | Historical results between two teams. |
| `compare_players` | Side-by-side profile comparison for two players. |
| `fetch_standings` | Full league table for a competition. |
