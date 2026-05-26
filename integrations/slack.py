"""
Slack integration — posts weekly digest and error summaries.
"""

import logging
import os
from datetime import datetime, timezone

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

log = logging.getLogger(__name__)

STAGE_EMOJI = {
    "Announced":          "📢",
    "Early Stage":        "🔍",
    "Planned":            "📋",
    "Under Construction": "🏗️",
    "Operational":        "✅",
    "On Hold":            "⏸️",
    "Cancelled":          "❌",
}


class SlackClient:
    def __init__(self):
        token = os.environ.get("SLACK_BOT_TOKEN")
        if not token:
            raise EnvironmentError(
                "SLACK_BOT_TOKEN env var not set. "
                "See skill/references/setup.md for instructions."
            )
        self._client = WebClient(token=token)

    def post_digest(self, channel, region_name, new_rows, stage_updates,
                    total_rows, file_url, summary):
        today = datetime.now(timezone.utc).strftime("%B %d, %Y")
        drive_url = file_url

        blocks = []

        blocks.append({
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"⚡ {region_name} — Weekly Grid Update ({today})",
            },
        })

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"_{summary}_"},
        })

        blocks.append({"type": "divider"})

        if new_rows:
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🆕 {len(new_rows)} New Project(s)*",
                },
            })
            for row in new_rows[:10]:
                mw = f"{row['size_mw']:.0f} MW" if row.get("size_mw") else "MW TBD"
                stage = row.get("stage", "Unknown")
                emoji = STAGE_EMOJI.get(stage, "•")
                name = row.get("name", "Unknown")
                loc = f"{row.get('county', '')} {row.get('state', '')}".strip()
                dev = row.get("developer") or "Unknown developer"
                src = row.get("source", "")

                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"{emoji} *{name}*\n"
                            f"  {loc} • {dev} • {mw} • {stage}\n"
                            f"  _Source: {src}_"
                        ),
                    },
                })

            if len(new_rows) > 10:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"_...and {len(new_rows) - 10} more — see full file in Drive_",
                    },
                })

        if stage_updates:
            blocks.append({"type": "divider"})
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🔄 {len(stage_updates)} Stage Change(s)*",
                },
            })
            for update in stage_updates[:5]:
                old = update.get("old_stage", "?")
                new = update.get("new_stage", "?")
                emoji = STAGE_EMOJI.get(new, "•")
                name = update.get("name", "Unknown")
                notes = update.get("notes", "")
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"{emoji} *{name}*: {old} → *{new}*\n  _{notes}_",
                    },
                })

        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"📊 Total dataset: *{total_rows} rows*  |  "
                    f"<{drive_url}|View full CSV>"
                ),
            },
        })

        self._post(channel=channel, blocks=blocks)

    def post_error_summary(self, channel, errors):
        today = datetime.now(timezone.utc).strftime("%B %d, %Y")
        lines = [f"*⚠️ Large Load Agent — {len(errors)} error(s) on {today}*\n"]
        for region_id, err in errors:
            lines.append(f"• *{region_id}:* `{err}`")
        lines.append("\nCheck GitHub Actions logs for details.")

        self._post(
            channel=channel,
            blocks=[{
                "type": "section",
                "text": {"type": "mrkdwn", "text": "\n".join(lines)},
            }],
        )

    def _post(self, channel, blocks):
        try:
            self._client.chat_postMessage(channel=channel, blocks=blocks)
            log.info(f"Slack message posted to {channel}")
        except SlackApiError as e:
            log.error(f"Slack API error: {e.response['error']}")
            raise
