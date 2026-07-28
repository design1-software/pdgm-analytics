# CY 2026 CMS Home Health PPS source data

Every number used by `services/reimbursement_service.py` comes from a file or
document listed here. Nothing is estimated or hand-entered. Downloaded
2026-07-27.

## Files in this directory

| File | Source |
|---|---|
| `case_mix_weights_lupa.csv` | [CY 2026 Final HH PDGM Case Mix Weights and LUPA Thresholds](https://www.cms.gov/files/zip/cy-2026-final-hh-pdgm-case-mix-weights-lupa-thresholds.zip) |
| `wage_index.csv` | [CY 2026 Final HH PPS Wage Index](https://www.cms.gov/files/zip/cy-2026-final-hh-pps-wage-index.zip) ("All areas - no counties listed" tab) |
| `comorbidity_interactions.xlsx` | [CY 2026 Final Low/High Comorbidity Adjustment Interactions](https://www.cms.gov/files/zip/cy-2026-final-low-comorbidity-high-comorbidity-adjustment-interactions.zip) |

All three are linked from the rule page for
[CMS-1828-F](https://www.cms.gov/medicare/payment/prospective-payment-systems/home-health/home-health-prospective-payment-system-regulations-and-notices/cms-1828-f).

Both CSVs are Windows-1252 encoded, not UTF-8.

### `case_mix_weights_lupa.csv`

432 rows — the complete grid of 12 clinical groups x 3 functional levels x 4
admission source/timing combinations x 3 comorbidity levels. `load_case_mix_table()`
asserts the count, so a partial parse fails loudly.

The HIPPS code encodes the grid positionally (derived from the data, not assumed):

| Position | Meaning |
|---|---|
| 1 | `1` Early-Community, `2` Early-Institutional, `3` Late-Community, `4` Late-Institutional |
| 2 | Clinical group `A`-`L` |
| 3 | Functional level: `A` Low, `B` Medium, `C` High |
| 4 | Comorbidity: `1` none, `2` single, `3` interaction |
| 5 | Always `1` |

Position 2 matches `pdgm_clinical_group_code` in
`CCFTF_pdgm_diagnosis_mapping.csv` one-for-one, which is what makes the
diagnosis CSV joinable to CMS weights.

Case-mix weights range 0.5364 to 1.9558. LUPA thresholds are 2, 3, 4 or 5 and
vary by HIPPS group.

### `wage_index.csv`

489 areas: 417 urban CBSAs, 51 statewide rural areas (`999xx`), and 21
transition codes (`50xxx`, created for the 5% cap on wage index decreases).
Values range 0.2719 (Puerto Rico) to 1.8317. There is no default — an unknown
area code raises rather than falling back to a guess.

## Constants transcribed into `reimbursement_service.py`

From **CR 14304 / Transmittal R13488CP**
([MLN Matters MM14304](https://www.cms.gov/files/document/mm14304-home-health-prospective-payment-system-cy-2026-rate-update.pdf)):

* Table 1 — national standardized 30-day period payment: **$2,038.22**
  (after the 0.98977 permanent and 0.97000 temporary adjustment factors)
* Table 2 — same for HHAs that did not submit quality data: **$1,998.41**
* Tables 3 and 4 — national per-visit payment amounts by discipline
* Table 7 — LUPA add-on factors: SN 1.7200, PT 1.6225, SLP 1.6696, OT 1.7238.
  These are the CY 2025-onward values; the older 1.8451 / 1.6700 / 1.6266
  factors quoted in the background section of MM14304 are superseded.

From the **CY 2026 HH PPS final rule**, 90 FR 55342 (Dec 2, 2025), at 55405-55406:

* Labor-related share **74.9%**, non-labor **25.1%** (CY 2024 and subsequent years)
* Order of operations, quoted directly:
  > Multiply the national, standardized 30-day period rate by the patient's
  > applicable case-mix weight. Divide the case-mix adjusted amount into a labor
  > (74.9 percent) and a non-labor portion (25.1 percent). Multiply the labor
  > portion by the applicable wage index based on the site of service of the
  > beneficiary. Add the wage-adjusted portion to the non-labor portion.

## Not implemented

Outlier payments (need visit minutes; FDL ratio 0.37, loss-sharing 0.80),
partial-period payment adjustments, the dNPWT device payment ($282.10), and
HHVBP adjustments.

## Refreshing for CY 2027

Replace both CSVs from the CY 2027 final rule page, update the rate constants and
`PAYMENT_YEAR` in `reimbursement_service.py`, and re-run
`tests/test_reimbursement_service.py` — the grid-completeness and formula tests
will catch a mismatched or partially updated file.
