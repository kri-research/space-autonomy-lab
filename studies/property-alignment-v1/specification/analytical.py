"""Exact rational background fixtures; none is a spacecraft recovery certificate."""

from fractions import Fraction as F


def rational(x) -> F:
    if type(x) not in (int, str, F):
        raise ValueError("Use exact integers, rational strings or Fractions")
    return F(x)


def braking_distance(speed, latency, inward_acceleration, brake) -> F:
    """Worst-case inward travel before arrest; speed>=0, acceleration>=0, brake>0."""
    v, t, a, b = map(rational, (speed, latency, inward_acceleration, brake))
    if min(v, t, a) < 0 or b <= 0:
        raise ValueError("Invalid scalar braking assumptions")
    return v * t + a * t * t / 2 + (v + a * t) ** 2 / (2 * b)


def robust_braking(
    clearance, speed, position_error, speed_error, age, delay, inward_acceleration, brake
) -> dict:
    """A box at measurement time, no better command history, and no earlier braking."""
    d, v, ep, ev, age, delay, a, b = map(
        rational,
        (clearance, speed, position_error, speed_error, age, delay, inward_acceleration, brake),
    )
    if min(ep, ev, age, delay, a) < 0 or v - ev < 0 or b <= 0:
        raise ValueError("Nonnegative closing-speed interval and positive brake required")
    lower, upper = d - ep, v + ev
    travel = braking_distance(upper, age + delay, a, b)
    return {
        "lower_clearance": lower,
        "upper_speed": upper,
        "required_distance": travel,
        "margin": lower - travel,
        "robust_arrest_possible": lower >= travel,
        "scope": "scalar_box_with_attainable_extremes_and_prescribed_wait",
    }


def exact_state_recovery(clearance, speed, brake) -> str:
    d, v, b = map(rational, (clearance, speed, brake))
    if v < 0 or b <= 0:
        raise ValueError("Nonnegative closing speed and positive brake required")
    if d < 0:
        return "initially_inadmissible"
    return (
        "demonstrably_recoverable"
        if d >= braking_distance(v, 0, 0, b)
        else "admissible_but_unrecoverable"
    )


def endpoint_input_interval(position, velocity, duration, authority, wall=1):
    """Necessary endpoint constraint only; it does not certify between-endpoint motion."""
    q, v, h, a, wall = map(rational, (position, velocity, duration, authority, wall))
    if min(h, a, wall) <= 0:
        raise ValueError("Positive horizon, authority and wall required")
    lo = max(-a, 2 * (-wall - q - v * h) / (h * h))
    hi = min(a, 2 * (wall - q - v * h) / (h * h))
    return None if lo > hi else (lo, hi)


def quadratic_extrema(position, velocity, acceleration, duration):
    q, v, u, h = map(rational, (position, velocity, acceleration, duration))
    if h <= 0:
        raise ValueError("Positive duration required")
    times = [F(0), h]
    if u and 0 < -v / u < h:
        times.append(-v / u)
    positions = [q + v * t + u * t * t / 2 for t in times]
    return min(positions), max(positions), q + v * h + u * h * h / 2, v + u * h
