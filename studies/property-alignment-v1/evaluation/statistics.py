"""Frozen-design statistical utilities.

The primary interval uses Hoeffding's inequality for independent bounded
Bernoulli draws and therefore does not require a common success probability
across the four fixed strata.
"""

import math

ALPHA = 0.05
TARGET_HALF_WIDTH = 0.05
STRATA_COUNT = 4


def required_total(half_width=TARGET_HALF_WIDTH, alpha=ALPHA):
    if not 0 < half_width < 1 or not 0 < alpha < 1:
        raise ValueError("Valid precision and alpha required")
    return math.ceil(math.log(2.0 / alpha) / (2.0 * half_width**2))


def balanced_size(strata=STRATA_COUNT):
    total = required_total()
    per = math.ceil(total / strata)
    # Multiple of 16 gives fixed equal chunks for checkpoint/parallel tests.
    per = math.ceil(per / 16) * 16
    return per, per * strata


def hoeffding_half_width(total, alpha=ALPHA):
    if type(total) is not int or total < 1:
        raise ValueError("Positive integer count required")
    return math.sqrt(math.log(2.0 / alpha) / (2.0 * total))


def hoeffding_interval(successes, total, alpha=ALPHA):
    if type(successes) is not int or not 0 <= successes <= total:
        raise ValueError("Invalid Bernoulli count")
    estimate = successes / total
    radius = hoeffding_half_width(total, alpha)
    return {
        "estimate": estimate,
        "lower": max(0.0, estimate - radius),
        "upper": min(1.0, estimate + radius),
        "half_width_bound": radius,
        "method": "Hoeffding independent bounded trials; heterogeneous probabilities allowed",
    }


def bounded_difference_interval(values, alpha=ALPHA):
    """Exploratory secondary CI for bounded paired differences in [-1,1]."""
    values = list(values)
    if not values or any(value < -1 or value > 1 for value in values):
        raise ValueError("Differences must lie in [-1,1]")
    estimate = sum(values) / len(values)
    radius = math.sqrt(2.0 * math.log(2.0 / alpha) / len(values))
    return {
        "estimate": estimate,
        "lower": max(-1.0, estimate - radius),
        "upper": min(1.0, estimate + radius),
        "half_width_bound": radius,
        "confirmatory": False,
    }


PER_STRATUM, PRIMARY_N = balanced_size()
assert PER_STRATUM == 192 and PRIMARY_N == 768
assert hoeffding_half_width(PRIMARY_N) < TARGET_HALF_WIDTH
