from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from enum import StrEnum
from numbers import Real
from pathlib import Path
from typing import Any

from .errors import FaultSpecError, FaultSuiteLoadError, UnsupportedFaultError

SCHEMA_VERSION = "kri-fault-suite/1.0"
RUNTIME_PROFILE = "simplified-rpo-v1"
MAX_CASES = 128
MAX_FAULTS_PER_CASE = 32
PROFILE_MAX_STEPS = 500
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_RESERVED_UNSUPPORTED = {"controller_internal", "model_seu", "model_upset"}


def _checked_identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise FaultSpecError(f"{path} must match [a-z0-9][a-z0-9._-]{{0,63}}")
    return value


def _checked_description(value: object, path: str) -> str:
    if not isinstance(value, str) or len(value) > 500:
        raise FaultSpecError(f"{path} must be a string of at most 500 characters")
    if any(ord(character) < 32 and character not in "\n\t" for character in value):
        raise FaultSpecError(f"{path} contains unsupported control characters")
    return value


def _checked_real(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise FaultSpecError(f"{path} must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise FaultSpecError(f"{path} must be finite")
    return result


class FaultKind(StrEnum):
    OBSERVED_RANGE_BIAS = "observed_range_bias"
    NAVIGATION_DROPOUT = "navigation_dropout"
    ACTUATOR_EFFECTIVENESS = "actuator_effectiveness"


@dataclass(frozen=True, slots=True)
class ActivationWindow:
    """Inclusive command-step activation window."""

    start_step: int
    end_step: int

    def __post_init__(self) -> None:
        if type(self.start_step) is not int or self.start_step < 0:
            raise FaultSpecError("activation.start_step must be a non-negative integer")
        if type(self.end_step) is not int or self.end_step < self.start_step:
            raise FaultSpecError(
                "activation.end_step must be an integer greater than or equal to start_step"
            )
        if self.end_step >= PROFILE_MAX_STEPS:
            raise FaultSpecError(
                f"activation.end_step must be below {PROFILE_MAX_STEPS} for {RUNTIME_PROFILE}"
            )

    def active(self, step: int) -> bool:
        return self.start_step <= step <= self.end_step

    def to_dict(self) -> dict[str, int]:
        return {"start_step": self.start_step, "end_step": self.end_step}


@dataclass(frozen=True, slots=True)
class ObservedRangeBiasFault:
    fault_id: str
    activation: ActivationWindow
    bias_m: float
    sensor_quality: float
    kind: FaultKind = FaultKind.OBSERVED_RANGE_BIAS

    def __post_init__(self) -> None:
        _checked_identifier(self.fault_id, "fault_id")
        if type(self.activation) is not ActivationWindow:
            raise FaultSpecError("fault activation must be an ActivationWindow")
        bias = _checked_real(self.bias_m, "bias_m")
        quality = _checked_real(self.sensor_quality, "sensor_quality")
        if abs(bias) > 1_000_000.0:
            raise FaultSpecError("bias_m must be within [-1000000, 1000000]")
        if not 0.0 <= quality <= 1.0:
            raise FaultSpecError("sensor_quality must be in [0, 1]")
        if self.kind is not FaultKind.OBSERVED_RANGE_BIAS:
            raise FaultSpecError("observed range bias kind is fixed")
        object.__setattr__(self, "bias_m", bias)
        object.__setattr__(self, "sensor_quality", quality)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.fault_id,
            "type": self.kind.value,
            "activation": self.activation.to_dict(),
            "bias": {"value": self.bias_m, "unit": "m"},
            "sensor_quality": {"value": self.sensor_quality, "unit": "ratio"},
        }


@dataclass(frozen=True, slots=True)
class NavigationDropoutFault:
    fault_id: str
    activation: ActivationWindow
    kind: FaultKind = FaultKind.NAVIGATION_DROPOUT

    def __post_init__(self) -> None:
        _checked_identifier(self.fault_id, "fault_id")
        if type(self.activation) is not ActivationWindow:
            raise FaultSpecError("fault activation must be an ActivationWindow")
        if self.kind is not FaultKind.NAVIGATION_DROPOUT:
            raise FaultSpecError("navigation dropout kind is fixed")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.fault_id,
            "type": self.kind.value,
            "activation": self.activation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ActuatorEffectivenessFault:
    fault_id: str
    activation: ActivationWindow
    effectiveness: float
    kind: FaultKind = FaultKind.ACTUATOR_EFFECTIVENESS

    def __post_init__(self) -> None:
        _checked_identifier(self.fault_id, "fault_id")
        if type(self.activation) is not ActivationWindow:
            raise FaultSpecError("fault activation must be an ActivationWindow")
        effectiveness = _checked_real(self.effectiveness, "effectiveness")
        if not 0.0 <= effectiveness <= 1.0:
            raise FaultSpecError("effectiveness must be in [0, 1]")
        if self.kind is not FaultKind.ACTUATOR_EFFECTIVENESS:
            raise FaultSpecError("actuator effectiveness kind is fixed")
        object.__setattr__(self, "effectiveness", effectiveness)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.fault_id,
            "type": self.kind.value,
            "activation": self.activation.to_dict(),
            "effectiveness": {"value": self.effectiveness, "unit": "ratio"},
        }


FaultSpec = ObservedRangeBiasFault | NavigationDropoutFault | ActuatorEffectivenessFault


@dataclass(frozen=True, slots=True)
class InitialStateSpec:
    range_m: float
    relative_velocity_mps: float
    propellant_fraction: float

    def __post_init__(self) -> None:
        range_m = _checked_real(self.range_m, "initial_state.range_m")
        velocity = _checked_real(
            self.relative_velocity_mps, "initial_state.relative_velocity_mps"
        )
        propellant = _checked_real(
            self.propellant_fraction, "initial_state.propellant_fraction"
        )
        if not 0.0 <= range_m <= 1_000_000_000.0:
            raise FaultSpecError("initial_state.range_m must be in [0, 1000000000]")
        if abs(velocity) > 10_000.0:
            raise FaultSpecError(
                "initial_state.relative_velocity_mps must be within [-10000, 10000]"
            )
        if not 0.0 <= propellant <= 1.0:
            raise FaultSpecError("initial_state.propellant_fraction must be in [0, 1]")
        object.__setattr__(self, "range_m", range_m)
        object.__setattr__(self, "relative_velocity_mps", velocity)
        object.__setattr__(self, "propellant_fraction", propellant)

    def to_dict(self) -> dict[str, object]:
        return {
            "range": {"value": self.range_m, "unit": "m"},
            "relative_velocity": {
                "value": self.relative_velocity_mps,
                "unit": "m/s",
            },
            "propellant_fraction": {
                "value": self.propellant_fraction,
                "unit": "ratio",
            },
        }


@dataclass(frozen=True, slots=True)
class FaultCase:
    case_id: str
    description: str
    faults: tuple[FaultSpec, ...]

    def __post_init__(self) -> None:
        _checked_identifier(self.case_id, "case_id")
        _checked_description(self.description, "case description")
        if type(self.faults) is not tuple:
            raise FaultSpecError("case faults must be a tuple")
        if len(self.faults) > MAX_FAULTS_PER_CASE:
            raise FaultSpecError(
                f"case faults must contain at most {MAX_FAULTS_PER_CASE} faults"
            )
        allowed = (
            ObservedRangeBiasFault,
            NavigationDropoutFault,
            ActuatorEffectivenessFault,
        )
        if any(type(fault) not in allowed for fault in self.faults):
            raise FaultSpecError("case contains an invalid fault specification")
        fault_ids = [fault.fault_id for fault in self.faults]
        if len(fault_ids) != len(set(fault_ids)):
            raise FaultSpecError("case contains duplicate fault ids")

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.case_id,
            "description": self.description,
            "faults": [fault.to_dict() for fault in self.faults],
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True, slots=True)
class FaultSuite:
    suite_id: str
    description: str
    initial_state: InitialStateSpec
    cases: tuple[FaultCase, ...]
    schema_version: str = SCHEMA_VERSION
    runtime_profile: str = RUNTIME_PROFILE

    def __post_init__(self) -> None:
        _checked_identifier(self.suite_id, "suite_id")
        _checked_description(self.description, "suite description")
        if type(self.initial_state) is not InitialStateSpec:
            raise FaultSpecError("initial_state must be an InitialStateSpec")
        if type(self.cases) is not tuple or not self.cases:
            raise FaultSpecError("cases must be a non-empty tuple")
        if len(self.cases) > MAX_CASES:
            raise FaultSpecError(f"cases must contain at most {MAX_CASES} cases")
        if any(type(case) is not FaultCase for case in self.cases):
            raise FaultSpecError("cases contains an invalid case")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise FaultSpecError("cases contains duplicate case ids")
        if self.schema_version != SCHEMA_VERSION:
            raise FaultSpecError(f"schema_version must be {SCHEMA_VERSION!r}")
        if self.runtime_profile != RUNTIME_PROFILE:
            raise FaultSpecError(f"runtime_profile must be {RUNTIME_PROFILE!r}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "description": self.description,
            "runtime_profile": self.runtime_profile,
            "initial_state": self.initial_state.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
        }

    @property
    def sha256(self) -> str:
        return _sha256(self.to_dict())


def canonical_json(data: object) -> bytes:
    """Return the canonical UTF-8 representation used for public identities."""

    try:
        text = json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FaultSpecError(f"value is not canonically serializable: {exc}") from exc
    return text.encode("utf-8")


def _sha256(data: object) -> str:
    return hashlib.sha256(canonical_json(data)).hexdigest()


def _mapping(
    value: object,
    path: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise FaultSpecError(f"{path} must be an object")
    result: dict[str, Any] = value
    if any(not isinstance(key, str) for key in result):
        raise FaultSpecError(f"{path} keys must be strings")
    allowed = required | (optional or set())
    missing = sorted(required - result.keys())
    extra = sorted(result.keys() - allowed)
    if missing:
        raise FaultSpecError(f"{path} is missing required keys: {', '.join(missing)}")
    if extra:
        raise FaultSpecError(f"{path} contains unknown keys: {', '.join(extra)}")
    return result


def _array(value: object, path: str) -> list[Any]:
    if type(value) is not list:
        raise FaultSpecError(f"{path} must be an array")
    return value


def _identifier(value: object, path: str) -> str:
    return _checked_identifier(value, path)


def _description(value: object, path: str) -> str:
    return _checked_description(value, path)


def _finite_real(value: object, path: str) -> float:
    return _checked_real(value, path)


def _quantity(value: object, path: str, unit: str) -> float:
    data = _mapping(value, path, required={"value", "unit"})
    if data["unit"] != unit:
        raise FaultSpecError(f"{path}.unit must be {unit!r}")
    return _finite_real(data["value"], f"{path}.value")


def _activation(value: object, path: str) -> ActivationWindow:
    data = _mapping(value, path, required={"start_step", "end_step"})
    return ActivationWindow(data["start_step"], data["end_step"])


def _fault(value: object, path: str) -> FaultSpec:
    base = _mapping(
        value,
        path,
        required={"id", "type", "activation"},
        optional={"bias", "sensor_quality", "effectiveness"},
    )
    fault_id = _identifier(base["id"], f"{path}.id")
    kind_value = base["type"]
    if not isinstance(kind_value, str):
        raise FaultSpecError(f"{path}.type must be a string")
    if kind_value in _RESERVED_UNSUPPORTED:
        raise UnsupportedFaultError(
            f"{path}.type {kind_value!r} is unsupported: generic external-controller "
            "internal corruption is not part of this milestone"
        )
    try:
        kind = FaultKind(kind_value)
    except ValueError as exc:
        raise UnsupportedFaultError(f"{path}.type {kind_value!r} is unsupported") from exc
    activation = _activation(base["activation"], f"{path}.activation")

    if kind is FaultKind.OBSERVED_RANGE_BIAS:
        expected = {"id", "type", "activation", "bias", "sensor_quality"}
        _mapping(value, path, required=expected)
        bias = _quantity(base["bias"], f"{path}.bias", "m")
        if abs(bias) > 1_000_000.0:
            raise FaultSpecError(f"{path}.bias.value must be within [-1000000, 1000000]")
        quality = _quantity(base["sensor_quality"], f"{path}.sensor_quality", "ratio")
        if not 0.0 <= quality <= 1.0:
            raise FaultSpecError(f"{path}.sensor_quality.value must be in [0, 1]")
        return ObservedRangeBiasFault(fault_id, activation, bias, quality)

    if kind is FaultKind.NAVIGATION_DROPOUT:
        _mapping(value, path, required={"id", "type", "activation"})
        return NavigationDropoutFault(fault_id, activation)

    _mapping(value, path, required={"id", "type", "activation", "effectiveness"})
    effectiveness = _quantity(base["effectiveness"], f"{path}.effectiveness", "ratio")
    if not 0.0 <= effectiveness <= 1.0:
        raise FaultSpecError(f"{path}.effectiveness.value must be in [0, 1]")
    return ActuatorEffectivenessFault(fault_id, activation, effectiveness)


def _initial_state(value: object) -> InitialStateSpec:
    data = _mapping(
        value,
        "initial_state",
        required={"range", "relative_velocity", "propellant_fraction"},
    )
    range_m = _quantity(data["range"], "initial_state.range", "m")
    velocity = _quantity(
        data["relative_velocity"], "initial_state.relative_velocity", "m/s"
    )
    propellant = _quantity(
        data["propellant_fraction"], "initial_state.propellant_fraction", "ratio"
    )
    if not 0.0 <= range_m <= 1_000_000_000.0:
        raise FaultSpecError("initial_state.range.value must be in [0, 1000000000]")
    if abs(velocity) > 10_000.0:
        raise FaultSpecError(
            "initial_state.relative_velocity.value must be within [-10000, 10000]"
        )
    if not 0.0 <= propellant <= 1.0:
        raise FaultSpecError("initial_state.propellant_fraction.value must be in [0, 1]")
    return InitialStateSpec(range_m, velocity, propellant)


def fault_suite_from_dict(value: object) -> FaultSuite:
    """Validate a decoded JSON value and build an immutable versioned suite."""

    data = _mapping(
        value,
        "suite",
        required={
            "schema_version",
            "suite_id",
            "description",
            "runtime_profile",
            "initial_state",
            "cases",
        },
    )
    if data["schema_version"] != SCHEMA_VERSION:
        raise FaultSpecError(f"schema_version must be {SCHEMA_VERSION!r}")
    if data["runtime_profile"] != RUNTIME_PROFILE:
        raise FaultSpecError(f"runtime_profile must be {RUNTIME_PROFILE!r}")
    suite_id = _identifier(data["suite_id"], "suite_id")
    description = _description(data["description"], "description")
    initial_state = _initial_state(data["initial_state"])
    raw_cases = _array(data["cases"], "cases")
    if not raw_cases:
        raise FaultSpecError("cases must contain at least one case")
    if len(raw_cases) > MAX_CASES:
        raise FaultSpecError(f"cases must contain at most {MAX_CASES} cases")

    cases: list[FaultCase] = []
    seen_cases: set[str] = set()
    for case_index, raw_case in enumerate(raw_cases):
        case_path = f"cases[{case_index}]"
        case_data = _mapping(
            raw_case,
            case_path,
            required={"id", "description", "faults"},
        )
        case_id = _identifier(case_data["id"], f"{case_path}.id")
        if case_id in seen_cases:
            raise FaultSpecError(f"duplicate case id: {case_id}")
        seen_cases.add(case_id)
        case_description = _description(
            case_data["description"], f"{case_path}.description"
        )
        raw_faults = _array(case_data["faults"], f"{case_path}.faults")
        if len(raw_faults) > MAX_FAULTS_PER_CASE:
            raise FaultSpecError(
                f"{case_path}.faults must contain at most {MAX_FAULTS_PER_CASE} faults"
            )
        faults: list[FaultSpec] = []
        seen_faults: set[str] = set()
        for fault_index, raw_fault in enumerate(raw_faults):
            fault = _fault(raw_fault, f"{case_path}.faults[{fault_index}]")
            if fault.fault_id in seen_faults:
                raise FaultSpecError(
                    f"{case_path}.faults contains duplicate fault id: {fault.fault_id}"
                )
            seen_faults.add(fault.fault_id)
            faults.append(fault)
        cases.append(FaultCase(case_id, case_description, tuple(faults)))

    return FaultSuite(
        suite_id=suite_id,
        description=description,
        initial_state=initial_state,
        cases=tuple(cases),
    )


class _DuplicateKeyError(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not permitted: {value}")


def loads_fault_suite(payload: str) -> FaultSuite:
    """Decode strict JSON, rejecting duplicate keys and non-finite constants."""

    if not isinstance(payload, str):
        raise FaultSuiteLoadError("suite payload must be text")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (json.JSONDecodeError, _DuplicateKeyError, ValueError) as exc:
        raise FaultSuiteLoadError(f"invalid fault-suite JSON: {exc}") from exc
    return fault_suite_from_dict(value)


def load_fault_suite(path: str | Path) -> FaultSuite:
    """Load a suite without including its local path in the suite identity."""

    source = Path(path)
    try:
        payload = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise FaultSuiteLoadError(f"could not read fault suite: {exc}") from exc
    return loads_fault_suite(payload)


def validate_fault_suite(path: str | Path) -> dict[str, object]:
    suite = load_fault_suite(path)
    return {
        "passed": True,
        "schema_version": suite.schema_version,
        "runtime_profile": suite.runtime_profile,
        "suite_id": suite.suite_id,
        "suite_sha256": suite.sha256,
        "case_count": len(suite.cases),
        "cases": [
            {
                "case_id": case.case_id,
                "case_sha256": case.sha256,
                "fault_count": len(case.faults),
                "fault_types": [fault.kind.value for fault in case.faults],
            }
            for case in suite.cases
        ],
        "composition": "fault array order; inclusive activation windows",
    }
