"""Referral coding quality: what an intake nurse screens every diagnosis for.

A referral's primary diagnosis has to clear several independent gates before it
can anchor a PDGM episode. Miss one and the referral comes back for rework, or
the episode is grouped wrong.

This is the analysis a CRM cannot produce: Salesforce records that a referral
arrived, and a BI tool records what it was worth. Neither knows that a code is
a manifestation requiring its etiology sequenced first, or that it is flagged
unacceptable as a principal diagnosis.

Reads only the CCFTF PDGM mapping and the CMS Section 111 exclusion list.
No patient data is involved at any point.
"""

import collections
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAPPING = os.path.join(ROOT, "data", "CCFTF_pdgm_diagnosis_mapping.csv")
EXCLUSIONS = os.path.join(ROOT, "data", "section111_excluded_icd10_fy2026.xlsx")
OUT = os.path.join(ROOT, "outputs", "tableau")

# Each gate: (column, failing value, label, why it matters at intake)
GATES = [
    ("NO_GROUP", None, "No PDGM clinical group",
     "Cannot anchor an episode; needs a different primary diagnosis"),
    ("UNACCEPTABLE_PDX", "1", "Unacceptable as principal",
     "CMS bars this code as a principal diagnosis"),
    ("UNSPECIFIED_PDX", "1", "Unspecified",
     "A more specific code exists and should be obtained"),
    ("MANIFESTATION_FLAG", "1", "Manifestation code",
     "Underlying etiology must be sequenced first"),
    ("ECOI_FLAG", "1", "External cause of injury",
     "Never valid as a principal diagnosis"),
    ("CODE_FIRST", "nonzero", "Code-first requirement",
     "Another diagnosis must be sequenced ahead of it"),
]


def load_exclusions():
    try:
        import openpyxl
    except ImportError:
        return set()
    wb = openpyxl.load_workbook(EXCLUSIONS, read_only=True, data_only=True)
    out = set()
    for ws in wb.worksheets:
        header = [str(c.value).strip().upper() if c.value else ""
                  for c in next(ws.iter_rows(min_row=1, max_row=1))]
        idx = next((i for i, h in enumerate(header) if h == "CODE"), 0)
        for row in ws.iter_rows(min_row=2):
            v = row[idx].value
            if isinstance(v, str) and v.strip():
                out.add(v.replace(".", "").replace(" ", "").upper())
    wb.close()
    return out


def fails(row, column, failing):
    if column == "NO_GROUP":
        return row["pdgm_clinical_group_name"] == "NO_GROUP"
    if failing == "nonzero":
        return row[column] not in ("0", "")
    return row[column] == failing


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(MAPPING, encoding="utf-8", errors="replace") as fh:
        rows = list(csv.DictReader(fh))
    excluded = load_exclusions()
    n = len(rows)

    print("Referral coding quality — %d ICD-10 codes in the PDGM mapping\n" % n)

    gate_rows = []
    for column, failing, label, why in GATES:
        hits = sum(1 for r in rows if fails(r, column, failing))
        gate_rows.append([label, hits, round(100 * hits / n, 2), why])
        print("  %-30s %6d  %5.1f%%" % (label, hits, 100 * hits / n))

    excl_hits = sum(1 for r in rows if r["icd10_code"] in excluded)
    gate_rows.append(["Section 111 excluded", excl_hits,
                      round(100 * excl_hits / n, 2),
                      "Excluded from primary selection under Section 111"])
    print("  %-30s %6d  %5.1f%%" % ("Section 111 excluded", excl_hits,
                                    100 * excl_hits / n))

    clean = [r for r in rows
             if all(not fails(r, c, f) for c, f, _, _ in GATES)
             and r["icd10_code"] not in excluded]
    print("\n  %-30s %6d  %5.1f%%" % ("CLEAN as PDGM primary", len(clean),
                                      100 * len(clean) / n))

    with open(os.path.join(OUT, "06_intake_coding_gates.csv"), "w",
              newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["gate", "codes_failing", "pct_of_all_codes", "why_it_matters"])
        w.writerows(gate_rows)
        w.writerow(["Clean as PDGM primary", len(clean),
                    round(100 * len(clean) / n, 2),
                    "Passes every gate above"])

    # Per-group coding difficulty: how often a codeable group hides a pitfall
    per_group = collections.defaultdict(lambda: [0, 0, 0])
    for r in rows:
        name = r["pdgm_clinical_group_name"]
        if name == "NO_GROUP":
            continue
        per_group[name][0] += 1
        if (r["UNSPECIFIED_PDX"] == "1" or r["MANIFESTATION_FLAG"] == "1"
                or r["CODE_FIRST"] not in ("0", "")):
            per_group[name][1] += 1
        if r["icd10_code"] in excluded:
            per_group[name][2] += 1

    data = []
    for name, (total, pitfall, excl) in per_group.items():
        data.append([name, total, pitfall, round(100 * pitfall / total, 1),
                     excl, round(100 * excl / total, 1)])
    data.sort(key=lambda r: -r[3])

    with open(os.path.join(OUT, "07_coding_difficulty_by_group.csv"), "w",
              newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["clinical_group", "codes", "codes_with_pitfall",
                    "pct_with_pitfall", "section111_excluded", "pct_excluded"])
        w.writerows(data)

    print("\nCoding difficulty by clinical group (pitfall = unspecified,")
    print("manifestation, or code-first requirement):\n")
    print("  %-18s %7s %10s %9s" % ("group", "codes", "pitfalls", "rate"))
    for name, total, pitfall, pct, _, _ in data[:6]:
        print("  %-18s %7d %10d %8.1f%%" % (name, total, pitfall, pct))

    print("\nWrote 06_intake_coding_gates.csv and "
          "07_coding_difficulty_by_group.csv to outputs/tableau/")


if __name__ == "__main__":
    main()
