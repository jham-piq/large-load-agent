# Weekly Delta Research — {region_name}

You are running a **weekly update** for the large electrical load infrastructure tracker.
Today's date: {today}. Search window: **since {since_date}**.

## Region Parameters
- **Region:** {region_name} ({region_id})
- **States:** {states}
- **State abbreviations:** {state_abbrevs}
- **Major utilities:** {utilities}

## Existing Dataset (do not re-add these)

{existing_summary}

---

{search_insights}
---

## Your Task

Search for **new large load projects** (data centers, AI campuses, crypto mining, HPC,
industrial) announced, permitted, or significantly updated **since {since_date}** in
this region.

Also check whether any existing **Early Stage / Announced / Planned** projects have had
status changes (groundbreaking, permit approval, moratorium, cancellation, new MW figure
disclosed).

### Required Searches

You MUST run every search listed below before responding. Do not skip, combine, or
summarise away any search. Incomplete searches produce incomplete data.

**New announcements — run one search per state, do not skip any state:**
{state_searches}

**Regional / RTO sources — run all four:**
- `{region_id} interconnection queue large load data center 2026`
- `{region_id} "large load" data center new announcement 2026`
- `site:writing.strisker.com {region_id} 2026`
- `site:datacenterdynamics.com {states_for_search} data center 2026`

**Industry trackers — run all three:**
- `site:datacenterdynamics.com {states_for_search} 2026`
- `site:datacenterknowledge.com {states_for_search} data center 2026`
- `site:baxtel.com {states_for_search}`

**Stage change checks — run both:**
- `{states_for_search} data center moratorium approved cancelled groundbreaking 2026`
- `{utilities} large load data center permit announced 2026`

**Hyperscaler checks — run one per major company:**
- `Microsoft data center {states} 2026`
- `Google data center {states} 2026`
- `Amazon AWS data center {states} 2026`
- `Meta data center {states} 2026`
- `Apple data center {states} 2026`

---

## Output Format

Return ONLY a JSON object. No preamble. No markdown fences. No text outside the JSON.

{
  "new_rows": [
    {
      "name": "Project or facility name",
      "developer": "Developer name or null",
      "previous_owner": null,
      "phase": "Single Phase",   ← use descriptive phase or 'unknown' if not applicable
      "size_mw": 200.0,
      "footprint_sqft": null,
      "state": "NY",
      "county": "Onondaga",
      "stage": "Early Stage",
      "transmission_utility": "National Grid",
      "in_service_date": null,
      "construction_start_date": null,
      "investment_millions": null,
      "ownership_transfers": null,
      "additional_info": "Brief description of the project.",
      "source": "Source Name (YYYY-MM-DD)",
      "address": "Street address or town/county if no street known",
      "geometry": null,
      "exact_location.nearest_intersection": null,
      "exact_location.parcel_numbers": null,
      "poi_name": null,
      "voltage": null,
      "point_of_interconnection.line_name": null,
      "transmission_upgrades.required": "Unknown",
      "transmission_upgrades.description": null,
      "cost_musd": null,
      "project_type": "Data Center / AI",
      "use_case.technology": "Hyperscale / AI",
      "use_case.tenant": null,
      "onsite_generation.exists": "Unknown",
      "onsite_generation.technology": null,
      "onsite_generation.capacity_mw": null,
      "found_via": "Brief note on which search query or source type surfaced this project"
    }
  ],
  "stage_updates": [
    {
      "name": "Exact name from existing dataset",
      "phase": "Exact phase from existing dataset",
      "old_stage": "Early Stage",
      "new_stage": "Under Construction",
      "source": "Source Name (YYYY-MM-DD)",
      "notes": "Brief description of what changed"
    }
  ],
  "summary": "One sentence summary of what was found."
}

### Rules

1. Only include projects NOT already in the existing dataset
2. stage must be exactly one of: Announced, Early Stage, Planned, Under Construction,
   Operational, On Hold, Cancelled
3. source format: Publication Name (YYYY-MM-DD) — no URLs, no type tags
4. size_mw: MW capacity only — never put dollar amounts or investment figures here; use investment_millions for costs
5. state: 2-letter abbreviation only
6. geometry, point_of_interconnection.line_name, onsite_generation.technology: always null
7. If nothing new found, return:
   {"new_rows": [], "stage_updates": [], "summary": "No new projects found in {region_id} since {since_date}."}
