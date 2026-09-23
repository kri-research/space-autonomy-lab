"""Proof-preserving queue reuse and bounded sufficient-prefix checks.

No failed sufficient search is labelled physical impossibility. Negative queue
claims require an attainable initial state and an allowed realized input witness.
Only the pre-candidate qualification path is changed; candidate.decide is intact.
"""

from dataclasses import dataclass
from fractions import Fraction as Q
from typing import Callable
import time

from adjudication.flow import Model, TaylorArc, make_arc, propagate_schedule
from adjudication.polynomial import PolynomialArc
from adjudication.geometry import bounds
from candidate.certify import execution_schedule
from candidate.information import Hypothesis, InformationSet
from evaluation.qualification import QUALIFICATION_ACTIONS
from specification.contract import load_property, Verdict as V

KEYS = ("containment", "collision_free", "keep_out_free")
MINIMUM_WIDTH = Q(1, 4096)
MAX_CELLS = 32768


def _physical(metrics):
    if any(metrics[k] == V.VIOLATED for k in KEYS):
        return "validated_violation"
    if all(metrics[k] == V.SATISFIED for k in KEYS):
        return "validated_containment"
    return "unresolved"


def check_window(arcs, prop, start, end, *, minimum_width=MINIMUM_WIDTH, max_cells=MAX_CELLS):
    """Continuous physical-prefix check; no dwell or recovery claim.

    A point enclosure is a subset of this same arc's interval extension on any
    interval containing that time. An unresolved point cannot justify a positive
    range proof. Stop that sufficient search without calling it a violation.
    Positive verdicts always require covering continuous range enclosures.
    """
    start, end, width = Q(start), Q(end), Q(minimum_width)
    if start < 0 or end <= start or end > Q(prop.horizon) or width <= 0:
        raise ValueError("Invalid proof window")
    if type(max_cells) is not int or max_cells < 1:
        raise ValueError("Positive integer proof budget required")
    arcs = tuple(arcs)
    cursor, previous = start, None
    for arc in arcs:
        if not isinstance(arc, (TaylorArc, PolynomialArc)):
            raise ValueError("Unsupported continuous enclosure")
        if Q(arc.start) != cursor or not cursor < Q(arc.end) <= end:
            raise ValueError("Gap, overlap or wrong extent")
        initial = arc.point(arc.start)
        if previous is not None and initial != previous:
            raise ValueError("Unjustified state reset")
        previous, cursor = arc.point(arc.end), Q(arc.end)
    if cursor != end or not arcs:
        raise ValueError("Incomplete proof window")
    points, cells = 0, 0
    cache = {}

    def at(i, t):
        nonlocal points
        key = (i, t)
        if key not in cache:
            cache[key] = bounds(arcs[i].point(t), prop)
            points += 1
        return cache[key]

    def result(status, reason, t=None):
        return {
            "status": status,
            "reason": reason,
            "witness_time_s": None if t is None else str(t),
            "point_evaluations": points,
            "range_evaluations": cells,
            "continuous_range_coverage": status == "validated_containment",
            "scope": "physical_prefix_only",
        }

    # Cheap probes can disqualify an enclosure proof, never certify containment.
    for i, arc in enumerate(arcs):
        for t in (Q(arc.end), Q(arc.start), (Q(arc.start) + Q(arc.end)) / 2):
            status = _physical(at(i, t))
            if status != "validated_containment":
                return result(status, "point_enclosure_not_contained", t)
    for i, arc in enumerate(arcs):
        stack = [(Q(arc.start), Q(arc.end))]
        while stack:
            a, b = stack.pop()
            if cells >= max_cells:
                return result("unresolved", "refinement_budget_exhausted")
            metrics = bounds(arc.range(a, b), prop)
            cells += 1
            status = _physical(metrics)
            if status == "validated_containment":
                continue
            if status == "validated_violation":
                return result(status, "entire_range_outside", (a + b) / 2)
            mid = (a + b) / 2
            status = _physical(at(i, mid))
            if status != "validated_containment":
                return result(status, "point_enclosure_not_contained", mid)
            if b - a <= width:
                return result("unresolved", "range_overlap_at_resolution_limit")
            stack.extend(((mid, b), (a, mid)))
    return result("validated_containment", "continuous_range_enclosures")


def _queue_arcs(info, hypothesis):
    schedule = execution_schedule(info, (0, 0))[:-4]
    if not schedule:
        return (), hypothesis.enclosure()
    arcs = tuple(propagate_schedule(Model("hcw"), hypothesis.enclosure(), schedule))
    return arcs, arcs[-1].point(info.application_time)


def _queue_result(info, hypothesis, arcs, prop):
    if arcs:
        return check_window(arcs, prop, 0, info.application_time)
    status = _physical(bounds(hypothesis.enclosure(), prop))
    return {
        "status": status,
        "reason": "initial_enclosure",
        "point_evaluations": 1,
        "range_evaluations": 0,
        "continuous_range_coverage": status == "validated_containment",
    }


def _origins(hypothesis):
    # Directional corners are merely admissible witnesses, not an exact HCW support oracle.
    directions = ((1, 1), (-1, 1), (0, -1), (0, 1), (1, 0), (-1, 0))
    for a, b in directions:
        signs = (a, b, a, b)
        origin = tuple(
            hi if sign > 0 else lo if sign < 0 else (lo + hi) / 2
            for lo, hi, sign in zip(hypothesis.lower, hypothesis.upper, signs, strict=True)
        )
        yield origin, (a, b)


def _witness_trajectory(info, origin, effectiveness, disturbance):
    initial = Hypothesis.point(origin).enclosure()
    if not info.queue:
        return (), initial
    segments = [
        (Q(j), Q(j + 1), tuple(effectiveness * x + w for x, w in zip(u, disturbance, strict=True)))
        for j, u in enumerate(info.queue)
    ]
    arcs = tuple(propagate_schedule(Model("hcw"), initial, segments))
    return arcs, initial


def queue_witness(info, hypothesis_index, prop=None):
    """Finite search for a TRUE compatible queue counterexample, never an outer-box corner."""
    if info.kind != "declared_exact_information_set":
        return None
    prop = load_property() if prop is None else prop
    hypothesis = info.hypotheses[hypothesis_index]
    for origin, signs in _origins(hypothesis):
        disturbance = tuple(Q(s) * info.disturbance for s in signs)
        for eta in sorted(set(info.effectiveness), reverse=True):
            arcs, initial = _witness_trajectory(info, origin, eta, disturbance)
            checkpoints = [(Q(0), initial)]
            for arc in arcs:
                checkpoints.append((Q(arc.end), arc.point(arc.end)))
                mid = (Q(arc.start) + Q(arc.end)) / 2
                checkpoints.append((mid, arc.point(mid)))
            for t, box in checkpoints:
                metrics = bounds(box, prop)
                if _physical(metrics) == "validated_violation":
                    return {
                        "information_sha256": info.identity(),
                        "model": "hcw",
                        "hypothesis": hypothesis_index,
                        "origin": list(map(str, origin)),
                        "effectiveness": str(eta),
                        "disturbance": list(map(str, disturbance)),
                        "time_s": str(t),
                        "components": {k: str(metrics[k]) for k in KEYS},
                        "enclosure": [[v.lo, v.hi] for v in box.coordinates],
                        "scope": "attainable_precommand_violation",
                        "new_command_used": False,
                    }
    return None


def recheck_queue_witness(info, witness):
    """Rebuild the concrete queue trajectory; stored success labels are never trusted."""
    try:
        if info.kind != "declared_exact_information_set" or witness["model"] != "hcw":
            return False
        if witness["information_sha256"] != info.identity():
            return False
        i = witness["hypothesis"]
        if type(i) is not int or not 0 <= i < len(info.hypotheses):
            return False
        origin = tuple(Q(v) for v in witness["origin"])
        eta, t = Q(witness["effectiveness"]), Q(witness["time_s"])
        w = tuple(Q(v) for v in witness["disturbance"])
        if (
            not info.hypotheses[i].contains(origin)
            or len(w) != 2
            or not info.effectiveness[0] <= eta <= info.effectiveness[1]
            or any(abs(x) > info.disturbance for x in w)
            or not 0 <= t <= info.application_time
        ):
            return False
        arcs, initial = _witness_trajectory(info, origin, eta, w)
        box = initial if t == 0 else next(a.point(t) for a in arcs if a.start <= t <= a.end)
        return _physical(bounds(box, load_property())) == "validated_violation"
    except (KeyError, TypeError, ValueError, ArithmeticError, StopIteration):
        return False


@dataclass(frozen=True)
class _QueueCache:
    information_identity: str
    hypothesis: Hypothesis
    final_box: object


def _continuation(info, cache, action):
    if cache.information_identity != info.identity() or cache.hypothesis not in info.hypotheses:
        raise ValueError("Queue cache belongs to different information")
    state = cache.final_box
    arcs = []
    for a, b, u in execution_schedule(info, action)[-4:]:
        arc = make_arc(Model("hcw"), state, u, a, b)
        arcs.append(arc)
        state = arc.point(b)
    return tuple(arcs)


def qualify(info: InformationSet, *, observer: Callable | None = None):
    """Qualification only. None eligibility is a computation/assumption blocker.

    False library certification is distinct from a checked queue violation.
    No command is applied and no protected population is sampled by this function.
    """
    if not isinstance(info, InformationSet):
        raise ValueError("Explicit information set required")
    started = time.perf_counter()
    queues, hypotheses = [], []
    counters = {
        "queue_propagations": 0,
        "continuation_propagations": 0,
        "range_evaluations": 0,
        "point_evaluations": 0,
    }
    phase = "validate_information"

    def emit(name, **values):
        nonlocal phase
        phase = name
        if observer is not None:
            observer({"phase": name, **values})

    def collect(proof):
        for k in ("range_evaluations", "point_evaluations"):
            counters[k] += proof.get(k, 0)

    def finish(status, eligible, **details):
        return {
            "schema": "sal-repaired-qualification/1",
            "status": status,
            "eligible": eligible,
            "information_sha256": info.identity(),
            "criterion": "every hypothesis admits fixed queue and a fixed-library one-second HCW prefix",
            "full_recovery_claim": False,
            "physical_impossibility_claim": status == "proved_precommand_violation",
            "queue_checks": queues,
            "hypotheses": hypotheses,
            "counters": counters,
            "wall_s": time.perf_counter() - started,
            "last_phase": phase,
            **details,
        }

    if info.kind != "declared_exact_information_set":
        return finish("unsupported_information", None)
    try:
        prop, caches = load_property(), []
        for i, h in enumerate(info.hypotheses):
            emit("queue_propagation", hypothesis=i)
            arcs, final = _queue_arcs(info, h)
            counters["queue_propagations"] += bool(info.queue)
            emit("queue_check", hypothesis=i)
            checked = _queue_result(info, h, arcs, prop)
            collect(checked)
            queues.append({"hypothesis": i, **checked})
            if checked["status"] != "validated_containment":
                emit("queue_witness", hypothesis=i)
                witness = queue_witness(info, i, prop)
                if witness is not None:
                    if not recheck_queue_witness(info, witness):
                        raise ArithmeticError("Queue witness failed recheck")
                    return finish("proved_precommand_violation", False, queue_witness=witness)
                return finish(
                    "not_certified_by_library",
                    False,
                    reason="shared_queue_enclosure_unresolved",
                    queue_witness=None,
                )
            caches.append(_QueueCache(info.identity(), h, final))
        for i, cache in enumerate(caches):
            attempts, accepted = [], None
            for j, values in enumerate(QUALIFICATION_ACTIONS):
                action = tuple(Q(str(x)) for x in values)
                emit("continuation", hypothesis=i, action_index=j)
                arcs = _continuation(info, cache, action)
                counters["continuation_propagations"] += 1
                checked = check_window(arcs, prop, info.application_time, info.application_time + 1)
                collect(checked)
                attempts.append({"action": list(map(str, action)), **checked})
                if checked["status"] == "validated_containment":
                    accepted = list(map(str, action))
                    break
            hypotheses.append(
                {
                    "hypothesis": i,
                    "qualified": accepted is not None,
                    "witness_action": accepted,
                    "attempts": attempts,
                }
            )
            if accepted is None:
                return finish(
                    "not_certified_by_library",
                    False,
                    reason="fixed_library_not_certified",
                    queue_witness=None,
                )
        emit("complete")
        return finish("qualified", True)
    except Exception as exc:
        # The caller must preserve this unknown and block qualification selection.
        return finish(
            "unresolved_computation", None, error_type=type(exc).__name__, error_message=str(exc)
        )
