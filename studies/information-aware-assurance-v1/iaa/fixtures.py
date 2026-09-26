"""Named engineering fixtures, not development/held-out statistical populations."""

from dataclasses import dataclass, field

from .plant import SensorFaults
from .types import StateBox, millis


@dataclass(frozen=True)
class Fixture:
    name: str
    initial: tuple[float, ...] = (0.5, -45.0, 0.0, 0.0)
    radii: tuple[float, ...] = (0.02, 0.02, 0.005, 0.005)
    horizon_ms: int = 30000
    faults: SensorFaults = field(default_factory=SensorFaults)
    effectiveness_after: float = 1.0
    actuator_fault_ms: int = 6000
    late_cycles: tuple[int, ...] = ()
    stalled_cycles: tuple[int, ...] = ()
    checker_enabled: bool = True
    additional_request_ms: tuple[int, ...] = (7250,)
    work_budget_mj: int = 500

    def __post_init__(self):
        millis(self.horizon_ms)
        millis(self.actuator_fault_ms)
        if self.horizon_ms % 500 or not 0 < self.horizon_ms <= 60000 or self.actuator_fault_ms % 10:
            raise ValueError("Unsupported fixture time grid/horizon")
        if not 0 <= self.effectiveness_after <= 1 or self.work_budget_mj < 0:
            raise ValueError("Invalid fixture resource/actuator setting")
        if any(type(t) is not int or t < 0 or t % 10 for t in self.additional_request_ms):
            raise ValueError("Additional requests must use the 10 ms clock grid")
        self.initial_box()

    def initial_box(self):
        return StateBox.around(self.initial, self.radii)


def fixtures():
    return (
        Fixture("nominal"),
        Fixture(
            "delayed_dropout_and_correlated_bias",
            faults=SensorFaults(
                range_bias_m=0.3,
                bearing_bias_rad=0.01,
                common_position_bias_m=(0.4, 0.2),
                range_delay_ms=200,
                bearing_delay_ms=400,
                dropout_bearing=True,
            ),
        ),
        Fixture("bounded_actuator_degradation", effectiveness_after=0.8),
        Fixture(
            "late_and_missing_decisions", late_cycles=(8, 9), stalled_cycles=tuple(range(14, 25))
        ),
        Fixture("unsupported_checker", checker_enabled=False, horizon_ms=5000),
        Fixture(
            "coast_entry_failure",
            initial=(0.0, -30.01, 0.0, 0.25),
            radii=(0.001, 0.001, 0.001, 0.001),
            horizon_ms=3000,
        ),
        Fixture("outside_model_actuator", effectiveness_after=0.2),
        Fixture(
            "invalid_timestamp_and_range",
            faults=SensorFaults(stamp_offset_ms=1000, invalid_range=True),
        ),
        Fixture("work_budget_exhaustion", work_budget_mj=40, horizon_ms=10000),
    )
