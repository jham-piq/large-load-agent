#!/usr/bin/env python3
"""
One-time cleanup (Nov 2026):
  1. Normalize free-text ERCOT stages to the eight valid stages.
  2. Move California rows out of the WECC file into CAISO and merge duplicates.
Run from the repo root:  python scripts/cleanup_2026_11.py
"""
import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from research.merge import VALID_STAGES, _enforce_schema  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"

# ---------------------------------------------------------------- 1. ERCOT
ERCOT_STAGE_MAP = {
    "Announced / planned": "Planned",
    "Site secured / planned": "Planned",
    "Construction (multi-building campus; Building 2 filed)": "Under Construction",
    "Early development; substation under construction": "Early Stage",
    "Announced / early concept": "Announced",
    "Construction / filed (TDLR TAS)": "Under Construction",
    "Construction": "Under Construction",
    "Announced / delivery target mid-2026": "Announced",
    "Construction (Building 1); campus planned": "Under Construction",
    "Early site work / construction planned (fall 2025)": "Planned",
    "Under construction; targeting operation Q4 2026": "Under Construction",
    "Announced (Powered Land deal)": "Announced",
    "Phase 1 built/operational; Phase 2 construction (target mid-2026 completion)": "Under Construction",
    "Announced / early development": "Announced",
    "Announced / planning (behind-the-meter concept)": "Announced",
    "Permits (interconnection.fyi record)": "Planned",
    "Proposed / permit approved (interconnection.fyi record)": "Planned",
    "Proposed (interconnection.fyi record)": "Early Stage",
}


def fix_ercot():
    path = DATA / "ERCOT_Large_Load_Projects.csv"
    df = pd.read_csv(path)
    bad = ~df["stage"].isin(VALID_STAGES)
    unmapped = set(df.loc[bad, "stage"]) - set(ERCOT_STAGE_MAP)
    if unmapped:
        raise SystemExit(f"Unmapped ERCOT stages: {unmapped}")
    for i in df.index[bad]:
        old = df.at[i, "stage"]
        df.at[i, "stage"] = ERCOT_STAGE_MAP[old]
        note = f"[Original stage text: {old}]"
        info = df.at[i, "additional_info"]
        df.at[i, "additional_info"] = note if pd.isna(info) else f"{info} {note}"
    # Drop the "Interconnection.fyi record" tag from names; it's a source, not a name
    df["name"] = df["name"].apply(
        lambda n: re.sub(r"\s*(–|-)?\s*\(?Interconnection\.fyi record\)?\s*$", "", n, flags=re.I).strip()
    )
    df = _enforce_schema(df)
    df.to_csv(path, index=False)
    print(f"ERCOT: normalized {bad.sum()} stages")


# ---------------------------------------------------------------- 2. California
def _merge_group(rows):
    """Keep the most complete row; fill its gaps from the others; union sources and notes."""
    rows = sorted(rows, key=lambda r: r.notna().sum(), reverse=True)
    base = rows[0].copy()
    for other in rows[1:]:
        for col in base.index:
            if pd.isna(base[col]) and pd.notna(other[col]):
                base[col] = other[col]
    for col, sep in (("source", " | "), ("additional_info", " ")):
        parts = []
        for r in rows:
            v = r[col]
            if pd.notna(v) and str(v).strip() and str(v).strip() not in parts:
                parts.append(str(v).strip())
        base[col] = sep.join(parts) if parts else base[col]
    return base


def fix_california():
    wpath, cpath = DATA / "WECC_Large_Load_Projects.csv", DATA / "CAISO_Large_Load_Projects.csv"
    w, c = pd.read_csv(wpath), pd.read_csv(cpath)
    ca = w[w["state"] == "CA"].copy()
    w = w[w["state"] != "CA"]
    pool = pd.concat([c, ca], ignore_index=True)

    # Same project, different names (checked by hand: same address/MW/developer).
    # Matched by name prefix so the groups survive new rows being added.
    groups = [
        ["Rucci", "Imperial Valley Computer", "Imperial County Hyperscale"],# 330 MW, Aten & Clark Rd, IID
        ["DataBank"],                             # 32 MW, 3094 E Vernon Ave
        ["Digital Realty"],                       # near One Wilshire
        ["Manchester Financial", "NAVWAR"],       # 400 MW, San Diego
        ["RB Inyokern"],                          # 99 MW, Kern County
    ]
    overrides = {
        0: {"stage": "On Hold"},  # Sept 2026 court order requires full EIR before permits
        1: {"stage": "Planned",   # rows said Announced / Planned / Under Construction
            "transmission_utility": "City of Vernon (Vernon Public Utilities)"},
    }
    merged, used = [], []
    for n, prefixes in enumerate(groups):
        hits = [i for i in pool.index if any(str(pool.at[i, "name"]).startswith(p) for p in prefixes)]
        if len(hits) < 2:
            raise SystemExit(f"California group {prefixes}: expected 2+ rows, found {len(hits)}")
        m = _merge_group([pool.loc[i] for i in hits])
        for col, val in overrides.get(n, {}).items():
            m[col] = val
        merged.append(m)
        used += hits
    pool = pool.drop(index=used)
    pool = pd.concat([pool, pd.DataFrame(merged)], ignore_index=True)

    _enforce_schema(w).to_csv(wpath, index=False)
    _enforce_schema(pool).to_csv(cpath, index=False)
    print(f"California: moved {len(ca)} rows WECC -> CAISO, merged {len(used) - len(groups)} duplicates; "
          f"WECC now {len(w)}, CAISO now {len(pool)}")




# ---------------------------------------------------------------- 3. Region fixes + MISO seed
# Rows filed under the wrong region (same project in two files, or serving utility
# is in another footprint). Only unambiguous cases; anything with a mixed utility
# string ("ComEd / Ameren", "Entergy Mississippi / Mississippi Power") stays put.
DROP_DUPLICATES = {   # file -> names to drop because the right region already has them
    "SPP":   ["CoreSite DA1", "Hut 8 Beacon Point Data Center Project"],  # Oncor / AEP Texas -> ERCOT
    "ERCOT": ["InfraTech Carson County Data Center Campus"],              # Panhandle -> SPP
    "PJM":   ["DC Blox Nashville Data Center",                            # TVA -> SERC
              "Energy Way Tech Campus"],                                  # Duke Energy Progress -> SERC
    "SERC":  ["Google West Creek Data Center Campus",                     # Dominion -> PJM
              "TeraWulf Muskie Data Campus"],                             # Kentucky Power (AEP) -> PJM
}

TO_MISO = {
    "SERC": ["AVAIO Digital Taurus Hub (Brandon)", "AVAIO Digital Little Rock Campus",
             "Meta Hyperion Data Center Campus", "Meta Hyperion Data Center Campus Expansion",
             "Amazon Web Services Louisiana Campus", "Cloverleaf Infrastructure Troy Data Center Campus",
             "Google Project Pyramid (West Memphis)", "Armory Innovation District Data Center (St. Louis)"],
    "SPP":  ["Applied Digital Deuel County (Toronto)",          # Otter Tail Power
             "Google West Memphis Data Center (Project Pyramid)"],  # Entergy Arkansas; dupe of SERC row
    "PJM":  ["Hut 8 Latham", "CyrusOne Springfield (Sangamon County)", "Pekin Data Center (withdrawn)",
             "Vantage Lighthouse Campus (Stargate Wisconsin)",
             "Dewberry Engineers / Undisclosed Developer Caledonia Data Center",
             "Kenosha Data Center (undisclosed)",
             "Oracle / OpenAI / Related Digital Saline Township Data Center",
             "Meta Elmore Township Data Center (On Hold — moratorium)",
             "Microsoft Gaines Township Data Center (On Hold)",
             "University of Michigan / Los Alamos AI Research Campus (Ypsilanti)",
             "Thor Equities Augusta Township Data Center",
             "Franklin Partners Lowell Township Data Center (On Hold)",
             "Sentinel Project Shirley Eagle Creek (Lake County)", "Amazon Hobart Data Center (Lake County)",
             "Amazon Web Services Northwest Indiana Expansion (Phase 2)", "Microsoft La Porte Data Center",
             "Google Indianapolis Data Center (rejected)",
             "Prologis Shelbyville Data Center (unfavorable recommendation)",
             "Meta Jeffersonville Data Center", "RadiusDC Plainfield Data Centers",
             "TeraWulf Justified Data Campus"],
}


def _match(df, wanted, region):
    """Exact name match, falling back to a unique prefix match (names were truncated in review)."""
    idx = []
    for w in wanted:
        hit = df.index[df["name"] == w]
        if len(hit) == 0:
            hit = df.index[df["name"].str.startswith(w[:55])]
        if len(hit) != 1:
            raise SystemExit(f"{region}: expected 1 row for '{w}', found {len(hit)}")
        idx.append(hit[0])
    return idx


def fix_regions():
    files = {r: DATA / f"{r}_Large_Load_Projects.csv" for r in ("SERC", "SPP", "PJM", "ERCOT")}
    dfs = {r: pd.read_csv(p) for r, p in files.items()}

    for r, names in DROP_DUPLICATES.items():
        dfs[r] = dfs[r].drop(index=_match(dfs[r], names, r))

    miso_parts = []
    for r, names in TO_MISO.items():
        idx = _match(dfs[r], names, r)
        miso_parts.append(dfs[r].loc[idx])
        dfs[r] = dfs[r].drop(index=idx)
    miso = pd.concat(miso_parts, ignore_index=True)

    # Google Project Pyramid came in from both SERC and SPP
    pyr = miso.index[miso["name"].str.contains("Project Pyramid")]
    keep = _merge_group([miso.loc[i] for i in pyr])
    keep["name"] = "Google Project Pyramid (West Memphis)"
    miso = pd.concat([miso.drop(index=pyr), pd.DataFrame([keep])], ignore_index=True)

    for r, df in dfs.items():
        _enforce_schema(df).to_csv(files[r], index=False)
    _enforce_schema(miso).to_csv(DATA / "MISO_Large_Load_Projects.csv", index=False)
    print(f"Regions: dropped {sum(map(len, DROP_DUPLICATES.values()))} cross-region duplicates; "
          f"seeded MISO with {len(miso)} rows")


if __name__ == "__main__":
    fix_ercot()
    fix_california()
    fix_regions()
