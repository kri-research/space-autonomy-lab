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

from kri_space_autonomy.fault_suite import canonical_json

from .errors import AssessmentPolicyLoadError, AssessmentPolicySpecError

POLICY_SCHEMA_VERSION = "kri-assessment-policy/1.0"
MAX_CASE_OVERRIDES = 128
_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CaseRequirement(StrEnum):
    REQUIRED = "required"
    INFORMATIONAL = "informational"


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise AssessmentPolicySpecError(
            f"{path} must match [a-z0-9][a-z0-9._-]{{0,63}}"
        )
    return value


def _description(value: object, path: str) -> str:
    if not isinstance(value, str) or len(value) > 500:
        raise AssessmentPolicySpecError(
            f"{path} must be a string of at most 500 characters"
        )
    if any(ord(character) < 32 and character not in "\n\t" for character in value):
        raise AssessmentPolicySpecError(f"{path} contains unsupported control characters")
    return value


def _sha256(value: object, path: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise AssessmentPolicySpecError(f"{path} must be 64 lowercase hex characters")
    return value


def _boolean(value: object, path: str) -> bool:
    if type(value) is not bool:
        raise AssessmentPolicySpecError(f"{path} must be a boolean")
    return value


def _ratio(value: object, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise AssessmentPolicySpecError(f"{path} must be a real scalar")
    result = float(value)
    if not math.isfinite(result):
        raise AssessmentPolicySpecError(f"{path} must be finite")
    if not 0.0 <= result <= 1.0:
        raise AssessmentPolicySpecError(f"{path} must be in [0, 1]")
    return result


def _mapping(
    value: object,
    path: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> dict[str, Any]:
    if type(value) is not dict:
        raise AssessmentPolicySpecError(f"{path} must be an object")
    result: dict[str, Any] = value
    if any(not isinstance(key, str) for key in result):
        raise AssessmentPolicySpecError(f"{path} keys must be strings")
    allowed = required | (optional or set())
    missing = sorted(required - result.keys())
    extra = sorted(result.keys() - allowed)
    if missing:
        raise AssessmentPolicySpecError(
            f"{path} is missing required keys: {', '.join(missing)}"
        )
    if extra:
        raise AssessmentPolicySpecError(
            f"{path} contains unknown keys: {', '.join(extra)}"
        )
    return result


def _array(value: object, path: str) -> list[Any]:
    if type(value) is not list:
        raise AssessmentPolicySpecError(f"{path} must be an array")
    return value


def _quantity_ratio(value: object, path: str) -> float:
    data = _mapping(value, path, required={"value", "unit"})
    if data["unit"] != "ratio":
        raise AssessmentPolicySpecError(f"{path}.unit must be 'ratio'")
    return _ratio(data["value"], f"{path}.value")


@dataclass(frozen=True, slots=True)
class AssessmentCriteria:
    require_success: bool
    require_zero_collision: bool
    minimum_propellant_remaining: float

    def __post_init__(self) -> None:
        _boolean(self.require_success, "criteria.require_success")
        _boolean(self.require_zero_collision, "criteria.require_zero_collision")
        object.__setattr__(
            self,
            "minimum_propellant_remaining",
            _ratio(
                self.minimum_propellant_remaining,
                "criteria.minimum_propellant_remaining",
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "require_success": self.require_success,
            "require_zero_collision": self.require_zero_collision,
            "minimum_propellant_remaining": {
                "value": self.minimum_propellant_remaining,
                "unit": "ratio",
            },
        }


@dataclass(frozen=True, slots=True)
class CriteriaOverride:
    require_success: bool | None = None
    require_zero_collision: bool | None = None
    minimum_propellant_remaining: float | None = None

    def __post_init__(self) -> None:
        if self.require_success is not None:
            _boolean(self.require_success, "override.criteria.require_success")
        if self.require_zero_collision is not None:
            _boolean(
                self.require_zero_collision,
                "override.criteria.require_zero_collision",
            )
        if self.minimum_propellant_remaining is not None:
            object.__setattr__(
                self,
                "minimum_propellant_remaining",
                _ratio(
                    self.minimum_propellant_remaining,
                    "override.criteria.minimum_propellant_remaining",
                ),
            )
        if all(
            value is None
            for value in (
                self.require_success,
                self.require_zero_collision,
                self.minimum_propellant_remaining,
            )
        ):
            raise AssessmentPolicySpecError(
                "override.criteria must contain at least one criterion"
            )

    def apply(self, base: AssessmentCriteria) -> AssessmentCriteria:
        return AssessmentCriteria(
            require_success=(
                base.require_success
                if self.require_success is None
                else self.require_success
            ),
            require_zero_collision=(
                base.require_zero_collision
                if self.require_zero_collision is None
                else self.require_zero_collision
            ),
            minimum_propellant_remaining=(
                base.minimum_propellant_remaining
                if self.minimum_propellant_remaining is None
                else self.minimum_propellant_remaining
            ),
        )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {}
        if self.require_success is not None:
            result["require_success"] = self.require_success
        if self.require_zero_collision is not None:
            result["require_zero_collision"] = self.require_zero_collision
        if self.minimum_propellant_remaining is not None:
            result["minimum_propellant_remaining"] = {
                "value": self.minimum_propellant_remaining,
                "unit": "ratio",
            }
        return result


@dataclass(frozen=True, slots=True)
class CaseAssessmentOverride:
    case_id: str
    requirement: CaseRequirement
    criteria: CriteriaOverride | None = None

    def __post_init__(self) -> None:
        _identifier(self.case_id, "case_override.case_id")
        if type(self.requirement) is not CaseRequirement:
            raise AssessmentPolicySpecError(
                "case_override.requirement must be 'required' or 'informational'"
            )
        if self.criteria is not None and type(self.criteria) is not CriteriaOverride:
            raise AssessmentPolicySpecError(
                "case_override.criteria must be a CriteriaOverride"
            )

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "case_id": self.case_id,
            "requirement": self.requirement.value,
        }
        if self.criteria is not None:
            result["criteria"] = self.criteria.to_dict()
        return result


@dataclass(frozen=True, slots=True)
class AssessmentPolicy:
    policy_id: str
    description: str
    suite_id: str
    suite_sha256: str
    default_case_requirement: CaseRequirement
    criteria: AssessmentCriteria
    case_overrides: tuple[CaseAssessmentOverride, ...]
    schema_version: str = POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _identifier(self.policy_id, "policy_id")
        _description(self.description, "description")
        _identifier(self.suite_id, "suite.id")
        _sha256(self.suite_sha256, "suite.sha256")
        if type(self.default_case_requirement) is not CaseRequirement:
            raise AssessmentPolicySpecError(
                "default_case_requirement must be 'required' or 'informational'"
            )
        if type(self.criteria) is not AssessmentCriteria:
            raise AssessmentPolicySpecError("criteria must be AssessmentCriteria")
        if type(self.case_overrides) is not tuple:
            raise AssessmentPolicySpecError("case_overrides must be a tuple")
        if len(self.case_overrides) > MAX_CASE_OVERRIDES:
            raise AssessmentPolicySpecError(
                f"case_overrides must contain at most {MAX_CASE_OVERRIDES} entries"
            )
        if any(type(item) is not CaseAssessmentOverride for item in self.case_overrides):
            raise AssessmentPolicySpecError(
                "case_overrides contains an invalid override"
            )
        case_ids = [item.case_id for item in self.case_overrides]
        if len(case_ids) != len(set(case_ids)):
            raise AssessmentPolicySpecError("case_overrides contains duplicate case ids")
        if self.schema_version != POLICY_SCHEMA_VERSION:
            raise AssessmentPolicySpecError(
                f"schema_version must be {POLICY_SCHEMA_VERSION!r}"
            )
        object.__setattr__(
            self,
            "case_overrides",
            tuple(sorted(self.case_overrides, key=lambda item: item.case_id)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "policy_id": self.policy_id,
            "description": self.description,
            "suite": {"id": self.suite_id, "sha256": self.suite_sha256},
            "default_case_requirement": self.default_case_requirement.value,
            "criteria": self.criteria.to_dict(),
            "case_overrides": [item.to_dict() for item in self.case_overrides],
        }

    @property
    def sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.to_dict())).hexdigest()

    def override_for(self, case_id: str) -> CaseAssessmentOverride | None:
        return next(
            (item for item in self.case_overrides if item.case_id == case_id),
            None,
        )


def _requirement(value: object, path: str) -> CaseRequirement:
    if not isinstance(value, str):
        raise AssessmentPolicySpecError(
            f"{path} must be 'required' or 'informational'"
        )
    try:
        return CaseRequirement(value)
    except ValueError as exc:
        raise AssessmentPolicySpecError(
            f"{path} must be 'required' or 'informational'"
        ) from exc


def _criteria(value: object, path: str) -> AssessmentCriteria:
    data = _mapping(
        value,
        path,
        required={
            "require_success",
            "require_zero_collision",
            "minimum_propellant_remaining",
        },
    )
    return AssessmentCriteria(
        require_success=_boolean(
            data["require_success"], f"{path}.require_success"
        ),
        require_zero_collision=_boolean(
            data["require_zero_collision"],
            f"{path}.require_zero_collision",
        ),
        minimum_propellant_remaining=_quantity_ratio(
            data["minimum_propellant_remaining"],
            f"{path}.minimum_propellant_remaining",
        ),
    )


def _criteria_override(value: object, path: str) -> CriteriaOverride:
    data = _mapping(
        value,
        path,
        required=set(),
        optional={
            "require_success",
            "require_zero_collision",
            "minimum_propellant_remaining",
        },
    )
    if not data:
        raise AssessmentPolicySpecError(f"{path} must contain at least one criterion")
    return CriteriaOverride(
        require_success=(
            _boolean(data["require_success"], f"{path}.require_success")
            if "require_success" in data
            else None
        ),
        require_zero_collision=(
            _boolean(
                data["require_zero_collision"],
                f"{path}.require_zero_collision",
            )
            if "require_zero_collision" in data
            else None
        ),
        minimum_propellant_remaining=(
            _quantity_ratio(
                data["minimum_propellant_remaining"],
                f"{path}.minimum_propellant_remaining",
            )
            if "minimum_propellant_remaining" in data
            else None
        ),
    )


def assessment_policy_from_dict(value: object) -> AssessmentPolicy:
    """Validate a decoded policy and return its normalized immutable form."""

    data = _mapping(
        value,
        "policy",
        required={
            "schema_version",
            "policy_id",
            "description",
            "suite",
            "default_case_requirement",
            "criteria",
            "case_overrides",
        },
    )
    if data["schema_version"] != POLICY_SCHEMA_VERSION:
        raise AssessmentPolicySpecError(
            f"schema_version must be {POLICY_SCHEMA_VERSION!r}"
        )
    suite = _mapping(data["suite"], "suite", required={"id", "sha256"})
    raw_overrides = _array(data["case_overrides"], "case_overrides")
    if len(raw_overrides) > MAX_CASE_OVERRIDES:
        raise AssessmentPolicySpecError(
            f"case_overrides must contain at most {MAX_CASE_OVERRIDES} entries"
        )
    overrides: list[CaseAssessmentOverride] = []
    seen: set[str] = set()
    for index, raw_override in enumerate(raw_overrides):
        path = f"case_overrides[{index}]"
        override = _mapping(
            raw_override,
            path,
            required={"case_id", "requirement"},
            optional={"criteria"},
        )
        case_id = _identifier(override["case_id"], f"{path}.case_id")
        if case_id in seen:
            raise AssessmentPolicySpecError(
                f"case_overrides contains duplicate case id: {case_id}"
            )
        seen.add(case_id)
        overrides.append(
            CaseAssessmentOverride(
                case_id=case_id,
                requirement=_requirement(
                    override["requirement"], f"{path}.requirement"
                ),
                criteria=(
                    _criteria_override(override["criteria"], f"{path}.criteria")
                    if "criteria" in override
                    else None
                ),
            )
        )
    return AssessmentPolicy(
        policy_id=_identifier(data["policy_id"], "policy_id"),
        description=_description(data["description"], "description"),
        suite_id=_identifier(suite["id"], "suite.id"),
        suite_sha256=_sha256(suite["sha256"], "suite.sha256"),
        default_case_requirement=_requirement(
            data["default_case_requirement"], "default_case_requirement"
        ),
        criteria=_criteria(data["criteria"], "criteria"),
        case_overrides=tuple(overrides),
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


def loads_assessment_policy(payload: str) -> AssessmentPolicy:
    """Decode strict JSON, rejecting duplicate keys and non-finite constants."""

    if not isinstance(payload, str):
        raise AssessmentPolicyLoadError("policy payload must be text")
    try:
        value = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (json.JSONDecodeError, _DuplicateKeyError, ValueError) as exc:
        raise AssessmentPolicyLoadError(f"invalid assessment-policy JSON: {exc}") from exc
    return assessment_policy_from_dict(value)


def load_assessment_policy(path: str | Path) -> AssessmentPolicy:
    """Load a policy without including its local path in its identity."""

    source = Path(path)
    try:
        payload = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AssessmentPolicyLoadError(f"could not read assessment policy: {exc}") from exc
    return loads_assessment_policy(payload)


def validate_assessment_policy(path: str | Path) -> dict[str, object]:
    policy = load_assessment_policy(path)
    return {
        "passed": True,
        "schema_version": policy.schema_version,
        "policy_id": policy.policy_id,
        "policy_sha256": policy.sha256,
        "suite_id": policy.suite_id,
        "suite_sha256": policy.suite_sha256,
        "default_case_requirement": policy.default_case_requirement.value,
        "case_override_count": len(policy.case_overrides),
    }
