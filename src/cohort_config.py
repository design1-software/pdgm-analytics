"""Parameters for the synthetic cohort generator.

CODE IS PUBLIC. PARAMETERS ARE NOT.

The values here are generic placeholders. They describe no real organisation.

A synthetic dataset is safe to publish; the parameters used to generate it are
not necessarily safe, because calibrating a generator to a real operation means
the parameters *are* that operation -- referral-source rankings, volume shares,
budget targets and staffing gaps are competitively sensitive even when no row of
real data is present.

To run against real values, create `cohort_config_local.py` beside this file
with any subset of the same names. It is gitignored and never committed:

    # cohort_config_local.py
    FACILITIES = {...}
    COMMUNITIES = [...]
    EPISODIC_BUDGET_PER_MONTH = ...

The generator imports the local file if it exists and falls back to these
defaults otherwise, so the repository always runs for anyone who clones it.
"""

# ---- Volume -------------------------------------------------------------
N_REFERRAL_RECORDS = 700
EPISODIC_BUDGET_PER_MONTH = 40      # illustrative target
MONTHS = ["2026-%02d" % m for m in range(2, 8)]

# ---- Clinical mix -------------------------------------------------------
# Illustrative distribution across the 12 PDGM clinical groups. NOT the ICD-10
# code distribution -- 41% of codes map to NO_GROUP, but records do not arrive
# uniformly across codes.
GROUP_MIX = {
    "E": 0.24, "A": 0.20, "C": 0.12, "H": 0.11, "L": 0.08, "B": 0.07,
    "K": 0.06, "I": 0.05, "J": 0.03, "D": 0.02, "F": 0.01, "G": 0.01,
}

# ---- Payer --------------------------------------------------------------
# Only traditional Medicare (including Medigap supplements) is governed by
# PDGM. Advantage, commercial and Medicaid are not.
PAYER_MIX = {
    "Medicare FFS": 0.24,
    "Medicare FFS + Supplement": 0.12,
    "Medicare Advantage": 0.34,
    "Commercial": 0.16,
    "Medicaid": 0.11,
    "Other": 0.03,
}
PDGM_PAYERS = {"Medicare FFS", "Medicare FFS + Supplement"}

# ---- Sources ------------------------------------------------------------
# Generic facility archetypes. Weights are illustrative.
SOURCE_MIX = {"Acute Care Hospital": 0.44, "SNF": 0.12, "Rehabilitation": 0.05,
              "Physician Office": 0.21, "Community/Home": 0.18}
INSTITUTIONAL = {"Acute Care Hospital", "SNF", "Rehabilitation"}

FACILITIES = {
    "Acute Care Hospital": [
        ("Regional Medical Center A", 0.24), ("Regional Medical Center B", 0.20),
        ("Academic Medical Center", 0.18), ("Community Hospital C", 0.14),
        ("Community Hospital D", 0.12), ("Specialty Cardiac Hospital", 0.12),
    ],
    "SNF": [("Skilled Nursing Facility A", 0.40),
            ("Skilled Nursing Facility B", 0.35),
            ("Skilled Nursing Facility C", 0.25)],
    "Rehabilitation": [("Rehabilitation Hospital A", 0.6),
                       ("Rehabilitation Hospital B", 0.4)],
    "Physician Office": [
        ("Primary Care Clinic A", 0.28), ("Primary Care Clinic B", 0.24),
        ("Multispecialty Clinic C", 0.20), ("Cardiology Clinic", 0.16),
        ("Primary Care Clinic D", 0.12),
    ],
    "Community/Home": [("Self/Family", 0.45), ("Community Case Manager", 0.35),
                       ("ALF Coordinator", 0.20)],
}
# A specialty hospital skews which clinical group arrives.
SOURCE_GROUP_SKEW = {"Specialty Cardiac Hospital": "H", "Cardiology Clinic": "H"}

# ---- Geography ----------------------------------------------------------
# Generic communities mapped to REAL CMS wage index areas, chosen to span a
# metro CBSA and a statewide rural area so the wage index effect is visible.
# County -> CBSA assignments are verifiable in the CMS wage index workbook.
COMMUNITIES = [
    ("Community 1", "Metro County",  "30780", 0.30),
    ("Community 2", "Metro County",  "30780", 0.17),
    ("Community 3", "Metro County",  "30780", 0.17),
    ("Community 4", "Metro County",  "30780", 0.11),
    ("Community 5", "Metro County",  "30780", 0.07),
    ("Community 6", "Metro County",  "30780", 0.06),
    ("Community 7", "Metro County",  "30780", 0.05),
    ("Community 8", "Rural County",  "99904", 0.04),
    ("Community 9", "Metro County",  "30780", 0.03),
]

# ---- Operations ---------------------------------------------------------
FUNCTIONAL_MIX = {"Low": 0.28, "Medium": 0.45, "High": 0.27}
COMORBIDITY_MIX = {0: 0.46, 1: 0.34, 2: 0.20}
DISPOSITION_MIX = {"Admitted": 0.74, "Declined": 0.16, "Pending": 0.10}
DECLINE_REASONS = ["Out of service area", "Insurance not accepted",
                   "No caregiver support", "Patient refused",
                   "Higher level of care needed", "Staffing capacity"]
RECERT_RATE = 0.22
LUPA_RATE_TARGET = 0.09

# Staffing capability by community. Constrained areas decline more and deliver
# fewer visits, which raises LUPA exposure. Illustrative.
STAFFING = {
    "Community 8": {"level": "Severely limited", "disciplines": "SN, PT",
                    "decline_mult": 3.2, "lupa_mult": 2.4},
    "Community 7": {"level": "Limited (no ST/HHA)",
                    "disciplines": "SN, PT, OT, MSW",
                    "decline_mult": 1.5, "lupa_mult": 1.3},
}
DEFAULT_STAFFING = {"level": "Full", "disciplines": "All",
                    "decline_mult": 1.0, "lupa_mult": 1.0}

# ---- Local override -----------------------------------------------------
try:  # pragma: no cover - optional, gitignored
    from cohort_config_local import *  # noqa: F401,F403
    USING_LOCAL_CONFIG = True
except ImportError:
    USING_LOCAL_CONFIG = False
