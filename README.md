# PDGM Analytics

Medicare home health reimbursement analysis built on primary CMS sources.

I work intake at a home health branch. This started as a payment estimator in a
production Flask app, and became a data-provenance rebuild when I found the
numbers underneath it were invented.

---

## What happened

The app's payment engine presented itself as CMS-derived. It wasn't:

| | What it used | What CMS publishes |
|---|---|---|
| Case-mix weights | 12 hand-written multipliers, 0.95–1.10 | 432 HIPPS cells, 0.5364–1.9558 |
| Wage index | 18 hardcoded ZIP prefixes, defaulting to 0.95 | 489 areas, 0.2719–1.8317 |
| LUPA thresholds | 4 constants | Per-HIPPS, varies 2–5 |
| Base rate | $1,901.12, labor share 68.7% | $2,038.22, labor share 74.9% |

A second module carried a 432-row weight table commented *"Source: CMS HH PPS
FY2026 Final Rule, Table 2."* Checked against the real table, **20 of its 367
distinct values appeared anywhere in CMS's actual 412**, and 90 of 144 code
families had comorbidity steps that were a constant additive delta — generated,
not transcribed. None of its 432 keys were valid HIPPS codes: it used `A1111`
where CMS uses `1KC11`.

Everything here is rebuilt from the CY 2026 HH PPS final rule (CMS-1828-F) and
CR 14304, read at runtime from `data/cms/cy2026/`. Provenance for every constant
is in [`data/cms/cy2026/SOURCES.md`](data/cms/cy2026/SOURCES.md), and
[`tests/test_payment.py`](tests/test_payment.py) pins each one to its source so a
future edit can't quietly substitute an estimate.

---

## Analyses

### Referral coding quality — the intake view

Of the 74,719 ICD-10 codes in the PDGM mapping, **only 53.9% are clean as a
primary diagnosis.** Each of the rest fails a gate that has to be caught at
intake:

| Gate | Codes | Share |
|---|---|---|
| No PDGM clinical group | 30,902 | 41.4% |
| External cause of injury — never principal | 7,461 | 10.0% |
| Code-first sequencing requirement | 5,220 | 7.0% |
| Section 111 excluded | 5,000 | 6.7% |
| Unspecified — more specific code exists | 3,473 | 4.6% |
| Unacceptable as principal | 1,603 | 2.1% |
| Manifestation — needs etiology first | 422 | 0.6% |

Difficulty is not evenly distributed. **MMTA-Cardiac carries a coding pitfall in
34.1% of its codes; Neuro Rehab in 3.2%.** A cardiac case is ten times more
likely to arrive needing rework.

A CRM records that an intake arrived. A BI tool records what it was worth.
Neither knows that a code is a manifestation requiring its etiology sequenced
first. That screen happens at intake, and this quantifies it.

### Payment structure

- **Payment is not knowable from a diagnosis code.** A HIPPS code has four
  dimensions — clinical group, functional level, admission source/timing,
  comorbidity. A diagnosis fixes one. So the honest output is a range across the
  other 36 combinations, not a single figure.
- **Wage index never changes ranking.** It is a scalar multiplier, so the
  ordering of clinical groups by payment is identical in Puerto Rico (0.2719)
  and San Jose (1.8317). "Top diagnoses by reimbursement per state" is not a
  real analysis; a test asserts this.
- **Higher payment demands more visits.** Spearman correlation between a group's
  average case-mix weight and its average LUPA threshold is **0.65**. Wound pays
  the most and needs 4+ visits in 75% of its cells; Complex and MMTA-Infectious
  never exceed 3. Gross payment is not margin.

---

## Synthetic intake cohort

`outputs/synthetic/SYNTHETIC_intake_records.csv` — **700 simulated records. No
real patient, agency, or organisational data.** Every row carries
`is_synthetic=TRUE`.

| Layer | Real or simulated |
|---|---|
| Case-mix weights, LUPA thresholds, wage index, national rate | **Real CMS** |
| ICD-10 → clinical group mapping | **Real CCFTF** |
| CBSA codes and wage index values | **Real CMS** |
| Every record, and all geography/facility labels | **Simulated** |

### Why the parameters are separated from the code

A synthetic dataset is safe to share. The parameters used to generate it are
not necessarily safe: calibrating a generator against a real operation means the
parameters *become* that operation. Referral-source rankings, volume shares,
budget targets and staffing constraints are competitively sensitive even when no
row of real data appears anywhere.

So `src/cohort_config.py` holds generic, illustrative placeholders and is
public. Real values, if used, go in `cohort_config_local.py`, which is
gitignored and never committed. The generator prefers the local file when
present and falls back to the defaults, so the repository always runs for anyone
who clones it.

This is the same separation a governed analytics team applies between code and
configuration, and the reason portfolio work is built on public or synthetic
inputs rather than sanitized production data.

---|---|
| Case-mix weights, LUPA thresholds, wage index, national rate | **Real CMS** |
| ICD-10 → clinical group mapping | **Real CCFTF** |
| County → CBSA assignments | **Real, verified against the CMS wage index workbook** |
| Service area and volume shape | **Real** (branch-reported) |
| Referral records, payer mix, dispositions, visit counts | **Simulated** |

Assumptions are declared at the top of
[`src/cohort_config.py`](src/cohort_config.py). Any chart built from this must say "synthetic" on its face.

---

## Layout

```
data/cms/cy2026/     CMS source files + SOURCES.md provenance
data/                CCFTF PDGM mapping, Section 111 exclusion list
src/cms_data.py      Loaders. No default wage index -- unknown areas raise
src/payment.py       CY2026 payment calculation, every constant cited inline
src/intake_quality.py        Referral coding-quality gates
src/build_cms_extracts.py    Tableau extracts from CMS data only
src/cohort_config.py         Generator parameters (generic placeholders)
src/make_synthetic_cohort.py Synthetic cohort generator
outputs/tableau/     Generated CSVs (CMS-derived, no PHI)
outputs/synthetic/   Generated cohort (synthetic, no PHI)
tests/               13 tests pinning the engine to its sources
```

## Running it

```bash
pip install -r requirements.txt
python3 src/build_cms_extracts.py      # CMS extracts for Tableau
python3 src/intake_quality.py          # coding-quality gates
python3 src/make_synthetic_cohort.py
python3 src/make_figures.py            # reads the extracts above
python3 -m pytest tests/ -q
```

No database and no API keys. The CMS files are in the repo; everything is
computed from them at run time.

## Reproducibility

Everything in `outputs/` is generated, and CI regenerates all of it on every
push and fails if a single byte differs from what is committed. A green run
means the published CSVs and figures are exactly what this code produces from
this data — not a snapshot someone exported once and forgot.

Three things are pinned to make that possible:

- **Dependencies.** `requirements.txt` is fully pinned. matplotlib in
  particular renders differently across releases, so an unpinned upgrade would
  read as "the analysis changed."
- **The font.** Inter is vendored in `assets/fonts/` (SIL OFL 1.1) and
  registered explicitly. A fallback list like
  `Helvetica Neue → Helvetica → Arial → DejaVu Sans` resolves differently on
  macOS and on a Linux runner, which changes glyph metrics and therefore the
  layout.
- **Timestamps.** matplotlib stamps a creation date into the SVG and its own
  version into the PNG. Both are suppressed; otherwise every run differs from
  the last regardless of the data.

If you change an analysis, re-run the scripts above and commit the regenerated
outputs along with the code.

## Refreshing for CY 2027

Replace the two CSVs in `data/cms/cy2026/` from the CY 2027 final rule, update
the rate constants and `PAYMENT_YEAR` in `src/payment.py`, and re-run the tests
— the grid-completeness and formula tests catch a partial or mismatched update.

---

## Note on data handling

No patient data and no organisational data are present in this repository, and
none passed through the analysis. The CMS files are public. The cohort is
generated from the illustrative parameters in `src/cohort_config.py`.

Portfolio and demonstration work here is built on public or synthetic inputs by
design, rather than on sanitized production data.
