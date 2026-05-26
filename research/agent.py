"""
Research Agent — calls OpenAI GPT-4o with web search enabled.
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from openai import OpenAI

from research.insights import render_insights

log = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent


class ResearchAgent:
    def __init__(self, model="gpt-4o-search-preview"):
        self.model = model
        self.client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
        self.delta_prompt = (PROMPTS_DIR / "delta_prompt.md").read_text()
        self.full_prompt = (PROMPTS_DIR / "full_prompt.md").read_text()

    def _render(self, template, **kwargs):
        result = template
        for key, value in kwargs.items():
            result = result.replace("{" + key + "}", str(value))
        return result

    def research(self, region, existing_df, mode, since_date):
        if mode == "full":
            return self._full_run(region, existing_df)
        else:
            return self._delta_run(region, existing_df, since_date)

    def _delta_run(self, region, existing_df, since_date):
        today = datetime.now().strftime("%Y-%m-%d")
        since = since_date or "last week"
        existing_summary = self._summarise_existing(existing_df)
        states = region.get("states", [])
        state_searches = "\n".join(
            f'- `{s} data center announced planned 2026`' for s in states
        )
        system = (
            "You are a power grid research analyst specializing in large electrical load "
            "projects (data centers, AI campuses, crypto mining, industrial). "
            "Search for new announcements and report ONLY what is genuinely new. "
            "Always respond with valid JSON matching the specified schema exactly. "
            "No preamble, no explanation outside the JSON."
        )
        search_insights = render_insights(region["id"], states)
        user = self._render(
            self.delta_prompt,
            region_id=region["id"],
            region_name=region["name"],
            states=", ".join(states),
            states_for_search=" OR ".join(states),
            state_abbrevs=", ".join(region.get("state_abbrevs", [])),
            utilities=", ".join(region.get("utilities", [])),
            since_date=since,
            today=today,
            existing_summary=existing_summary,
            state_searches=state_searches,
            search_insights=search_insights,
        )
        return self._call_openai(system=system, user=user)

    def _full_run(self, region, existing_df):
        today = datetime.now().strftime("%Y-%m-%d")
        system = (
            "You are a power grid research analyst specializing in large electrical load "
            "projects. Run a comprehensive research pass on the given region. "
            "Always respond with valid JSON matching the specified schema exactly. "
            "No preamble, no explanation outside the JSON."
        )
        user = self._render(
            self.full_prompt,
            region_id=region["id"],
            region_name=region["name"],
            states=", ".join(region.get("states", [])),
            state_abbrevs=", ".join(region.get("state_abbrevs", [])),
            utilities=", ".join(region.get("utilities", [])),
            today=today,
        )
        return self._call_openai(system=system, user=user)

    def _call_openai(self, system, user):
        log.info("Calling OpenAI API (gpt-4o-search-preview)...")
        response = self.client.chat.completions.create(
            model="gpt-4o-search-preview",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        log.info(f"  finish_reason={response.choices[0].finish_reason}")
        text = response.choices[0].message.content or ""
        return self._parse_response(text)

    def _parse_response(self, text):
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                try:
                    data = json.loads(match.group())
                except json.JSONDecodeError:
                    log.warning("Could not parse JSON from OpenAI response")
                    data = {}
            else:
                log.warning("No JSON found in OpenAI response")
                data = {}
        data.setdefault("new_rows", [])
        data.setdefault("stage_updates", [])
        data.setdefault("summary", "")
        return data

    def _summarise_existing(self, df):
        if df is None or df.empty:
            return "No existing data."
        non_op = df[~df["stage"].isin(["Operational", "Cancelled"])]
        lines = ["Existing non-operational projects (DO NOT re-add these):"]
        for _, row in non_op.iterrows():
            mw = f"{row['size_mw']:.0f} MW" if pd.notna(row.get("size_mw")) else "MW unknown"
            lines.append(
                f"  - {row['name']} | {row.get('county', '?')} {row['state']} | "
                f"{mw} | {row['stage']}"
            )
        total = len(df)
        op = len(df[df["stage"] == "Operational"])
        lines.append(f"\nTotal rows: {total} ({op} operational, {len(non_op)} in pipeline)")
        return "\n".join(lines)
