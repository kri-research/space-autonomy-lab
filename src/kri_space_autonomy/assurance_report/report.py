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
    RESULT_SCHEMA_VERSION,
    FaultCaseResult,
    FaultSuite,
    FaultSuiteRunResult,
    canonical_json,
    fault_suite_from_dict,
    load_fault_suite,
    replay_fault_suite,
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
        if payload.get("schema_version") != REPORT_SCHEMA_VERSION:
            raise AssessmentResultSpecError(
                f"report schema_version must be {REPORT_SCHEMA_VERSION!r}"
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
) -> dict[str, Any]:
    if type(value) is not dict:
        raise AssessmentResultSpecError(f"{path} must be an object")
    result: dict[str, Any] = value
    if any(not isinstance(key, str) for key in result):
        raise AssessmentResultSpecError(f"{path} keys must be strings")
    missing = sorted(required - result.keys())
    extra = sorted(result.keys() - required)
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
    )


def fault_suite_result_from_dict(value: object) -> FaultSuiteRunResult:
    """Strictly validate a decoded `kri-fault-suite-result/1.0` document."""

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
    )
    if data["result_schema_version"] != RESULT_SCHEMA_VERSION:
        raise AssessmentResultSpecError(
            f"result_schema_version must be {RESULT_SCHEMA_VERSION!r}"
        )
    raw_cases = _array(data["cases"], "result.cases")
    cases = tuple(_case_result(item, index) for index, item in enumerate(raw_cases))
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise AssessmentResultSpecError("result.cases contains duplicate case ids")
    result = FaultSuiteRunResult(
        suite_id=_identifier(data["suite_id"], "result.suite_id"),
        suite_sha256=_sha256(data["suite_sha256"], "result.suite_sha256"),
        runtime_profile=_identifier(
            data["runtime_profile"], "result.runtime_profile"
        ),
        controller=_controller_identity(data["controller"]),
        cases=cases,
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

    unsigned: dict[str, object] = {
        "schema_version": REPORT_SCHEMA_VERSION,
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
    replay = replay_fault_suite(controller_spec, checked_suite)
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

    lines = [
        f"# Test-harness assessment: {overall['decision']}",
        "",
        f"- **Controller:** `{controller['controller_id']}` v`{controller['controller_version']}` "
        f"(module SHA-256 `{controller['plugin_module_sha256']}`)",
        f"- **Fault suite:** `{suite['suite_id']}` (SHA-256 `{suite['suite_sha256']}`)",
        f"- **Assessment policy:** `{policy['policy_id']}` "
        f"(SHA-256 `{policy['policy_sha256']}`)",
        f"- **Runtime profile:** `{suite['runtime_profile']}`",
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
