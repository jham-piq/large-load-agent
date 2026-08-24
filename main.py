#!/usr/bin/env python3
"""
Large Load Agent — Weekly Research Orchestrator
Runs every Monday via GitHub Actions. For each region in config.yaml:
  1. Downloads existing CSV from Google Drive
  2. Runs full or delta research via Claude API
  3. Merges new rows / applies stage updates
  4. Uploads updated CSV to Google Drive
  5. Posts digest to Slack
"""

import argparse
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from integrations.drive import DriveClient
from integrations.slack import SlackClient
from research.agent import ResearchAgent
from research.insights import update_insights
from research.merge import merge_results

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).parent / "config.yaml"
SEARCH_LOG = Path(__file__).parent / "research" / "SEARCH_LOG.md"


def append_search_log(region_name, mode, new_rows, stage_updates):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"\n## {today} — {region_name} ({mode} run)\n"]

    if new_rows:
        lines.append(f"### New projects (+{len(new_rows)})\n")
        for row in new_rows:
            mw = f", {row['size_mw']:.0f} MW" if row.get("size_mw") else ""
            lines.append(f"- **{row.get('name', 'Unknown')}** ({row.get('state', '?')}, {row.get('stage', '?')}{mw})")
            lines.append(f"  - Source: {row.get('source', 'Unknown')}")
            found_via = row.get("found_via", "").strip()
            if found_via:
                lines.append(f"  - Found via: {found_via}")
        lines.append("")

    if stage_updates:
        lines.append(f"### Stage updates ({len(stage_updates)})\n")
        for u in stage_updates:
            lines.append(f"- **{u.get('name')}**: {u.get('old_stage')} → {u.get('new_stage')}")
            if u.get("notes"):
                lines.append(f"  - {u.get('notes')}")
        lines.append("")

    with open(SEARCH_LOG, "a") as f:
        f.write("\n".join(lines))
    log.info(f"Search log updated: {SEARCH_LOG}")


def load_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


def run_region(region, cfg, drive, slack, agent, dry_run, mode_override):
    region_id = region["id"]
    region_name = region["name"]
    log.info(f"{'='*60}")
    log.info(f"Starting region: {region_name}")

    file_id = region.get("drive_file_id")
    last_run = region.get("last_run")
    mode = mode_override or region.get("mode", "auto")

    if mode == "auto":
        mode = "full" if not file_id else "delta"

    log.info(f"Mode: {mode}  |  Drive file: {file_id or 'NEW'}")

    existing_df = drive.download_csv(file_id) if file_id else None

    result = agent.research(
        region=region,
        existing_df=existing_df,
        mode=mode,
        since_date=last_run,
    )

    new_rows = result.get("new_rows", [])
    stage_updates = result.get("stage_updates", [])
    summary = result.get("summary", "")

    log.info(f"Research complete: {len(new_rows)} new rows, {len(stage_updates)} stage updates")

    if not new_rows and not stage_updates:
        log.info("Nothing new — skipping Drive write and Slack post")
        return

    updated_df = merge_results(
        existing_df=existing_df,
        new_rows=new_rows,
        stage_updates=stage_updates,
        region_id=region_id,
    )

    log.info(f"Merged CSV: {len(updated_df)} total rows")

    append_search_log(region_name, mode, new_rows, stage_updates)
    update_insights(region_id, new_rows, stage_updates)

    if dry_run:
        log.info("DRY RUN — skipping Drive upload and Slack post")
        print(updated_df.tail(10).to_string())
        return

    new_file_path = drive.upload_csv(
        df=updated_df,
        file_path=file_id,
        filename=f"{region_id}_Large_Load_Projects.csv",
    )

    region["drive_file_id"] = new_file_path
    region["last_run"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_config(cfg)

    file_url = drive.get_file_url(new_file_path)
    channel = region.get("slack_channel") or cfg["agent"]["slack_channel"]
    slack.post_digest(
        channel=channel,
        region_name=region_name,
        new_rows=new_rows,
        stage_updates=stage_updates,
        total_rows=len(updated_df),
        file_url=file_url,
        summary=summary,
    )

    log.info(f"Done: {region_name}")


def main():
    parser = argparse.ArgumentParser(description="Large Load Agent")
    parser.add_argument("--region", help="Run a single region by ID (e.g. NYISO)")
    parser.add_argument("--mode", choices=["full", "delta"], help="Override run mode")
    parser.add_argument("--dry-run", action="store_true", help="Skip Drive/Slack writes")
    args = parser.parse_args()

    cfg = load_config()

    drive = DriveClient()
    slack = SlackClient() if not args.dry_run else None
    agent = ResearchAgent(model=cfg["agent"]["model"])

    regions = cfg["regions"]
    if args.region:
        regions = [r for r in regions if r["id"].upper() == args.region.upper()]
        if not regions:
            log.error(f"Region '{args.region}' not found in config.yaml")
            sys.exit(1)

    log.info(f"Running {len(regions)} region(s): {[r['id'] for r in regions]}")

    errors = []
    for i, region in enumerate(regions):
        if i > 0:
            time.sleep(15)  # avoid rate limits between regions
        try:
            run_region(
                region=region,
                cfg=cfg,
                drive=drive,
                slack=slack,
                agent=agent,
                dry_run=args.dry_run,
                mode_override=args.mode,
            )
        except Exception as e:
            log.exception(f"Error processing {region['id']}: {e}")
            errors.append((region["id"], str(e)))

    if errors:
        log.error(f"Completed with {len(errors)} error(s):")
        for region_id, err in errors:
            log.error(f"  {region_id}: {err}")
        if slack:
            slack.post_error_summary(
                channel=cfg["agent"]["slack_channel"],
                errors=errors,
            )
        sys.exit(1)

    log.info("All regions complete.")


if __name__ == "__main__":
    main()
