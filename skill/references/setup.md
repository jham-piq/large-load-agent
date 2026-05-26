# Setup Guide

## Overview

Three credentials needed, all stored as GitHub repository secrets:

| Secret | What it is |
|--------|-----------|
| ANTHROPIC_API_KEY | Your Anthropic API key |
| GOOGLE_SERVICE_ACCOUNT_JSON | Google Cloud service account key (full JSON) |
| SLACK_BOT_TOKEN | Slack bot OAuth token (starts with xoxb-) |

---

## Step 1 — Anthropic API Key

1. Go to console.anthropic.com
2. Create an API key
3. Add to GitHub secrets as ANTHROPIC_API_KEY

---

## Step 2 — Google Drive Service Account

### 2a. Create the service account

1. Go to console.cloud.google.com
2. Enable the Google Drive API:
   APIs & Services → Enable APIs → search "Drive API" → Enable
3. Go to IAM & Admin → Service Accounts → Create Service Account
   - Name: large-load-agent
   - Click through the role and user access steps (no changes needed)
4. Click the service account you just created → Keys → Add Key → Create new key → JSON
5. A JSON file downloads automatically — open it and copy the entire contents
6. Add to GitHub secrets as GOOGLE_SERVICE_ACCOUNT_JSON (paste the raw JSON)

### 2b. Create and share your Drive folder

1. Go to drive.google.com
2. Create a new folder called "Large Load Research"
3. Open the folder — copy the ID from the URL:
   drive.google.com/drive/folders/THIS_PART_IS_THE_ID
4. Paste that ID into config.yaml under agent.drive_folder_id
5. Right-click the folder → Share
6. Paste the service account email (looks like large-load-agent@your-project.iam.gserviceaccount.com)
   — you'll find this email in the JSON file you downloaded, in the "client_email" field
7. Give it Editor access → Send

---

## Step 3 — Slack Bot

1. Go to api.slack.com/apps → Create New App → From Scratch
2. Name: Large Load Agent
3. Go to OAuth & Permissions → Scopes → Bot Token Scopes → Add: chat:write
4. Click Install to Workspace → Authorize
   (if you are not an admin, this will send an approval request to your admin)
5. Once approved, copy the Bot User OAuth Token (starts with xoxb-)
6. Add to GitHub secrets as SLACK_BOT_TOKEN
7. In Slack, go to your target channel → click the name at the top → Integrations
   → Add apps → find Large Load Agent → Add

---

## Step 4 — GitHub Secrets

1. In your repo: Settings → Secrets and variables → Actions
2. Click New repository secret for each:
   - ANTHROPIC_API_KEY
   - GOOGLE_SERVICE_ACCOUNT_JSON
   - SLACK_BOT_TOKEN

---

## Step 5 — Test Before Monday

1. Go to Actions tab in your repo
2. Click "Monday Large Load Research" → Run workflow
3. Set dry_run: true first to verify credentials work without writing anything
4. Check the logs — you should see Claude searching and returning results
5. If that looks good, run again with dry_run: false to do the real first run
