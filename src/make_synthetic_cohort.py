"""Generate a SYNTHETIC home health intake cohort for dashboard development.

Produces a simulated cohort with a realistic schema so the analysis pipeline
and dashboards can be built and demonstrated end to end without touching any
real records.

WHAT IS REAL vs SIMULATED
    REAL       ICD-10 -> PDGM clinical group mapping (CCFTF, 74,719 rows)
    REAL       CY2026 CMS case-mix weights and LUPA thresholds (432 cells)
    REAL       CY2026 CMS wage index values and CBSA codes
    SIMULATED  every record: volumes, payer mix, source mix, dispositions,
               comorbidity capture, visit counts, geography labels

    Every output row carries is_synthetic=TRUE, and the output file name says
    SYNTHETIC. Any chart built from this must say so on its face. These numbers
    describe no real organisation, branch, or person.

PARAMETERS
    All distributions live in cohort_config.py and are illustrative
    placeholders. They are not measured from any operation. See that file for
    why parameters are kept separate from this code.
"""

import collections
import csv
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "outputs", "synthetic")
sys.path.insert(0, os.path.join(ROOT, "src"))
import cms_data
import payment
from payment import PER_VISIT_RATES

SEED = 20260728

# Parameters live in cohort_config.py (generic defaults, safe to publish).
# Real operating values go in cohort_config_local.py, which is gitignored --
# a generator calibrated to a real operation encodes that operation.
from cohort_config import *  # noqa: F401,F403
import cohort_config

N_REFERRALS = N_REFERRAL_RECORDS


def pick(mapping, rng):
    r, acc = rng.random(), 0.0
    for k, p in mapping.items():
        acc += p
        if r <= acc:
            return k
    return list(mapping)[-1]


def main():
    rng = random.Random(SEED)
    os.makedirs(OUT, exist_ok=True)

    # Real ICD-10 codes, grouped by their real clinical group
    codes = collections.defaultdict(list)
    with open(os.path.join(ROOT, "data", "CCFTF_pdgm_diagnosis_mapping.csv"),
              encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            g = row["pdgm_clinical_group_code"].strip()
            if g in GROUP_MIX:
                codes[g].append((row["icd10_code"], row["description"],
                                 row["COMORBIDITY_GROUP"]))

    
    areas = cms_data.load_wage_index()
    community_w = [c[3] for c in COMMUNITIES]

    rows = []
    for i in range(1, N_REFERRALS + 1):
        # source first -- a specialty hospital skews which clinical group arrives
        source_type = pick(SOURCE_MIX, rng)
        _f = FACILITIES[source_type]
        facility = rng.choices([x[0] for x in _f], weights=[x[1] for x in _f])[0]
        group = pick(GROUP_MIX, rng)
        if facility in SOURCE_GROUP_SKEW and rng.random() < 0.75:
            group = SOURCE_GROUP_SKEW[facility]
        icd, desc, comorb_grp = rng.choice(codes[group])
        community, county, area_code, _ = rng.choices(COMMUNITIES, weights=community_w)[0]
        payer = pick(PAYER_MIX, rng)
        functional = pick(FUNCTIONAL_MIX, rng)
        comorbidity = pick(COMORBIDITY_MIX, rng)
        staffing = STAFFING.get(community, DEFAULT_STAFFING)
        p_decline = min(0.85, DISPOSITION_MIX["Declined"] * staffing["decline_mult"])
        roll = rng.random()
        if roll < p_decline:
            disposition = "Declined"
        elif roll < p_decline + DISPOSITION_MIX["Pending"]:
            disposition = "Pending"
        else:
            disposition = "Admitted"
        is_recert = rng.random() < RECERT_RATE

        institutional = source_type in INSTITUTIONAL
        timing = "%s - %s" % ("Late" if is_recert else "Early",
                              "Institutional" if institutional else "Community")

        pay = payment.calculate(group, functional, timing, comorbidity,
                                    area_code)
        threshold = pay["lupa_threshold"]

        visits = {}
        total_visits = ""
        est_payment = ""
        is_lupa = ""
        if disposition == "Admitted":
            if rng.random() < min(0.6, LUPA_RATE_TARGET * staffing["lupa_mult"]):
                total = rng.randint(1, max(1, threshold - 1))
            else:
                total = rng.randint(threshold, threshold + rng.randint(2, 9))
            sn = max(1, int(total * rng.uniform(0.4, 0.7)))
            pt = max(0, int((total - sn) * rng.uniform(0.4, 0.9)))
            ot = max(0, total - sn - pt)
            visits = {"Skilled Nursing": sn, "Physical Therapy": pt,
                      "Occupational Therapy": ot}
            visits = {k: v for k, v in visits.items() if v > 0}
            paid = payment.calculate(
                group, functional, timing, comorbidity, area_code,
                visits_by_discipline=visits,
                first_skilled_discipline="Skilled Nursing")
            total_visits = total
            est_payment = paid["estimated_payment"]
            is_lupa = "TRUE" if paid["is_lupa"] else "FALSE"

        rows.append({
            "synthetic_record_id": "SYN_%04d" % i,
            "is_synthetic": "TRUE",
            "record_month": rng.choice(MONTHS),
            "source_facility": facility,
            "source_type": source_type,
            "prior_setting": "Inpatient" if institutional else "Home",
            "admission_source": "Institutional" if institutional else "Community",
            "admission_type": "Recertification" if is_recert else "New admission",
            "primary_icd10": icd,
            "primary_dx_description": desc,
            "clinical_group_code": group,
            "clinical_group": cms_data.CLINICAL_GROUPS[group],
            "comorbidity_group": comorb_grp,
            "comorbidity_level": comorbidity,
            "functional_level": functional,
            "community": community,
            "county": county,
            "area_code": area_code,
            "area_name": areas[area_code]["name"],
            "wage_index": areas[area_code]["wage_index"],
            "payer_type": payer,
            "pdgm_in_scope": "TRUE" if payer in PDGM_PAYERS else "FALSE",
            "disposition": disposition,
            "decline_reason": ((rng.choice(DECLINE_REASONS)
                                if staffing["level"] == "Full" or rng.random() > 0.6
                                else "Staffing capacity")
                               if disposition == "Declined" else ""),
            "staffing_level": staffing["level"],
            "disciplines_available": staffing["disciplines"],
            "hipps_code": pay["hipps_code"],
            "case_mix_weight": pay["case_mix_weight"],
            "lupa_threshold": threshold,
            "total_visits": total_visits,
            "is_lupa": is_lupa,
            "estimated_payment": est_payment,
        })

    path = os.path.join(OUT, "SYNTHETIC_intake_records.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    print("Wrote %s  (%d rows, %d columns)" % (path, len(rows), len(rows[0])))
    ffs = [r for r in rows if r["pdgm_in_scope"] == "TRUE"]
    adm = [r for r in rows if r["disposition"] == "Admitted"]
    lup = [r for r in adm if r["is_lupa"] == "TRUE"]
    print("  Medicare FFS (PDGM in scope): %d (%.0f%%)"
          % (len(ffs), 100 * len(ffs) / len(rows)))
    print("  Admitted: %d   LUPA episodes: %d (%.1f%% of admitted)"
          % (len(adm), len(lup), 100 * len(lup) / len(adm)))
    inst = sum(1 for r in rows if r["admission_source"] == "Institutional")
    print("  Institutional admission source: %d (%.0f%%)"
          % (inst, 100 * inst / len(rows)))
    print("  Distinct clinical groups present: %d"
          % len(set(r["clinical_group"] for r in rows)))


if __name__ == "__main__":
    main()
