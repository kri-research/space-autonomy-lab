"""Exact scalar held-command feasibility with bounded sensing and actuation.
All values are rational SI quantities. This is a closed-form specialization of
standard set-membership safety, not a new general viability theorem.
"""

from dataclasses import dataclass
from fractions import Fraction as Q


def rational(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a physical quantity")
    try:
        return Q(value)
    except (ValueError, TypeError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError("Finite rational quantity required") from exc


@dataclass(frozen=True)
class ScalarBox:
    qlo: Q
    qhi: Q
    vlo: Q
    vhi: Q

    def __post_init__(self):
        for name in ("qlo", "qhi", "vlo", "vhi"):
            object.__setattr__(self, name, rational(getattr(self, name)))
        if self.qlo > self.qhi or self.vlo > self.vhi:
            raise ValueError("Reversed state interval")


def quadratic_range(q, v, acceleration, duration):
    q, v, a, t = map(rational, (q, v, acceleration, duration))
    if t < 0:
        raise ValueError("Negative duration")
    times = [Q(0), t]
    if a and 0 < -v / a < t:
        times.append(-v / a)
    values = [q + v * s + a * s * s / 2 for s in times]
    return min(values), max(values)


def acceleration_ceiling(clearance, outward_speed, duration):
    """inf_(0<t<=T) 2c/t^2-2v/t; None means no finite feasible acceleration."""
    c, v, t = map(rational, (clearance, outward_speed, duration))
    if t <= 0:
        raise ValueError("Positive held duration required")
    if c < 0 or (c == 0 and v > 0):
        return None
    if c > 0 and v > 0 and 2 * c < v * t:
        return -v * v / (2 * c)
    return 2 * c / (t * t) - 2 * v / t


def parameters(halfwidth, authority, effectiveness, disturbance):
    length, umax, w = map(rational, (halfwidth, authority, disturbance))
    eta = tuple(map(rational, effectiveness))
    if length <= 0 or umax < 0 or w < 0 or len(eta) != 2 or not 0 <= eta[0] <= eta[1] <= 1:
        raise ValueError("Invalid physical bounds")
    return length, umax, eta, w


def common_inputs(
    boxes, duration, halfwidth=1, authority="2/5", effectiveness=(1, 1), disturbance=0
):
    """Necessary AND sufficient for one shared constant command on [0,T]."""
    length, umax, eta, w = parameters(halfwidth, authority, effectiveness, disturbance)
    boxes = tuple(boxes)
    if not boxes or any(not isinstance(b, ScalarBox) for b in boxes):
        raise ValueError("Nonempty exact information set required")
    lo, hi = -umax, umax
    obligations = []
    for i, box in enumerate(boxes):
        upper = acceleration_ceiling(length - box.qhi, box.vhi, duration)
        reflected = acceleration_ceiling(length + box.qlo, -box.vlo, duration)
        if upper is None or reflected is None:
            return {
                "status": "proved_no_common_held_command",
                "reason": "initial_or_outward_boundary",
                "hypothesis": i,
            }
        amin, amax = w - reflected, upper - w
        for e in set(eta):
            if e == 0:
                if not amin <= 0 <= amax:
                    return {
                        "status": "proved_no_common_held_command",
                        "reason": "zero_authority_realization",
                        "hypothesis": i,
                    }
            else:
                lo, hi = max(lo, amin / e), min(hi, amax / e)
        obligations.append(
            {
                "hypothesis": i,
                "effective_acceleration_lower": str(amin),
                "effective_acceleration_upper": str(amax),
            }
        )
    return {
        "status": "exact_feasible_interval" if lo <= hi else "proved_no_common_held_command",
        "lower": str(lo),
        "upper": str(hi),
        "obligations": obligations,
        "scope": "one_held_command_continuous_containment",
        "infinite_horizon_recovery": False,
    }


def action_is_safe(
    boxes, action, duration, halfwidth=1, authority="2/5", effectiveness=(1, 1), disturbance=0
):
    """Structurally separate quadratic-extrema check, not the ceiling formula."""
    length, umax, eta, w = parameters(halfwidth, authority, effectiveness, disturbance)
    action, duration = map(rational, (action, duration))
    if duration <= 0 or abs(action) > umax:
        return False
    boxes = tuple(boxes)
    if not boxes:
        raise ValueError("Nonempty information set required")
    for box in boxes:
        amin = min(e * action for e in eta) - w
        amax = max(e * action for e in eta) + w
        if quadratic_range(box.qlo, box.vlo, amin, duration)[0] < -length:
            return False
        if quadratic_range(box.qhi, box.vhi, amax, duration)[1] > length:
            return False
    return True


def propagate_queue(
    boxes, queue, halfwidth=1, authority="2/5", effectiveness=(1, 1), disturbance=0
):
    """Independent eta/w on each queued segment; extremal q/v remain jointly attainable.
    Queue entries are (positive duration, known commanded acceleration).
    """
    length, umax, eta, w = parameters(halfwidth, authority, effectiveness, disturbance)
    boxes, queue = tuple(boxes), tuple(queue)
    if not boxes:
        raise ValueError("Nonempty information set required")
    safe = all(-length <= b.qlo <= b.qhi <= length for b in boxes)
    for duration, command in queue:
        duration, command = map(rational, (duration, command))
        if duration <= 0 or abs(command) > umax:
            raise ValueError("Invalid queued command")
        amin = min(e * command for e in eta) - w
        amax = max(e * command for e in eta) + w
        result = []
        for b in boxes:
            safe &= quadratic_range(b.qlo, b.vlo, amin, duration)[0] >= -length
            safe &= quadratic_range(b.qhi, b.vhi, amax, duration)[1] <= length
            result.append(
                ScalarBox(
                    b.qlo + b.vlo * duration + amin * duration**2 / 2,
                    b.qhi + b.vhi * duration + amax * duration**2 / 2,
                    b.vlo + amin * duration,
                    b.vhi + amax * duration,
                )
            )
        boxes = tuple(result)
    return boxes, bool(safe)


def held_duration_bracket(boxes, maximum, steps=30, **kwargs):
    """Nested held-command feasibility; no claim about arbitrary switching policies."""
    upper = rational(maximum)
    if upper <= 0 or type(steps) is not int or not 1 <= steps <= 80:
        raise ValueError("Bounded search required")
    if common_inputs(boxes, upper, **kwargs)["status"] == "exact_feasible_interval":
        return {"lower_s": str(upper), "upper_s": None, "right_censored": True}
    lower = Q(0)
    for _ in range(steps):
        middle = (lower + upper) / 2
        if common_inputs(boxes, middle, **kwargs)["status"] == "exact_feasible_interval":
            lower = middle
        else:
            upper = middle
    return {"lower_s": str(lower), "upper_s": str(upper), "right_censored": False}
