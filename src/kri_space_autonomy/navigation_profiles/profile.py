from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import kri_space_autonomy.experiment_002.config as frozen_production_config_module
import kri_space_autonomy.experiment_003.config as frozen_config_module
import kri_space_autonomy.experiment_003.estimator as frozen_estimator_module
import kri_space_autonomy.experiment_003.interfaces as frozen_interfaces_module
import kri_space_autonomy.experiment_003.measurements as frozen_measurements_module
import kri_space_autonomy.experiment_003.model as frozen_model_module
from kri_space_autonomy.controller_adapter.contract import (
    ControllerContext,
    ControllerObservation,
    ObservationStatus,
)
from kri_space_autonomy.experiment_003.config import Experiment003Config, load_config
from kri_space_autonomy.experiment_003.estimator import (
    FilterHealth,
    FilterReason,
    NavigationFilter,
    NavigationSnapshot,
    PacketDisposition,
)
from kri_space_autonomy.experiment_003.interfaces import policy_observation
from kri_space_autonomy.experiment_003.measurements import (
    MeasurementFault,
    navigation_packet,
)
from kri_space_autonomy.types import Observation

from .fault_plan import PacketFaultKind, PacketFaultSpec

NAVIGATION_PROFILE_SCHEMA_VERSION = "kri-navigation-profile/1.0"
DIRECT_PROFILE = "direct"
ESTIMATED_PROFILE = "estimated"
FOUNDATION_FREEZE_ID = "d032ed6b22ff3bb74bc5b03caf2b287a8310b16eb8d76665020a66d98eab2297"
FOUNDATION_MANIFEST_SHA256 = (
    "683a15f1b88a428607fb564b454ea519122607821eafe2206f388a7fd0ce6cba"
)
ESTIMATOR_CLASS_ID = "kri_space_autonomy.experiment_003.estimator.NavigationFilter"
MEASUREMENT_FACTORY_ID = (
    "kri_space_autonomy.experiment_003.measurements.navigation_packet"
)
BRIDGE_RUNTIME_PROFILE = "simplified-rpo-v1"
BRIDGE_MODEL_BOUNDARY = (
    "Frozen Experiment 003 first-order-actuator/process model applied without retuning "
    "to the product harness instantaneous-actuation plant; requested controller commands "
    "feed prediction and product observations feed measurement updates."
)
EXPECTED_FROZEN_FILE_SHA256 = {
    "experiments/002/config.json": (
        "05f65a0fdf2695b00df076bb3b23b38f87d9623da10c9fb17f4616c61cd2f0fe"
    ),
    "experiments/003/config.json": (
        "e83f59a5c3c86defab150285b1dc30d170b08f82c8f949a348944efe5963b4c9"
    ),
    "src/kri_space_autonomy/experiment_002/config.py": (
        "e8037c84ff45885f1010761a59fed185e8796f505aed68db6cccd59453f536d9"
    ),
    "src/kri_space_autonomy/experiment_003/config.py": (
        "01f69c04da4e2959c1c5397c737e3ae49f905a3e5ed81433f88860c009689503"
    ),
    "src/kri_space_autonomy/experiment_003/estimator.py": (
        "3502d00eef9a4a34417775ca1e20fc609a2726797c7a30ddb564d5fc58a3d481"
    ),
    "src/kri_space_autonomy/experiment_003/interfaces.py": (
        "06a0af5e1538dd139908ecdbd26d7efaade58e3b862dfba6e136a3a283320b10"
    ),
    "src/kri_space_autonomy/experiment_003/measurements.py": (
        "57573a90e559b9a74e4dd02fb7b2e783ee5d245eaddf59b1e204f1cff404d386"
    ),
    "src/kri_space_autonomy/experiment_003/model.py": (
        "073ae8eff0b14bee4d9bcc99f14c6a526521925549ffe8ac2dc44341b1420a48"
    ),
}
_FROZEN_CONFIG_PATH = Path("experiments/003/config.json")
_PRODUCTION_CONFIG_PATH = Path("experiments/002/config.json")
_FOUNDATION_MANIFEST_PATH = Path("experiments/003/freeze-manifest.json")
_FROZEN_SOURCE_PATHS = (
    _FROZEN_CONFIG_PATH,
    _PRODUCTION_CONFIG_PATH,
    Path("src/kri_space_autonomy/experiment_002/config.py"),
    Path("src/kri_space_autonomy/experiment_003/config.py"),
    Path("src/kri_space_autonomy/experiment_003/estimator.py"),
    Path("src/kri_space_autonomy/experiment_003/interfaces.py"),
    Path("src/kri_space_autonomy/experiment_003/measurements.py"),
    Path("src/kri_space_autonomy/experiment_003/model.py"),
)
_LOADED_SOURCE_MODULES = {
    Path("src/kri_space_autonomy/experiment_002/config.py"): (
        frozen_production_config_module
    ),
    Path("src/kri_space_autonomy/experiment_003/config.py"): frozen_config_module,
    Path("src/kri_space_autonomy/experiment_003/estimator.py"): frozen_estimator_module,
    Path("src/kri_space_autonomy/experiment_003/interfaces.py"): frozen_interfaces_module,
    Path("src/kri_space_autonomy/experiment_003/measurements.py"): (
        frozen_measurements_module
    ),
    Path("src/kri_space_autonomy/experiment_003/model.py"): frozen_model_module,
}


class NavigationProfileError(ValueError):
    """Raised when a product navigation profile cannot fail closed safely."""


class NavigationProfileName(StrEnum):
    DIRECT = DIRECT_PROFILE
    ESTIMATED = ESTIMATED_PROFILE


@dataclass(frozen=True, slots=True)
class NavigationProfileIdentity:
    profile: NavigationProfileName
    foundation_freeze_id: str
    freeze_manifest_sha256: str
    frozen_file_sha256: dict[str, str]
    estimator_class: str
    measurement_factory: str
    bridge_runtime_profile: str
    bridge_model_boundary: str
    schema_version: str = NAVIGATION_PROFILE_SCHEMA_VERSION

    def unsigned_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile": self.profile.value,
            "foundation_freeze_id": self.foundation_freeze_id,
            "freeze_manifest_sha256": self.freeze_manifest_sha256,
            "frozen_file_sha256": dict(sorted(self.frozen_file_sha256.items())),
            "estimator_class": self.estimator_class,
            "measurement_factory": self.measurement_factory,
            "bridge_runtime_profile": self.bridge_runtime_profile,
            "bridge_model_boundary": self.bridge_model_boundary,
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(_canonical_json(self.unsigned_dict())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {**self.unsigned_dict(), "identity_sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class NavigationDiagnostics:
    profile: NavigationProfileName
    identity_sha256: str
    raw_observation_status_counts: dict[str, int]
    controller_observation_status_counts: dict[str, int]
    estimator_health_counts: dict[str, int]
    estimator_reason_counts: dict[str, int]
    packet_disposition_counts: dict[str, int]
    missing_packet_steps: int
    final_health: str
    final_reason: str
    accepted_updates: int
    innovation_rejections: int
    invalid_packets: int
    final_prediction_only_age_s: float | None
    navigation_trace_sha256: str
    packet_fault: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile.value,
            "identity_sha256": self.identity_sha256,
            "raw_observation_status_counts": dict(self.raw_observation_status_counts),
            "controller_observation_status_counts": dict(
                self.controller_observation_status_counts
            ),
            "estimator_health_counts": dict(self.estimator_health_counts),
            "estimator_reason_counts": dict(self.estimator_reason_counts),
            "packet_disposition_counts": dict(self.packet_disposition_counts),
            "missing_packet_steps": self.missing_packet_steps,
            "final_health": self.final_health,
            "final_reason": self.final_reason,
            "accepted_updates": self.accepted_updates,
            "innovation_rejections": self.innovation_rejections,
            "invalid_packets": self.invalid_packets,
            "final_prediction_only_age_s": self.final_prediction_only_age_s,
            "navigation_trace_sha256": self.navigation_trace_sha256,
            "packet_fault": self.packet_fault,
        }


class NavigationProfile(Protocol):
    name: NavigationProfileName

    def reset(self, context: ControllerContext) -> None: ...

    def validate_initial_navigation(self, range_m: float, velocity_mps: float) -> None: ...

    def observe(
        self,
        observation: Observation,
        packet_fault: PacketFaultSpec | None = None,
    ) -> ControllerObservation: ...

    def accept_command(self, command_mps2: float) -> None: ...

    @property
    def identity(self) -> NavigationProfileIdentity | None: ...

    def diagnostics(self) -> NavigationDiagnostics | None: ...


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise NavigationProfileError(
            f"could not read frozen navigation asset {path.name}: {exc}"
        ) from exc


def _load_foundation_manifest(root: Path) -> tuple[dict[str, object], str]:
    path = root / _FOUNDATION_MANIFEST_PATH
    manifest_sha256 = _file_sha256(path)
    if manifest_sha256 != FOUNDATION_MANIFEST_SHA256:
        raise NavigationProfileError("Experiment 003 foundation manifest bytes changed")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NavigationProfileError(
            f"could not load frozen Experiment 003 foundation manifest: {exc}"
        ) from exc
    if type(manifest) is not dict or manifest.get("freeze_id") != FOUNDATION_FREEZE_ID:
        raise NavigationProfileError("Experiment 003 foundation freeze identity changed")
    unsigned = dict(manifest)
    unsigned.pop("freeze_id")
    if hashlib.sha256(_canonical_json(unsigned)).hexdigest() != FOUNDATION_FREEZE_ID:
        raise NavigationProfileError("Experiment 003 foundation self-hash is invalid")
    return manifest, manifest_sha256


def load_frozen_navigation_assets(
    repository_root: str | Path = ".",
) -> tuple[Experiment003Config, object, NavigationProfileIdentity]:
    """Load and verify the exact frozen Experiment 003 estimator assets read-only."""

    root = Path(repository_root)
    manifest, manifest_sha256 = _load_foundation_manifest(root)
    source_hashes = manifest.get("source_file_hashes")
    historical_hashes = manifest.get("historical_evidence_hashes")
    if type(source_hashes) is not dict or type(historical_hashes) is not dict:
        raise NavigationProfileError("foundation manifest is missing frozen source hashes")
    verified: dict[str, str] = {}
    for relative in _FROZEN_SOURCE_PATHS:
        name = relative.as_posix()
        pinned = EXPECTED_FROZEN_FILE_SHA256[name]
        expected = source_hashes.get(name, historical_hashes.get(name))
        if expected != pinned:
            raise NavigationProfileError(f"foundation manifest binding changed: {name}")
        expected_path = (root / relative).resolve()
        observed = _file_sha256(expected_path)
        if observed != pinned:
            raise NavigationProfileError(f"frozen navigation asset hash mismatch: {name}")
        module = _LOADED_SOURCE_MODULES.get(relative)
        if module is not None:
            loaded_name = getattr(module, "__file__", None)
            if not isinstance(loaded_name, str):
                raise NavigationProfileError(f"loaded navigation module has no source: {name}")
            loaded_path = Path(loaded_name).resolve()
            if loaded_path != expected_path:
                raise NavigationProfileError(
                    f"loaded navigation module is not the verified source: {name}"
                )
            if _file_sha256(loaded_path) != pinned:
                raise NavigationProfileError(
                    f"loaded navigation module hash mismatch: {name}"
                )
        verified[name] = observed
    try:
        study, production = load_config(
            root / _FROZEN_CONFIG_PATH,
            root / _PRODUCTION_CONFIG_PATH,
        )
    except (OSError, TypeError, ValueError) as exc:
        raise NavigationProfileError(
            f"frozen navigation configuration failed validation: {exc}"
        ) from exc
    identity = NavigationProfileIdentity(
        profile=NavigationProfileName.ESTIMATED,
        foundation_freeze_id=FOUNDATION_FREEZE_ID,
        freeze_manifest_sha256=manifest_sha256,
        frozen_file_sha256=verified,
        estimator_class=ESTIMATOR_CLASS_ID,
        measurement_factory=MEASUREMENT_FACTORY_ID,
        bridge_runtime_profile=BRIDGE_RUNTIME_PROFILE,
        bridge_model_boundary=BRIDGE_MODEL_BOUNDARY,
    )
    return study, production, identity


def _observation_status(observation: Observation) -> ObservationStatus:
    if observation.range_m is None or observation.relative_velocity_mps is None:
        return ObservationStatus.MISSING
    if observation.sensor_quality < 1.0:
        return ObservationStatus.DEGRADED
    return ObservationStatus.NOMINAL


def controller_observation_from_snapshot(
    snapshot: NavigationSnapshot,
    *,
    step: int,
    propellant_fraction: float,
    command_period_s: float,
) -> ControllerObservation:
    """Map frozen estimator health to the unchanged public controller observation."""

    time_s = step * command_period_s
    mapped = policy_observation(snapshot, propellant_fraction, time_s)
    return ControllerObservation(
        step=step,
        time_s=time_s,
        range_m=mapped.range_m,
        relative_velocity_mps=mapped.relative_velocity_mps,
        propellant_fraction=mapped.propellant,
        sensor_quality=mapped.sensor_quality,
    )


class DirectNavigationProfile:
    """Identity mapping that preserves the pre-existing direct product behavior."""

    name = NavigationProfileName.DIRECT

    def __init__(self) -> None:
        self._context: ControllerContext | None = None
        self._next_step = 0
        self._awaiting_command = False

    @property
    def identity(self) -> None:
        return None

    def reset(self, context: ControllerContext) -> None:
        if type(context) is not ControllerContext:
            raise NavigationProfileError("navigation reset context is invalid")
        self._context = context
        self._next_step = 0
        self._awaiting_command = False

    def validate_initial_navigation(self, range_m: float, velocity_mps: float) -> None:
        return None

    def observe(
        self,
        observation: Observation,
        packet_fault: PacketFaultSpec | None = None,
    ) -> ControllerObservation:
        if packet_fault is not None:
            raise NavigationProfileError(
                "packet faults require navigation_profile='estimated'"
            )
        if self._context is None or self._awaiting_command:
            raise NavigationProfileError("direct navigation lifecycle is out of sequence")
        if type(observation) is not Observation or observation.step != self._next_step:
            raise NavigationProfileError("direct navigation observation step is invalid")
        public = ControllerObservation(
            step=observation.step,
            time_s=observation.step * self._context.command_period_s,
            range_m=observation.range_m,
            relative_velocity_mps=observation.relative_velocity_mps,
            propellant_fraction=observation.propellant,
            sensor_quality=observation.sensor_quality,
        )
        self._awaiting_command = True
        return public

    def accept_command(self, command_mps2: float) -> None:
        if not self._awaiting_command or not math.isfinite(command_mps2):
            raise NavigationProfileError("direct navigation command lifecycle is invalid")
        self._next_step += 1
        self._awaiting_command = False

    def diagnostics(self) -> None:
        return None


class EstimatedNavigationProfile:
    """Thin product bridge around the frozen Experiment 003 primary filter."""

    name = NavigationProfileName.ESTIMATED

    def __init__(self, repository_root: str | Path = ".") -> None:
        self.study, self.production, self._identity = load_frozen_navigation_assets(
            repository_root
        )
        self._filter: NavigationFilter | None = None
        self._context: ControllerContext | None = None
        self._next_step = 0
        self._previous_requested_command: float | None = None
        self._awaiting_command = False
        self._previous_packet = None
        self._raw_counts = {status.value: 0 for status in ObservationStatus}
        self._controller_counts = {status.value: 0 for status in ObservationStatus}
        self._health_counts = {health.value: 0 for health in FilterHealth}
        self._reason_counts = {reason.value: 0 for reason in FilterReason}
        self._packet_counts = {
            **{disposition.value: 0 for disposition in PacketDisposition},
            "missing": 0,
        }
        self._trace: list[dict[str, object]] = []
        self._packet_fault: PacketFaultSpec | None = None

    @property
    def identity(self) -> NavigationProfileIdentity:
        return self._identity

    @property
    def frozen_filter(self) -> NavigationFilter:
        if self._filter is None:
            raise NavigationProfileError("estimated navigation has not been reset")
        return self._filter

    def reset(self, context: ControllerContext) -> None:
        if type(context) is not ControllerContext:
            raise NavigationProfileError("navigation reset context is invalid")
        if abs(context.command_period_s - self.production.command_period_s) > 1e-12:
            raise NavigationProfileError(
                "estimated navigation requires the frozen one-second command period"
            )
        if (
            context.minimum_acceleration_mps2 < -self.production.max_acceleration_mps2
            or context.maximum_acceleration_mps2 > self.production.max_acceleration_mps2
        ):
            raise NavigationProfileError(
                "controller acceleration bounds exceed the frozen estimator profile"
            )
        try:
            self._filter = NavigationFilter(self.study, self.production)
        except (ArithmeticError, RuntimeError, ValueError) as exc:
            raise NavigationProfileError(
                f"frozen navigation filter initialization failed: {exc}"
            ) from exc
        self._context = context
        self._next_step = 0
        self._previous_requested_command = None
        self._awaiting_command = False
        self._previous_packet = None
        self._raw_counts = {status.value: 0 for status in ObservationStatus}
        self._controller_counts = {status.value: 0 for status in ObservationStatus}
        self._health_counts = {health.value: 0 for health in FilterHealth}
        self._reason_counts = {reason.value: 0 for reason in FilterReason}
        self._packet_counts = {
            **{disposition.value: 0 for disposition in PacketDisposition},
            "missing": 0,
        }
        self._trace = []
        self._packet_fault = None

    def validate_initial_navigation(self, range_m: float, velocity_mps: float) -> None:
        values = (range_m, velocity_mps)
        if not all(math.isfinite(value) for value in values):
            raise NavigationProfileError("estimated initial navigation must be finite")
        limits = self.study.state_absolute_limits
        if abs(range_m) > limits[0] or abs(velocity_mps) > limits[1]:
            raise NavigationProfileError(
                "initial navigation exceeds the frozen estimator state limits"
            )

    def _measurement_fault(
        self, packet_fault: PacketFaultSpec | None, time_s: float
    ) -> MeasurementFault:
        if packet_fault is None or not packet_fault.activation.active(self._next_step):
            return MeasurementFault("product_nominal", "primary", None, None)
        onset = packet_fault.activation.start_step * self.production.command_period_s
        end = (packet_fault.activation.end_step + 1) * self.production.command_period_s
        if packet_fault.kind is PacketFaultKind.STALE_PACKET:
            return MeasurementFault("E3_primary_stale", "primary", onset, end)
        return MeasurementFault(
            "E4_primary_covariance_underreporting",
            "primary",
            onset,
            end,
            covariance_factor=self.study.covariance_underreporting_factor,
        )

    def _validate_observation(self, observation: Observation) -> None:
        if type(observation) is not Observation:
            raise NavigationProfileError("estimated navigation input must be an Observation")
        if observation.step != self._next_step:
            raise NavigationProfileError(
                f"estimated navigation observation step must be {self._next_step}"
            )
        for name, value in (
            ("propellant", observation.propellant),
            ("sensor_quality", observation.sensor_quality),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise NavigationProfileError(f"estimated navigation {name} must be in [0, 1]")
        missing = (observation.range_m is None, observation.relative_velocity_mps is None)
        if missing[0] != missing[1]:
            raise NavigationProfileError(
                "estimated navigation range and velocity must be present or missing together"
            )
        for name, value in (
            ("range_m", observation.range_m),
            ("relative_velocity_mps", observation.relative_velocity_mps),
        ):
            if value is not None and not math.isfinite(value):
                raise NavigationProfileError(f"estimated navigation {name} must be finite")

    def observe(
        self,
        observation: Observation,
        packet_fault: PacketFaultSpec | None = None,
    ) -> ControllerObservation:
        if self._filter is None or self._context is None or self._awaiting_command:
            raise NavigationProfileError("estimated navigation lifecycle is out of sequence")
        self._validate_observation(observation)
        if self._next_step > 0:
            if self._previous_requested_command is None:
                raise NavigationProfileError("estimated navigation is missing the prior command")
            try:
                self._filter.advance(
                    self._previous_requested_command,
                    self._next_step * self._context.command_period_s,
                )
            except (ArithmeticError, RuntimeError, ValueError) as exc:
                raise NavigationProfileError(
                    f"frozen estimator prediction failed closed: {exc}"
                ) from exc
        raw_status = _observation_status(observation)
        self._raw_counts[raw_status.value] += 1
        time_s = self._next_step * self._context.command_period_s
        disposition = "missing"
        if observation.range_m is not None and observation.relative_velocity_mps is not None:
            try:
                packet = navigation_packet(
                    sequence_id=self._next_step,
                    measured_at_s=time_s,
                    received_at_s=time_s,
                    range_value_m=observation.range_m,
                    velocity_value_mps=observation.relative_velocity_mps,
                    range_noise_m=0.0,
                    velocity_noise_mps=0.0,
                    range_quantization_m=self.production.range_quantization_m,
                    velocity_quantization_mps=self.production.velocity_quantization_mps,
                    nominal_covariance=self._filter.nominal_measurement_covariance,
                    channel="primary",
                    fault=self._measurement_fault(packet_fault, time_s),
                    previous_packet=self._previous_packet,
                )
            except (ArithmeticError, RuntimeError, ValueError) as exc:
                raise NavigationProfileError(
                    f"frozen navigation packet construction failed closed: {exc}"
                ) from exc
            if packet is not None:
                try:
                    diagnostic = self._filter.ingest(packet)
                except (ArithmeticError, RuntimeError, ValueError) as exc:
                    raise NavigationProfileError(
                        f"frozen estimator packet update failed closed: {exc}"
                    ) from exc
                disposition = diagnostic.disposition.value
                self._previous_packet = packet
        self._packet_counts[disposition] += 1
        snapshot = self._filter.snapshot()
        public = controller_observation_from_snapshot(
            snapshot,
            step=self._next_step,
            propellant_fraction=observation.propellant,
            command_period_s=self._context.command_period_s,
        )
        self._controller_counts[public.status.value] += 1
        self._health_counts[snapshot.health.value] += 1
        self._reason_counts[snapshot.reason.value] += 1
        self._trace.append(
            {
                "step": self._next_step,
                "raw_status": raw_status.value,
                "packet_disposition": disposition,
                "health": snapshot.health.value,
                "reason": snapshot.reason.value,
                "controller_status": public.status.value,
                "mean": snapshot.mean.tolist(),
                "covariance": snapshot.covariance.tolist(),
            }
        )
        if packet_fault is not None:
            if self._packet_fault is not None and self._packet_fault != packet_fault:
                raise NavigationProfileError("only one packet-fault spec is allowed per case")
            self._packet_fault = packet_fault
        self._awaiting_command = True
        return public

    def accept_command(self, command_mps2: float) -> None:
        if not self._awaiting_command:
            raise NavigationProfileError("estimated navigation command lifecycle is invalid")
        if not math.isfinite(command_mps2):
            raise NavigationProfileError("estimated navigation command must be finite")
        self._previous_requested_command = float(command_mps2)
        self._next_step += 1
        self._awaiting_command = False

    def diagnostics(self) -> NavigationDiagnostics:
        if self._filter is None:
            raise NavigationProfileError("estimated navigation has not been reset")
        snapshot = self._filter.snapshot()
        return NavigationDiagnostics(
            profile=self.name,
            identity_sha256=self.identity.sha256,
            raw_observation_status_counts=dict(self._raw_counts),
            controller_observation_status_counts=dict(self._controller_counts),
            estimator_health_counts=dict(self._health_counts),
            estimator_reason_counts=dict(self._reason_counts),
            packet_disposition_counts=dict(self._packet_counts),
            missing_packet_steps=self._packet_counts["missing"],
            final_health=snapshot.health.value,
            final_reason=snapshot.reason.value,
            accepted_updates=snapshot.accepted_updates,
            innovation_rejections=snapshot.innovation_rejections,
            invalid_packets=snapshot.invalid_packets,
            final_prediction_only_age_s=snapshot.prediction_only_age_s,
            navigation_trace_sha256=hashlib.sha256(_canonical_json(self._trace)).hexdigest(),
            packet_fault=(
                None if self._packet_fault is None else self._packet_fault.to_dict()
            ),
        )


def navigation_profile_name(value: str | NavigationProfileName) -> NavigationProfileName:
    if type(value) is NavigationProfileName:
        return value
    if not isinstance(value, str):
        raise NavigationProfileError("navigation profile must be direct or estimated")
    try:
        return NavigationProfileName(value)
    except ValueError as exc:
        raise NavigationProfileError("navigation profile must be direct or estimated") from exc


def build_navigation_profile(
    profile: str | NavigationProfileName = NavigationProfileName.DIRECT,
    *,
    repository_root: str | Path = ".",
) -> NavigationProfile:
    selected = navigation_profile_name(profile)
    if selected is NavigationProfileName.DIRECT:
        return DirectNavigationProfile()
    return EstimatedNavigationProfile(repository_root)
