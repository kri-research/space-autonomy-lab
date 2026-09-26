"""Bounded-error contracts, persistent fault hypotheses and outer-only outputs."""

from dataclasses import dataclass, replace
from fractions import Fraction as Q

from iaa.types import Command, ObservationPacket, StateBox, identity, millis, rational

from .intervals import Interval, interval


class ResourceLimit(RuntimeError):
    pass


class Budget:
    def __init__(self, limit):
        self.limit = limit
        self.used = 0

    def tick(self, n=1):
        self.used += n
        if self.used > self.limit:
            raise ResourceLimit("Deterministic operation limit exhausted")


@dataclass(frozen=True)
class HistorySegment:
    start_ms: int
    end_ms: int
    action: tuple[Q, Q]

    def __post_init__(self):
        millis(self.start_ms)
        millis(self.end_ms)
        c = Command(self.action, self.start_ms, self.end_ms, "history")
        object.__setattr__(self, "action", c.acceleration)


def history_prefix(history, until_ms):
    out = []
    for s in history:
        if s.start_ms >= until_ms:
            break
        part = HistorySegment(s.start_ms, min(s.end_ms, until_ms), s.action)
        if out and out[-1].end_ms == part.start_ms and out[-1].action == part.action:
            out[-1] = replace(out[-1], end_ms=part.end_ms)
        else:
            out.append(part)
    return tuple(out)


def validate_history(history, now_ms, max_segments=256):
    millis(now_ms)
    if len(history) > max_segments:
        raise ResourceLimit("Command history capacity exhausted")
    t = 0
    for s in history:
        if not isinstance(s, HistorySegment) or s.start_ms != t or s.end_ms > now_ms:
            raise ValueError("Missing, overlapping or future applied command history")
        t = s.end_ms
    if t != now_ms:
        raise ValueError("Applied history must cover initialization through decision time")
    return history_prefix(history, now_ms)


@dataclass(frozen=True)
class FaultHypothesis:
    label: str
    # Constant latent offsets: common x/y (m), range (m), bearing (rad).
    biases: tuple[Interval, Interval, Interval, Interval]
    active_window_ms: tuple[int, int] | None = None

    def __post_init__(self):
        object.__setattr__(self, "biases", tuple(self.biases))
        if self.active_window_ms is not None:
            object.__setattr__(self, "active_window_ms", tuple(self.active_window_ms))
        if (
            not isinstance(self.label, str)
            or not self.label
            or len(self.label) > 64
            or len(self.biases) != 4
        ):
            raise ValueError("Invalid hypothesis identity/dimensions")
        if any(not isinstance(x, Interval) or max(abs(x.lo), abs(x.hi)) > 2 for x in self.biases):
            raise ValueError("Reference bias domain exceeded")
        if self.active_window_ms is not None:
            a, b = self.active_window_ms
            millis(a)
            millis(b)
            if b <= a:
                raise ValueError("Invalid fault window")

    def modes(self, low_ms, high_ms):
        if self.active_window_ms is None:
            return (True,)
        a, b = self.active_window_ms
        out = []
        if high_ms >= a and low_ms < b:
            out.append(True)
        if low_ms < a or high_ms >= b:
            out.append(False)
        return tuple(out)


def default_hypotheses():
    z = interval(0)
    full = (Interval(-Q(1, 2), Q(1, 2)),) * 2 + (
        Interval(-Q(2, 5), Q(2, 5)),
        Interval(-Q(1, 50), Q(1, 50)),
    )
    return (
        FaultHypothesis("no_bias", (z, z, z, z)),
        FaultHypothesis("persistent_range", (z, z, full[2], z)),
        FaultHypothesis("persistent_shared_and_channels", full),
        FaultHypothesis("window_shared_and_channels", full, (5000, 10000)),
    )


@dataclass(frozen=True)
class SensorContract:
    range_error_m: Q = Q(1, 100)
    bearing_error_rad: Q = Q(1, 1000)
    max_timestamp_uncertainty_ms: int = 2
    fresh_age_ms: int = 600
    max_horizon_ms: int = 30000
    max_packets: int = 128
    max_cells: int = 16
    initial_splits: int = 1
    max_operations: int = 100000
    hypotheses: tuple[FaultHypothesis, ...] = ()
    schema: str = "iaa-sensor-contract/2"

    def __post_init__(self):
        object.__setattr__(self, "hypotheses", tuple(self.hypotheses))
        if not self.hypotheses:
            object.__setattr__(self, "hypotheses", default_hypotheses())
        if any(not isinstance(h, FaultHypothesis) for h in self.hypotheses):
            raise ValueError("Invalid fault hypothesis")
        for name in ("range_error_m", "bearing_error_rad"):
            x = rational(getattr(self, name))
            object.__setattr__(self, name, x)
            if not 0 <= x <= 1:
                raise ValueError("Unsupported error bound")
        limits = {
            "max_timestamp_uncertainty_ms": 100,
            "fresh_age_ms": 60000,
            "max_horizon_ms": 60000,
            "max_packets": 256,
            "max_cells": 64,
            "initial_splits": 3,
            "max_operations": 1000000,
        }
        for name, upper in limits.items():
            x = getattr(self, name)
            if type(x) is not int or not 0 <= x <= upper:
                raise ValueError("Unsupported resource or time bound")
        if min(self.max_horizon_ms, self.max_packets, self.max_cells, self.max_operations) <= 0:
            raise ValueError("Positive resource limits required")
        if not 1 <= len(self.hypotheses) <= self.max_cells or len(
            {h.label for h in self.hypotheses}
        ) != len(self.hypotheses):
            raise ValueError("Cannot retain all declared fault hypotheses")
        if self.schema != "iaa-sensor-contract/2":
            raise ValueError("Unsupported sensor contract")


@dataclass(frozen=True)
class Cell:
    hypothesis: str
    bounds: tuple[Interval, ...]

    def __post_init__(self):
        if len(self.bounds) != 8 or any(not isinstance(v, Interval) for v in self.bounds):
            raise ValueError("Eight augmented state/bias coordinates required")

    def state(self):
        return StateBox(tuple(x.lo for x in self.bounds[:4]), tuple(x.hi for x in self.bounds[:4]))

    def with_state(self, box):
        return replace(
            self,
            bounds=tuple(Interval(a, b) for a, b in zip(box.lower, box.upper, strict=True))
            + self.bounds[4:],
        )

    def contains_state(self, state):
        return self.state().contains(state)


def merge_cells(cells, limit):
    """Only outward hulls; never discard a hypothesis on a weight or cell limit."""
    groups = {}
    for c in cells:
        groups.setdefault(c.hypothesis, []).append(c)
    if len(groups) > limit:
        raise ResourceLimit("Cannot preserve all hypotheses")
    cells = list(cells)
    merges = 0
    while len(cells) > limit:
        label = max(groups, key=lambda h: len(groups[h]))
        group = groups[label]
        a, b = group.pop(), group.pop()
        joined = Cell(
            label,
            tuple(
                Interval(min(x.lo, y.lo), max(x.hi, y.hi))
                for x, y in zip(a.bounds, b.bounds, strict=True)
            ),
        )
        group.append(joined)
        cells = [c for g in groups.values() for c in g]
        merges += 1
    return tuple(cells), merges


def initial_cells(box, contract):
    cells = []
    for h in contract.hypotheses:
        group = [
            Cell(
                h.label,
                tuple(Interval(a, b) for a, b in zip(box.lower, box.upper, strict=True)) + h.biases,
            )
        ]
        for _ in range(contract.initial_splits):
            new = []
            for c in group:
                scales = (1, 1, Q(1, 10), Q(1, 10), 1, 1, 1, Q(1, 50))
                j = max(range(8), key=lambda k: c.bounds[k].width / scales[k])
                x = c.bounds[j]
                mid = (x.lo + x.hi) / 2
                if not x.width:
                    new.append(c)
                    continue
                for piece in (Interval(x.lo, mid), Interval(mid, x.hi)):
                    bs = list(c.bounds)
                    bs[j] = piece
                    new.append(replace(c, bounds=tuple(bs)))
            group = new
        cells.extend(group)
    return merge_cells(cells, contract.max_cells)[0]


@dataclass(frozen=True)
class Estimate:
    cells: tuple[Cell, ...]
    at_ms: int
    status: str
    diagnostics: dict
    prior_at_decision: StateBox | None
    scope: str = "outer_observation_consistency_only"
    schema: str = "iaa-observation-set/2"

    def __post_init__(self):
        millis(self.at_ms)
        object.__setattr__(self, "cells", tuple(self.cells))
        if self.schema != "iaa-observation-set/2":
            raise ValueError("Unsupported estimate schema")
        if self.scope != "outer_observation_consistency_only":
            raise ValueError("Unsupported estimate scope")
        if any(not isinstance(c, Cell) for c in self.cells):
            raise ValueError("Invalid estimate cell")
        if self.prior_at_decision is not None and not isinstance(self.prior_at_decision, StateBox):
            raise ValueError("Invalid prior representation")

    def hull(self):
        if not self.cells:
            return None
        return StateBox(
            tuple(min(c.bounds[j].lo for c in self.cells) for j in range(4)),
            tuple(max(c.bounds[j].hi for c in self.cells) for j in range(4)),
        )

    def contains_state(self, state):
        return any(c.contains_state(state) for c in self.cells)

    def negative_certificate_input(self):
        raise ValueError(
            "Outer enclosure corners are not attainable observation-compatible witnesses"
        )

    def identity(self):
        return identity(self)


def packet_key(p):
    return (
        min(p.available_ms, p.acquired_ms + p.timestamp_uncertainty_ms),
        p.acquired_ms,
        p.sequence,
        p.channel,
        p.packet_id,
    )


def validate_packet(p, contract):
    if not isinstance(p, ObservationPacket):
        raise ValueError("ObservationPacket required")
    if p.timestamp_uncertainty_ms > contract.max_timestamp_uncertainty_ms:
        raise ValueError("Timestamp uncertainty outside declared contract")
    if abs(rational(p.value)) > 1000000:
        raise ValueError("Observation numeric domain exceeded")
    return p
