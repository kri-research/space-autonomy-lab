from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from .config import Experiment003Config
from .model import (
    measurement_matrix,
    nominal_measurement_covariance,
    piecewise_disturbance_covariance,
    transition_matrices,
)

FloatArray = NDArray[np.float64]


class FilterHealth(StrEnum):
    VALID = "valid"
    DEGRADED = "degraded"
    DIVERGED = "diverged"


class FilterReason(StrEnum):
    NONE = "none"
    INITIAL_PRIOR = "initial_prior"
    PREDICTION_ONLY = "prediction_only"
    INNOVATION_REJECTED = "innovation_rejected"
    STALE_OR_DUPLICATE_PACKET = "stale_or_duplicate_packet"
    INVALID_PACKET = "invalid_packet"
    NONFINITE_NUMERICS = "nonfinite_numerics"
    COVARIANCE_NOT_POSITIVE_SEMIDEFINITE = "covariance_not_positive_semidefinite"
    COVARIANCE_TRACE_LIMIT = "covariance_trace_limit"
    INNOVATION_CONDITION_LIMIT = "innovation_condition_limit"
    STATE_LIMIT = "state_limit"


class PacketDisposition(StrEnum):
    ACCEPTED = "accepted"
    INNOVATION_REJECTED = "innovation_rejected"
    TOO_OLD = "too_old"
    FUTURE_MEASUREMENT = "future_measurement"
    DUPLICATE = "duplicate"
    INVALID = "invalid"
    FILTER_DIVERGED = "filter_diverged"


@dataclass(frozen=True)
class NavigationPacket:
    sequence_id: int
    measured_at_s: float
    received_at_s: float
    range_m: float
    relative_velocity_mps: float
    reported_covariance: FloatArray

    def __post_init__(self) -> None:
        if type(self.sequence_id) is not int or self.sequence_id < 0:
            raise ValueError("sequence_id must be a non-negative integer")
        scalars = (
            self.measured_at_s,
            self.received_at_s,
            self.range_m,
            self.relative_velocity_mps,
        )
        if not all(np.isfinite(value) for value in scalars):
            raise ValueError("packet scalar values must be finite")
        if self.measured_at_s < 0.0 or self.received_at_s < self.measured_at_s:
            raise ValueError("packet timestamps are inconsistent")
        covariance = np.asarray(self.reported_covariance, dtype=np.float64)
        if covariance.shape != (2, 2) or not np.all(np.isfinite(covariance)):
            raise ValueError("reported covariance must be a finite 2 by 2 matrix")
        if not np.allclose(covariance, covariance.T, atol=1e-15, rtol=0.0):
            raise ValueError("reported covariance must be symmetric")
        if float(np.linalg.eigvalsh(covariance)[0]) <= 0.0:
            raise ValueError("reported covariance must be positive definite")
        object.__setattr__(self, "reported_covariance", np.array(covariance, copy=True))

    @property
    def measurement(self) -> FloatArray:
        return np.array([self.range_m, self.relative_velocity_mps], dtype=np.float64)


@dataclass(frozen=True)
class UpdateDiagnostic:
    sequence_id: int
    measured_at_s: float
    received_at_s: float
    disposition: PacketDisposition
    nis: float | None
    innovation: tuple[float, float] | None


@dataclass(frozen=True)
class NavigationSnapshot:
    time_s: float
    mean: FloatArray
    covariance: FloatArray
    health: FilterHealth
    reason: FilterReason
    last_accepted_measurement_time_s: float | None
    prediction_only_age_s: float | None
    consecutive_innovation_rejections: int
    accepted_updates: int
    innovation_rejections: int
    invalid_packets: int
    last_nis: float | None

    @property
    def range_m(self) -> float:
        return float(self.mean[0])

    @property
    def relative_velocity_mps(self) -> float:
        return float(self.mean[1])


@dataclass(frozen=True)
class _Meta:
    health: FilterHealth
    reason: FilterReason
    last_accepted_time_s: float | None
    consecutive_rejections: int
    accepted_updates: int
    innovation_rejections: int
    invalid_packets: int
    last_nis: float | None


@dataclass
class _Node:
    time_s: float
    prior_mean: FloatArray
    prior_covariance: FloatArray
    prior_meta: _Meta
    packets: list[NavigationPacket]
    posterior_mean: FloatArray
    posterior_covariance: FloatArray
    posterior_meta: _Meta
    diagnostics: list[UpdateDiagnostic]


class _Divergence(RuntimeError):
    def __init__(self, reason: FilterReason):
        super().__init__(reason.value)
        self.reason = reason


class NavigationFilter:
    """Deterministic fixed-lag linear navigation filter.

    The filter accepts measurements and executed commands only. It has no route
    for simulator state, realized disturbance, actuator effectiveness, fault
    labels, or evaluator outputs.
    """

    def __init__(self, study: Experiment003Config, production) -> None:
        self.study = study
        self.production = production
        self.transition, self.command_vector = transition_matrices(
            production.command_period_s,
            production.actuator_time_constant_s,
        )
        self.process_covariance = piecewise_disturbance_covariance(
            production.command_period_s,
            production.exogenous_period_s,
            production.process_accel_sigma_mps2,
            study.actuator_model_process_sigma_mps2,
        )
        self.observation = measurement_matrix()
        self.nominal_measurement_covariance = nominal_measurement_covariance(
            production.range_noise_sigma_m,
            production.velocity_noise_sigma_mps,
            production.range_quantization_m,
            production.velocity_quantization_mps,
        )
        mean = study.initial_mean_array
        covariance = study.initial_covariance
        self._validate_mean_covariance(mean, covariance)
        meta = _Meta(
            FilterHealth.DEGRADED,
            FilterReason.INITIAL_PRIOR,
            None,
            0,
            0,
            0,
            0,
            None,
        )
        initial = _Node(
            0.0,
            mean.copy(),
            covariance.copy(),
            meta,
            [],
            mean.copy(),
            covariance.copy(),
            meta,
            [],
        )
        self._nodes: dict[float, _Node] = {0.0: initial}
        self._controls: dict[float, float] = {}
        self._seen_sequences: set[int] = set()
        self._current_time = 0.0
        self._last_diagnostic: UpdateDiagnostic | None = None

    @staticmethod
    def _key(time_s: float) -> float:
        return round(float(time_s), 12)

    @property
    def current_time_s(self) -> float:
        return self._current_time

    @property
    def last_diagnostic(self) -> UpdateDiagnostic | None:
        return self._last_diagnostic

    def _diverged_meta(self, meta: _Meta, reason: FilterReason) -> _Meta:
        return replace(meta, health=FilterHealth.DIVERGED, reason=reason)

    def _validate_mean_covariance(
        self, mean: FloatArray, covariance: FloatArray
    ) -> tuple[FloatArray, FloatArray]:
        vector = np.asarray(mean, dtype=np.float64)
        matrix = np.asarray(covariance, dtype=np.float64)
        if vector.shape != (3,) or matrix.shape != (3, 3):
            raise _Divergence(FilterReason.NONFINITE_NUMERICS)
        if not np.all(np.isfinite(vector)) or not np.all(np.isfinite(matrix)):
            raise _Divergence(FilterReason.NONFINITE_NUMERICS)
        limits = np.asarray(self.study.state_absolute_limits, dtype=np.float64)
        if np.any(np.abs(vector) > limits):
            raise _Divergence(FilterReason.STATE_LIMIT)
        symmetric = 0.5 * (matrix + matrix.T)
        eigenvalues = np.linalg.eigvalsh(symmetric)
        minimum = float(eigenvalues[0])
        tolerance = self.study.covariance_negative_eigenvalue_tolerance
        if minimum < -tolerance:
            raise _Divergence(FilterReason.COVARIANCE_NOT_POSITIVE_SEMIDEFINITE)
        if minimum <= 0.0:
            symmetric += np.eye(3, dtype=np.float64) * (tolerance - minimum)
        if float(np.trace(symmetric)) > self.study.covariance_trace_limit:
            raise _Divergence(FilterReason.COVARIANCE_TRACE_LIMIT)
        return np.array(vector, copy=True), symmetric

    def _prediction_meta(self, previous: _Meta, time_s: float) -> _Meta:
        if previous.health is FilterHealth.DIVERGED:
            return previous
        if previous.last_accepted_time_s is None:
            return replace(
                previous,
                health=FilterHealth.DEGRADED,
                reason=FilterReason.PREDICTION_ONLY,
            )
        age = time_s - previous.last_accepted_time_s
        if age > self.study.degraded_after_prediction_only_s + 1e-12:
            return replace(
                previous,
                health=FilterHealth.DEGRADED,
                reason=FilterReason.PREDICTION_ONLY,
            )
        return replace(previous, health=FilterHealth.VALID, reason=FilterReason.NONE)

    def advance(self, command_mps2: float, end_time_s: float) -> NavigationSnapshot:
        if not np.isfinite(command_mps2) or not np.isfinite(end_time_s):
            raise ValueError("command and end time must be finite")
        start_key = self._key(self._current_time)
        expected = self._current_time + self.production.command_period_s
        if abs(end_time_s - expected) > 1e-12:
            raise ValueError("filter advances exactly one frozen command period at a time")
        end_key = self._key(end_time_s)
        if end_key in self._nodes:
            raise ValueError("filter time cannot regress or repeat")
        previous = self._nodes[start_key]
        self._controls[start_key] = float(command_mps2)
        prior_meta = self._prediction_meta(previous.posterior_meta, end_key)
        try:
            if prior_meta.health is FilterHealth.DIVERGED:
                raise _Divergence(prior_meta.reason)
            mean = self.transition @ previous.posterior_mean + self.command_vector * command_mps2
            covariance = (
                self.transition @ previous.posterior_covariance @ self.transition.T
                + self.process_covariance
            )
            mean, covariance = self._validate_mean_covariance(mean, covariance)
        except _Divergence as exc:
            mean = previous.posterior_mean.copy()
            covariance = previous.posterior_covariance.copy()
            prior_meta = self._diverged_meta(prior_meta, exc.reason)
        node = _Node(
            end_key,
            mean.copy(),
            covariance.copy(),
            prior_meta,
            [],
            mean.copy(),
            covariance.copy(),
            prior_meta,
            [],
        )
        self._nodes[end_key] = node
        self._current_time = end_key
        return self.snapshot()

    def _mark_invalid_packet(
        self,
        packet: NavigationPacket,
        disposition: PacketDisposition,
    ) -> UpdateDiagnostic:
        current = self._nodes[self._key(self._current_time)]
        if current.posterior_meta.health is not FilterHealth.DIVERGED:
            current.posterior_meta = replace(
                current.posterior_meta,
                health=FilterHealth.DEGRADED,
                reason=(
                    FilterReason.STALE_OR_DUPLICATE_PACKET
                    if disposition in {PacketDisposition.TOO_OLD, PacketDisposition.DUPLICATE}
                    else FilterReason.INVALID_PACKET
                ),
                invalid_packets=current.posterior_meta.invalid_packets + 1,
            )
        diagnostic = UpdateDiagnostic(
            packet.sequence_id,
            packet.measured_at_s,
            packet.received_at_s,
            disposition,
            None,
            None,
        )
        self._last_diagnostic = diagnostic
        return diagnostic

    def ingest(self, packet: NavigationPacket) -> UpdateDiagnostic:
        current = self._nodes[self._key(self._current_time)]
        if current.posterior_meta.health is FilterHealth.DIVERGED:
            return self._mark_invalid_packet(packet, PacketDisposition.FILTER_DIVERGED)
        if abs(packet.received_at_s - self._current_time) > 1e-12:
            return self._mark_invalid_packet(packet, PacketDisposition.INVALID)
        if packet.sequence_id in self._seen_sequences:
            return self._mark_invalid_packet(packet, PacketDisposition.DUPLICATE)
        if packet.measured_at_s > self._current_time + 1e-12:
            return self._mark_invalid_packet(packet, PacketDisposition.FUTURE_MEASUREMENT)
        if self._current_time - packet.measured_at_s > self.study.maximum_packet_lag_s + 1e-12:
            return self._mark_invalid_packet(packet, PacketDisposition.TOO_OLD)
        measured_key = self._key(packet.measured_at_s)
        if measured_key not in self._nodes:
            return self._mark_invalid_packet(packet, PacketDisposition.INVALID)
        self._nodes[measured_key].packets.append(packet)
        self._seen_sequences.add(packet.sequence_id)
        self._replay_from(measured_key)
        diagnostic = next(
            item
            for item in self._nodes[measured_key].diagnostics
            if item.sequence_id == packet.sequence_id
        )
        self._last_diagnostic = diagnostic
        return diagnostic

    def _update(
        self,
        mean: FloatArray,
        covariance: FloatArray,
        meta: _Meta,
        packet: NavigationPacket,
    ) -> tuple[FloatArray, FloatArray, _Meta, UpdateDiagnostic]:
        if meta.health is FilterHealth.DIVERGED:
            diagnostic = UpdateDiagnostic(
                packet.sequence_id,
                packet.measured_at_s,
                packet.received_at_s,
                PacketDisposition.FILTER_DIVERGED,
                None,
                None,
            )
            return mean, covariance, meta, diagnostic
        innovation = packet.measurement - self.observation @ mean
        innovation_covariance = (
            self.observation @ covariance @ self.observation.T
            + packet.reported_covariance
        )
        try:
            condition = float(np.linalg.cond(innovation_covariance))
            if not np.isfinite(condition) or condition > self.study.innovation_condition_limit:
                raise _Divergence(FilterReason.INNOVATION_CONDITION_LIMIT)
            solved_innovation = np.linalg.solve(innovation_covariance, innovation)
            nis = float(innovation @ solved_innovation)
            if not np.isfinite(nis):
                raise _Divergence(FilterReason.NONFINITE_NUMERICS)
        except np.linalg.LinAlgError as exc:
            raise _Divergence(FilterReason.INNOVATION_CONDITION_LIMIT) from exc
        innovation_tuple = (float(innovation[0]), float(innovation[1]))
        if nis > self.study.nis_reject_threshold:
            rejected_meta = replace(
                meta,
                health=FilterHealth.DEGRADED,
                reason=FilterReason.INNOVATION_REJECTED,
                consecutive_rejections=meta.consecutive_rejections + 1,
                innovation_rejections=meta.innovation_rejections + 1,
                last_nis=nis,
            )
            diagnostic = UpdateDiagnostic(
                packet.sequence_id,
                packet.measured_at_s,
                packet.received_at_s,
                PacketDisposition.INNOVATION_REJECTED,
                nis,
                innovation_tuple,
            )
            return mean, covariance, rejected_meta, diagnostic
        gain = np.linalg.solve(
            innovation_covariance,
            self.observation @ covariance,
        ).T
        updated_mean = mean + gain @ innovation
        identity = np.eye(3, dtype=np.float64)
        residual_operator = identity - gain @ self.observation
        updated_covariance = (
            residual_operator @ covariance @ residual_operator.T
            + gain @ packet.reported_covariance @ gain.T
        )
        updated_mean, updated_covariance = self._validate_mean_covariance(
            updated_mean, updated_covariance
        )
        updated_meta = replace(
            meta,
            health=FilterHealth.VALID,
            reason=FilterReason.NONE,
            last_accepted_time_s=packet.measured_at_s,
            consecutive_rejections=0,
            accepted_updates=meta.accepted_updates + 1,
            last_nis=nis,
        )
        diagnostic = UpdateDiagnostic(
            packet.sequence_id,
            packet.measured_at_s,
            packet.received_at_s,
            PacketDisposition.ACCEPTED,
            nis,
            innovation_tuple,
        )
        return updated_mean, updated_covariance, updated_meta, diagnostic

    def _replay_from(self, start_time_s: float) -> None:
        times = sorted(time for time in self._nodes if time >= start_time_s - 1e-12)
        for index, time_s in enumerate(times):
            node = self._nodes[time_s]
            if index > 0 or time_s > start_time_s + 1e-12:
                previous_time = self._key(time_s - self.production.command_period_s)
                previous = self._nodes[previous_time]
                command = self._controls[previous_time]
                node.prior_meta = self._prediction_meta(previous.posterior_meta, time_s)
                if node.prior_meta.health is FilterHealth.DIVERGED:
                    node.prior_mean = previous.posterior_mean.copy()
                    node.prior_covariance = previous.posterior_covariance.copy()
                else:
                    try:
                        node.prior_mean = (
                            self.transition @ previous.posterior_mean
                            + self.command_vector * command
                        )
                        node.prior_covariance = (
                            self.transition
                            @ previous.posterior_covariance
                            @ self.transition.T
                            + self.process_covariance
                        )
                        node.prior_mean, node.prior_covariance = self._validate_mean_covariance(
                            node.prior_mean, node.prior_covariance
                        )
                    except _Divergence as exc:
                        node.prior_mean = previous.posterior_mean.copy()
                        node.prior_covariance = previous.posterior_covariance.copy()
                        node.prior_meta = self._diverged_meta(node.prior_meta, exc.reason)
            mean = node.prior_mean.copy()
            covariance = node.prior_covariance.copy()
            meta = node.prior_meta
            diagnostics: list[UpdateDiagnostic] = []
            for packet in sorted(
                node.packets,
                key=lambda item: (item.sequence_id, item.received_at_s),
            ):
                try:
                    mean, covariance, meta, diagnostic = self._update(
                        mean, covariance, meta, packet
                    )
                except _Divergence as exc:
                    meta = self._diverged_meta(meta, exc.reason)
                    diagnostic = UpdateDiagnostic(
                        packet.sequence_id,
                        packet.measured_at_s,
                        packet.received_at_s,
                        PacketDisposition.FILTER_DIVERGED,
                        None,
                        None,
                    )
                diagnostics.append(diagnostic)
            node.posterior_mean = mean
            node.posterior_covariance = covariance
            node.posterior_meta = meta
            node.diagnostics = diagnostics

    def snapshot(self) -> NavigationSnapshot:
        node = self._nodes[self._key(self._current_time)]
        meta = node.posterior_meta
        age = (
            None
            if meta.last_accepted_time_s is None
            else self._current_time - meta.last_accepted_time_s
        )
        return NavigationSnapshot(
            time_s=self._current_time,
            mean=node.posterior_mean.copy(),
            covariance=node.posterior_covariance.copy(),
            health=meta.health,
            reason=meta.reason,
            last_accepted_measurement_time_s=meta.last_accepted_time_s,
            prediction_only_age_s=age,
            consecutive_innovation_rejections=meta.consecutive_rejections,
            accepted_updates=meta.accepted_updates,
            innovation_rejections=meta.innovation_rejections,
            invalid_packets=meta.invalid_packets,
            last_nis=meta.last_nis,
        )
