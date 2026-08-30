from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from .estimator import NavigationPacket

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class MeasurementFault:
    stratum_id: str
    channel: str
    onset_s: float | None
    end_s: float | None
    range_bias_m: float | None = None
    covariance_factor: float = 1.0

    def active(self, time_s: float) -> bool:
        return (
            self.onset_s is not None
            and time_s >= self.onset_s
            and (self.end_s is None or time_s < self.end_s)
        )

    def affects(self, channel: str) -> bool:
        return self.channel == channel or self.channel == "shared"


def quantize(value: float, quantum: float) -> float:
    if not np.isfinite(value) or not np.isfinite(quantum) or quantum <= 0.0:
        raise ValueError("quantization inputs must be finite and quantum must be positive")
    return float(np.rint(value / quantum) * quantum)


def navigation_packet(
    *,
    sequence_id: int,
    measured_at_s: float,
    received_at_s: float,
    range_value_m: float,
    velocity_value_mps: float,
    range_noise_m: float,
    velocity_noise_mps: float,
    range_quantization_m: float,
    velocity_quantization_mps: float,
    nominal_covariance: FloatArray,
    channel: str,
    fault: MeasurementFault,
    previous_packet: NavigationPacket | None,
) -> NavigationPacket | None:
    """Create one controller-observable packet from scalar navigation values.

    Biases remain unannounced. A stale fault repeats the prior packet identity and
    source epoch, allowing the online filter to detect duplicate data without a
    private fault label.
    """

    if channel not in {"primary", "monitor"}:
        raise ValueError("channel must be primary or monitor")
    active = fault.active(received_at_s) and fault.affects(channel)
    if active and fault.stratum_id == "E2_primary_dropout":
        return None
    if active and fault.stratum_id == "E3_primary_stale":
        if previous_packet is None:
            return None
        return NavigationPacket(
            previous_packet.sequence_id,
            previous_packet.measured_at_s,
            received_at_s,
            previous_packet.range_m,
            previous_packet.relative_velocity_mps,
            previous_packet.reported_covariance,
        )
    measured_range = quantize(
        range_value_m + range_noise_m,
        range_quantization_m,
    )
    measured_velocity = quantize(
        velocity_value_mps + velocity_noise_mps,
        velocity_quantization_mps,
    )
    if active and fault.range_bias_m is not None:
        measured_range += fault.range_bias_m
    covariance_factor = fault.covariance_factor if active else 1.0
    covariance = np.asarray(nominal_covariance, dtype=np.float64) * covariance_factor
    return NavigationPacket(
        sequence_id,
        measured_at_s,
        received_at_s,
        measured_range,
        measured_velocity,
        covariance,
    )
