from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class PlanarNavigationPacket:
    """A timestamped Cartesian LVLH navigation packet.

    Measurement order is ``[x_m, y_m, vx_mps, vy_mps]``. The 4 by 4
    covariance uses the corresponding outer-product units: position-position
    entries are m^2, position-velocity entries are m^2/s, and
    velocity-velocity entries are m^2/s^2.
    """

    sequence_id: int
    measured_at_s: float
    received_at_s: float
    measurement: FloatArray
    reported_covariance: FloatArray

    def __post_init__(self) -> None:
        if type(self.sequence_id) is not int or self.sequence_id < 0:
            raise ValueError("sequence_id must be a non-negative integer")
        if not np.isfinite(self.measured_at_s) or not np.isfinite(self.received_at_s):
            raise ValueError("packet timestamps must be finite")
        if self.measured_at_s < 0.0 or self.received_at_s < self.measured_at_s:
            raise ValueError("packet timestamps are inconsistent")
        measurement = np.asarray(self.measurement, dtype=np.float64)
        covariance = np.asarray(self.reported_covariance, dtype=np.float64)
        if measurement.shape != (4,) or not np.all(np.isfinite(measurement)):
            raise ValueError("packet measurement must be a finite four-vector")
        if covariance.shape != (4, 4) or not np.all(np.isfinite(covariance)):
            raise ValueError("reported covariance must be a finite 4 by 4 matrix")
        if not np.allclose(covariance, covariance.T, rtol=0.0, atol=1e-15):
            raise ValueError("reported covariance must be symmetric")
        if float(np.linalg.eigvalsh(covariance)[0]) <= 0.0:
            raise ValueError("reported covariance must be positive definite")
        object.__setattr__(self, "measurement", np.array(measurement, copy=True))
        object.__setattr__(self, "reported_covariance", np.array(covariance, copy=True))


@dataclass(frozen=True)
class MeasurementFault:
    kind: str
    channel: str
    onset_s: float | None
    end_s: float | None
    additive_bias: tuple[float, float, float, float] | None = None
    covariance_factor: float = 1.0

    def __post_init__(self) -> None:
        if self.kind not in {"none", "bias", "dropout", "stale", "covariance_underreporting"}:
            raise ValueError("unknown measurement fault kind")
        if self.channel not in {"none", "primary", "monitor", "shared"}:
            raise ValueError("unknown measurement fault channel")
        if self.onset_s is None:
            if self.end_s is not None:
                raise ValueError("fault end requires a fault onset")
        elif (
            not np.isfinite(self.onset_s)
            or self.onset_s < 0.0
            or (self.end_s is not None and self.end_s <= self.onset_s)
        ):
            raise ValueError("fault timing is invalid")
        if self.additive_bias is not None:
            bias = np.asarray(self.additive_bias, dtype=np.float64)
            if bias.shape != (4,) or not np.all(np.isfinite(bias)):
                raise ValueError("measurement bias must be a finite four-vector")
        if not np.isfinite(self.covariance_factor) or self.covariance_factor <= 0.0:
            raise ValueError("covariance factor must be finite and positive")

    def active(self, receipt_time_s: float, channel: str) -> bool:
        affected = self.channel in {channel, "shared"}
        return bool(
            affected
            and self.onset_s is not None
            and receipt_time_s >= self.onset_s
            and (self.end_s is None or receipt_time_s < self.end_s)
        )


def quantize_measurement(values: FloatArray, quantum: FloatArray) -> FloatArray:
    vector = np.asarray(values, dtype=np.float64)
    steps = np.asarray(quantum, dtype=np.float64)
    if vector.shape != (4,) or not np.all(np.isfinite(vector)):
        raise ValueError("measurement must be a finite four-vector")
    if steps.shape != (4,) or np.any(steps <= 0.0) or not np.all(np.isfinite(steps)):
        raise ValueError("quantization must be a finite positive four-vector")
    return np.rint(vector / steps) * steps


def navigation_packet(
    *,
    sequence_id: int,
    measured_at_s: float,
    received_at_s: float,
    latent_state: FloatArray,
    measurement_noise: FloatArray,
    quantization: FloatArray,
    nominal_covariance: FloatArray,
    channel: str,
    fault: MeasurementFault,
    previous_packet: PlanarNavigationPacket | None,
) -> PlanarNavigationPacket | None:
    """Construct one observable packet without exposing its fault metadata."""

    if channel not in {"primary", "monitor"}:
        raise ValueError("channel must be primary or monitor")
    active = fault.active(received_at_s, channel)
    if active and fault.kind == "dropout":
        return None
    if active and fault.kind == "stale":
        if previous_packet is None:
            return None
        return PlanarNavigationPacket(
            previous_packet.sequence_id,
            previous_packet.measured_at_s,
            received_at_s,
            previous_packet.measurement,
            previous_packet.reported_covariance,
        )
    value = np.asarray(latent_state, dtype=np.float64) + np.asarray(
        measurement_noise, dtype=np.float64
    )
    value = quantize_measurement(value, quantization)
    if active and fault.additive_bias is not None:
        value = value + np.asarray(fault.additive_bias, dtype=np.float64)
    factor = fault.covariance_factor if active else 1.0
    return PlanarNavigationPacket(
        sequence_id,
        measured_at_s,
        received_at_s,
        value,
        np.asarray(nominal_covariance, dtype=np.float64) * factor,
    )
