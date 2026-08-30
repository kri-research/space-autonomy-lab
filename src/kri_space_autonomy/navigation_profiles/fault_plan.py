from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from kri_space_autonomy.fault_suite.manifest import ActivationWindow, canonical_json

NAVIGATION_FAULT_PLAN_SCHEMA_VERSION = "kri-navigation-fault-plan/1.0"
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class NavigationFaultPlanError(ValueError):
    """Raised when an illustrative product packet-fault plan is invalid."""


class PacketFaultKind(StrEnum):
    STALE_PACKET = "stale_packet"
    COVARIANCE_UNDERREPORTING = "covariance_underreporting"


@dataclass(frozen=True, slots=True)
class PacketFaultSpec:
    fault_id: str
    kind: PacketFaultKind
    activation: ActivationWindow

    def __post_init__(self) -> None:
        _identifier(self.fault_id, "packet_fault.id")
        if type(self.kind) is not PacketFaultKind:
            raise NavigationFaultPlanError(
                "packet_fault.type must be stale_packet or covariance_underreporting"
            )
        if type(self.activation) is not ActivationWindow:
            raise NavigationFaultPlanError(
                "packet_fault.activation must be an ActivationWindow"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.fault_id,
            "type": self.kind.value,
            "activation": self.activation.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class NavigationFaultCase:
    case_id: str
    packet_fault: PacketFaultSpec

    def __post_init__(self) -> None:
        _identifier(self.case_id, "case_id")
        if type(self.packet_fault) is not PacketFaultSpec:
            raise NavigationFaultPlanError("packet_fault must be a PacketFaultSpec")

    def to_dict(self) -> dict[str, object]:
        return {"case_id": self.case_id, "packet_fault": self.packet_fault.to_dict()}


@dataclass(frozen=True, slots=True)
class NavigationFaultPlan:
    plan_id: str
    description: str
    suite_id: str
    suite_sha256: str
    cases: tuple[NavigationFaultCase, ...]
    schema_version: str = NAVIGATION_FAULT_PLAN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.plan_id, "plan_id")
        _description(self.description, "description")
        _identifier(self.suite_id, "suite.id")
        _sha256(self.suite_sha256, "suite.sha256")
        if type(self.cases) is not tuple:
            raise NavigationFaultPlanError("cases must be a tuple")
        if any(type(case) is not NavigationFaultCase for case in self.cases):
            raise NavigationFaultPlanError("cases contains an invalid case")
        case_ids = [case.case_id for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise NavigationFaultPlanError("cases contains duplicate case ids")
        if self.schema_version != NAVIGATION_FAULT_PLAN_SCHEMA_VERSION:
            raise NavigationFaultPlanError(
                f"schema_version must be {NAVIGATION_FAULT_PLAN_SCHEMA_VERSION!r}"
            )
        object.__setattr__(self, "cases", tuple(sorted(self.cases, key=lambda item: item.case_id)))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "plan_id": self.plan_id,
            "description": self.description,
            "suite": {"id": self.suite_id, "sha256": self.suite_sha256},
            "cases": [case.to_dict() for case in self.cases],
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict())).hexdigest()

    def fault_for(self, case_id: str) -> PacketFaultSpec | None:
        record = next((case for case in self.cases if case.case_id == case_id), None)
        return None if record is None else record.packet_fault

    def validate_suite(self, *, suite_id: str, suite_sha256: str, case_ids: set[str]) -> None:
        if self.suite_id != suite_id or self.suite_sha256 != suite_sha256:
            raise NavigationFaultPlanError(
                "navigation fault plan does not identify the supplied fault suite"
            )
        unknown = sorted(case.case_id for case in self.cases if case.case_id not in case_ids)
        if unknown:
            raise NavigationFaultPlanError(
                "navigation fault plan references unknown suite cases: " + ", ".join(unknown)
            )


class _DuplicateKeyError(ValueError):
    pass


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise NavigationFaultPlanError(
            f"{path} must match [a-z0-9][a-z0-9._-]{{0,63}}"
        )
    return value


def _description(value: object, path: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 500:
        raise NavigationFaultPlanError(
            f"{path} must be a non-empty string of at most 500 characters"
        )
    if any(ord(character) < 32 for character in value):
        raise NavigationFaultPlanError(f"{path} contains unsupported control characters")
    return value


def _sha256(value: object, path: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise NavigationFaultPlanError(f"{path} must be 64 lowercase hex characters")
    return value


def _mapping(value: object, path: str, required: set[str]) -> dict[str, Any]:
    if type(value) is not dict:
        raise NavigationFaultPlanError(f"{path} must be an object")
    result: dict[str, Any] = value
    if any(not isinstance(key, str) for key in result):
        raise NavigationFaultPlanError(f"{path} keys must be strings")
    missing = sorted(required - result.keys())
    extra = sorted(result.keys() - required)
    if missing:
        raise NavigationFaultPlanError(f"{path} is missing required keys: {', '.join(missing)}")
    if extra:
        raise NavigationFaultPlanError(f"{path} contains unknown keys: {', '.join(extra)}")
    return result


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant is not permitted: {value}")


def navigation_fault_plan_from_dict(value: object) -> NavigationFaultPlan:
    data = _mapping(
        value,
        "plan",
        {"schema_version", "plan_id", "description", "suite", "cases"},
    )
    if data["schema_version"] != NAVIGATION_FAULT_PLAN_SCHEMA_VERSION:
        raise NavigationFaultPlanError(
            f"schema_version must be {NAVIGATION_FAULT_PLAN_SCHEMA_VERSION!r}"
        )
    suite = _mapping(data["suite"], "suite", {"id", "sha256"})
    raw_cases = data["cases"]
    if type(raw_cases) is not list:
        raise NavigationFaultPlanError("cases must be an array")
    cases: list[NavigationFaultCase] = []
    for index, raw_case in enumerate(raw_cases):
        case_path = f"cases[{index}]"
        case = _mapping(raw_case, case_path, {"case_id", "packet_fault"})
        raw_fault = _mapping(
            case["packet_fault"],
            f"{case_path}.packet_fault",
            {"id", "type", "activation"},
        )
        kind_value = raw_fault["type"]
        if not isinstance(kind_value, str):
            raise NavigationFaultPlanError(
                f"{case_path}.packet_fault.type must be a string"
            )
        try:
            kind = PacketFaultKind(kind_value)
        except ValueError as exc:
            raise NavigationFaultPlanError(
                f"{case_path}.packet_fault.type is unsupported"
            ) from exc
        activation = _mapping(
            raw_fault["activation"],
            f"{case_path}.packet_fault.activation",
            {"start_step", "end_step"},
        )
        try:
            window = ActivationWindow(activation["start_step"], activation["end_step"])
        except ValueError as exc:
            raise NavigationFaultPlanError(str(exc)) from exc
        cases.append(
            NavigationFaultCase(
                case_id=_identifier(case["case_id"], f"{case_path}.case_id"),
                packet_fault=PacketFaultSpec(
                    fault_id=_identifier(
                        raw_fault["id"], f"{case_path}.packet_fault.id"
                    ),
                    kind=kind,
                    activation=window,
                ),
            )
        )
    return NavigationFaultPlan(
        plan_id=_identifier(data["plan_id"], "plan_id"),
        description=_description(data["description"], "description"),
        suite_id=_identifier(suite["id"], "suite.id"),
        suite_sha256=_sha256(suite["sha256"], "suite.sha256"),
        cases=tuple(cases),
    )


def loads_navigation_fault_plan(payload: str) -> NavigationFaultPlan:
    if not isinstance(payload, str):
        raise NavigationFaultPlanError("navigation fault plan payload must be text")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (json.JSONDecodeError, _DuplicateKeyError, ValueError) as exc:
        raise NavigationFaultPlanError(f"invalid navigation fault plan JSON: {exc}") from exc
    return navigation_fault_plan_from_dict(value)


def load_navigation_fault_plan(path: str | Path) -> NavigationFaultPlan:
    try:
        payload = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise NavigationFaultPlanError(f"could not read navigation fault plan: {exc}") from exc
    return loads_navigation_fault_plan(payload)


def validate_navigation_fault_plan(path: str | Path) -> dict[str, object]:
    plan = load_navigation_fault_plan(path)
    return {
        "passed": True,
        "schema_version": plan.schema_version,
        "plan_id": plan.plan_id,
        "plan_sha256": plan.sha256,
        "suite_id": plan.suite_id,
        "suite_sha256": plan.suite_sha256,
        "case_count": len(plan.cases),
        "cases": [
            {
                "case_id": case.case_id,
                "packet_fault_id": case.packet_fault.fault_id,
                "packet_fault_type": case.packet_fault.kind.value,
                "activation": case.packet_fault.activation.to_dict(),
            }
            for case in plan.cases
        ],
        "classification": "illustrative_product_stress_cases_not_scientific_evidence",
    }
