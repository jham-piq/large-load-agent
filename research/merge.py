"""
Merge new research results into existing CSV.
Handles dedup on name+phase, stage updates, and schema validation.
"""

import logging
from datetime import datetime, timezone
from difflib import SequenceMatcher

import pandas as pd

log = logging.getLogger(__name__)

VALID_STAGES = {
    "Announced", "Early Stage", "Planned", "Under Construction",
    "Operational", "On Hold", "Cancelled", "Land Banked",
}

# Canonical Atlas column order — enforced on every save
CANONICAL_COLUMNS = [
    "name", "developer", "previous_owner", "phase", "size_mw", "footprint_sqft",
    "state", "county", "stage", "transmission_utility", "in_service_date",
    "construction_start_date", "investment_millions", "ownership_transfers",
    "additional_info", "source", "address", "geometry",
    "exact_location.nearest_intersection", "exact_location.parcel_numbers",
    "poi_name", "voltage", "point_of_interconnection.line_name",
    "transmission_upgrades.required", "transmission_upgrades.description",
    "cost_musd", "project_type", "use_case.technology", "use_case.tenant",
    "onsite_generation.exists", "onsite_generation.technology",
    "onsite_generation.capacity_mw",
]

GIS_NULL_COLS = [
    "geometry",
    "point_of_interconnection.line_name",
    "onsite_generation.technology",
]

REQUIRED_STR_COLS = ["name", "phase", "state"]


def merge_results(existing_df, new_rows, stage_updates, region_id):
    if existing_df is None or existing_df.empty:
        existing_df = pd.DataFrame()

    valid_rows = []
    for row in new_rows:
        row = _clean_row(row)
        issues = _validate_row(row)
        if issues:
            log.warning(f"Skipping invalid row '{row.get('name')}': {issues}")
            continue
        valid_rows.append(row)

    if not valid_rows and not stage_updates:
        log.info("No valid new rows or stage updates after validation")
        return existing_df

    if not existing_df.empty:
        existing_keys = set(
            zip(
                existing_df["name"].str.lower().str.strip(),
                existing_df["phase"].str.lower().str.strip(),
            )
        )
        before = len(valid_rows)
        valid_rows = [
            r for r in valid_rows
            if (r["name"].lower().strip(), r["phase"].lower().strip()) not in existing_keys
        ]
        dupes = before - len(valid_rows)
        if dupes:
            log.info(f"Dropped {dupes} duplicate row(s) already in existing dataset")

    if stage_updates and not existing_df.empty:
        for update in stage_updates:
            name = update.get("name", "")
            phase = update.get("phase", "Single Phase")
            new_stage = update.get("new_stage", "")
            source = update.get("source", "")
            notes = update.get("notes", "")

            if new_stage not in VALID_STAGES:
                log.warning(f"Invalid stage '{new_stage}' in update for '{name}' — skipping")
                continue

            mask = _find_row(existing_df, name, phase)
            if mask is None or mask.sum() == 0:
                log.warning(f"Stage update: '{name}' not found in existing dataset — skipping")
                continue

            existing_df.loc[mask, "stage"] = new_stage
            if source:
                existing_df.loc[mask, "source"] = (
                    existing_df.loc[mask, "source"].fillna("") + f" | {source}"
                )
            if notes:
                existing_df.loc[mask, "additional_info"] = (
                    existing_df.loc[mask, "additional_info"].fillna("") +
                    f" [Stage updated {datetime.now(timezone.utc).strftime('%Y-%m-%d')}: {notes}]"
                )
            log.info(f"Stage update applied: '{name}' → {new_stage}")

    if valid_rows:
        new_df = pd.DataFrame(valid_rows)
        combined = (
            pd.concat([existing_df, new_df], ignore_index=True)
            if not existing_df.empty else new_df
        )
    else:
        combined = existing_df

    for col in GIS_NULL_COLS:
        if col in combined.columns:
            combined[col] = float("nan")

    float_cols = [
        "size_mw", "footprint_sqft", "investment_millions",
        "exact_location.parcel_numbers", "voltage", "cost_musd",
        "onsite_generation.capacity_mw",
    ]
    for col in float_cols:
        if col in combined.columns:
            combined[col] = pd.to_numeric(combined[col], errors="coerce")

    combined = _enforce_schema(combined)

    log.info(
        f"Merge complete: {len(combined)} total rows "
        f"(+{len(valid_rows)} new, {len(stage_updates)} stage updates)"
    )
    return combined


def _enforce_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enforce canonical column set, order, and Atlas load requirements.
    - Drops any columns not in CANONICAL_COLUMNS (e.g. found_via, Idaho-specific cols)
    - Adds any missing canonical columns as NaN
    - Reorders columns to match Atlas expectation
    - Cleans source field: strips list brackets, removes bare URLs
    - Raises ValueError if name+phase uniqueness or null constraints are violated
    """
    # Add missing canonical columns
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = float("nan")

    # Drop non-canonical columns (found_via, Idaho queue columns, etc.)
    extra = [c for c in df.columns if c not in CANONICAL_COLUMNS]
    if extra:
        log.info(f"Dropping non-canonical columns: {extra}")
        df = df.drop(columns=extra)

    # Enforce column order
    df = df[CANONICAL_COLUMNS]

    # Clean source field
    if "source" in df.columns:
        df["source"] = df["source"].apply(_clean_source)

    # Clean all numeric columns — strip range notation, commas, text
    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = df[col].apply(_clean_numeric)

    # Ensure phase is never null — Atlas uses name+phase as deterministic ID
    if "phase" in df.columns:
        df["phase"] = df["phase"].apply(
            lambda v: v if (isinstance(v, str) and v.strip()) else "unknown"
        )

    # --- Atlas load requirements ---
    # 1. name and phase must never be null
    null_name = df["name"].isna().sum()
    null_phase = df["phase"].isna().sum()
    if null_name > 0:
        bad = df[df["name"].isna()][["state", "stage", "address"]].head(3).to_dict("records")
        raise ValueError(f"Atlas load error: {null_name} row(s) have null 'name'. Examples: {bad}")
    if null_phase > 0:
        bad = df[df["phase"].isna()][["name", "state"]].head(3).to_dict("records")
        raise ValueError(f"Atlas load error: {null_phase} row(s) have null 'phase'. Examples: {bad}")

    # 2. name + phase must be unique
    dupes = df[df.duplicated(subset=["name", "phase"], keep=False)]
    if not dupes.empty:
        pairs = dupes[["name", "phase"]].drop_duplicates().head(5).values.tolist()
        raise ValueError(
            f"Atlas load error: {len(dupes)} row(s) share a duplicate name+phase. "
            f"Pairs: {pairs}"
        )

    return df


NUMERIC_COLS = [
    "size_mw", "footprint_sqft", "investment_millions",
    "exact_location.parcel_numbers", "voltage", "cost_musd",
    "onsite_generation.capacity_mw",
]


def _clean_numeric(val):
    """
    Extract the first clean number from a value that may contain range notation,
    commas, units, or parenthetical text.

    Examples:
      "250+"         → 250.0
      "100–250"      → 100.0
      "1,600"        → 1600.0
      "200 (Phase 1)"→ 200.0
      "Up to 150"    → 150.0
      "3,700,000"    → 3700000.0
      "25000+"       → 25000.0
    """
    import re
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return float("nan")
    s = str(val).strip().replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", s)
    if match:
        return float(match.group())
    return float("nan")


def _clean_source(val) -> str:
    """
    Normalize source field for Atlas compatibility.

    Handles several formats found in baseline files:
      - ['Source (date)']                        → Source (date)
      - [Tag] Source (date): https://...         → Source (date)
      - [Tag] A (date): URL | [Tag] B (date): URL → A (date) | B (date)
      - bare https://domain.com/path             → domain.com
    """
    import re
    if pd.isna(val):
        return val
    s = str(val).strip()

    # Simple Python list: ['Source (date)'] → Source (date)
    if s.startswith("['") and s.endswith("']"):
        s = s[2:-2].strip()
        return s

    # Tagged multi-source format: [Tag] Name (date): URL | [Tag] Name (date): URL
    if re.search(r"\[[A-Za-z ]+\]", s):
        parts = s.split("|")
        cleaned = []
        for part in parts:
            part = part.strip()
            # Remove [Tag] prefix
            part = re.sub(r"^\[[^\]]+\]\s*", "", part)
            # Remove : URL suffix
            part = re.sub(r":\s*https?://\S+", "", part).strip()
            if part:
                cleaned.append(part)
        return " | ".join(cleaned)

    # Bare URL
    if re.match(r"^https?://", s):
        domain = re.sub(r"^https?://(www\.)?", "", s).split("/")[0]
        return domain

    return s


def _find_row(df, name, phase, fuzzy_threshold=0.85):
    """
    Find matching row(s) for a stage update using a tiered strategy:
      1. Exact name + exact phase
      2. Exact name + any phase (if unique match)
      3. Fuzzy name match (>=fuzzy_threshold) + any phase (if unique match)
    Returns a boolean mask or None if no match found.
    """
    name_l = name.lower().strip()
    phase_l = phase.lower().strip()
    names = df["name"].str.lower().str.strip()
    phases = df["phase"].str.lower().str.strip()

    # 1. Exact name + exact phase
    mask = (names == name_l) & (phases == phase_l)
    if mask.sum() == 1:
        return mask
    if mask.sum() > 1:
        log.warning(f"Stage update: '{name}' matched {mask.sum()} rows — applying to all")
        return mask

    # 2. Exact name, any phase
    mask = names == name_l
    if mask.sum() == 1:
        matched_phase = df.loc[mask, "phase"].iloc[0]
        log.info(f"Stage update: '{name}' matched on name only (phase '{matched_phase}')")
        return mask
    if mask.sum() > 1:
        log.warning(
            f"Stage update: '{name}' matched {mask.sum()} phases — "
            f"phases: {list(df.loc[mask, 'phase'])}. Skipping to avoid ambiguity."
        )
        return None

    # 3. Fuzzy name match, any phase
    best_score, best_idx = 0.0, None
    for idx, row_name in names.items():
        score = SequenceMatcher(None, name_l, row_name).ratio()
        if score > best_score:
            best_score, best_idx = score, idx
    if best_score >= fuzzy_threshold and best_idx is not None:
        matched_name = df.loc[best_idx, "name"]
        log.info(
            f"Stage update: fuzzy matched '{name}' → '{matched_name}' "
            f"(score={best_score:.2f})"
        )
        mask = df.index == best_idx
        return mask

    return None


def _clean_row(row):
    row = dict(row)
    row.setdefault("stage", "Announced")
    row.setdefault("onsite_generation.exists", "Unknown")
    row.setdefault("transmission_upgrades.required", "Unknown")

    for col in GIS_NULL_COLS:
        row[col] = None

    for k, v in row.items():
        if isinstance(v, str):
            row[k] = v.strip()

    # Ensure phase is never empty/null — Atlas requires it for deterministic ID
    if not row.get("phase"):
        row["phase"] = "unknown"

    return row


def _validate_row(row):
    issues = []

    for col in REQUIRED_STR_COLS:
        if not row.get(col):
            issues.append(f"Missing required field: {col}")

    stage = row.get("stage", "")
    if stage and stage not in VALID_STAGES:
        issues.append(f"Invalid stage: '{stage}'")

    state = row.get("state", "")
    if state and len(state) != 2:
        issues.append(f"state must be 2-letter abbreviation, got: '{state}'")

    return issues
