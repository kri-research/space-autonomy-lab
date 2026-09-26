"""Public decision context contains no future measurement, truth or fault label."""

from dataclasses import dataclass
from fractions import Fraction as Q

from iaa.types import Command, identity, millis, rational
from sa02.bridge import ALLOWED
from sa02.model import Estimate, HistorySegment, SensorContract


@dataclass(frozen=True)
class Timing:
    now_ms: int = 100
    first_apply_ms: int = 200
    acquire_ms: int = 250
    apply_ms: int = 700
    range_delay_ms: int = 40
    bearing_delay_ms: int = 70
    processing_ms: int = 50
    planner_model_ms: int = 50
    request_lead_ms: int = 100
    timestamp_ms: int = 2
    hold_ms: int = 500
    reserve_ms: int = 3000

    def __post_init__(self):
        for value in self.__dict__.values():
            millis(value)
        if not (
            self.now_ms < self.first_apply_ms <= self.acquire_ms
            and self.now_ms + self.planner_model_ms <= self.first_apply_ms
            and self.acquire_ms == self.now_ms + self.planner_model_ms + self.request_lead_ms
            and self.acquire_ms + self.timestamp_ms < self.apply_ms
            and self.first_apply_ms - self.now_ms <= 200
            and self.apply_ms - self.first_apply_ms == 500
            and self.hold_ms == 500
            and self.reserve_ms == 3000
        ):
            raise ValueError("Unsupported two-slot timeline")
        if self.acquire_ms - self.timestamp_ms < self.now_ms:
            raise ValueError("Prospective acquisition precedes decision")

    def ready(self, channel):
        delay = self.range_delay_ms if channel == "range" else self.bearing_delay_ms
        return self.acquire_ms + delay + self.processing_ms

    @property
    def end_ms(self):
        return self.apply_ms + self.hold_ms + self.reserve_ms


@dataclass(frozen=True)
class Context:
    estimate: Estimate
    sensors: SensorContract
    timing: Timing = Timing()
    queued_action: tuple = (Q(0), Q(0))
    resource_mj: Q = Q(500)
    max_operations: int = 50000
    max_nodes: int = 255
    assumptions_supported: bool = True
    schema: str = "iaa-sa03-context/1"

    def __post_init__(self):
        if self.schema != "iaa-sa03-context/1":
            raise ValueError("Unsupported context schema")
        if not isinstance(self.estimate, Estimate) or not isinstance(self.sensors, SensorContract):
            raise ValueError("Typed prior and sensor contract required")
        if not isinstance(self.timing, Timing):
            raise ValueError("Typed timing contract required")
        labels = {h.label for h in self.sensors.hypotheses}
        if any(c.hypothesis not in labels for c in self.estimate.cells):
            raise ValueError("Undeclared retained hypothesis")
        if self.estimate.at_ms != self.timing.now_ms:
            raise ValueError("Estimate and decision clock mismatch")
        if self.estimate.diagnostics.get("sensor_contract_sha256") != identity(self.sensors):
            raise ValueError("Observation model identity mismatch")
        if self.timing.timestamp_ms > self.sensors.max_timestamp_uncertainty_ms:
            raise ValueError("Unsupported clock uncertainty")
        if type(self.assumptions_supported) is not bool:
            raise ValueError("Explicit assumption validity required")
        object.__setattr__(self, "resource_mj", rational(self.resource_mj))
        if self.resource_mj < 0:
            raise ValueError("Negative resource budget")
        for name, cap in (("max_operations", 100000), ("max_nodes", 511)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= cap:
                raise ValueError("Unsupported bounded search resources")
        cmd = Command(self.queued_action, self.timing.now_ms, self.timing.first_apply_ms, "queue")
        object.__setattr__(self, "queued_action", cmd.acceleration)

    @property
    def usable(self):
        return (
            self.assumptions_supported
            and self.estimate.status in ALLOWED
            and bool(self.estimate.cells)
        )

    def queue(self):
        t = self.timing
        return (
            HistorySegment(t.now_ms, t.first_apply_ms, self.queued_action),
            HistorySegment(t.first_apply_ms, t.apply_ms, (Q(0), Q(0))),
        )

    def identity(self):
        return identity(self)


class RequestLedger:
    """Single-request simulation guard; not a physical security boundary."""

    def __init__(self, available_mj):
        self.available = rational(available_mj)
        if self.available < 0:
            raise ValueError("Negative resource")
        self.seen = set()
        self.busy_until = 0

    def reserve(self, request_id, now_ms, until_ms, cost_mj):
        millis(now_ms)
        millis(until_ms)
        cost = rational(cost_mj)
        if not isinstance(request_id, str) or not request_id or until_ms <= now_ms or cost < 0:
            raise ValueError("Malformed request")
        if request_id in self.seen:
            return "duplicate"
        self.seen.add(request_id)
        if now_ms < self.busy_until:
            return "request_in_flight"
        if cost > self.available:
            return "resource_exhausted"
        self.available -= cost
        self.busy_until = until_ms
        return "reserved"
