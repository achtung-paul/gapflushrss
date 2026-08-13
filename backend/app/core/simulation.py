# RSS (Root Sum Square) tolerance stack-up math, per PROJECT_BRIEF.md
# step 4-6. Deliberately plain functions with no DB/FastAPI imports --
# the API route just calls these with numbers it already has, which
# makes the maths easy to check by hand or test on its own.
#
# Statistical basis (confirmed with the user, since this is the one
# assumption that decides whether the numbers mean anything): every
# chain component's tolerance_value is treated as that component's
# natural +/-3 sigma spread (a Cp=1 assumption). To combine several
# components, we first convert each to its own 1 sigma value
# (tolerance_value / 3), combine those with root-sum-square, and only
# then scale the combined 1 sigma back up to whichever confidence level
# (3 sigma, 4 sigma, 5 sigma) we're reporting.

import math

# Reported instead of a RAG colour when there's nothing to evaluate --
# i.e. the tolerance chain is still empty. Without this, an empty chain
# combines to a spread of exactly 0, which sits comfortably inside any
# tolerance band and comes back "green" at every sigma level. That makes
# "nobody has done this analysis yet" look identical to "this analysis
# passed", which is the most dangerous way for a stack-up tool to be
# wrong -- so it gets its own status rather than a colour.
NOT_EVALUATED = "not_evaluated"

# The RAG rule from the brief, step 6: a breach past the tolerance limit
# is "amber" if it's within this fraction of the limit that was
# breached, otherwise "red".
AMBER_THRESHOLD_FRACTION = 0.05


def combine_rss(tolerance_values: list[float]) -> float:
    """Combine a list of +/-3 sigma tolerance values into one 1 sigma value."""
    one_sigma_values = [value / 3 for value in tolerance_values]
    return math.sqrt(sum(value**2 for value in one_sigma_values))


def evaluate_band(
    nominal: float, upper_limit: float, lower_limit: float, spread: float
) -> tuple[str, float, float]:
    """Compare a predicted +/-spread around nominal against the target's tolerance band.

    Returns (rag, lower_bound, upper_bound) where lower_bound/upper_bound
    are the predicted extremes (nominal -/+ spread). Applies the brief's
    rule symmetrically -- a breach below the lower limit is judged the
    same way as a breach above the upper limit.
    """
    lower_bound = nominal - spread
    upper_bound = nominal + spread
    band_lower = nominal - lower_limit
    band_upper = nominal + upper_limit

    upper_breach = upper_bound - band_upper
    lower_breach = band_lower - lower_bound

    if upper_breach <= 0 and lower_breach <= 0:
        return "green", lower_bound, upper_bound

    # A limit of 0 means "no headroom at all", so any breach on that
    # side is immediately red rather than dividing by zero.
    worst_status = "green"
    if upper_breach > 0:
        upper_is_red = upper_limit == 0 or upper_breach > AMBER_THRESHOLD_FRACTION * upper_limit
        worst_status = "red" if upper_is_red else "amber"
    if lower_breach > 0:
        lower_is_red = lower_limit == 0 or lower_breach > AMBER_THRESHOLD_FRACTION * lower_limit
        lower_status = "red" if lower_is_red else "amber"
        if lower_status == "red" or worst_status == "green":
            worst_status = lower_status

    return worst_status, lower_bound, upper_bound


def run_simulation(
    tolerance_values: list[float],
    nominal: float,
    upper_limit: float,
    lower_limit: float,
    sigma_levels: list[int] = (3, 4, 5),
) -> dict:
    """Run the RSS stack-up at each requested sigma level and evaluate against the target band.

    sigma_levels defaults to the app's original fixed 3/4/5 -- callers
    that care about a particular client's configured model (which levels
    they've chosen to see, see models/statistical_model_setting.py) pass
    their own list explicitly; this function has no idea what a "client"
    is and never will (see the module docstring).
    """
    combined_one_sigma = combine_rss(tolerance_values)
    # An empty chain has nothing to say about whether the target is met --
    # see NOT_EVALUATED. The rows are still returned (with a zero spread)
    # so the results table renders its usual shape, just without a verdict.
    has_chain = len(tolerance_values) > 0

    results = []
    for sigma_level in sigma_levels:
        spread = combined_one_sigma * sigma_level
        rag, lower_bound, upper_bound = evaluate_band(nominal, upper_limit, lower_limit, spread)
        results.append(
            {
                "sigma_level": sigma_level,
                "spread": spread,
                "lower_bound": lower_bound,
                "upper_bound": upper_bound,
                "rag": rag if has_chain else NOT_EVALUATED,
            }
        )
    return {"sigma_1": combined_one_sigma, "results": results}
