"""Data layer: wraps the football-data.org v4 API."""

from .client import (
    get_live_matches,
    get_match_details,
    get_team_recent_form,
    get_team_squad,
    get_head_to_head,
    get_standings,
)

__all__ = [
    "get_live_matches",
    "get_match_details",
    "get_team_recent_form",
    "get_team_squad",
    "get_head_to_head",
    "get_standings",
]
