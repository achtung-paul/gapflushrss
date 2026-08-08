# Angled-interface tolerance stack-up math (direction == OTHER on an
# AnalysisEntry -- see models/analysis_entry.py). Deliberately a separate
# module from core/simulation.py, not an addition to it: simulation.py's
# whole model assumes every tolerance_value is a component's natural +/-3
# sigma spread (divides by 3 before combining, then scales back up to
# 3/4/5 sigma for reporting). The angled model given to build this feature
# has no such assumption -- Worst Case is a direct linear sum of resolved
# values, RSS is a direct root-sum-square of them, with no /3 anywhere.
# Keeping this in its own file with its own docstring stops that
# difference from ever being "unified away" by a well-meaning refactor,
# which would silently change one model's numbers.
#
# Only evaluate_band and NOT_EVALUATED are reused from core/simulation.py
# (the RAG rule) -- combine_rss and run_simulation are not touched by, or
# reachable from, anything here.

import math

from app.core.simulation import NOT_EVALUATED, evaluate_band

WORST_CASE = "WORST_CASE"
RSS = "RSS"


def resolve_variations(x_tolerance: float, y_tolerance: float, angle_degrees: float) -> tuple[float, float]:
    """Resolve one component's X/Y tolerances onto an interface at this angle.

    Vx = Tx * cos(theta), Vy = Ty * sin(theta) -- two independent factors,
    not one shared multiplier. They only coincide (both ~0.7071) at 45
    degrees; at any other angle they diverge, e.g. 30 degrees gives 0.866
    and 0.500. Computing them separately here is what makes that true --
    a single shared constant would be wrong at every angle but 45.
    """
    angle_radians = math.radians(angle_degrees)
    return x_tolerance * math.cos(angle_radians), y_tolerance * math.sin(angle_radians)


def worst_case_total(variations: list[tuple[float, float]]) -> float:
    """Sum every resolved Vx and Vy across all rows -- every variation at its extreme."""
    return sum(vx for vx, _ in variations) + sum(vy for _, vy in variations)


def rss_total(variations: list[tuple[float, float]]) -> float:
    """Root-sum-square every individual resolved Vx and Vy across all rows.

    No division by 3 here, unlike core/simulation.py's combine_rss -- this
    model treats each resolved value as the magnitude it is, with no sigma
    assumption attached. Do not "share" the two combine functions.
    """
    return math.sqrt(sum(vx**2 for vx, _ in variations) + sum(vy**2 for _, vy in variations))


def run_angled_simulation(
    rows: list[tuple[float, float]],
    angle_degrees: float,
    method: str,
    nominal: float,
    upper_limit: float,
    lower_limit: float,
) -> dict:
    """Resolve every (x_tolerance, y_tolerance) row onto the interface angle,
    combine by the chosen method, and evaluate the total against the
    target band.

    rows are (x_tolerance, y_tolerance) pairs in table order; the returned
    "rows" list echoes that same order with each row's resolved (vx, vy)
    so the API can zip it back onto the ORM objects for id/name without
    this module knowing anything about the database.
    """
    if method not in (WORST_CASE, RSS):
        # Unreachable via the API (calculation_method is enum-typed), but a
        # silent fallback to one of the two totals would be the wrong
        # failure mode -- better a loud error than a quietly wrong number.
        raise ValueError(f"Unknown calculation method: {method!r}")

    variations = [resolve_variations(tx, ty, angle_degrees) for tx, ty in rows]
    # An empty table has nothing to say about whether the target is met --
    # same reasoning as core/simulation.py's NOT_EVALUATED. A zero total
    # sits inside any band and would otherwise read as a pass.
    has_rows = len(rows) > 0

    total_variation = worst_case_total(variations) if method == WORST_CASE else rss_total(variations)
    rag, lower_bound, upper_bound = evaluate_band(nominal, upper_limit, lower_limit, total_variation)

    return {
        "total_variation": total_variation,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "rag": rag if has_rows else NOT_EVALUATED,
        "rows": [{"vx": vx, "vy": vy} for vx, vy in variations],
    }
