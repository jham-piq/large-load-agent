# Full Research Run — {region_name}

This is the **first run** for {region_name} ({region_id}).
Run a comprehensive large load research pass on this region.

## Region Parameters
- **Region:** {region_name} ({region_id})
- **States:** {states}
- **State abbreviations:** {state_abbrevs}
- **Major utilities:** {utilities}
- **Research date:** {today}

---

Follow this research workflow:

1. **Queue baseline** — find total MW in {region_id} interconnection queue
2. **Regulatory** — FERC filings, state PUC/PSC dockets, RTO queue reports
3. **Utility** — IRP and 10-year transmission plans for: {utilities}
4. **Industry / Developer** — trade sites: datacenterdynamics.com, datacenterknowledge.com,
   baxtel.com, cleanview.co, buildcentral.com
5. **Local newspapers** — per-state searches for early-stage and contested projects.
   For EACH state run at minimum:
   - `[STATE] data center announced planned 2026 MW developer`
   - `[STATE] data center moratorium rezoning opposition 2026`
6. **National news** — hyperscale announcements, state econ dev press releases,
   site:writing.strisker.com for the region
7. **Stage changes** — apply controlled vocabulary to all found projects
8. **MW + address enrichment** — fill gaps for non-operational rows
9. **Load sanity check** — compare pipeline MW total to published RTO estimate
10. **Output JSON**

---

## Output Format

Return ONLY a JSON object. No preamble. No markdown fences. No text outside the JSON.

{
  "new_rows": [ ],
  "stage_updates": [],
  "queue_baseline": {
    "total_mw": 12000,
    "num_requests": 48,
    "as_of_date": "2025-12-31",
    "source": "Source Name (Date)"
  },
  "sanity_check": {
    "published_estimate_mw": 12000,
    "our_pipeline_mw": 9891,
    "coverage_pct": 82,
    "assessment": "Acceptable",
    "notes": "Brief explanation of any gap"
  },
  "summary": "First run complete for {region_id}. Found N pipeline projects totalling Z MW."
}

Each row in new_rows uses the same schema as the delta prompt, including the `found_via` field noting which search query or source type surfaced the project.

### Rules

1. stage must be exactly one of: Announced, Early Stage, Planned, Under Construction,
   On Hold, Cancelled
2. Track the **pipeline** only. Do not return facilities that are already built and
   running — no colocation directory listings, no existing data center inventories.
   A project belongs in the output only if its load is not yet energized.
3. source format: Publication Name (YYYY-MM-DD) — no URLs, no type tags
4. size_mw: MW capacity only — never put dollar amounts or investment figures here; use investment_millions for costs
5. state: 2-letter abbreviation only
6. geometry, point_of_interconnection.line_name, onsite_generation.technology: always null
