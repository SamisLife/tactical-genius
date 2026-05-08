"""The agent brain — a LangGraph ReAct loop powered by Gemini."""

import os
from typing import Iterator

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from dotenv import load_dotenv

from ..tools import all_tools

load_dotenv()

SYSTEM_PROMPT = """You are Tactical Genius, an elite AI soccer analyst and co-manager.

You have tools to fetch live match data, team form, squad info, head-to-head records, and league standings.
When asked to analyze a match or recommend tactics, always gather data before drawing conclusions — never guess.

Your recommendations should be specific: what to change, why the data supports it, and what impact to expect.
Think like a world-class manager: consider fatigue, form, matchup advantages, game state, and what's at stake.

When you need a team ID, always call find_team first with the team's name — never guess IDs.
When you need a player ID, call fetch_squad to get the full squad with IDs, then use those."""


def build_agent():
    # gemini-2.5-flash is the recommended free-tier model as of mid-2025
    # override with GEMINI_MODEL in .env (e.g. gemini-2.5-flash-lite for lighter usage)
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    model = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )
    return create_react_agent(
        model=model,
        tools=all_tools,
        prompt=SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )


# single shared instance — memory persists across calls within the same process
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def stream_query(query: str, thread_id: str = "default") -> Iterator[dict]:
    """
    Stream the agent's reasoning step by step.
    Yields dicts with keys: "type" (tool_call | tool_result | answer), "content".
    """
    agent = _get_agent()
    config = {"configurable": {"thread_id": thread_id}}

    for chunk in agent.stream(
        {"messages": [("user", query)]},
        config=config,
        stream_mode="updates",
    ):
        # chunk is {"agent": {...}} or {"tools": {...}}
        if "agent" in chunk:
            msg = chunk["agent"]["messages"][-1]
            # tool calls show up as AIMessage with tool_calls populated
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                for tc in msg.tool_calls:
                    yield {"type": "tool_call", "name": tc["name"], "args": tc["args"]}
            elif msg.content:
                content = msg.content
                if isinstance(content, list):
                    content = "\n".join(
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in content
                    )
                yield {"type": "answer", "content": content}

        elif "tools" in chunk:
            for msg in chunk["tools"]["messages"]:
                yield {"type": "tool_result", "name": msg.name, "content": msg.content}
