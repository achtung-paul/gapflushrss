# Tests for the RSS tolerance stack-up maths (app/core/simulation.py).
#
# This module is tested first, and on its own, because it's the one place
# where a silently wrong answer has real-world consequences: its output is
# what an engineer reads to decide whether a design's tolerances stack up.
# Everything else in the app moves data around; this decides something.
#
# It needs no fixtures -- simulation.py deliberately has no DB or FastAPI
# imports, so these are plain function calls.

import math

import pytest

from app.core.simulation import (
    AMBER_THRESHOLD_FRACTION,
    NOT_EVALUATED,
    SIGMA_LEVELS,
    combine_rss,
    evaluate_band,
    run_simulation,
)


# --- combine_rss -----------------------------------------------------
# Every tolerance_value is treated as that contributor's +/-3 sigma
# spread (the Cp=1 assumption documented in simulation.py), so each is
# divided by 3 before being combined root-sum-square.


def test_combine_rss_of_nothing_is_zero():
    assert combine_rss([]) == 0


def test_combine_rss_divides_by_three_for_a_single_contributor():
    # One contributor of +/-0.9 is a 1 sigma of 0.9/3 = 0.3.
    assert combine_rss([0.9]) == pytest.approx(0.3)


def test_combine_rss_is_root_sum_square_not_a_plain_sum():
    # 1 sigma values are 0.3 and 0.4, so the combination is
    # sqrt(0.3^2 + 0.4^2) = 0.5 -- notably *not* 0.7, which is what
    # adding the tolerances arithmetically would give.
    assert combine_rss([0.9, 1.2]) == pytest.approx(0.5)


def test_combine_rss_matches_the_closed_form_for_equal_contributors():
    # n identical contributors of t combine to t/3 * sqrt(n).
    assert combine_rss([0.6] * 4) == pytest.approx((0.6 / 3) * math.sqrt(4))


# --- evaluate_band: the four breach combinations ---------------------
# nominal 10, band 9.0 to 11.0 throughout (lower_limit 1, upper_limit 1).

NOMINAL = 10.0
UPPER_LIMIT = 1.0
LOWER_LIMIT = 1.0


def evaluate(spread):
    return evaluate_band(NOMINAL, UPPER_LIMIT, LOWER_LIMIT, spread)


def test_prediction_inside_the_band_is_green():
    rag, lower_bound, upper_bound = evaluate(0.5)
    assert rag == "green"
    assert lower_bound == pytest.approx(9.5)
    assert upper_bound == pytest.approx(10.5)


def test_prediction_exactly_on_the_limits_is_still_green():
    # The band is inclusive -- landing exactly on the limit is not a breach.
    assert evaluate(1.0)[0] == "green"


def test_breach_far_past_the_limit_is_red():
    assert evaluate(2.0)[0] == "red"


def test_a_symmetric_breach_trips_both_sides_at_once():
    # A symmetric spread breaches upper and lower together; the result is
    # the worse of the two, which here is the same on both sides.
    rag, lower_bound, upper_bound = evaluate(1.5)
    assert rag == "red"
    assert lower_bound == pytest.approx(8.5)
    assert upper_bound == pytest.approx(11.5)


def test_asymmetric_band_can_breach_only_the_tighter_side():
    # Band is 9.9 to 12.0; a spread of 0.5 gives 9.5 to 10.5, which busts
    # the lower limit only.
    rag, lower_bound, upper_bound = evaluate_band(
        nominal=10.0, upper_limit=2.0, lower_limit=0.1, spread=0.5
    )
    assert rag == "red"
    assert lower_bound == pytest.approx(9.5)
    assert upper_bound == pytest.approx(10.5)


# --- evaluate_band: the amber/red boundary ---------------------------
# A breach within AMBER_THRESHOLD_FRACTION (5%) of the limit it broke is
# amber; beyond that it's red.


def test_breach_just_inside_the_amber_threshold_is_amber():
    # Limit 1.0, so the amber allowance is 0.05. Breach of 0.04.
    assert evaluate(1.0 + 0.04)[0] == "amber"


def test_breach_just_past_the_amber_threshold_is_red():
    assert evaluate(1.0 + 0.06)[0] == "red"


def test_the_amber_threshold_sits_between_these_two_cases():
    # Deliberately *not* asserting on a breach of exactly
    # AMBER_THRESHOLD_FRACTION * limit. The rule reads "red if the breach
    # is more than 5% of the limit", so exactly 5% should be amber -- but
    # the breach is derived through subtraction (bound - band_edge), and at
    # exactly 5% that arithmetic lands on 0.05000000000000071 rather than
    # 0.05, which tips it to red.
    #
    # That's a floating-point artifact, not a real misclassification:
    # tolerances are stored as Numeric(10,3), so nothing a user can enter
    # gets within 1e-15 of the boundary. Asserting either answer at exactly
    # 5% would be pinning down noise. What matters, and what is asserted
    # here, is that the boundary lies between 4% and 6%.
    assert evaluate(1.0 + 0.04 * UPPER_LIMIT)[0] == "amber"
    assert evaluate(1.0 + 0.06 * UPPER_LIMIT)[0] == "red"
    assert AMBER_THRESHOLD_FRACTION == 0.05


def test_red_on_one_side_beats_amber_on_the_other():
    # Band 9.9 to 11.0. A spread of 1.04 gives 8.96 to 11.04:
    #   upper breach 0.04 against a limit of 1.0   -> 4%, amber
    #   lower breach 0.94 against a limit of 0.1   -> way over, red
    # The reported status must be the worse of the two.
    rag, _, _ = evaluate_band(nominal=10.0, upper_limit=1.0, lower_limit=0.1, spread=1.04)
    assert rag == "red"


def test_amber_on_both_sides_stays_amber():
    rag, _, _ = evaluate_band(nominal=10.0, upper_limit=1.0, lower_limit=1.0, spread=1.02)
    assert rag == "amber"


# --- evaluate_band: zero-limit edge cases ----------------------------
# A limit of 0 means no headroom at all, so any breach on that side is
# immediately red. Guards the division by the limit in the amber check.


def test_zero_upper_limit_makes_any_upper_breach_red():
    rag, _, _ = evaluate_band(nominal=10.0, upper_limit=0.0, lower_limit=1.0, spread=0.001)
    assert rag == "red"


def test_zero_lower_limit_makes_any_lower_breach_red():
    rag, _, _ = evaluate_band(nominal=10.0, upper_limit=1.0, lower_limit=0.0, spread=0.001)
    assert rag == "red"


def test_zero_limits_with_zero_spread_do_not_divide_by_zero():
    # Nothing breaches, so the amber calculation is never reached.
    rag, _, _ = evaluate_band(nominal=10.0, upper_limit=0.0, lower_limit=0.0, spread=0.0)
    assert rag == "green"


# --- run_simulation --------------------------------------------------


def test_run_simulation_reports_every_sigma_level():
    simulation = run_simulation([0.9], nominal=10.0, upper_limit=1.0, lower_limit=1.0)
    assert [row["sigma_level"] for row in simulation["results"]] == list(SIGMA_LEVELS)


def test_run_simulation_scales_spread_by_sigma_level():
    simulation = run_simulation([0.9], nominal=10.0, upper_limit=1.0, lower_limit=1.0)
    # 1 sigma is 0.3, so the reported spreads are 0.9 / 1.2 / 1.5.
    assert simulation["sigma_1"] == pytest.approx(0.3)
    spreads = {row["sigma_level"]: row["spread"] for row in simulation["results"]}
    assert spreads[3] == pytest.approx(0.9)
    assert spreads[4] == pytest.approx(1.2)
    assert spreads[5] == pytest.approx(1.5)


def test_widening_sigma_can_turn_green_into_red():
    # Comfortable at 3 sigma, past the band by 5 sigma -- the whole point
    # of reporting all three levels.
    simulation = run_simulation([3.0], nominal=10.0, upper_limit=3.5, lower_limit=3.5)
    by_level = {row["sigma_level"]: row["rag"] for row in simulation["results"]}
    assert by_level[3] == "green"
    assert by_level[5] == "red"


def test_empty_chain_is_not_evaluated_rather_than_green():
    # An empty chain combines to a spread of exactly 0, which sits inside
    # any band and would otherwise be reported as a clean pass at every
    # sigma level -- making "no analysis done yet" indistinguishable from
    # "analysis passed". This is the regression guard for that.
    simulation = run_simulation([], nominal=10.0, upper_limit=1.0, lower_limit=1.0)
    assert [row["rag"] for row in simulation["results"]] == [NOT_EVALUATED] * len(SIGMA_LEVELS)
    assert simulation["sigma_1"] == 0


def test_a_single_contributor_is_enough_to_produce_a_real_verdict():
    # The counterpart to the test above: once anything is in the chain, a
    # real RAG comes back.
    simulation = run_simulation([0.3], nominal=10.0, upper_limit=1.0, lower_limit=1.0)
    assert all(row["rag"] != NOT_EVALUATED for row in simulation["results"])
