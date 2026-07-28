"""CY 2026 Home Health PPS payment calculation.

Every constant is transcribed from a primary CMS source and cited inline.
Nothing here is estimated or interpolated.

Sources
-------
* CR 14304 / Transmittal R13488CP, "Home Health Prospective Payment System
  (HH PPS) Rate Update for Calendar Year (CY) 2026", Tables 1-5 and 7.
* CY 2026 HH PPS final rule (CMS-1828-F), 90 FR 55342 (December 2, 2025),
  for the labor-related share and the order of operations below.
* Per-group case-mix weights, LUPA thresholds and wage index values are read
  at runtime from data/cms/cy2026/ via cms_data.

Scope: computes the case-mix and wage-adjusted 30-day period payment, and
LUPA per-visit payments. Does NOT compute outlier payments, partial-period
adjustments, or the dNPWT device add-on.
"""

import cms_data

# Transmittal R13488CP, Tables 1 and 2 -- national standardized 30-day period
# payment, after the 0.98977 permanent and 0.97000 temporary adjustments.
NATIONAL_30_DAY_RATE = 2038.22            # submitted quality data
NATIONAL_30_DAY_RATE_NO_QUALITY = 1998.41  # did not submit

# 90 FR 55405-55406: "for CY 2024 and subsequent years, the labor-related
# share will be 74.9 percent, and the non-labor-related share 25.1 percent."
LABOR_SHARE = 0.749
NON_LABOR_SHARE = 0.251

# Transmittal R13488CP, Tables 3 and 4 -- national per-visit amounts.
PER_VISIT_RATES = {
    "Home Health Aide": 80.12,
    "Medical Social Services": 283.64,
    "Occupational Therapy": 194.74,
    "Physical Therapy": 193.42,
    "Skilled Nursing": 176.96,
    "Speech-Language Pathology": 210.25,
}

# Transmittal R13488CP, Table 7. CY2025-onward values; the older
# 1.8451 / 1.6700 / 1.6266 factors are superseded.
LUPA_ADD_ON_FACTORS = {
    "Skilled Nursing": 1.7200,
    "Physical Therapy": 1.6225,
    "Speech-Language Pathology": 1.6696,
    "Occupational Therapy": 1.7238,
}

# Display abbreviations used on a plan of care.
DISCIPLINE_LABELS = {
    "Skilled Nursing": "SN", "Physical Therapy": "PT",
    "Occupational Therapy": "OT", "Speech-Language Pathology": "ST",
    "Home Health Aide": "HHA", "Medical Social Services": "SW",
}

PAYMENT_YEAR = 2026

DISCLAIMER = (
    "Estimate based on the CY 2026 HH PPS final rule (CMS-1828-F) and CR 14304. "
    "Excludes outlier payments, partial-period adjustments, dNPWT and HHVBP. "
    "Not a guarantee of payment."
)


def period_payment(case_mix_weight, wage_index, submitted_quality_data=True):
    """Case-mix and wage-adjusted 30-day period payment.

    Follows the order of operations in 90 FR 55405-55406 exactly:
    case-mix adjust, split labor / non-labor, wage-adjust the labor portion,
    recombine.
    """
    base = (NATIONAL_30_DAY_RATE if submitted_quality_data
            else NATIONAL_30_DAY_RATE_NO_QUALITY)
    case_mix_adjusted = base * case_mix_weight
    labor = case_mix_adjusted * LABOR_SHARE * wage_index
    non_labor = case_mix_adjusted * NON_LABOR_SHARE
    return labor + non_labor


def calculate(clinical_group, functional_level, admission_source_timing,
              comorbidity_level, area_code, visits_by_discipline=None,
              first_skilled_discipline=None, submitted_quality_data=True):
    """Full payment for one 30-day period.

    All five case-mix/geography inputs are required -- there are no defaults.
    A diagnosis alone identifies only the clinical group; guessing the rest
    is what produces wrong numbers.
    """
    cell = cms_data.load_case_mix_table()[
        (clinical_group, functional_level, admission_source_timing,
         comorbidity_level)
    ]
    area = cms_data.load_wage_index()[str(area_code).strip()]
    wi = area["wage_index"]

    result = {
        "hipps_code": cell["hipps"],
        "clinical_group": cell["clinical_group"],
        "case_mix_weight": cell["weight"],
        "lupa_threshold": cell["lupa_threshold"],
        "area_code": area["code"],
        "area_name": area["name"],
        "wage_index": wi,
        "period_payment": round(period_payment(cell["weight"], wi,
                                               submitted_quality_data), 2),
        "is_lupa": False,
        "payment_year": PAYMENT_YEAR,
        "disclaimer": DISCLAIMER,
    }
    result["estimated_payment"] = result["period_payment"]

    if visits_by_discipline:
        total = sum(int(v) for v in visits_by_discipline.values())
        result["total_visits"] = total
        if total < cell["lupa_threshold"]:
            rates = PER_VISIT_RATES
            amount = 0.0
            for discipline, visits in visits_by_discipline.items():
                rate = rates[discipline]
                adjusted = rate * LABOR_SHARE * wi + rate * NON_LABOR_SHARE
                amount += adjusted * int(visits)
            if first_skilled_discipline in LUPA_ADD_ON_FACTORS:
                rate = rates[first_skilled_discipline]
                adjusted = rate * LABOR_SHARE * wi + rate * NON_LABOR_SHARE
                amount += adjusted * (LUPA_ADD_ON_FACTORS[first_skilled_discipline] - 1)
            result["is_lupa"] = True
            result["estimated_payment"] = round(amount, 2)
    return result


def payment_range(clinical_group, area_code, comorbidity_level=None):
    """Floor and ceiling across every functional level and admission timing.

    Used when only the diagnosis and location are known -- which is the normal
    case at intake. Returns the span rather than implying a single number is
    knowable from a diagnosis code.
    """
    levels = (cms_data.COMORBIDITY_LEVELS if comorbidity_level is None
              else (comorbidity_level,))
    payments = []
    for functional in cms_data.FUNCTIONAL_LEVELS:
        for timing in cms_data.ADMISSION_SOURCE_TIMINGS:
            for comorbidity in levels:
                payments.append(calculate(clinical_group, functional, timing,
                                          comorbidity, area_code))
    lo = min(payments, key=lambda p: p["period_payment"])
    hi = max(payments, key=lambda p: p["period_payment"])
    return {
        "clinical_group": lo["clinical_group"],
        "area_name": lo["area_name"],
        "wage_index": lo["wage_index"],
        "combinations": len(payments),
        "min_payment": lo["period_payment"],
        "max_payment": hi["period_payment"],
        "min_hipps": lo["hipps_code"],
        "max_hipps": hi["hipps_code"],
        "lupa_thresholds": sorted({p["lupa_threshold"] for p in payments}),
        "payment_year": PAYMENT_YEAR,
    }
