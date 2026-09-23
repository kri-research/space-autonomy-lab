"""Shared validated numerical search with separately implemented online predicates.
No offline geometry is imported. Clear nominal prediction is not recoverability.
"""

from fractions import Fraction as Q
import math
import numpy as np
from adjudication.flow import Model, propagate_schedule
from specification.contract import Verdict as V
from .native import components


def abs_bounds(lo, hi):
    return (Q(0) if lo <= 0 <= hi else min(abs(lo), abs(hi)), max(abs(lo), abs(hi)))


def predicted_box(box, predicate, radius, tolerance=1e-9):
    if predicate not in ("in_band", "closed_union"):
        raise ValueError("Unknown predicate")
    eps = Q(tolerance)
    if eps < 0 or not math.isfinite(radius) or radius <= 0:
        raise ValueError("Invalid scale")
    (xl, xh), (yl, yh) = [(Q(c.lo), Q(c.hi)) for c in box.coordinates[:2]]
    ax0, ax1 = abs_bounds(xl, xh)
    ay0, ay1 = abs_bounds(yl, yh)
    r2 = Q(radius) ** 2
    keep = (
        V.SATISFIED
        if ax0**2 + ay0**2 > r2
        else V.VIOLATED
        if ax1**2 + ay1**2 <= r2
        else V.UNRESOLVED
    )
    if predicate == "in_band":
        low, high = max(yl, Q(-100)), min(yh, Q(-30))
        if low > high or ax1 + high / 10 <= eps:
            geometry = V.SATISFIED
        elif yl >= -100 and yh <= -30 and ax0 + low / 10 > eps:
            geometry = V.VIOLATED
        else:
            geometry = V.UNRESOLVED
    else:
        cl = min(Q(-30), max(Q(-100), yl))
        ch = min(Q(-30), max(Q(-100), yh))
        ain = -100 - yl <= eps and yh + 30 <= eps and ax1 + ch / 10 <= eps
        aout = -100 - yh > eps or yl + 30 > eps or ax0 + cl / 10 > eps
        ell0, ell1 = abs_bounds((yl + 30) / 3, (yh + 30) / 3)
        lo = (ax0 / 2) ** 2 + ell0**2
        hi = (ax1 / 2) ** 2 + ell1**2
        level = (1 + eps / 2) ** 2
        geometry = (
            V.SATISFIED
            if ain or hi <= level
            else V.VIOLATED
            if aout and lo > level
            else V.UNRESOLVED
        )
    return {"predicate": geometry, "keep_out": keep}


def inspect_arcs(arcs, predicate, radius, *, resolution=Q(1, 4096), max_cells=16384):
    arcs = tuple(arcs)
    if not arcs:
        return {
            "status": "unresolved",
            "reason": "missing_arcs",
            "range_evaluations": 0,
            "ambiguous_leaves": 0,
        }
    statuses = []
    witnesses = []
    evaluations = 0
    uncertain = 0
    for arc in arcs:
        stack = [(Q(arc.start), Q(arc.end))]
        while stack:
            a, b = stack.pop()
            evaluations += 1
            if evaluations > max_cells:
                return {
                    "status": "unresolved",
                    "reason": "budget_exhausted",
                    "range_evaluations": evaluations,
                    "ambiguous_leaves": uncertain,
                }
            metrics = predicted_box(arc.range(a, b), predicate, radius)
            points = [
                (t, predicted_box(arc.point(t), predicate, radius)) for t in (a, (a + b) / 2, b)
            ]
            bad = [
                (t, k) for t, p in points for k in ("predicate", "keep_out") if p[k] == V.VIOLATED
            ]
            if bad:
                statuses.append("violated")
                witnesses.extend(bad)
                continue
            if all(v == V.SATISFIED for v in metrics.values()):
                statuses.append("clear")
                continue
            if b - a > resolution:
                mid = (a + b) / 2
                stack.extend([(mid, b), (a, mid)])
                continue
            statuses.append("unresolved")
            uncertain += 1
    status = (
        "violated"
        if "violated" in statuses
        else "unresolved"
        if "unresolved" in statuses
        else "clear"
    )
    return {
        "status": status,
        "reason": None,
        "range_evaluations": evaluations,
        "ambiguous_leaves": uncertain,
        "first_witness_s": float(min(t for t, k in witnesses)) if witnesses else None,
        "witness_components": sorted({k for t, k in witnesses}),
    }


def screen(mean, command, predicate, radius):
    try:
        arcs = propagate_schedule(
            Model("hcw"), np.asarray(mean).tolist(), [(0, 1, np.asarray(command).tolist())]
        )
        return inspect_arcs(arcs, predicate, radius)
    except Exception as exc:
        return {
            "status": "unresolved",
            "reason": type(exc).__name__,
            "range_evaluations": 0,
            "ambiguous_leaves": 0,
        }


class ControlledGate:
    def __init__(self, fallback, predicate):
        if predicate not in ("in_band", "closed_union"):
            raise ValueError("Unknown predicate")
        self.fallback = fallback
        self.predicate = predicate
        self.integrity_latched = False
        self.cfg, self.ctrl, _, _, _, _ = components()

    def gate(self, snapshot, proposal):
        cfg = self.cfg
        ctrl = self.ctrl
        visited = ["controller_identity"]
        if proposal.controller_identity != self.fallback.controller_identity:
            self.integrity_latched = True
        reason = "CONTROLLER_INTEGRITY" if self.integrity_latched else None
        if reason is None:
            visited.append("estimator_divergence")
            if snapshot.health is ctrl.FilterHealth.DIVERGED:
                reason = "ESTIMATOR_DIVERGED"
        if reason is None:
            visited.append("estimator_quality")
            if (
                snapshot.health is ctrl.FilterHealth.DEGRADED
                or snapshot.prediction_only_age_s is None
                or snapshot.prediction_only_age_s > cfg.degraded_after_prediction_only_s
                or snapshot.consecutive_innovation_rejections
                >= cfg.max_consecutive_innovation_rejections
            ):
                reason = "ESTIMATOR_QUALITY"
        if reason is None:
            visited.append("command_bound")
            if np.linalg.norm(proposal.acceleration_mps2) > cfg.max_acceleration_mps2 + 1e-12:
                reason = "COMMAND_BOUND"
        diagnostic = None
        radius = None
        if reason is None:
            visited.append("geometry")
            sigma = float(
                np.sqrt(max(0.0, float(np.linalg.eigvalsh(snapshot.covariance[:2, :2])[-1])))
            )
            radius = cfg.keep_out_radius_m + cfg.uncertainty_sigma_multiplier * sigma
            diagnostic = screen(snapshot.mean, proposal.acceleration_mps2, self.predicate, radius)
            if diagnostic["status"] != "clear":
                reason = (
                    "UNCERTAINTY_AWARE_GEOMETRY"
                    if diagnostic["status"] == "violated"
                    else "NUMERICAL_UNRESOLVED"
                )
        selected = proposal.acceleration_mps2
        if reason:
            visited.append("fallback")
            selected = self.fallback.decide(
                ctrl.observation_from_snapshot(snapshot)
            ).acceleration_mps2
        return ctrl.GateDecision(
            proposal.acceleration_mps2, selected, reason is not None, reason, radius
        ), {
            "visited_branches": visited,
            "geometry_evaluated": diagnostic is not None,
            "screen": diagnostic,
            "predicate": self.predicate,
            "fallback_verified_safe": False,
        }
