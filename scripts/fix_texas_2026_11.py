#!/usr/bin/env python3
"""
One-time Texas cleanup (Nov 2026). Texas rows were spread across SERC, SPP and
ERCOT by state instead of by serving utility. This sorts them:
  ERCOT: Oncor, AEP Texas, CPS, CenterPoint, co-ops inside ERCOT
  SPP:   Panhandle / South Plains (Xcel SPS) and NE Texas (SWEPCO)
  SERC:  no Texas utilities, so every SERC Texas row moves out
Duplicates are merged into one row instead of copied.
Run from the repo root:  python scripts/fix_texas_2026_11.py
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research.merge import _enforce_schema  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
REGIONS = ("SERC", "SPP", "ERCOT")

# (target region, target row prefix or None for a straight move,
#  [(source region, source row prefix), ...], {field overrides})
# When a target row exists, it is kept as the base and the sources only fill blanks.
MERGES = [
    # SERC -> ERCOT, already tracked in ERCOT under another name
    ("ERCOT", "Crusoe – AI Data Center Campus (Abilene)",
     [("SERC", "Stargate Abilene Campus")], {"size_mw": 1200.0}),
    ("ERCOT", "Vantage Frontier Campus", [("SERC", "Stargate Shackelford County Campus")], {}),
    ("ERCOT", "OpenAI – SB Energy Data Center (Milam County)", [("SERC", "Stargate Milam County Campus")], {}),
    ("ERCOT", "Project Kati 2 (Soluna)", [("SERC", "Soluna Project Kati Campus Expansion")], {}),
    ("ERCOT", "Google (Midlothian – Railport Pkwy)", [("SERC", "Google Midlothian Data Center Campus")], {}),
    # SERC -> ERCOT, new to ERCOT
    ("ERCOT", None, [("SERC", "Google Haskell County Data Center Campus")], {}),
    ("ERCOT", None, [("SERC", "Tract Caldwell County Technology Park")], {}),
    ("ERCOT", None, [("SERC", "Stream Data Centers San Antonio III-VII")], {}),
    ("ERCOT", None, [("SERC", "San Marcos AI Data Center")], {}),
    ("ERCOT", None, [("SERC", "Compass Datacenters Red Oak Campus 2")], {}),
    ("ERCOT", None, [("SERC", "Rowan Digital Infrastructure Project Temple")], {}),
    ("ERCOT", None, [("SERC", "KDC Taylor Data Center Campus")], {}),
    # SPP -> ERCOT (DFW, Austin, Houston-area and Brownsville projects)
    ("ERCOT", "SpaceX Terafab Semiconductor Factory", [("SPP", "Terafab Semiconductor Manufacturing Campus")], {}),
    ("ERCOT", "Digital Realty DFW45", [("SPP", "Digital Realty DFW45")], {}),
    ("ERCOT", "DataBank DFW15", [("SPP", "DataBank DFW15")], {}),
    ("ERCOT", "Colovore AUS01", [("SPP", "Colovore Hutto AUS01")], {}),
    ("ERCOT", "Taylor Technology Campus", [("SPP", "Taylor Technology Campus")], {}),
    ("ERCOT", "SpaceX Starbase Supercomputing Facility", [("SPP", "SpaceX Starbase Super-compute Facility")], {}),
    ("ERCOT", None, [("SPP", "Project Longhorn - Building One")], {}),
    # ERCOT / SERC -> SPP (Xcel SPS Panhandle, SWEPCO northeast Texas)
    ("SPP", None, [("ERCOT", "Fermi America – Texas Panhandle"), ("SERC", "Fermi America Project Matador")],
     {"size_mw": 11000.0, "transmission_utility": "Xcel Energy (SPS)"}),
    ("SPP", None, [("ERCOT", "Google / Crusoe Goodnight AI Data Center Campus"),
                   ("SERC", "Google Armstrong County Data Center Campus")],
     {"stage": "Under Construction", "transmission_utility": "Xcel Energy (SPS)"}),
    ("SPP", None, [("ERCOT", "Project Big Pine")], {}),
    ("SPP", "Aligned Data Centers Project Caprock", [("SERC", "Aligned Project Caprock")],
     {"transmission_utility": "Xcel Energy (SPS)"}),
]


def _find(df, prefix, region):
    hit = df.index[df["name"].str.startswith(prefix)]
    if len(hit) != 1:
        raise SystemExit(f"{region}: expected 1 row starting '{prefix}', found {len(hit)}")
    return hit[0]


def _combine(base, others):
    """Base row wins; others fill its blanks; sources and notes are unioned."""
    base = base.copy()
    for o in others:
        for col in base.index:
            if pd.isna(base[col]) and pd.notna(o[col]):
                base[col] = o[col]
    for col, sep in (("source", " | "), ("additional_info", " ")):
        parts = []
        for r in [base, *others]:
            v = r[col]
            if pd.notna(v) and str(v).strip() and str(v).strip() not in parts:
                parts.append(str(v).strip())
        if parts:
            base[col] = sep.join(parts)
    return base


def main():
    dfs = {r: pd.read_csv(DATA / f"{r}_Large_Load_Projects.csv") for r in REGIONS}
    drops = {r: [] for r in REGIONS}
    for target, target_prefix, sources, overrides in MERGES:
        src_rows = []
        for region, prefix in sources:
            i = _find(dfs[region], prefix, region)
            src_rows.append(dfs[region].loc[i])
            drops[region].append(i)
        if target_prefix:
            ti = _find(dfs[target], target_prefix, target)
            row = _combine(dfs[target].loc[ti], src_rows)
            for col, val in overrides.items():
                row[col] = val
            dfs[target].loc[ti] = row
        else:
            row = _combine(src_rows[0], src_rows[1:])
            for col, val in overrides.items():
                row[col] = val
            dfs[target] = pd.concat([dfs[target], pd.DataFrame([row])], ignore_index=True)

    # Drop source rows after all merges (indices refer to the original frames)
    for region in REGIONS:
        original_len = len(pd.read_csv(DATA / f"{region}_Large_Load_Projects.csv"))
        keep = [i for i in dfs[region].index if not (i < original_len and i in drops[region])]
        dfs[region] = dfs[region].loc[keep]
        _enforce_schema(dfs[region]).to_csv(DATA / f"{region}_Large_Load_Projects.csv", index=False)

    left = (dfs["SERC"]["state"] == "TX").sum()
    print(f"Texas rows left in SERC: {left}")
    for r in REGIONS:
        print(f"{r}: {len(dfs[r])} rows")


if __name__ == "__main__":
    main()
