from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from .config import Experiment004Config
from .dynamics import discrete_matrices, piecewise_acceleration_covariance
from .measurements import PlanarNavigationPacket

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
class UpdateDiagnostic:
    sequence_id: int
    measured_at_s: float
    received_at_s: float
    disposition: PacketDisposition
    nis: float | None
    innovation: tuple[float, float, float, float] | None


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


@dataclass(frozen=True)
class _Meta:
    health: FilterHealth
    reason: FilterReason
    last_accepted_tick: int | None
    consecutive_rejections: int
    accepted_updates: int
    innovation_rejections: int
    invalid_packets: int
    last_nis: float | None


@dataclass
class _Node:
    tick: int
    prior_mean: FloatArray
    prior_covariance: FloatArray
    prior_meta: _Meta
    packets: list[PlanarNavigationPacket]
    posterior_mean: FloatArray
    posterior_covariance: FloatArray
    posterior_meta: _Meta
    diagnostics: list[UpdateDiagnostic]


class _Divergence(RuntimeError):
    def __init__(self, reason: FilterReason):
        super().__init__(reason.value)
        self.reason = reason


class PlanarNavigationFilter:
    """Deterministic fixed-lag linear filter with no truth or fault-label route."""

    def __init__(self, config: Experiment004Config) -> None:
        self.config = config
        self.transition, self.command_map = discrete_matrices(
            config.mean_motion_rad_s,
            config.command_period_s,
        )
        self.process_covariance = piecewise_acceleration_covariance(
            config.mean_motion_rad_s,
            config.command_period_s,
            config.process_acceleration_draw_period_s,
            config.process_acceleration_sigma_mps2,
        )
        self.observation = np.eye(4, dtype=np.float64)
        self.nominal_measurement_covariance = config.nominal_measurement_covariance
        mean, covariance = self._validate_mean_covariance(
            config.initial_mean_array,
            config.initial_covariance,
        )
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
            0,
            mean.copy(),
            covariance.copy(),
            meta,
            [],
            mean.copy(),
            covariance.copy(),
            meta,
            [],
        )
        self._nodes: dict[int, _Node] = {0: initial}
        self._controls: dict[int, FloatArray] = {}
        self._seen_sequences: set[int] = set()
        self._current_tick = 0
        self._last_diagnostic: UpdateDiagnostic | None = None

    @property
    def current_time_s(self) -> float:
        return self._current_tick * self.config.command_period_s

    @property
    def last_diagnostic(self) -> UpdateDiagnostic | None:
        return self._last_diagnostic

    def _time_to_tick(self, time_s: float) -> int:
        if not np.isfinite(time_s) or time_s < 0.0:
            raise ValueError("filter time must be finite and non-negative")
        ratio = float(time_s) / self.config.command_period_s
        tick = round(ratio)
        if abs(ratio - tick) > 1e-10:
            raise ValueError("filter timestamps must lie on the command grid")
        return int(tick)

    def _validate_mean_covariance(
        self,
        mean: FloatArray,
        covariance: FloatArray,
    ) -> tuple[FloatArray, FloatArray]:
        vector = np.asarray(mean, dtype=np.float64)
        matrix = np.asarray(covariance, dtype=np.float64)
        if vector.shape != (4,) or matrix.shape != (4, 4):
            raise _Divergence(FilterReason.NONFINITE_NUMERICS)
        if not np.all(np.isfinite(vector)) or not np.all(np.isfinite(matrix)):
            raise _Divergence(FilterReason.NONFINITE_NUMERICS)
        limits = np.asarray(self.config.state_absolute_limits, dtype=np.float64)
        if np.any(np.abs(vector) > limits):
            raise _Divergence(FilterReason.STATE_LIMIT)
        symmetric = 0.5 * (matrix + matrix.T)
        eigenvalues = np.linalg.eigvalsh(symmetric)
        minimum = float(eigenvalues[0])
        tolerance = self.config.covariance_negative_eigenvalue_tolerance
        if minimum < -tolerance:
            raise _Divergence(FilterReason.COVARIANCE_NOT_POSITIVE_SEMIDEFINITE)
        if minimum <= 0.0:
            symmetric += np.eye(4, dtype=np.float64) * (tolerance - minimum)
        if float(np.trace(symmetric)) > self.config.covariance_trace_limit:
            raise _Divergence(FilterReason.COVARIANCE_TRACE_LIMIT)
        return np.array(vector, copy=True), symmetric

    @staticmethod
    def _diverged_meta(meta: _Meta, reason: FilterReason) -> _Meta:
        return replace(meta, health=FilterHealth.DIVERGED, reason=reason)

    def _prediction_meta(self, previous: _Meta, tick: int) -> _Meta:
        if previous.health is FilterHealth.DIVERGED:
            return previous
        if previous.last_accepted_tick is None:
            return replace(
                previous,
                health=FilterHealth.DEGRADED,
                reason=FilterReason.PREDICTION_ONLY,
            )
        age_s = (tick - previous.last_accepted_tick) * self.config.command_period_s
        if age_s > self.config.degraded_after_prediction_only_s + 1e-12:
            return replace(
                previous,
                health=FilterHealth.DEGRADED,
                reason=FilterReason.PREDICTION_ONLY,
            )
        return replace(previous, health=FilterHealth.VALID, reason=FilterReason.NONE)

    def advance(self, acceleration_mps2: FloatArray, end_time_s: float) -> NavigationSnapshot:
        command = np.asarray(acceleration_mps2, dtype=np.float64)
        if command.shape != (2,) or not np.all(np.isfinite(command)):
            raise ValueError("filter command must be a finite two-vector")
        end_tick = self._time_to_tick(end_time_s)
        if end_tick != self._current_tick + 1:
            raise ValueError("filter advances exactly one command period at a time")
        previous = self._nodes[self._current_tick]
        self._controls[self._current_tick] = np.array(command, copy=True)
        prior_meta = self._prediction_meta(previous.posterior_meta, end_tick)
        try:
            if prior_meta.health is FilterHealth.DIVERGED:
                raise _Divergence(prior_meta.reason)
            mean = self.transition @ previous.posterior_mean + self.command_map @ command
            covariance = (
                self.transition @ previous.posterior_covariance @ self.transition.T
                + self.process_covariance
            )
            mean, covariance = self._validate_mean_covariance(mean, covariance)
        except _Divergence as exc:
            mean = previous.posterior_mean.copy()
            covariance = previous.posterior_covariance.copy()
            prior_meta = self._diverged_meta(prior_meta, exc.reason)
        self._nodes[end_tick] = _Node(
            end_tick,
            mean.copy(),
            covariance.copy(),
            prior_meta,
            [],
            mean.copy(),
            covariance.copy(),
            prior_meta,
            [],
        )
        self._current_tick = end_tick
        return self.snapshot()

    def _mark_invalid(
        self,
        packet: PlanarNavigationPacket,
        disposition: PacketDisposition,
    ) -> UpdateDiagnostic:
        node = self._nodes[self._current_tick]
        if node.posterior_meta.health is not FilterHealth.DIVERGED:
            node.posterior_meta = replace(
                node.posterior_meta,
                health=FilterHealth.DEGRADED,
                reason=(
                    FilterReason.STALE_OR_DUPLICATE_PACKET
                    if disposition in {PacketDisposition.TOO_OLD, PacketDisposition.DUPLICATE}
                    else FilterReason.INVALID_PACKET
                ),
                invalid_packets=node.posterior_meta.invalid_packets + 1,
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

    def ingest(self, packet: PlanarNavigationPacket) -> UpdateDiagnostic:
        current = self._nodes[self._current_tick]
        if current.posterior_meta.health is FilterHealth.DIVERGED:
            return self._mark_invalid(packet, PacketDisposition.FILTER_DIVERGED)
        try:
            receipt_tick = self._time_to_tick(packet.received_at_s)
            measured_tick = self._time_to_tick(packet.measured_at_s)
        except ValueError:
            return self._mark_invalid(packet, PacketDisposition.INVALID)
        if receipt_tick != self._current_tick:
            return self._mark_invalid(packet, PacketDisposition.INVALID)
        if packet.sequence_id in self._seen_sequences:
            return self._mark_invalid(packet, PacketDisposition.DUPLICATE)
        if measured_tick > self._current_tick:
            return self._mark_invalid(packet, PacketDisposition.FUTURE_MEASUREMENT)
        lag_s = (self._current_tick - measured_tick) * self.config.command_period_s
        if lag_s > self.config.maximum_packet_lag_s + 1e-12:
            return self._mark_invalid(packet, PacketDisposition.TOO_OLD)
        if measured_tick not in self._nodes:
            return self._mark_invalid(packet, PacketDisposition.INVALID)
        self._nodes[measured_tick].packets.append(packet)
        self._seen_sequences.add(packet.sequence_id)
        self._replay_from(measured_tick)
        diagnostic = next(
            item
            for item in self._nodes[measured_tick].diagnostics
            if item.sequence_id == packet.sequence_id
        )
        self._last_diagnostic = diagnostic
        return diagnostic

    def _update(
        self,
        mean: FloatArray,
        covariance: FloatArray,
        meta: _Meta,
        packet: PlanarNavigationPacket,
        measured_tick: int,
    ) -> tuple[FloatArray, FloatArray, _Meta, UpdateDiagnostic]:
        innovation = packet.measurement - mean
        innovation_covariance = covariance + packet.reported_covariance
        try:
            condition = float(np.linalg.cond(innovation_covariance))
            if not np.isfinite(condition) or condition > self.config.innovation_condition_limit:
                raise _Divergence(FilterReason.INNOVATION_CONDITION_LIMIT)
            solved = np.linalg.solve(innovation_covariance, innovation)
            nis = float(innovation @ solved)
            if not np.isfinite(nis):
                raise _Divergence(FilterReason.NONFINITE_NUMERICS)
        except np.linalg.LinAlgError as exc:
            raise _Divergence(FilterReason.INNOVATION_CONDITION_LIMIT) from exc
        innovation_tuple = tuple(float(value) for value in innovation)
        if nis > self.config.nis_reject_threshold:
            rejected = replace(
                meta,
                health=FilterHealth.DEGRADED,
                reason=FilterReason.INNOVATION_REJECTED,
                consecutive_rejections=meta.consecutive_rejections + 1,
                innovation_rejections=meta.innovation_rejections + 1,
                last_nis=nis,
            )
            return mean, covariance, rejected, UpdateDiagnostic(
                packet.sequence_id,
                packet.measured_at_s,
                packet.received_at_s,
                PacketDisposition.INNOVATION_REJECTED,
                nis,
                innovation_tuple,
            )
        gain = np.linalg.solve(innovation_covariance, covariance).T
        updated_mean = mean + gain @ innovation
        residual = np.eye(4, dtype=np.float64) - gain
        updated_covariance = (
            residual @ covariance @ residual.T
            + gain @ packet.reported_covariance @ gain.T
        )
        updated_mean, updated_covariance = self._validate_mean_covariance(
            updated_mean,
            updated_covariance,
        )
        updated_meta = replace(
            meta,
            health=FilterHealth.VALID,
            reason=FilterReason.NONE,
            last_accepted_tick=measured_tick,
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

    def _replay_from(self, start_tick: int) -> None:
        for tick in range(start_tick, self._current_tick + 1):
            node = self._nodes[tick]
            if tick > start_tick:
                previous = self._nodes[tick - 1]
                command = self._controls[tick - 1]
                node.prior_meta = self._prediction_meta(previous.posterior_meta, tick)
                if node.prior_meta.health is FilterHealth.DIVERGED:
                    node.prior_mean = previous.posterior_mean.copy()
                    node.prior_covariance = previous.posterior_covariance.copy()
                else:
                    try:
                        node.prior_mean = (
                            self.transition @ previous.posterior_mean
                            + self.command_map @ command
                        )
                        node.prior_covariance = (
                            self.transition
                            @ previous.posterior_covariance
                            @ self.transition.T
                            + self.process_covariance
                        )
                        node.prior_mean, node.prior_covariance = (
                            self._validate_mean_covariance(
                                node.prior_mean,
                                node.prior_covariance,
                            )
                        )
                    except _Divergence as exc:
                        node.prior_mean = previous.posterior_mean.copy()
                        node.prior_covariance = previous.posterior_covariance.copy()
                        node.prior_meta = self._diverged_meta(node.prior_meta, exc.reason)
            mean = node.prior_mean.copy()
            covariance = node.prior_covariance.copy()
            meta = node.prior_meta
            diagnostics: list[UpdateDiagnostic] = []
            for packet in sorted(node.packets, key=lambda item: item.sequence_id):
                if meta.health is FilterHealth.DIVERGED:
                    diagnostic = UpdateDiagnostic(
                        packet.sequence_id,
                        packet.measured_at_s,
                        packet.received_at_s,
                        PacketDisposition.FILTER_DIVERGED,
                        None,
                        None,
                    )
                else:
                    try:
                        mean, covariance, meta, diagnostic = self._update(
                            mean,
                            covariance,
                            meta,
                            packet,
                            tick,
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
        node = self._nodes[self._current_tick]
        meta = node.posterior_meta
        last_time = (
            None
            if meta.last_accepted_tick is None
            else meta.last_accepted_tick * self.config.command_period_s
        )
        age = None if last_time is None else self.current_time_s - last_time
        return NavigationSnapshot(
            time_s=self.current_time_s,
            mean=node.posterior_mean.copy(),
            covariance=node.posterior_covariance.copy(),
            health=meta.health,
            reason=meta.reason,
            last_accepted_measurement_time_s=last_time,
            prediction_only_age_s=age,
            consecutive_innovation_rejections=meta.consecutive_rejections,
            accepted_updates=meta.accepted_updates,
            innovation_rejections=meta.innovation_rejections,
            invalid_packets=meta.invalid_packets,
            last_nis=meta.last_nis,
        )
