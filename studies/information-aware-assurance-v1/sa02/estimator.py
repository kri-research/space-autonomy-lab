"""Simulation-only causal bounded-error observation consistency."""

from dataclasses import replace
from fractions import Fraction as Q

from iaa.enclosure import step
from iaa.types import StateBox, identity, millis, rational

from .intervals import (
    Interval,
    contract_linear,
    interval,
    radial_contract,
    sincos,
    sqrt_bounds,
    symmetric,
)
from .model import (
    Budget,
    Estimate,
    ResourceLimit,
    SensorContract,
    history_prefix,
    initial_cells,
    merge_cells,
    packet_key,
    validate_history,
    validate_packet,
)


def advance(box, history, start_ms, end_ms, budget):
    """Integrate the supplied applied history, including switching boundaries."""
    velocity = [max(abs(box.lower[j]), abs(box.upper[j])) for j in (2, 3)]
    t = start_ms
    for segment in history:
        a, b = max(start_ms, segment.start_ms), min(end_ms, segment.end_ms)
        if a >= b:
            continue
        if a != t:
            raise ValueError("Missing known command interval")
        while t < b:
            dt = min(50, b - t)
            budget.tick()
            box, tube = step(box, segment.action, dt)
            velocity = [
                max(v, abs(tube.lower[j]), abs(tube.upper[j]))
                for v, j in zip(velocity, (2, 3), strict=True)
            ]
            t += dt
    if t != end_ms:
        raise ValueError("Command history does not cover propagation")
    return box, tuple(velocity)


def contract_packet(cell, packet, hypothesis, move, contract, active, budget):
    """Necessary polar conditions at latest possible acquisition time."""
    out = cell.bounds
    degenerate = False
    for _ in range(2):
        budget.tick()
        cx, cy, br, bb = out[4:] if active else (interval(0),) * 4
        px, py = out[0] + cx + symmetric(move[0]), out[1] + cy + symmetric(move[1])
        radius = sqrt_bounds(px.square() + py.square())
        if packet.channel == "range":
            observed = interval(rational(packet.value)) + symmetric(contract.range_error_m)
            possible = observed - br
            if possible.hi < 0:
                return None, degenerate
            allowed = radius.intersect(Interval(max(Q(0), possible.lo), possible.hi))
            if allowed is None:
                return None, degenerate
            coords = radial_contract(px, py, allowed)
            if coords is None:
                return None, degenerate
            if active:
                bias = out[6].intersect(observed - radius)
                if bias is None:
                    return None, degenerate
                out = out[:6] + (bias,) + out[7:]
        else:
            if radius.lo == 0:
                degenerate = True
                return replace(cell, bounds=out), degenerate
            angle = interval(rational(packet.value)) - bb + symmetric(contract.bearing_error_rad)
            sine, cosine = sincos(angle)
            x, y = px.intersect(radius * cosine), py.intersect(radius * sine)
            if x is None or y is None:
                return None, degenerate
            coords = (x, y)
        for j in (0, 1):
            coefficients = [Q(0)] * 8
            coefficients[j] = Q(1)
            if active:
                coefficients[4 + j] = Q(1)
            out = contract_linear(out, coefficients, coords[j] + symmetric(move[j]))
            if out is None:
                return None, degenerate
    return replace(cell, bounds=out), degenerate


class Observer:
    """Bounded episode with persistent biases; late arrivals replay retained data."""

    def __init__(self, initial: StateBox, contract: SensorContract | None = None):
        self.contract = contract or SensorContract()
        if (
            max(abs(x) for x in (*initial.lower[:2], *initial.upper[:2])) > 1000
            or max(abs(x) for x in (*initial.lower[2:], *initial.upper[2:])) > 10
        ):
            raise ValueError("Reference state domain exceeded")
        self.initial = initial
        self.prior = initial
        self.prior_at = 0
        self.max_velocity = tuple(max(abs(initial.lower[j]), abs(initial.upper[j])) for j in (2, 3))
        self.history = ()
        self.packets = {}
        self.processed = ()
        self.posterior = initial_cells(initial, self.contract)
        self.posterior_at = 0
        self.inconsistent = False
        self.hypotheses = {h.label: h for h in self.contract.hypotheses}

    def _report(self, cells, now, status, diagnostics):
        channels = {}
        for channel in ("range", "bearing"):
            observed = [p for p in self.packets.values() if p.channel == channel]
            fresh = any(
                now - (p.acquired_ms - p.timestamp_uncertainty_ms) <= self.contract.fresh_age_ms
                for p in observed
            )
            channels[channel] = "fresh" if fresh else "stale" if observed else "missing"
        diagnostics.update(
            channel_status=channels,
            retained_packet_identity=identity(tuple(sorted(self.packets.values(), key=packet_key))),
            operations=diagnostics.get("operations", 0),
            retained_packets=len(self.packets),
            representation_cells=len(cells),
            hypotheses=sorted({c.hypothesis for c in cells}),
            bounds_origin="assumed_simulation_contract_not_sensor_calibration",
            negative_use="unsupported_outer_enclosure",
            sensor_contract_sha256=identity(self.contract),
        )
        return Estimate(
            tuple(cells), now, status, diagnostics, self.prior if self.prior_at == now else None
        )

    def update(self, packets, history, now_ms):
        millis(now_ms)
        diagnostics = {
            "replayed_out_of_order": False,
            "coarsening_merges": 0,
            "rejected_hypothesis_cells": 0,
            "bearing_degeneracy": False,
            "ignored_future": 0,
            "ignored_invalid": 0,
            "packet_capacity_exhausted": False,
        }
        budget = Budget(self.contract.max_operations)
        if now_ms < self.prior_at or now_ms > self.contract.max_horizon_ms:
            return self._report((), now_ms, "unsupported_time", diagnostics)
        try:
            history = validate_history(history, now_ms)
            if identity(history_prefix(history, self.prior_at)) != identity(self.history):
                return self._report((), now_ms, "unsupported_changed_command_history", diagnostics)
            predicted, v = advance(self.prior, history, self.prior_at, now_ms, budget)
            self.prior, self.prior_at, self.history = predicted, now_ms, history
            self.max_velocity = tuple(max(a, b) for a, b in zip(v, self.max_velocity, strict=True))
            if len(packets) > 512:
                raise ResourceLimit("Input batch capacity exceeded")
            for p in packets:
                try:
                    validate_packet(p, self.contract)
                except (ValueError, TypeError, OverflowError):
                    diagnostics["ignored_invalid"] += 1
                    continue
                if p.available_ms > now_ms or p.acquired_ms - p.timestamp_uncertainty_ms > now_ms:
                    diagnostics["ignored_future"] += 1
                    continue
                if p.packet_id in self.packets:
                    if self.packets[p.packet_id] != p:
                        self.inconsistent = True
                        diagnostics["conflicting_packet_identity"] = True
                    continue
                if len(self.packets) >= self.contract.max_packets:
                    diagnostics["packet_capacity_exhausted"] = True
                    continue
                self.packets[p.packet_id] = p
            if self.inconsistent:
                diagnostics["operations"] = budget.used
                return self._report((), now_ms, "inconsistent_observations", diagnostics)
            ordered = tuple(sorted(self.packets.values(), key=packet_key))
            identifiers = tuple(p.packet_id for p in ordered)
            incremental = identifiers[: len(self.processed)] == self.processed
            if incremental:
                cells, t = self.posterior, self.posterior_at
                pending = ordered[len(self.processed) :]
            else:
                cells, t = initial_cells(self.initial, self.contract), 0
                pending = ordered
                diagnostics["replayed_out_of_order"] = True
            for p in pending:
                q = min(p.available_ms, p.acquired_ms + p.timestamp_uncertainty_ms)
                lower = max(0, p.acquired_ms - p.timestamp_uncertainty_ms)
                if lower > q:
                    raise ValueError("Empty acquisition-time interval")
                move = tuple(v * Q(q - lower, 1000) for v in self.max_velocity)
                fresh = []
                for c in cells:
                    box, _ = advance(c.state(), history, t, q, budget)
                    c = c.with_state(box)
                    for active in self.hypotheses[c.hypothesis].modes(lower, q):
                        contracted, degenerate = contract_packet(
                            c, p, self.hypotheses[c.hypothesis], move, self.contract, active, budget
                        )
                        diagnostics["bearing_degeneracy"] |= degenerate
                        if contracted is None:
                            diagnostics["rejected_hypothesis_cells"] += 1
                        else:
                            fresh.append(contracted)
                if not fresh:
                    diagnostics["operations"] = budget.used
                    self.inconsistent = True
                    diagnostics["first_conflicting_packet"] = p.packet_id
                    diagnostics["interpretation"] = (
                        "data_or_model_inconsistent_not_absence_of_physical_state"
                    )
                    return self._report((), now_ms, "inconsistent_observations", diagnostics)
                cells, merges = merge_cells(fresh, self.contract.max_cells)
                diagnostics["coarsening_merges"] += merges
                t = q
            self.posterior, self.posterior_at, self.processed = cells, t, identifiers
            current = []
            for c in cells:
                box, _ = advance(c.state(), history, t, now_ms, budget)
                low = tuple(max(a, b) for a, b in zip(box.lower, self.prior.lower, strict=True))
                high = tuple(min(a, b) for a, b in zip(box.upper, self.prior.upper, strict=True))
                if all(a <= b for a, b in zip(low, high, strict=True)):
                    current.append(c.with_state(StateBox(low, high)))
            if not current:
                self.inconsistent = True
                diagnostics["operations"] = budget.used
                return self._report((), now_ms, "inconsistent_observations", diagnostics)
            fresh = any(
                now_ms - (p.acquired_ms - p.timestamp_uncertainty_ms) <= self.contract.fresh_age_ms
                for p in ordered
            )
            status = "updated" if fresh else "prediction_only_missing_or_stale"
            if diagnostics["packet_capacity_exhausted"]:
                status = "resource_exhausted_retained_constraints"
            if diagnostics["ignored_invalid"]:
                status = "unsupported_packets_ignored"
            diagnostics["operations"] = budget.used
            return self._report(current, now_ms, status, diagnostics)
        except ResourceLimit as exc:
            diagnostics.update(operations=budget.used, reason=str(exc))
            if self.inconsistent:
                return self._report((), now_ms, "inconsistent_observations", diagnostics)
            cells = initial_cells(self.prior, self.contract) if self.prior_at == now_ms else ()
            return self._report(cells, now_ms, "resource_exhausted_prior_only", diagnostics)
        except (ValueError, ArithmeticError, TypeError) as exc:
            diagnostics.update(operations=budget.used, reason=type(exc).__name__ + ":" + str(exc))
            return self._report((), now_ms, "numerical_or_history_failure", diagnostics)


def predict_to_application(estimate, queue, application_ms, max_operations=100000):
    """Propagate known queued inputs; do not invent future observations."""
    millis(application_ms)
    if (
        not estimate.cells
        or application_ms < estimate.at_ms
        or application_ms - estimate.at_ms > 200
    ):
        raise ValueError("Unsupported application prediction")
    t = estimate.at_ms
    for segment in queue:
        if segment.start_ms != t or segment.end_ms > application_ms:
            raise ValueError("Queue coverage mismatch")
        t = segment.end_ms
    if t != application_ms:
        raise ValueError("Missing queue")
    budget = Budget(max_operations)
    cells = tuple(
        c.with_state(advance(c.state(), queue, estimate.at_ms, application_ms, budget)[0])
        for c in estimate.cells
    )
    return replace(
        estimate,
        cells=cells,
        at_ms=application_ms,
        prior_at_decision=None,
        diagnostics={**estimate.diagnostics, "application_prediction_operations": budget.used},
    )
