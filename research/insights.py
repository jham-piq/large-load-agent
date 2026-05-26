"""
Search insights tracker.

After each run: records which queries, sources, and states found new projects.
Before each run: renders a markdown summary that gets injected into the prompt
so the model searches more effectively over time.
"""

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

INSIGHTS_PATH = Path(__file__).parent.parent / "data" / "search_insights.json"
TOP_N = 10


def _load() -> dict:
    if INSIGHTS_PATH.exists():
        with open(INSIGHTS_PATH) as f:
            return json.load(f)
    return {}


def _save(data: dict):
    INSIGHTS_PATH.parent.mkdir(exist_ok=True)
    with open(INSIGHTS_PATH, "w") as f:
        json.dump(data, f, indent=2)


def update_insights(region_id: str, new_rows: list, stage_updates: list):
    """Record what worked in this run."""
    data = _load()
    region = data.setdefault(region_id, {
        "total_runs": 0,
        "total_finds": 0,
        "sources": {},
        "queries": {},
        "states_with_finds": {},
        "states_no_finds_streak": {},
        "last_updated": None,
    })

    region["total_runs"] += 1
    region["total_finds"] += len(new_rows)
    region["last_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    states_found_this_run = set()

    for row in new_rows:
        # Track sources
        source = row.get("source", "").strip()
        if source:
            pub = source.split("(")[0].strip()
            region["sources"][pub] = region["sources"].get(pub, 0) + 1

        # Track queries that found things
        found_via = row.get("found_via", "").strip()
        if found_via:
            region["queries"][found_via] = region["queries"].get(found_via, 0) + 1

        # Track states
        state = row.get("state", "").strip()
        if state:
            region["states_with_finds"][state] = region["states_with_finds"].get(state, 0) + 1
            states_found_this_run.add(state)

    # Update no-find streaks: increment for states that didn't find anything, reset for those that did
    all_known_states = set(region["states_with_finds"].keys()) | set(region["states_no_finds_streak"].keys())
    for state in all_known_states:
        if state in states_found_this_run:
            region["states_no_finds_streak"][state] = 0
        else:
            region["states_no_finds_streak"][state] = region["states_no_finds_streak"].get(state, 0) + 1

    _save(data)
    log.info(f"Insights updated for {region_id}")


def render_insights(region_id: str, all_states: list) -> str:
    """Return a markdown block summarising past search performance for the region."""
    data = _load()
    region = data.get(region_id)

    if not region or region["total_runs"] < 1:
        return ""

    lines = ["## Search Intelligence (from prior runs)\n"]

    # Top sources
    if region["sources"]:
        top_sources = sorted(region["sources"].items(), key=lambda x: -x[1])[:TOP_N]
        lines.append("**High-signal sources** (prioritise these):")
        for src, count in top_sources:
            lines.append(f"- {src}: {count} find(s)")
        lines.append("")

    # Top queries
    if region["queries"]:
        top_queries = sorted(region["queries"].items(), key=lambda x: -x[1])[:TOP_N]
        lines.append("**Search queries that found new projects** (re-use and vary these):")
        for q, count in top_queries:
            lines.append(f"- `{q}` → {count} find(s)")
        lines.append("")

    # States with no finds streak >= 2
    cold_states = [
        s for s in all_states
        if region["states_no_finds_streak"].get(s, 0) >= 2
    ]
    if cold_states:
        lines.append(f"**Coverage gaps** (no finds in 2+ runs — search harder): {', '.join(sorted(cold_states))}\n")

    # States with most finds
    if region["states_with_finds"]:
        hot_states = sorted(region["states_with_finds"].items(), key=lambda x: -x[1])[:5]
        lines.append("**Most active states** (check for updates and stage changes):")
        for state, count in hot_states:
            lines.append(f"- {state}: {count} find(s) historically")
        lines.append("")

    lines.append(f"_(Based on {region['total_runs']} prior run(s), {region['total_finds']} total finds)_\n")

    return "\n".join(lines)
