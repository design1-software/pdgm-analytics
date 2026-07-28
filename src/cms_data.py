"""Loaders for the CY 2026 CMS Home Health PPS source data.

Every value served by this module comes from a file published by CMS and staged
under ``data/cms/cy2026/``. Nothing here is estimated, interpolated, or
hand-entered. See ``data/cms/cy2026/SOURCES.md`` for provenance.

Deliberately stdlib-only: the two CSVs are ~25KB combined, so pandas buys
nothing and would make this import-heavy for a hot request path.
"""

import csv
import os
import re
import threading

_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cms", "cy2026"
)

CASE_MIX_FILE = os.path.join(_DATA_DIR, "case_mix_weights_lupa.csv")
WAGE_INDEX_FILE = os.path.join(_DATA_DIR, "wage_index.csv")

# CMS publishes these CSVs in Windows-1252, not UTF-8 (e.g. "Mayagüez, PR").
_ENCODING = "cp1252"

_lock = threading.Lock()
_case_mix_cache = None
_wage_index_cache = None

# Valid input domains, as they appear in the CMS case-mix file.
FUNCTIONAL_LEVELS = ("Low", "Medium", "High")
ADMISSION_SOURCE_TIMINGS = (
    "Early - Community",
    "Early - Institutional",
    "Late - Community",
    "Late - Institutional",
)
COMORBIDITY_LEVELS = (0, 1, 2)  # none / single / interaction

# The 12 PDGM clinical groups, keyed by the letter used in HIPPS position 2.
# These letters match pdgm_clinical_group_code in CCFTF_pdgm_diagnosis_mapping.csv
# one-for-one, which is what makes the diagnosis CSV joinable to CMS weights.
CLINICAL_GROUPS = {
    "A": "MMTA - Other",
    "B": "Neuro",
    "C": "Wound",
    "D": "Complex",
    "E": "MS Rehab",
    "F": "Behavioral Health",
    "G": "MMTA - Surgical Aftercare",
    "H": "MMTA - Cardiac",
    "I": "MMTA - Endocrine",
    "J": "MMTA - GI/GU",
    "K": "MMTA - Infectious",
    "L": "MMTA - Respiratory",
}


def load_case_mix_table():
    """Return {(group_letter, functional_level, admission_source_timing, comorbidity): row}.

    Each row is a dict with ``hipps``, ``weight`` and ``lupa_threshold``. The CMS
    file is a complete 12 x 3 x 4 x 3 = 432 cell grid, so every valid combination
    resolves; a KeyError means the caller passed something outside the domains
    above, not that CMS omitted a case.
    """
    global _case_mix_cache
    if _case_mix_cache is not None:
        return _case_mix_cache
    with _lock:
        if _case_mix_cache is not None:
            return _case_mix_cache
        with open(CASE_MIX_FILE, encoding=_ENCODING, newline="") as fh:
            rows = list(csv.DictReader(fh))
        if not rows:
            raise ValueError("CMS case-mix file is empty: %s" % CASE_MIX_FILE)

        # The comorbidity/weight/LUPA headers contain embedded newlines in the
        # CMS export, so address them positionally rather than by literal name.
        cols = list(rows[0].keys())
        comorbidity_col, weight_col, lupa_col = cols[3], cols[4], cols[5]

        table = {}
        for row in rows:
            hipps = row["HIPPS"].strip()
            group_and_level = row["Clinical Group and Functional Level"].strip()
            group_name, functional_level = group_and_level.rsplit(" - ", 1)
            key = (
                hipps[1],
                functional_level,
                row["Admission Source and Timing"].strip(),
                int(row[comorbidity_col]),
            )
            table[key] = {
                "hipps": hipps,
                "clinical_group": group_name,
                "weight": float(row[weight_col]),
                "lupa_threshold": int(row[lupa_col]),
            }
        if len(table) != 432:
            raise ValueError(
                "Expected 432 PDGM case-mix cells, parsed %d from %s"
                % (len(table), CASE_MIX_FILE)
            )
        _case_mix_cache = table
        return _case_mix_cache


_STATE_BY_NAME = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "DISTRICT OF COLUMBIA": "DC", "FLORIDA": "FL", "GEORGIA": "GA", "GUAM": "GU",
    "HAWAII": "HI", "IDAHO": "ID", "ILLINOIS": "IL", "INDIANA": "IN",
    "IOWA": "IA", "KANSAS": "KS", "KENTUCKY": "KY", "LOUISIANA": "LA",
    "MAINE": "ME", "MARYLAND": "MD", "MASSACHUSETTS": "MA", "MICHIGAN": "MI",
    "MINNESOTA": "MN", "MISSISSIPPI": "MS", "MISSOURI": "MO", "MONTANA": "MT",
    "NEBRASKA": "NE", "NEVADA": "NV", "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM", "NEW YORK": "NY", "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK", "OREGON": "OR",
    "PENNSYLVANIA": "PA", "PUERTO RICO": "PR", "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC", "SOUTH DAKOTA": "SD", "TENNESSEE": "TN",
    "TEXAS": "TX", "UTAH": "UT", "VERMONT": "VT", "VIRGIN ISLANDS": "VI",
    "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY",
}


def _states_for_area(code, name):
    """Best-effort state codes for an area, used only for grouping the selector."""
    if code.startswith("999"):
        abbr = _STATE_BY_NAME.get(name.strip().upper())
        return [abbr] if abbr else []
    # Urban CBSA names look like "Kansas City, MO-KS" or "Appleton, WI".
    match = re.search(r",\s*([A-Z]{2}(?:-[A-Z]{2})*)\s*$", name.strip())
    if match:
        return match.group(1).split("-")
    abbr = _STATE_BY_NAME.get(name.strip().upper())
    return [abbr] if abbr else []


def load_wage_index():
    """Return {area_code: {name, wage_index, kind, states}} for all CY 2026 areas.

    ``kind`` is ``rural`` (statewide 999xx), ``transition`` (the 50xxx county
    codes CMS created for the 5% cap) or ``urban`` (a CBSA).
    """
    global _wage_index_cache
    if _wage_index_cache is not None:
        return _wage_index_cache
    with _lock:
        if _wage_index_cache is not None:
            return _wage_index_cache
        areas = {}
        with open(WAGE_INDEX_FILE, encoding=_ENCODING, newline="") as fh:
            for row in csv.reader(fh):
                if len(row) < 3:
                    continue
                code, name, value = row[0].strip(), row[1].strip(), row[2].strip()
                # Section banners and the repeated header rows fail this test.
                if not (len(code) == 5 and code.isdigit()):
                    continue
                try:
                    wage_index = float(value)
                except ValueError:
                    continue
                if code.startswith("999"):
                    kind = "rural"
                elif code.startswith("50"):
                    kind = "transition"
                else:
                    kind = "urban"
                areas[code] = {
                    "code": code,
                    "name": name,
                    "wage_index": wage_index,
                    "kind": kind,
                    "states": _states_for_area(code, name),
                }
        if not areas:
            raise ValueError("Parsed no areas from %s" % WAGE_INDEX_FILE)
        _wage_index_cache = areas
        return _wage_index_cache


def get_wage_index(area_code):
    """Return the CY 2026 wage index for a CBSA / rural / transition code.

    Raises KeyError for unknown codes. There is deliberately no default: guessing
    a wage index is what the previous implementation did wrong.
    """
    return load_wage_index()[str(area_code).strip()]["wage_index"]


def list_areas():
    """All areas sorted for a picker: by state, then name."""
    areas = load_wage_index().values()
    return sorted(areas, key=lambda a: ((a["states"] or ["ZZ"])[0], a["name"]))
