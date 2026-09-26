"""Conservative complete reading partitions, with no sampled future truth."""

from dataclasses import replace
from fractions import Fraction as Q

from iaa.enclosure import inside, separated, step, terminal
from iaa.types import StateBox
from sa02.estimator import advance
from sa02.intervals import (
    Interval,
    contract_linear,
    interval,
    radial_contract,
    sincos,
    sqrt_bounds,
    symmetric,
)
from sa02.model import ResourceLimit

ACTIONS = ((Q(0), Q(0)), (Q(1, 50), Q(0)), (Q(-1, 50), Q(0)), (Q(0), Q(1, 50)), (Q(0), Q(-1, 50)))


def hull(cells):
    if not cells:
        raise ValueError("Empty outer representation")
    return StateBox(
        tuple(min(c.bounds[j].lo for c in cells) for j in range(4)),
        tuple(max(c.bounds[j].hi for c in cells) for j in range(4)),
    )


def carry(cells, history, start, stop, budget):
    result = []
    velocity = [Q(0), Q(0)]
    for cell in cells:
        box, vel = advance(cell.state(), history, start, stop, budget)
        result.append(cell.with_state(box))
        velocity = [max(v, w) for v, w in zip(velocity, vel, strict=True)]
    return tuple(result), tuple(velocity)


def waiting_check(context, budget):
    box = hull(context.estimate.cells)
    if not inside(box) or not separated(box):
        return False
    for segment in context.queue():
        t = segment.start_ms
        while t < segment.end_ms:
            h = min(50, segment.end_ms - t)
            budget.tick()
            box, tube = step(box, segment.action, h)
            if not inside(tube) or not separated(tube):
                return False
            t += h
    return True


def action_check(box, action, budget):
    """Continuous .5 s input + 3 s coast; exact conservative task-cost difference."""
    if action not in ACTIONS:
        raise ValueError("Unsupported finite action class")
    if not inside(box) or not separated(box):
        return dict(safe=False, useful=False, reason="entry_not_enclosed")
    displacement = [interval(0), interval(0)]
    original = box
    goal_hold = True
    for k in range(70):
        budget.tick()
        box, tube = step(box, action if k < 10 else (0, 0), 50)
        if not inside(tube) or not separated(tube):
            return dict(safe=False, useful=False, reason="prefix_or_coast_unresolved")
        if k < 10:
            goal_hold &= terminal(tube)
            for j in range(2):
                displacement[j] += Interval(tube.lower[j + 2], tube.upper[j + 2]) * Q(1, 20)
    change = interval(0)
    for j, target in enumerate((Q(0), Q(-40))):
        error = Interval(original.lower[j] - target, original.upper[j] - target)
        change += 2 * error * displacement[j] + displacement[j].square()
    progress = change.hi <= -Q(1, 1000000)
    return dict(
        safe=True,
        useful=bool(goal_hold or progress),
        action=action,
        task_change_upper_m2=change.hi,
        goal_eligible_for_hold=bool(goal_hold),
        strict_task_progress=bool(progress),
        full_recovery=False,
    )


def choose_action(cells, budget):
    box = hull(cells)
    # Heuristic ordering only; every chosen result has the same sufficient check.
    midpoint = [
        (box.lower[j] + box.upper[j]) / 2 - target for j, target in enumerate((Q(0), Q(-40)))
    ]
    actions = sorted(ACTIONS, key=lambda u: sum(x * a for x, a in zip(midpoint, u, strict=True)))
    fallback = None
    attempts = []
    for action in actions:
        result = action_check(box, action, budget)
        attempts.append(result)
        if result["safe"]:
            fallback = fallback or result
            if result["useful"]:
                return result, attempts
    return fallback, attempts


def condition_bin(cell, reading, channel, active, move, sensors, budget):
    """SA02 necessary constraints adapted to an interval of possible readings.

    The reading interval includes every value in a partition leaf, not a midpoint.
    """
    out = cell.bounds
    for _ in range(2):
        budget.tick()
        cx, cy, br, bb = out[4:] if active else (interval(0),) * 4
        px = out[0] + cx + symmetric(move[0])
        py = out[1] + cy + symmetric(move[1])
        radius = sqrt_bounds(px.square() + py.square())
        if channel == "range":
            observed = reading + symmetric(sensors.range_error_m)
            possible = observed - br
            if possible.hi < 0:
                return None
            allowed = radius.intersect(Interval(max(Q(0), possible.lo), possible.hi))
            if allowed is None:
                return None
            coords = radial_contract(px, py, allowed)
            if coords is None:
                return None
            if active:
                bias = out[6].intersect(observed - radius)
                if bias is None:
                    return None
                out = out[:6] + (bias,) + out[7:]
        elif channel == "bearing":
            if radius.lo == 0:
                return replace(cell, bounds=out)
            angle = reading - bb + symmetric(sensors.bearing_error_rad)
            sine, cosine = sincos(angle)
            x, y = px.intersect(radius * cosine), py.intersect(radius * sine)
            if x is None or y is None:
                return None
            coords = x, y
        else:
            raise ValueError("Unknown channel")
        for j in (0, 1):
            coefficients = [Q(0)] * 8
            coefficients[j] = Q(1)
            if active:
                coefficients[4 + j] = Q(1)
            out = contract_linear(out, coefficients, coords[j] + symmetric(move[j]))
            if out is None:
                return None
    return replace(cell, bounds=out)


def outcome_partition(context, channel, budget):
    timing = context.timing
    q = timing.acquire_ms + timing.timestamp_ms
    low = timing.acquire_ms - timing.timestamp_ms
    cells, velocity = carry(context.estimate.cells, context.queue(), timing.now_ms, q, budget)
    move = tuple(v * Q(q - low, 1000) for v in velocity)
    hypotheses = {h.label: h for h in context.sensors.hypotheses}
    modes = [(c, active) for c in cells for active in hypotheses[c.hypothesis].modes(low, q)]
    if channel == "range":
        outputs = []
        for c, active in modes:
            cx, cy, br, _ = c.bounds[4:] if active else (interval(0),) * 4
            radius = sqrt_bounds(
                (c.bounds[0] + cx + symmetric(move[0])).square()
                + (c.bounds[1] + cy + symmetric(move[1])).square()
            )
            outputs.append(radius + br + symmetric(context.sensors.range_error_m))
        domain = Interval(max(Q(0), min(x.lo for x in outputs)), max(x.hi for x in outputs))
        resolution = Q(1, 8)
    elif channel == "bearing":
        # 22/7 exceeds pi; this covers every wrapped bearing without float exclusions.
        domain = Interval(-Q(22, 7), Q(22, 7))
        resolution = Q(1, 128)
    else:
        raise ValueError("Unknown channel")
    pending = [(domain, 0)]
    leaves = []
    nodes = 0
    while pending:
        reading, depth = pending.pop()
        nodes += 1
        if nodes > context.max_nodes:
            raise ResourceLimit("Complete future-outcome partition exceeded node cap")
        retained = []
        for c, active in modes:
            result = condition_bin(c, reading, channel, active, move, context.sensors, budget)
            if result is not None:
                retained.append(result)
        if not retained:
            leaves.append(
                dict(reading=reading, status="excluded_by_necessary_constraint", cells=())
            )
        elif reading.width <= resolution or depth >= 12:
            future, _ = carry(tuple(retained), context.queue(), q, timing.apply_ms, budget)
            leaves.append(dict(reading=reading, status="outer_branch", cells=future))
        else:
            mid = (reading.lo + reading.hi) / 2
            pending.extend(
                ((Interval(mid, reading.hi), depth + 1), (Interval(reading.lo, mid), depth + 1))
            )
    leaves.sort(key=lambda x: x["reading"].lo)
    return domain, tuple(leaves), nodes
