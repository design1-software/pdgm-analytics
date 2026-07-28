"""Build Tableau-ready extracts from the PDGM mapping + CY 2026 CMS data.

No database involved: the diagnosis mapping is a CSV and the CMS rate data
lives in data/cms/cy2026/. Everything below is computed from those files.
"""

import csv, collections, os, sys, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs", "tableau")
sys.path.insert(0, os.path.join(ROOT, "src"))

import cms_data
import payment

os.makedirs(OUT, exist_ok=True)


rows = list(csv.DictReader(open(os.path.join(ROOT, "data", "CCFTF_pdgm_diagnosis_mapping.csv"),
                                encoding="utf-8", errors="replace")))

# Section 111 exclusions
import openpyxl
wb = openpyxl.load_workbook(os.path.join(ROOT, "data", "section111_excluded_icd10_fy2026.xlsx"),
                            read_only=True, data_only=True)
excluded = set()
for ws in wb.worksheets:
    header = [str(c.value).strip().upper() if c.value else ""
              for c in next(ws.iter_rows(min_row=1, max_row=1))]
    idx = next((i for i, h in enumerate(header) if h == "CODE"), 0)
    for row in ws.iter_rows(min_row=2):
        v = row[idx].value
        if isinstance(v, str) and v.strip():
            excluded.add(v.replace(".", "").replace(" ", "").upper())
wb.close()


def write(name, header, data):
    path = os.path.join(OUT, name)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(data)
    print("  %-42s %5d rows" % (name, len(data)))


# ---- 1. Clinical group distribution + coding-surface size -----------------
grp_codes = collections.defaultdict(list)
for r in rows:
    grp_codes[(r["pdgm_clinical_group_code"], r["pdgm_clinical_group_name"])].append(r)

d1 = []
for (code, name), members in sorted(grp_codes.items(), key=lambda kv: -len(kv[1])):
    excl = sum(1 for m in members if m["icd10_code"] in excluded)
    unacceptable = sum(1 for m in members if m["UNACCEPTABLE_PDX"] == "1")
    unspecified = sum(1 for m in members if m["UNSPECIFIED_PDX"] == "1")
    with_comorbidity = sum(1 for m in members if m["COMORBIDITY_GROUP"] != "No_group")
    d1.append([code or "NA", name, len(members),
               round(100 * len(members) / len(rows), 2),
               excl, round(100 * excl / len(members), 2),
               unacceptable, unspecified, with_comorbidity])
write("01_clinical_group_distribution.csv",
      ["group_code", "group_name", "icd10_codes", "pct_of_all_codes",
       "section111_excluded", "pct_excluded", "unacceptable_pdx",
       "unspecified_pdx", "codes_with_comorbidity_group"], d1)

# ---- 2. Geography: wage index + payment by area and state ----------------
areas = cms_data.list_areas()
d2 = []
for a in areas:
    # Reference cell: same HIPPS everywhere, so differences are pure geography.
    ref = payment.calculate("A", "Medium", "Early - Community", 0, a["code"])
    d2.append([a["code"], a["name"], (a["states"] or [""])[0], a["kind"],
               a["wage_index"], ref["period_payment"]])
write("02_wage_index_by_area.csv",
      ["area_code", "area_name", "state", "area_kind", "wage_index",
       "reference_payment_1AB11"], d2)

by_state = collections.defaultdict(list)
for a in areas:
    if a["states"]:
        by_state[a["states"][0]].append(a)
d2s = []
for st, members in sorted(by_state.items()):
    wis = [m["wage_index"] for m in members]
    pays = [payment.calculate("A", "Medium", "Early - Community", 0,
                                  m["code"])["period_payment"] for m in members]
    d2s.append([st, len(members), min(wis), round(statistics.median(wis), 4),
                max(wis), min(pays), round(statistics.median(pays), 2), max(pays)])
write("02b_wage_index_by_state.csv",
      ["state", "areas", "wage_index_min", "wage_index_median", "wage_index_max",
       "reference_payment_min", "reference_payment_median",
       "reference_payment_max"], d2s)

# ---- 3. The full CY2026 HIPPS grid (weights + LUPA thresholds) -----------
table = cms_data.load_case_mix_table()
d3 = []
for (letter, func, timing, com), cell in sorted(table.items()):
    timing_part, source_part = timing.split(" - ")
    d3.append([cell["hipps"], letter, cell["clinical_group"], func,
               timing_part, source_part, com, cell["weight"],
               cell["lupa_threshold"]])
write("03_hipps_grid.csv",
      ["hipps", "group_code", "clinical_group", "functional_level",
       "episode_timing", "admission_source", "comorbidity_level",
       "case_mix_weight", "lupa_threshold"], d3)

# ---- 4. LUPA threshold structure by clinical group -----------------------
d4 = []
for letter in sorted(cms_data.CLINICAL_GROUPS):
    cells = [c for k, c in table.items() if k[0] == letter]
    ths = [c["lupa_threshold"] for c in cells]
    d4.append([letter, cms_data.CLINICAL_GROUPS[letter],
               min(ths), max(ths), round(statistics.mean(ths), 2),
               sum(1 for t in ths if t >= 4), len(ths),
               round(100 * sum(1 for t in ths if t >= 4) / len(ths), 1)])
write("04_lupa_threshold_structure.csv",
      ["group_code", "clinical_group", "lupa_min", "lupa_max", "lupa_mean",
       "cells_threshold_4plus", "total_cells", "pct_cells_4plus"], d4)

# ---- 5. Reimbursement variance: group x state floor/ceiling --------------
d5 = []
for st, members in sorted(by_state.items()):
    rep = max(members, key=lambda m: m["wage_index"])
    for letter in sorted(cms_data.CLINICAL_GROUPS):
        rng = payment.payment_range(letter, rep["code"])
        d5.append([st, rep["name"], rep["wage_index"], letter,
                   cms_data.CLINICAL_GROUPS[letter],
                   rng["min_payment"], rng["max_payment"],
                   round(rng["max_payment"] - rng["min_payment"], 2)])
write("05_payment_range_by_state_group.csv",
      ["state", "reference_area", "wage_index", "group_code", "clinical_group",
       "min_payment", "max_payment", "spread"], d5)

print("\nOutput: %s" % OUT)
