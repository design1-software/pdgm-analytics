"""Tests that pin the payment engine to its published CMS sources.

These exist because the original implementation of this calculation used
invented case-mix multipliers and eighteen hardcoded ZIP-prefix wage index
guesses. Every assertion below traces to a specific CMS document, so a future
edit that silently substitutes an estimate fails here.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import cms_data
import payment


# -- source data integrity -------------------------------------------------

def test_case_mix_grid_is_complete():
    """CMS publishes 12 groups x 3 functional x 4 timing x 3 comorbidity."""
    table = cms_data.load_case_mix_table()
    assert len(table) == 432
    assert table[("K", "High", "Early - Community", 0)]["hipps"] == "1KC11"


def test_every_grid_cell_resolves():
    table = cms_data.load_case_mix_table()
    for letter in cms_data.CLINICAL_GROUPS:
        for functional in cms_data.FUNCTIONAL_LEVELS:
            for timing in cms_data.ADMISSION_SOURCE_TIMINGS:
                for comorbidity in cms_data.COMORBIDITY_LEVELS:
                    cell = table[(letter, functional, timing, comorbidity)]
                    assert cell["weight"] > 0
                    assert cell["lupa_threshold"] in (2, 3, 4, 5)


def test_wage_index_has_no_default():
    """Guessing a wage index is the defect this rebuild exists to remove."""
    assert cms_data.get_wage_index("99901") == 0.6367
    with pytest.raises(KeyError):
        cms_data.get_wage_index("00000")


def test_wage_index_area_counts():
    areas = cms_data.load_wage_index()
    assert len(areas) == 489
    kinds = {}
    for a in areas.values():
        kinds[a["kind"]] = kinds.get(a["kind"], 0) + 1
    assert kinds == {"urban": 417, "rural": 51, "transition": 21}


# -- the payment formula ---------------------------------------------------

def test_payment_matches_the_published_formula():
    """90 FR 55405: case-mix adjust, split 74.9/25.1, wage-adjust labor."""
    result = payment.calculate("K", "High", "Early - Community", 0, "10180")
    expected = (payment.NATIONAL_30_DAY_RATE
                * result["case_mix_weight"]
                * (payment.LABOR_SHARE * result["wage_index"]
                   + payment.NON_LABOR_SHARE))
    assert result["period_payment"] == round(expected, 2)
    assert result["hipps_code"] == "1KC11"


def test_wage_index_of_one_equals_national_rate():
    """0.749 * 1.0 + 0.251 == 1.0, so WI 1.0 is the unadjusted rate."""
    weight = 1.2345
    assert round(payment.period_payment(weight, 1.0), 4) == \
        round(payment.NATIONAL_30_DAY_RATE * weight, 4)


def test_no_quality_data_pays_less():
    kwargs = dict(clinical_group="K", functional_level="High",
                  admission_source_timing="Early - Community",
                  comorbidity_level=0, area_code="10180")
    assert (payment.calculate(submitted_quality_data=False, **kwargs)["period_payment"]
            < payment.calculate(**kwargs)["period_payment"])


def test_geography_changes_payment_but_never_ranking():
    """Wage index is a scalar multiplier: it moves magnitude, not order.

    This is why 'top diagnoses by reimbursement per state' is not a real
    analysis -- the ranking is identical in every state.
    """
    def ranking(area):
        pays = [(g, payment.payment_range(g, area)["max_payment"])
                for g in cms_data.CLINICAL_GROUPS]
        return [g for g, _ in sorted(pays, key=lambda t: -t[1])]

    cheapest = min(cms_data.load_wage_index().values(),
                   key=lambda a: a["wage_index"])["code"]
    dearest = max(cms_data.load_wage_index().values(),
                  key=lambda a: a["wage_index"])["code"]
    assert ranking(cheapest) == ranking(dearest)


# -- LUPA ------------------------------------------------------------------

def test_lupa_pays_per_visit_below_threshold():
    kwargs = dict(clinical_group="F", functional_level="High",
                  admission_source_timing="Early - Community",
                  comorbidity_level=0, area_code="10180")
    full = payment.calculate(**kwargs)
    lupa = payment.calculate(visits_by_discipline={"Skilled Nursing": 1},
                             first_skilled_discipline="Skilled Nursing",
                             **kwargs)
    assert lupa["is_lupa"] is True
    assert lupa["estimated_payment"] < full["period_payment"]


def test_visits_at_threshold_pay_the_full_period():
    result = payment.calculate(
        "F", "High", "Early - Community", 0, "10180",
        visits_by_discipline={"Skilled Nursing": 20})
    assert result["is_lupa"] is False
    assert result["estimated_payment"] == result["period_payment"]


def test_lupa_thresholds_vary_by_group():
    """The original implementation returned one hardcoded threshold."""
    thresholds = set()
    for timing in cms_data.ADMISSION_SOURCE_TIMINGS:
        for functional in cms_data.FUNCTIONAL_LEVELS:
            thresholds.add(payment.calculate(
                "F", functional, timing, 0, "10180")["lupa_threshold"])
    assert len(thresholds) > 1


# -- payment range ---------------------------------------------------------

def test_range_spans_all_thirty_six_combinations():
    result = payment.payment_range("E", "10180")
    assert result["combinations"] == 36
    assert result["min_payment"] < result["max_payment"]


def test_range_narrows_when_comorbidity_is_known():
    wide = payment.payment_range("E", "10180")
    narrow = payment.payment_range("E", "10180", comorbidity_level=0)
    assert narrow["combinations"] == 12
    assert narrow["max_payment"] < wide["max_payment"]
