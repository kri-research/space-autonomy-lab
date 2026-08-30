from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from numbers import Real
from pathlib import Path
from typing import Any

from kri_space_autonomy.controller_adapter import CONTRACT_VERSION, ControllerIdentity
from kri_space_autonomy.fault_suite import (
    ESTIMATED_RESULT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    FaultCaseResult,
    FaultSuite,
    FaultSuiteRunResult,
    canonical_json,
    fault_suite_from_dict,
    load_fault_suite,
    replay_fault_suite,
)
from kri_space_autonomy.navigation_profiles import (
    BRIDGE_MODEL_BOUNDARY,
    BRIDGE_RUNTIME_PROFILE,
    ESTIMATOR_CLASS_ID,
    EXPECTED_FROZEN_FILE_SHA256,
    FOUNDATION_FREEZE_ID,
    FOUNDATION_MANIFEST_SHA256,
    MEASUREMENT_FACTORY_ID,
    NAVIGATION_PROFILE_SCHEMA_VERSION,
    NavigationFaultPlanError,
    navigation_fault_plan_from_dict,
)

from .errors import (
    AssessmentCompatibilityError,
    AssessmentResultLoadError,
    AssessmentResultSpecError,
)
from .policy import (
    AssessmentCriteria,
    AssessmentPolicy,
    CaseRequirement,
    load_assessment_policy,
)

REPORT_SCHEMA_VERSION = "kri-assurance-report/1.0"
ESTIMATED_REPORT_SCHEMA_VERSION = "kri-assurance-report/1.1"
ERROR_SCHEMA_VERSION = "kri-assurance-error/1.0"
EVIDENCE_BOUNDARY = (
    "Evidence from a simplified one-dimensional RPO test harness; not a full GNC assessment, "
    "formal verification, certification, or a flight-safety claim."
)
BASE_LIMITATIONS = (
    "Evidence comes from the simplified one-dimensional RPO test harness.",
    "The harness does not represent a full guidance, navigation, and control stack or operational "
    "fault prevalence.",
    "The assessment is not formal verification, certification, or a flight-safety claim.",
    "No runtime-assurance intervention counts or controller-internal/model-corruption evidence are "
    "reported for external controllers.",
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")


@dataclass(frozen=True, slots=True)
class AssuranceReport:
    """Immutable wrapper around one deterministic, path-free report payload."""

    _payload: dict[str, object]

    def __post_init__(self) -> None:
        payload = copy.deepcopy(self._payload)
        if payload.get("schema_version") not in {
            REPORT_SCHEMA_VERSION,
            ESTIMATED_REPORT_SCHEMA_VERSION,
        }:
            raise AssessmentResultSpecError(
                "report schema_version must be a supported direct or estimated schema"
            )
        fingerprint = payload.get("report_fingerprint_sha256")
        if not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint):
            raise AssessmentResultSpecError(
                "report_fingerprint_sha256 must be 64 lowercase hex characters"
            )
        unsigned = dict(payload)
        unsigned.pop("report_fingerprint_sha256")
        expected = hashlib.sha256(canonical_json(unsigned)).hexdigest()
        if fingerprint != expected:
            raise AssessmentResultSpecError("report fingerprint does not match payload")
        object.__setattr__(self, "_payload", payload)

    @property
    def decision(self) -> str:
        overall = self._payload["overall"]
        assert isinstance(overall, dict)
        return str(overall["decision"])

    @property
    def fingerprint(self) -> str:
        return str(self._payload["report_fingerprint_sha256"])

    def to_dict(self) -> dict[str, object]:
        return copy.deepcopy(self._payload)


def _mapping(
    value: object,
    path: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise AssessmentResultSpecError(f"{path} must be an object")
    result: dict[str, Any] = value
    if any(not isinstance(key, str) for key in result):
        raise AssessmentResultSpecError(f"{path} keys must be strings")
    allowed = required | (optional or set())
    missing = sorted(required - result.keys())
    extra = sorted(result.keys() - allowed)
    if missing:
        raise AssessmentResultSpecError(
            f"{path} is missing required keys: {', '.join(missing)}"
        )
    if extra:
        raise AssessmentResultSpecError(
            f"{path} contains unknown keys: {', '.join(extra)}"
        )
    return result


def _array(value: object, path: str) -> list[Any]:
    if type(value) is not list:
        raise AssessmentResultSpecError(f"{path} must be an array")
    return value


def _string(value: object, path: str, *, maximum: int = 500) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise AssessmentResultSpecError(
            f"{path} must be a non-empty string of at most {maximum} characters"
        )
    if any(ord(character) < 32 for character in value):
        raise AssessmentResultSpecError(f"{path} contains unsupported control characters")
    return value


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise AssessmentResultSpecError(
            f"{path} must match [a-z0-9][a-z0-9._-]{{0,63}}"
        )
    return value


def _sha256(value: object, path: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise AssessmentResultSpecError(f"{path} must be 64 lowercase hex characters")
    return value


def _boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise AssessmentResultSpecError(f"{path} must be a boolean")
    return value


def _integer(value: object, path: str) -> int:
    if type(value) is not int or value < 0:
        raise AssessmentResultSpecError(f"{path} must be a non-negative integer")
    return value


def _finite(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise AssessmentResultSpecError(f"{path} must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise AssessmentResultSpecError(f"{path} must be finite")
    return result


def _count_mapping(
    value: object,
    path: str,
    expected_keys: set[str],
) -> dict[str, int]:
    data = _mapping(value, path, required=expected_keys)
    return {key: _integer(data[key], f"{path}.{key}") for key in sorted(data)}


def _navigation_case_diagnostics(
    value: object,
    path: str,
    *,
    commands: int,
    degraded_steps: int,
    missing_steps: int,
) -> dict[str, object]:
    data = _mapping(
        value,
        path,
        required={
            "profile",
            "identity_sha256",
            "raw_observation_status_counts",
            "controller_observation_status_counts",
            "estimator_health_counts",
            "estimator_reason_counts",
            "packet_disposition_counts",
            "missing_packet_steps",
            "final_health",
            "final_reason",
            "accepted_updates",
            "innovation_rejections",
            "invalid_packets",
            "final_prediction_only_age_s",
            "navigation_trace_sha256",
            "packet_fault",
        },
    )
    if data["profile"] != "estimated":
        raise AssessmentResultSpecError(f"{path}.profile must be 'estimated'")
    _sha256(data["identity_sha256"], f"{path}.identity_sha256")
    statuses = {"nominal", "degraded", "missing"}
    raw_counts = _count_mapping(
        data["raw_observation_status_counts"],
        f"{path}.raw_observation_status_counts",
        statuses,
    )
    controller_counts = _count_mapping(
        data["controller_observation_status_counts"],
        f"{path}.controller_observation_status_counts",
        statuses,
    )
    health_counts = _count_mapping(
        data["estimator_health_counts"],
        f"{path}.estimator_health_counts",
        {"valid", "degraded", "diverged"},
    )
    reason_counts = data["estimator_reason_counts"]
    if type(reason_counts) is not dict or not reason_counts:
        raise AssessmentResultSpecError(f"{path}.estimator_reason_counts must be an object")
    checked_reasons = {
        _string(key, f"{path}.estimator_reason_counts key", maximum=100): _integer(
            count, f"{path}.estimator_reason_counts.{key}"
        )
        for key, count in reason_counts.items()
    }
    disposition_counts = data["packet_disposition_counts"]
    if type(disposition_counts) is not dict or not disposition_counts:
        raise AssessmentResultSpecError(f"{path}.packet_disposition_counts must be an object")
    checked_dispositions = {
        _string(key, f"{path}.packet_disposition_counts key", maximum=100): _integer(
            count, f"{path}.packet_disposition_counts.{key}"
        )
        for key, count in disposition_counts.items()
    }
    if (
        sum(raw_counts.values()) != commands
        or sum(controller_counts.values()) != commands
        or sum(health_counts.values()) != commands
        or sum(checked_reasons.values()) != commands
        or sum(checked_dispositions.values()) != commands
    ):
        raise AssessmentResultSpecError(
            f"{path} diagnostic counts must each sum to commands"
        )
    if controller_counts["degraded"] + controller_counts["missing"] != degraded_steps:
        raise AssessmentResultSpecError(
            f"{path} delivered status counts do not match degraded_observation_steps"
        )
    if controller_counts["missing"] != missing_steps:
        raise AssessmentResultSpecError(
            f"{path} delivered missing count does not match missing_observation_steps"
        )
    missing_packets = _integer(data["missing_packet_steps"], f"{path}.missing_packet_steps")
    if checked_dispositions.get("missing") != missing_packets:
        raise AssessmentResultSpecError(
            f"{path}.missing_packet_steps does not match packet dispositions"
        )
    final_health = _string(data["final_health"], f"{path}.final_health", maximum=64)
    if final_health not in {"valid", "degraded", "diverged"}:
        raise AssessmentResultSpecError(f"{path}.final_health is invalid")
    final_reason = _string(data["final_reason"], f"{path}.final_reason", maximum=100)
    age_value = data["final_prediction_only_age_s"]
    age = None if age_value is None else _finite(age_value, f"{path}.final_prediction_only_age_s")
    if age is not None and age < 0.0:
        raise AssessmentResultSpecError(
            f"{path}.final_prediction_only_age_s must be non-negative"
        )
    packet_fault = data["packet_fault"]
    if packet_fault is not None and type(packet_fault) is not dict:
        raise AssessmentResultSpecError(f"{path}.packet_fault must be an object or null")
    return {
        "profile": "estimated",
        "identity_sha256": data["identity_sha256"],
        "raw_observation_status_counts": raw_counts,
        "controller_observation_status_counts": controller_counts,
        "estimator_health_counts": health_counts,
        "estimator_reason_counts": checked_reasons,
        "packet_disposition_counts": checked_dispositions,
        "missing_packet_steps": missing_packets,
        "final_health": final_health,
        "final_reason": final_reason,
        "accepted_updates": _integer(data["accepted_updates"], f"{path}.accepted_updates"),
        "innovation_rejections": _integer(
            data["innovation_rejections"], f"{path}.innovation_rejections"
        ),
        "invalid_packets": _integer(data["invalid_packets"], f"{path}.invalid_packets"),
        "final_prediction_only_age_s": age,
        "navigation_trace_sha256": _sha256(
            data["navigation_trace_sha256"], f"{path}.navigation_trace_sha256"
        ),
        "packet_fault": copy.deepcopy(packet_fault),
    }


def _navigation_result_identity(value: object) -> dict[str, object]:
    data = _mapping(
        value,
        "result.navigation",
        required={
            "profile",
            "identity",
            "fault_plan",
            "controller_input_contract",
            "harness_evaluator_outputs",
            "classification",
        },
    )
    if data["profile"] != "estimated":
        raise AssessmentResultSpecError("result.navigation.profile must be 'estimated'")
    identity = _mapping(
        data["identity"],
        "result.navigation.identity",
        required={
            "schema_version",
            "profile",
            "foundation_freeze_id",
            "freeze_manifest_sha256",
            "frozen_file_sha256",
            "estimator_class",
            "measurement_factory",
            "bridge_runtime_profile",
            "bridge_model_boundary",
            "identity_sha256",
        },
    )
    expected_identity_fields = {
        "schema_version": NAVIGATION_PROFILE_SCHEMA_VERSION,
        "profile": "estimated",
        "foundation_freeze_id": FOUNDATION_FREEZE_ID,
        "freeze_manifest_sha256": FOUNDATION_MANIFEST_SHA256,
        "estimator_class": ESTIMATOR_CLASS_ID,
        "measurement_factory": MEASUREMENT_FACTORY_ID,
        "bridge_runtime_profile": BRIDGE_RUNTIME_PROFILE,
        "bridge_model_boundary": BRIDGE_MODEL_BOUNDARY,
    }
    for key, expected in expected_identity_fields.items():
        if identity[key] != expected:
            raise AssessmentResultSpecError(
                f"result.navigation.identity.{key} does not match the supported frozen profile"
            )
    claimed_identity = _sha256(
        identity["identity_sha256"], "result.navigation.identity.identity_sha256"
    )
    unsigned_identity = dict(identity)
    unsigned_identity.pop("identity_sha256")
    observed_identity = hashlib.sha256(canonical_json(unsigned_identity)).hexdigest()
    if claimed_identity != observed_identity:
        raise AssessmentResultSpecError("navigation identity SHA-256 does not match payload")
    frozen_files = identity["frozen_file_sha256"]
    if frozen_files != EXPECTED_FROZEN_FILE_SHA256:
        raise AssessmentResultSpecError(
            "result.navigation.identity.frozen_file_sha256 does not match the supported profile"
        )
    fault_plan = data["fault_plan"]
    if fault_plan is not None:
        if type(fault_plan) is not dict:
            raise AssessmentResultSpecError(
                "result.navigation.fault_plan must be an object or null"
            )
        unsigned_plan = dict(fault_plan)
        claimed_plan_sha256 = _sha256(
            unsigned_plan.pop("plan_sha256", None),
            "result.navigation.fault_plan.plan_sha256",
        )
        try:
            parsed_plan = navigation_fault_plan_from_dict(unsigned_plan)
        except NavigationFaultPlanError as exc:
            raise AssessmentResultSpecError(
                f"result.navigation.fault_plan is invalid: {exc}"
            ) from exc
        if parsed_plan.sha256 != claimed_plan_sha256:
            raise AssessmentResultSpecError(
                "result.navigation.fault_plan SHA-256 does not match payload"
            )
    if type(data["controller_input_contract"]) is not dict:
        raise AssessmentResultSpecError(
            "result.navigation.controller_input_contract must be an object"
        )
    if type(data["harness_evaluator_outputs"]) is not list:
        raise AssessmentResultSpecError(
            "result.navigation.harness_evaluator_outputs must be an array"
        )
    _string(data["classification"], "result.navigation.classification")
    return copy.deepcopy(data)


def _controller_identity(value: object) -> ControllerIdentity:
    data = _mapping(
        value,
        "result.controller",
        required={
            "plugin_spec",
            "controller_id",
            "controller_version",
            "contract_version",
            "deterministic",
            "plugin_module_sha256",
        },
    )
    contract_version = _string(
        data["contract_version"], "result.controller.contract_version", maximum=64
    )
    if contract_version != CONTRACT_VERSION:
        raise AssessmentResultSpecError(
            f"result.controller.contract_version must be {CONTRACT_VERSION!r}"
        )
    deterministic = _boolean(
        data["deterministic"], "result.controller.deterministic"
    )
    if deterministic is not True:
        raise AssessmentResultSpecError(
            "result.controller.deterministic must be true"
        )
    return ControllerIdentity(
        plugin_spec=_string(data["plugin_spec"], "result.controller.plugin_spec"),
        controller_id=_identifier(
            data["controller_id"], "result.controller.controller_id"
        ),
        controller_version=_string(
            data["controller_version"],
            "result.controller.controller_version",
            maximum=64,
        ),
        contract_version=contract_version,
        deterministic=deterministic,
        plugin_module_sha256=_sha256(
            data["plugin_module_sha256"],
            "result.controller.plugin_module_sha256",
        ),
    )


def _case_result(value: object, index: int) -> FaultCaseResult:
    path = f"result.cases[{index}]"
    data = _mapping(
        value,
        path,
        required={
            "case_id",
            "case_sha256",
            "fault_sequence",
            "success",
            "collision",
            "steps",
            "commands",
            "degraded_observation_steps",
            "missing_observation_steps",
            "actuator_modified_steps",
            "final_range_m",
            "final_speed_mps",
            "propellant_remaining",
            "command_trace_sha256",
        },
        optional={"navigation"},
    )
    fault_sequence = tuple(
        _identifier(item, f"{path}.fault_sequence[{fault_index}]")
        for fault_index, item in enumerate(
            _array(data["fault_sequence"], f"{path}.fault_sequence")
        )
    )
    if len(fault_sequence) != len(set(fault_sequence)):
        raise AssessmentResultSpecError(f"{path}.fault_sequence contains duplicates")
    success = _boolean(data["success"], f"{path}.success")
    collision = _boolean(data["collision"], f"{path}.collision")
    if success and collision:
        raise AssessmentResultSpecError(
            f"{path}.success and collision cannot both be true"
        )
    steps = _integer(data["steps"], f"{path}.steps")
    commands = _integer(data["commands"], f"{path}.commands")
    degraded = _integer(
        data["degraded_observation_steps"],
        f"{path}.degraded_observation_steps",
    )
    missing = _integer(
        data["missing_observation_steps"],
        f"{path}.missing_observation_steps",
    )
    actuator = _integer(
        data["actuator_modified_steps"], f"{path}.actuator_modified_steps"
    )
    if commands > steps:
        raise AssessmentResultSpecError(f"{path}.commands cannot exceed steps")
    if degraded > commands or missing > degraded or actuator > commands:
        raise AssessmentResultSpecError(
            f"{path} observation/actuator counts are inconsistent with commands"
        )
    propellant = _finite(
        data["propellant_remaining"], f"{path}.propellant_remaining"
    )
    if not 0.0 <= propellant <= 1.0:
        raise AssessmentResultSpecError(
            f"{path}.propellant_remaining must be in [0, 1]"
        )
    navigation = (
        None
        if "navigation" not in data
        else _navigation_case_diagnostics(
            data["navigation"],
            f"{path}.navigation",
            commands=commands,
            degraded_steps=degraded,
            missing_steps=missing,
        )
    )
    return FaultCaseResult(
        case_id=_identifier(data["case_id"], f"{path}.case_id"),
        case_sha256=_sha256(data["case_sha256"], f"{path}.case_sha256"),
        fault_sequence=fault_sequence,
        success=success,
        collision=collision,
        steps=steps,
        commands=commands,
        degraded_observation_steps=degraded,
        missing_observation_steps=missing,
        actuator_modified_steps=actuator,
        final_range_m=_finite(data["final_range_m"], f"{path}.final_range_m"),
        final_speed_mps=_finite(data["final_speed_mps"], f"{path}.final_speed_mps"),
        propellant_remaining=propellant,
        command_trace_sha256=_sha256(
            data["command_trace_sha256"], f"{path}.command_trace_sha256"
        ),
        navigation=navigation,
    )


def _validate_navigation_crosslinks(
    navigation: dict[str, object],
    cases: tuple[FaultCaseResult, ...],
    *,
    suite_id: str,
    suite_sha256: str,
) -> None:
    identity = navigation["identity"]
    assert isinstance(identity, dict)
    identity_sha256 = identity["identity_sha256"]
    for case in cases:
        assert case.navigation is not None
        if case.navigation["identity_sha256"] != identity_sha256:
            raise AssessmentResultSpecError(
                f"case {case.case_id} navigation identity does not match result identity"
            )
    plan_payload = navigation["fault_plan"]
    if plan_payload is None:
        if any(case.navigation["packet_fault"] is not None for case in cases):
            raise AssessmentResultSpecError(
                "case packet faults require a bound navigation fault plan"
            )
        return
    assert isinstance(plan_payload, dict)
    unsigned_plan = dict(plan_payload)
    claimed = unsigned_plan.pop("plan_sha256")
    try:
        plan = navigation_fault_plan_from_dict(unsigned_plan)
        plan.validate_suite(
            suite_id=suite_id,
            suite_sha256=suite_sha256,
            case_ids={case.case_id for case in cases},
        )
    except NavigationFaultPlanError as exc:
        raise AssessmentResultSpecError(
            f"result navigation fault plan is incompatible: {exc}"
        ) from exc
    if plan.sha256 != claimed:
        raise AssessmentResultSpecError(
            "result navigation fault plan SHA-256 does not match payload"
        )
    for case in cases:
        expected = plan.fault_for(case.case_id)
        expected_payload = None if expected is None else expected.to_dict()
        if case.navigation["packet_fault"] != expected_payload:
            raise AssessmentResultSpecError(
                f"case {case.case_id} packet fault does not match navigation plan"
            )


def fault_suite_result_from_dict(value: object) -> FaultSuiteRunResult:
    """Strictly validate a decoded direct v1.0 or estimated v1.1 result."""

    data = _mapping(
        value,
        "result",
        required={
            "result_schema_version",
            "suite_id",
            "suite_sha256",
            "runtime_profile",
            "controller",
            "cases",
            "result_sha256",
        },
        optional={"navigation"},
    )
    schema_version = data["result_schema_version"]
    if schema_version not in {RESULT_SCHEMA_VERSION, ESTIMATED_RESULT_SCHEMA_VERSION}:
        raise AssessmentResultSpecError(
            "result_schema_version must be a supported direct or estimated result schema"
        )
    if schema_version == RESULT_SCHEMA_VERSION and "navigation" in data:
        raise AssessmentResultSpecError(
            "direct result schema must not contain estimated navigation metadata"
        )
    if schema_version == ESTIMATED_RESULT_SCHEMA_VERSION and "navigation" not in data:
        raise AssessmentResultSpecError(
            "estimated result schema requires navigation metadata"
        )
    raw_cases = _array(data["cases"], "result.cases")
    cases = tuple(_case_result(item, index) for index, item in enumerate(raw_cases))
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise AssessmentResultSpecError("result.cases contains duplicate case ids")
    navigation = (
        None
        if "navigation" not in data
        else _navigation_result_identity(data["navigation"])
    )
    if schema_version == RESULT_SCHEMA_VERSION and any(
        case.navigation is not None for case in cases
    ):
        raise AssessmentResultSpecError(
            "direct result schema must not contain case navigation diagnostics"
        )
    if schema_version == ESTIMATED_RESULT_SCHEMA_VERSION and any(
        case.navigation is None for case in cases
    ):
        raise AssessmentResultSpecError(
            "estimated result schema requires navigation diagnostics for every case"
        )
    suite_id = _identifier(data["suite_id"], "result.suite_id")
    suite_sha256 = _sha256(data["suite_sha256"], "result.suite_sha256")
    if navigation is not None:
        _validate_navigation_crosslinks(
            navigation,
            cases,
            suite_id=suite_id,
            suite_sha256=suite_sha256,
        )
    result = FaultSuiteRunResult(
        suite_id=suite_id,
        suite_sha256=suite_sha256,
        runtime_profile=_identifier(
            data["runtime_profile"], "result.runtime_profile"
        ),
        controller=_controller_identity(data["controller"]),
        cases=cases,
        navigation=navigation,
        result_schema_version=schema_version,
    )
    claimed = _sha256(data["result_sha256"], "result.result_sha256")
    if claimed != result.result_sha256:
        raise AssessmentResultSpecError("result_sha256 does not match result payload")
    return result


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


def loads_fault_suite_result(payload: str) -> FaultSuiteRunResult:
    if not isinstance(payload, str):
        raise AssessmentResultLoadError("result payload must be text")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (json.JSONDecodeError, _DuplicateKeyError, ValueError) as exc:
        raise AssessmentResultLoadError(f"invalid fault-suite result JSON: {exc}") from exc
    return fault_suite_result_from_dict(value)


def load_fault_suite_result(path: str | Path) -> FaultSuiteRunResult:
    source = Path(path)
    try:
        payload = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AssessmentResultLoadError(f"could not read fault-suite result: {exc}") from exc
    return loads_fault_suite_result(payload)


def _coerce_suite(value: FaultSuite | str | Path) -> FaultSuite:
    if type(value) is FaultSuite:
        return fault_suite_from_dict(value.to_dict())
    return load_fault_suite(value)


def _coerce_policy(value: AssessmentPolicy | str | Path) -> AssessmentPolicy:
    if type(value) is AssessmentPolicy:
        return value
    return load_assessment_policy(value)


def _coerce_result(
    value: FaultSuiteRunResult | str | Path,
) -> FaultSuiteRunResult:
    if type(value) is FaultSuiteRunResult:
        return fault_suite_result_from_dict(value.to_dict())
    return load_fault_suite_result(value)


def _validate_compatibility(
    result: FaultSuiteRunResult,
    suite: FaultSuite,
    policy: AssessmentPolicy,
) -> None:
    if policy.suite_id != suite.suite_id or policy.suite_sha256 != suite.sha256:
        raise AssessmentCompatibilityError(
            "assessment policy does not identify the supplied fault suite"
        )
    if (
        result.suite_id != suite.suite_id
        or result.suite_sha256 != suite.sha256
        or result.runtime_profile != suite.runtime_profile
    ):
        raise AssessmentCompatibilityError(
            "fault-suite result does not identify the supplied fault suite and runtime profile"
        )
    expected = {case.case_id: case for case in suite.cases}
    unknown_overrides = sorted(
        override.case_id
        for override in policy.case_overrides
        if override.case_id not in expected
    )
    if unknown_overrides:
        raise AssessmentCompatibilityError(
            "assessment policy references unknown suite cases: "
            + ", ".join(unknown_overrides)
        )
    observed_ids = [case.case_id for case in result.cases]
    extra = sorted(set(observed_ids) - expected.keys())
    if extra:
        raise AssessmentCompatibilityError(
            "fault-suite result contains unknown cases: " + ", ".join(extra)
        )
    expected_observed_order = [
        case.case_id for case in suite.cases if case.case_id in set(observed_ids)
    ]
    if observed_ids != expected_observed_order:
        raise AssessmentCompatibilityError(
            "fault-suite result cases are not in declared suite order"
        )
    for case_result in result.cases:
        case = expected[case_result.case_id]
        expected_faults = tuple(fault.fault_id for fault in case.faults)
        if case_result.case_sha256 != case.sha256:
            raise AssessmentCompatibilityError(
                f"case hash mismatch for {case.case_id}"
            )
        if case_result.fault_sequence != expected_faults:
            raise AssessmentCompatibilityError(
                f"fault sequence mismatch for {case.case_id}"
            )


def _effective_policy(
    policy: AssessmentPolicy, case_id: str
) -> tuple[CaseRequirement, AssessmentCriteria]:
    override = policy.override_for(case_id)
    if override is None:
        return policy.default_case_requirement, policy.criteria
    criteria = (
        policy.criteria
        if override.criteria is None
        else override.criteria.apply(policy.criteria)
    )
    return override.requirement, criteria


def _criteria_rows(
    result: FaultCaseResult,
    criteria: AssessmentCriteria,
) -> list[dict[str, object]]:
    return [
        {
            "criterion_id": "case_success",
            "enabled": criteria.require_success,
            "operator": "equals",
            "expected": True if criteria.require_success else None,
            "observed": result.success,
            "passed": result.success if criteria.require_success else None,
        },
        {
            "criterion_id": "zero_collision",
            "enabled": criteria.require_zero_collision,
            "operator": "equals",
            "expected": False if criteria.require_zero_collision else None,
            "observed": result.collision,
            "passed": (not result.collision)
            if criteria.require_zero_collision
            else None,
        },
        {
            "criterion_id": "minimum_propellant_remaining",
            "enabled": True,
            "operator": "greater_than_or_equal",
            "expected": criteria.minimum_propellant_remaining,
            "observed": result.propellant_remaining,
            "passed": (
                result.propellant_remaining
                >= criteria.minimum_propellant_remaining
            ),
        },
    ]


def _criterion_message(case_id: str, row: dict[str, object]) -> str:
    criterion = row["criterion_id"]
    observed = row["observed"]
    expected = row["expected"]
    if criterion == "case_success":
        return f"{case_id}: required case success was false."
    if criterion == "zero_collision":
        return f"{case_id}: collision was observed."
    return (
        f"{case_id}: propellant remaining {float(observed):.9f} was below "
        f"the declared minimum {float(expected):.9f}."
    )


def _comparison(
    case_id: str,
    result: FaultCaseResult | None,
    nominal_id: str | None,
    nominal: FaultCaseResult | None,
) -> dict[str, object]:
    if result is None:
        return {"available": False, "reason": "case result is missing"}
    if nominal_id is None:
        return {
            "available": False,
            "reason": "suite does not declare exactly one fault-free nominal case",
        }
    if nominal is None:
        return {"available": False, "reason": "nominal case result is missing"}
    if case_id == nominal_id:
        return {"available": False, "reason": "case is the nominal reference"}
    return {
        "available": True,
        "reference_case_id": nominal_id,
        "final_range_delta_m": result.final_range_m - nominal.final_range_m,
        "final_speed_delta_mps": result.final_speed_mps - nominal.final_speed_mps,
        "propellant_remaining_delta": (
            result.propellant_remaining - nominal.propellant_remaining
        ),
        "steps_delta": result.steps - nominal.steps,
        "commands_delta": result.commands - nominal.commands,
    }


def _case_evidence(result: FaultCaseResult) -> dict[str, object]:
    return {
        "success": result.success,
        "collision": result.collision,
        "final_range_m": result.final_range_m,
        "final_speed_mps": result.final_speed_mps,
        "propellant_remaining": result.propellant_remaining,
        "steps": result.steps,
        "commands": result.commands,
        "degraded_observation_steps": result.degraded_observation_steps,
        "missing_observation_steps": result.missing_observation_steps,
        "actuator_modified_steps": result.actuator_modified_steps,
    }


def _estimated_information_sections(result: FaultCaseResult) -> dict[str, object]:
    if result.navigation is None:
        return {}
    navigation = copy.deepcopy(result.navigation)
    delivered = navigation["controller_observation_status_counts"]
    return {
        "controller_inputs": {
            "contract_fields": [
                "step",
                "time_s",
                "range_m",
                "relative_velocity_mps",
                "propellant_fraction",
                "sensor_quality",
            ],
            "delivered_status_counts": delivered,
            "privileged_inputs_excluded": True,
        },
        "navigation_diagnostics": navigation,
        "harness_evaluator_outputs": {
            "success": result.success,
            "collision": result.collision,
            "final_range_m": result.final_range_m,
            "final_speed_mps": result.final_speed_mps,
            "propellant_remaining": result.propellant_remaining,
            "steps": result.steps,
        },
    }


def assess_fault_suite_result(
    result: FaultSuiteRunResult | str | Path,
    suite: FaultSuite | str | Path,
    policy: AssessmentPolicy | str | Path,
) -> AssuranceReport:
    """Assess one validated suite result without rerunning simulator or fault logic."""

    checked_suite = _coerce_suite(suite)
    checked_policy = _coerce_policy(policy)
    checked_result = _coerce_result(result)
    _validate_compatibility(checked_result, checked_suite, checked_policy)

    result_by_id = {item.case_id: item for item in checked_result.cases}
    nominal_cases = [case for case in checked_suite.cases if not case.faults]
    nominal_id = nominal_cases[0].case_id if len(nominal_cases) == 1 else None
    nominal_result = result_by_id.get(nominal_id) if nominal_id is not None else None

    case_records: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    informational_findings: list[dict[str, object]] = []
    required_count = 0
    informational_count = 0
    passed_required = 0
    failed_required = 0
    incomplete_count = 0

    for case in checked_suite.cases:
        requirement, criteria = _effective_policy(checked_policy, case.case_id)
        if requirement is CaseRequirement.REQUIRED:
            required_count += 1
        else:
            informational_count += 1
        case_result = result_by_id.get(case.case_id)
        if case_result is None:
            incomplete_count += 1
            case_records.append(
                {
                    "case_id": case.case_id,
                    "case_sha256": case.sha256,
                    "case_result_sha256": None,
                    "command_trace_sha256": None,
                    "fault_sequence": [fault.fault_id for fault in case.faults],
                    "requirement": requirement.value,
                    "assessment": "INCOMPLETE",
                    "criteria_passed": None,
                    "criteria": [],
                    "evidence": None,
                    "nominal_comparison": _comparison(
                        case.case_id, None, nominal_id, nominal_result
                    ),
                    "reason": "declared suite case result is missing",
                }
            )
            failures.append(
                {
                    "case_id": case.case_id,
                    "criterion_id": "case_result_present",
                    "expected": True,
                    "observed": False,
                    "affects_overall": True,
                    "message": f"{case.case_id}: declared suite case result is missing.",
                }
            )
            continue

        criteria_rows = _criteria_rows(case_result, criteria)
        enabled_passed = all(
            bool(row["passed"])
            for row in criteria_rows
            if row["enabled"] is True
        )
        if requirement is CaseRequirement.REQUIRED:
            assessment = "PASS" if enabled_passed else "FAIL"
            if enabled_passed:
                passed_required += 1
            else:
                failed_required += 1
        else:
            assessment = "INFORMATIONAL"

        for row in criteria_rows:
            if row["enabled"] is not True or row["passed"] is not False:
                continue
            finding = {
                "case_id": case.case_id,
                "criterion_id": row["criterion_id"],
                "expected": row["expected"],
                "observed": row["observed"],
                "affects_overall": requirement is CaseRequirement.REQUIRED,
                "message": _criterion_message(case.case_id, row),
            }
            if requirement is CaseRequirement.REQUIRED:
                failures.append(finding)
            else:
                informational_findings.append(finding)

        case_records.append(
            {
                "case_id": case.case_id,
                "case_sha256": case_result.case_sha256,
                "case_result_sha256": hashlib.sha256(
                    canonical_json(case_result.to_dict())
                ).hexdigest(),
                "command_trace_sha256": case_result.command_trace_sha256,
                "fault_sequence": list(case_result.fault_sequence),
                "requirement": requirement.value,
                "assessment": assessment,
                "criteria_passed": enabled_passed,
                "criteria": criteria_rows,
                "evidence": _case_evidence(case_result),
                "nominal_comparison": _comparison(
                    case.case_id, case_result, nominal_id, nominal_result
                ),
                "reason": (
                    "all enabled declared criteria passed"
                    if enabled_passed
                    else "one or more enabled declared criteria failed"
                ),
                **_estimated_information_sections(case_result),
            }
        )

    if incomplete_count:
        decision = "INCOMPLETE"
    elif failed_required:
        decision = "FAIL"
    else:
        decision = "PASS"

    limitations = list(BASE_LIMITATIONS)
    if nominal_id is None:
        limitations.append(
            "Nominal comparisons are unavailable because the suite does not contain exactly one "
            "fault-free case."
        )
    elif nominal_result is None:
        limitations.append(
            "Nominal comparisons are unavailable because the nominal result is missing."
        )
    if checked_result.navigation is not None:
        limitations.extend(
            [
                "Estimated-profile runs are illustrative product engineering stress tests, not "
                "new Experiment 003 evidence or hypothesis tests.",
                "The frozen Experiment 003 estimator retains its first-order actuator and process "
                "model while the product simplified-rpo-v1 plant applies acceleration "
                "instantaneously; this explicit model boundary was not retuned away.",
                "Estimator covariance, health, and packet diagnostics are harness diagnostics; "
                "the external controller receives only the documented ControllerObservation.",
            ]
        )

    unsigned: dict[str, object] = {
        "schema_version": (
            ESTIMATED_REPORT_SCHEMA_VERSION
            if checked_result.navigation is not None
            else REPORT_SCHEMA_VERSION
        ),
        "evidence_boundary": EVIDENCE_BOUNDARY,
        "overall": {
            "decision": decision,
            "required_case_count": required_count,
            "informational_case_count": informational_count,
            "passed_required_case_count": passed_required,
            "failed_required_case_count": failed_required,
            "incomplete_case_count": incomplete_count,
        },
        "controller": checked_result.controller.to_dict(),
        "fault_suite": {
            "schema_version": checked_suite.schema_version,
            "suite_id": checked_suite.suite_id,
            "suite_sha256": checked_suite.sha256,
            "runtime_profile": checked_suite.runtime_profile,
            "result_schema_version": checked_result.result_schema_version,
            "result_sha256": checked_result.result_sha256,
        },
        "assessment_policy": {
            "schema_version": checked_policy.schema_version,
            "policy_id": checked_policy.policy_id,
            "policy_sha256": checked_policy.sha256,
        },
        "cases": case_records,
        "failures": failures,
        "informational_findings": informational_findings,
        "limitations": limitations,
    }
    if checked_result.navigation is not None:
        unsigned["navigation"] = copy.deepcopy(checked_result.navigation)
        unsigned["information_boundaries"] = {
            "controller_inputs": (
                "Only ControllerObservation step/time, estimated range/velocity, propellant "
                "telemetry, and deterministic health-derived sensor_quality."
            ),
            "navigation_harness_diagnostics": (
                "Estimator health/reason and packet dispositions are report-only diagnostics."
            ),
            "harness_evaluator_outputs": (
                "Truth-derived success, collision, final state, and propellant outputs are used "
                "only for harness scoring and are never controller inputs."
            ),
            "offline_truth_error_and_nees_reported": False,
        }
    payload = {
        **unsigned,
        "report_fingerprint_sha256": hashlib.sha256(
            canonical_json(unsigned)
        ).hexdigest(),
    }
    return AssuranceReport(payload)


def assess_controller(
    controller_spec: str,
    suite: FaultSuite | str | Path,
    policy: AssessmentPolicy | str | Path,
    *,
    navigation_profile: str = "direct",
    navigation_fault_plan=None,
    repository_root: str | Path = ".",
) -> AssuranceReport:
    """Replay a controller on a declared suite, then generate its deterministic report."""

    checked_suite = _coerce_suite(suite)
    checked_policy = _coerce_policy(policy)
    if (
        checked_policy.suite_id != checked_suite.suite_id
        or checked_policy.suite_sha256 != checked_suite.sha256
    ):
        raise AssessmentCompatibilityError(
            "assessment policy does not identify the supplied fault suite"
        )
    replay = replay_fault_suite(
        controller_spec,
        checked_suite,
        navigation_profile=navigation_profile,
        navigation_fault_plan=navigation_fault_plan,
        repository_root=repository_root,
    )
    result = fault_suite_result_from_dict(replay["result"])
    return assess_fault_suite_result(result, checked_suite, checked_policy)


def render_report_json(report: AssuranceReport) -> str:
    if type(report) is not AssuranceReport:
        raise AssessmentResultSpecError("report must be an AssuranceReport")
    return json.dumps(
        report.to_dict(),
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _format_number(value: object, digits: int = 6) -> str:
    return f"{float(value):.{digits}f}"


def render_report_markdown(report: AssuranceReport) -> str:
    if type(report) is not AssuranceReport:
        raise AssessmentResultSpecError("report must be an AssuranceReport")
    data = report.to_dict()
    overall = data["overall"]
    controller = data["controller"]
    suite = data["fault_suite"]
    policy = data["assessment_policy"]
    assert isinstance(overall, dict)
    assert isinstance(controller, dict)
    assert isinstance(suite, dict)
    assert isinstance(policy, dict)
    navigation = data.get("navigation")
    navigation_lines: list[str] = []
    if isinstance(navigation, dict):
        identity = navigation.get("identity")
        if isinstance(identity, dict):
            navigation_lines = [
                f"- **Navigation profile:** `estimated` "
                f"(identity SHA-256 `{identity['identity_sha256']}`)",
                f"- **Frozen estimator foundation:** `{identity['foundation_freeze_id']}`",
            ]

    lines = [
        f"# Test-harness assessment: {overall['decision']}",
        "",
        f"- **Controller:** `{controller['controller_id']}` v`{controller['controller_version']}` "
        f"(module SHA-256 `{controller['plugin_module_sha256']}`)",
        f"- **Fault suite:** `{suite['suite_id']}` (SHA-256 `{suite['suite_sha256']}`)",
        f"- **Assessment policy:** `{policy['policy_id']}` "
        f"(SHA-256 `{policy['policy_sha256']}`)",
        f"- **Runtime profile:** `{suite['runtime_profile']}`",
        *navigation_lines,
        f"- **Report fingerprint:** `{data['report_fingerprint_sha256']}`",
        "",
        f"> **Evidence boundary:** {data['evidence_boundary']}",
        "",
        "## Cases",
        "",
        "| Case | Role / assessment | Success / collision | Propellant | Final range / speed | "
        "Steps / commands | Degraded / missing obs. | Actuator-modified | "
        "Δ propellant vs nominal |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    cases = data["cases"]
    assert isinstance(cases, list)
    for case in cases:
        assert isinstance(case, dict)
        evidence = case["evidence"]
        comparison = case["nominal_comparison"]
        if evidence is None:
            values = ("—",) * 7
        else:
            assert isinstance(evidence, dict)
            delta = "—"
            if isinstance(comparison, dict) and comparison.get("available") is True:
                delta = _format_number(comparison["propellant_remaining_delta"], 9)
            values = (
                f"{evidence['success']} / {evidence['collision']}",
                _format_number(evidence["propellant_remaining"], 9),
                f"{_format_number(evidence['final_range_m'])} / "
                f"{_format_number(evidence['final_speed_mps'])}",
                f"{evidence['steps']} / {evidence['commands']}",
                f"{evidence['degraded_observation_steps']} / "
                f"{evidence['missing_observation_steps']}",
                str(evidence["actuator_modified_steps"]),
                delta,
            )
        lines.append(
            f"| `{case['case_id']}` | {case['requirement']} / **{case['assessment']}** | "
            + " | ".join(values)
            + " |"
        )

    if isinstance(navigation, dict):
        lines.extend(
            [
                "",
                "## Estimated navigation diagnostics",
                "",
                "These are harness diagnostics, not controller inputs. Truth-derived final "
                "state and success/collision values remain evaluator outputs only. Offline "
                "truth error and NEES are not reported here.",
                "",
                "| Case | Final health / reason | Accepted / innovation-rejected / invalid | "
                "Missing packets | Delivered nominal / degraded / missing | "
                "Navigation trace SHA-256 |",
                "| --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for case in cases:
            assert isinstance(case, dict)
            diagnostic = case.get("navigation_diagnostics")
            if not isinstance(diagnostic, dict):
                continue
            delivered = diagnostic["controller_observation_status_counts"]
            assert isinstance(delivered, dict)
            lines.append(
                f"| `{case['case_id']}` | {diagnostic['final_health']} / "
                f"{diagnostic['final_reason']} | {diagnostic['accepted_updates']} / "
                f"{diagnostic['innovation_rejections']} / {diagnostic['invalid_packets']} | "
                f"{diagnostic['missing_packet_steps']} | {delivered['nominal']} / "
                f"{delivered['degraded']} / {delivered['missing']} | "
                f"`{diagnostic['navigation_trace_sha256']}` |"
            )

    failures = data["failures"]
    findings = data["informational_findings"]
    limitations = data["limitations"]
    assert isinstance(failures, list)
    assert isinstance(findings, list)
    assert isinstance(limitations, list)
    lines.extend(["", "## Failures", ""])
    if failures:
        lines.extend(f"- {item['message']}" for item in failures if isinstance(item, dict))
    else:
        lines.append("- None.")
    lines.extend(["", "## Informational findings", ""])
    if findings:
        lines.extend(f"- {item['message']}" for item in findings if isinstance(item, dict))
    else:
        lines.append("- None.")
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in limitations)
    lines.append("")
    return "\n".join(lines)


def _atomic_write(path: str | Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary_name = handle.name
        os.replace(temporary_name, destination)
    except OSError:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise


def write_assurance_report(
    report: AssuranceReport,
    *,
    json_path: str | Path | None = None,
    markdown_path: str | Path | None = None,
) -> None:
    """Write either or both stable formats without embedding local output paths."""

    if json_path is None and markdown_path is None:
        raise ValueError("at least one report output path is required")
    if json_path is not None and markdown_path is not None:
        if Path(json_path).absolute() == Path(markdown_path).absolute():
            raise ValueError("JSON and Markdown output paths must be different")
    if json_path is not None:
        _atomic_write(json_path, render_report_json(report))
    if markdown_path is not None:
        _atomic_write(markdown_path, render_report_markdown(report))
