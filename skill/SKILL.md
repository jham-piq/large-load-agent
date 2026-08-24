---
name: large-load-agent
description: >
  Weekly agentic workflow that researches large electrical load projects (data centers, AI
  campuses, industrial loads) for grid planning. Runs every Monday via GitHub Actions: reads
  existing regional CSVs from the git repo (data/ folder), searches for new projects announced
  since the prior week using GPT-5.6 with web search, appends new rows, updates stage changes,
  and posts a digest to Slack. The CSVs are committed back to the repo after each run so they
  serve as the baseline for the next run. Use this skill whenever the user asks to run the
  weekly large load agent, update a region's data, check for new data center announcements,
  or trigger the Monday research job. Also use it when the user asks to add a new region.
---

# Large Load Agent — Weekly Research Skill

Researches large electrical load projects across US grid regions.
Runs in two modes: full (first run for a new region) and delta (weekly updates).

## Quick Reference

- Run script:    python main.py [--region NYISO] [--mode full|delta] [--dry-run]
- Add a region:  Edit config.yaml, set drive_file_id to the CSV path in data/, trigger a run
- Load baseline: Copy existing CSV to data/<REGION>_Large_Load_Projects.csv, set drive_file_id
- Force re-run:  python main.py --region NYISO --mode full
- Check logs:    GitHub Actions → Actions tab → latest Monday run

## How It Works

Every Monday 9am UTC (GitHub Actions cron)
  For each region in config.yaml:
    1. Read existing CSV from data/<REGION>_Large_Load_Projects.csv (committed in git)
       No CSV (drive_file_id: null) → run FULL mode (comprehensive first run)
       CSV exists                  → run DELTA mode (search for what's new since last run)
    2. GPT-5.6 (Responses API web search) searches for new announcements and stage changes
    3. Merge new rows into existing CSV (dedup on name+phase)
    4. Save updated CSV back to data/ folder
    5. Update search_insights.json with what queries/sources found new projects
    6. Append findings to research/SEARCH_LOG.md
    7. Post Slack digest: N new rows, M stage changes, link to GitHub file
    8. Commit data/, config.yaml, research/SEARCH_LOG.md back to git

## Loading a Baseline CSV for a New Region

1. Copy the existing regional file into the repo:
     cp /path/to/REGION_Large_Load_Final.csv data/REGION_Large_Load_Projects.csv

2. Add/update the region entry in config.yaml:
     drive_file_id: data/REGION_Large_Load_Projects.csv
     last_run: 'YYYY-MM-DD'   # date the baseline file was current as of
     mode: delta

3. Run a dry-run first to preview what gets added:
     python main.py --region REGION --mode delta --dry-run

4. If the preview looks good, run for real:
     python main.py --region REGION --mode delta

## File Structure

  main.py                          entry point / orchestrator
  config.yaml                      regions, CSV paths, Slack channels, run state
  data/                            regional CSVs (committed to git as source of truth)
    <REGION>_Large_Load_Projects.csv
    search_insights.json           per-region signal tracking (sources, queries, states)
  research/agent.py                calls OpenAI Responses API with web search
  research/delta_prompt.md         weekly delta research prompt (injects search insights)
  research/full_prompt.md          comprehensive first-run prompt
  research/merge.py                CSV merge, dedup, and validation logic
  research/insights.py             tracks what works; renders insights into prompts
  research/SEARCH_LOG.md           human-readable log of every find and how it was found
  integrations/drive.py            local CSV read/write (misnamed legacy; not Google Drive)
  integrations/slack.py            Slack digest posting
  .github/workflows/weekly.yml     GitHub Actions scheduler + git commit-back
  skill/references/setup.md        one-time credential setup walkthrough

## Adding a New Region from Scratch

1. Add entry to config.yaml:
     - id: PJM
       name: "PJM (Mid-Atlantic)"
       states: [VA, MD, PA, OH, IN, IL, WV, DE, NJ]
       state_abbrevs: [VA, MD, PA, OH, IN, IL, WV, DE, NJ]
       utilities: [Dominion Energy, AEP, Duke Energy, ComEd, PPL, PSEG]
       drive_file_id: null        # null = no baseline, triggers full run
       slack_channel: "#proj-large-load-queue"
       mode: auto
       last_run: null

2. Run a full pass to build the initial dataset:
     python main.py --region PJM --mode full --dry-run   # preview first
     python main.py --region PJM --mode full             # then for real

3. Push to main — GitHub Actions will run delta updates every Monday from there.

## Self-Improving Search

After each run, search_insights.json accumulates:
- Which source publications find new projects most often
- Which search queries are productive
- Which states have gone multiple runs without a find (coverage gaps)

This is injected into the delta prompt on every subsequent run so the model
searches more effectively over time. Review research/SEARCH_LOG.md to see
what each run found and how.

## Setup

See skill/references/setup.md for the one-time credential setup walkthrough.
Requires two GitHub secrets: OPENAI_API_KEY, SLACK_BOT_TOKEN
