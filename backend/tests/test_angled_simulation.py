# Tests for the angled-interface tolerance stack-up maths
# (app/core/angled_simulation.py).
#
# Same reasoning as test_simulation.py: no fixtures needed, since this
# module deliberately has no DB or FastAPI imports.

import math

import pytest

from app.core.angled_simulation import (
    RSS,
    WORST_CASE,
    resolve_variations,
    rss_total,
    run_angled_simulation,
    worst_case_total,
)
from app.core.simulation import NOT_EVALUATED


# --- resolve_variations ------------------------------------------------
# Vx = Tx * cos(theta), Vy = Ty * sin(theta) -- two independent factors.
# They only coincide at 45 degrees; every other angle must prove they
# don't share one constant.


def test_resolve_variations_at_45_degrees_matches_the_spec_example():
    vx, vy = resolve_variations(1.0, 1.0, 45)
    assert vx == pytest.approx(0.70710678, rel=1e-6)
    assert vy == pytest.approx(0.70710678, rel=1e-6)


def test_resolve_variations_diverges_at_30_degrees():
    # cos(30) = 0.8660254, sin(30) = 0.5 -- not equal, and not 0.7071.
    vx, vy = resolve_variations(1.0, 0.2, 30)
    assert vx == pytest.approx(0.8660254, rel=1e-6)
    assert vy == pytest.approx(0.1, rel=1e-6)


def test_resolve_variations_diverges_at_60_degrees():
    # cos(60) = 0.5, sin(60) = 0.8660254 -- the mirror of the 30 degree case.
    vx, vy = resolve_variations(1.0, 0.2, 60)
    assert vx == pytest.approx(0.5, rel=1e-6)
    assert vy == pytest.approx(0.1732051, rel=1e-6)


def test_resolve_variations_at_0_degrees_is_pure_x():
    vx, vy = resolve_variations(2.0, 2.0, 0)
    assert vx == pytest.approx(2.0)
    assert vy == pytest.approx(0.0, abs=1e-9)


def test_resolve_variations_at_90_degrees_is_pure_y():
    vx, vy = resolve_variations(2.0, 2.0, 90)
    assert vx == pytest.approx(0.0, abs=1e-9)
    assert vy == pytest.approx(2.0)


# --- worst_case_total / rss_total --------------------------------------


def test_worst_case_total_sums_every_resolved_value():
    variations = [(0.70710678, 0.70710678), (0.35355339, 0.35355339)]
    assert worst_case_total(variations) == pytest.approx(2.12132034, rel=1e-6)


def test_rss_total_is_root_sum_square_not_the_worst_case_figure():
    variations = [(0.70710678, 0.70710678), (0.35355339, 0.35355339)]
    total = rss_total(variations)
    assert total == pytest.approx(1.11803399, rel=1e-6)
    assert total != pytest.approx(worst_case_total(variations))


def test_rss_total_has_no_sigma_division_unlike_combine_rss():
    # A single row with a 3.0 X-tolerance at 0 degrees resolves to Vx=3.0.
    # If this accidentally reused core/simulation.py's combine_rss (which
    # divides by 3 before combining), the total would come out as 1.0
    # instead of 3.0.
    variations = [resolve_variations(3.0, 0.0, 0)]
    assert rss_total(variations) == pytest.approx(3.0)
    assert worst_case_total(variations) == pytest.approx(3.0)


# --- run_angled_simulation ----------------------------------------------
# nominal 5.0, band 3.5 to 6.5 (upper_limit 1.5, lower_limit 1.5).

NOMINAL = 5.0
UPPER_LIMIT = 1.5
LOWER_LIMIT = 1.5


def simulate(rows, angle, method):
    return run_angled_simulation(rows, angle, method, NOMINAL, UPPER_LIMIT, LOWER_LIMIT)


def test_worst_case_45_degree_example_is_red():
    result = simulate([(1.0, 1.0), (0.5, 0.5)], 45, WORST_CASE)
    assert result["total_variation"] == pytest.approx(2.12132034, rel=1e-6)
    # 5.0 +/- 2.121 = 2.879 to 7.121 -- breaches the 6.5 upper limit by
    # 0.621, which is far more than 5% of the 1.5 limit (0.075).
    assert result["rag"] == "red"


def test_rss_45_degree_example_is_green():
    result = simulate([(1.0, 1.0), (0.5, 0.5)], 45, RSS)
    assert result["total_variation"] == pytest.approx(1.11803399, rel=1e-6)
    # 5.0 +/- 1.118 = 3.882 to 6.118 -- inside the 3.5 to 6.5 band.
    assert result["rag"] == "green"


def test_toggling_method_does_not_change_the_row_breakdown():
    rows = [(1.0, 1.0), (0.5, 0.5)]
    worst = simulate(rows, 45, WORST_CASE)
    rss = simulate(rows, 45, RSS)
    assert worst["rows"] == rss["rows"]
    assert worst["total_variation"] != rss["total_variation"]


def test_degenerate_angles_prove_no_stray_constant():
    rows = [(1.0, 0.2)]
    assert simulate(rows, 0, WORST_CASE)["total_variation"] == pytest.approx(1.0)
    assert simulate(rows, 90, WORST_CASE)["total_variation"] == pytest.approx(0.2)


def test_amber_red_boundary():
    # A limit of 1.5: 5% of it is 0.075. A total of 1.55 breaches by 0.05
    # (<= 0.075, so amber); a total of 1.7 breaches by 0.2 (> 0.075, so red).
    amber = simulate([(1.55, 0.0)], 0, WORST_CASE)
    red = simulate([(1.7, 0.0)], 0, WORST_CASE)
    assert amber["rag"] == "amber"
    assert red["rag"] == "red"


def test_empty_rows_is_not_evaluated_not_green():
    result = simulate([], 45, WORST_CASE)
    assert result["total_variation"] == 0.0
    assert result["rag"] == NOT_EVALUATED
    assert result["rows"] == []


def test_unknown_method_raises():
    with pytest.raises(ValueError):
        simulate([(1.0, 1.0)], 45, "AVERAGE")
