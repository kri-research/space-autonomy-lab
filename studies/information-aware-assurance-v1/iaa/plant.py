"""Simulation-only HCW truth and sensor generation; never imported by controller.

Closed-form constant-input flow is numerically evaluated in binary64. It is a
corroborating plant implementation, not measured or independently validated physics.
"""

import math
from dataclasses import dataclass

from .types import ObservationPacket, rational

MEAN_MOTION = 0.0011


def flow(state, action, seconds, effectiveness=1.0, disturbance=(0.0, 0.0), n=MEAN_MOTION):
    values = (*state, *action, seconds, effectiveness, *disturbance, n)
    if any(not math.isfinite(float(v)) for v in values) or seconds < 0 or n < 0:
        raise ValueError("Invalid plant value")
    if len(state) != 4 or len(action) != 2 or len(disturbance) != 2:
        raise ValueError("Invalid plant dimensions")
    x, y, vx, vy = map(float, state)
    ax, ay = [
        float(effectiveness) * float(u) + float(w) for u, w in zip(action, disturbance, strict=True)
    ]
    t = float(seconds)
    if n == 0:
        return (x + vx * t + ax * t * t / 2, y + vy * t + ay * t * t / 2, vx + ax * t, vy + ay * t)
    q = n * t
    s = math.sin(q)
    c = math.cos(q)
    omc = 2 * math.sin(q / 2) ** 2
    qms = q**3 / 6 - q**5 / 120 + q**7 / 5040 if abs(q) < 0.01 else q - s
    return (
        (1 + 3 * omc) * x + s / n * vx + 2 * omc / n * vy + omc / n**2 * ax + 2 * qms / n**2 * ay,
        y
        - 6 * qms * x
        - 2 * omc / n * vx
        + (4 * s / n - 3 * t) * vy
        - 2 * qms / n**2 * ax
        + (4 * omc / n**2 - 1.5 * t * t) * ay,
        3 * n * s * x + c * vx + 2 * s * vy + s / n * ax + 2 * omc / n * ay,
        -6 * n * omc * x
        - 2 * s * vx
        + (1 - 4 * omc) * vy
        - 2 * omc / n * ax
        + (4 * s / n - 3 * t) * ay,
    )


@dataclass(frozen=True)
class SensorFaults:
    start_ms: int = 5000
    end_ms: int = 10000
    range_bias_m: float = 0.0
    bearing_bias_rad: float = 0.0
    common_position_bias_m: tuple[float, float] = (0.0, 0.0)
    range_delay_ms: int = 40
    bearing_delay_ms: int = 70
    dropout_range: bool = False
    dropout_bearing: bool = False
    stamp_offset_ms: int = 0
    invalid_range: bool = False

    def __post_init__(self):
        for v in (self.start_ms, self.end_ms, self.range_delay_ms, self.bearing_delay_ms):
            if type(v) is not int or v < 0 or v % 10:
                raise ValueError("Sensor events require 10 ms grid")
        if self.end_ms < self.start_ms or type(self.stamp_offset_ms) is not int:
            raise ValueError("Invalid fault interval/timestamp")
        for v in (self.range_bias_m, self.bearing_bias_rad, *self.common_position_bias_m):
            rational(v)


def observe(state, acquired_ms, sequence, faults):
    """Fault configuration stays on the plant side, not in delivered packet metadata."""
    active = faults.start_ms <= acquired_ms < faults.end_ms
    common = faults.common_position_bias_m if active else (0.0, 0.0)
    x, y = state[0] + common[0], state[1] + common[1]
    r = math.hypot(x, y) + (faults.range_bias_m if active else 0)
    beta = math.atan2(y, x) + (faults.bearing_bias_rad if active else 0)
    beta = math.atan2(math.sin(beta), math.cos(beta))
    output = []
    discarded = []
    for channel, value, delay, drop in [
        ("range", r, faults.range_delay_ms, active and faults.dropout_range),
        ("bearing", beta, faults.bearing_delay_ms, active and faults.dropout_bearing),
    ]:
        if drop:
            discarded.append({"channel": channel, "reason": "simulated_dropout"})
            continue
        try:
            p = ObservationPacket(
                f"{sequence}-{channel}",
                sequence,
                channel,
                float("nan") if active and faults.invalid_range and channel == "range" else value,
                acquired_ms + (faults.stamp_offset_ms if active else 0),
                acquired_ms + delay,
                unit="m" if channel == "range" else "rad",
            )
            output.append(p)
        except ValueError:
            discarded.append({"channel": channel, "reason": "invalid_packet_rejected"})
    return tuple(output), tuple(discarded)
