from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path

from kri_space_autonomy.controller_adapter import (
    ControllerAdapter,
    ControllerContext,
    ControllerIdentity,
    ObservationStatus,
    load_controller,
)
from kri_space_autonomy.environment import EnvironmentConfig, ProximityEnvironment
from kri_space_autonomy.types import Action, SpacecraftState

from .errors import FaultApplicationError, FaultSpecError
from .manifest import (
    RUNTIME_PROFILE,
    FaultCase,
    FaultSuite,
    canonical_json,
    fault_suite_from_dict,
    load_fault_suite,
)
from .pipeline import DeterministicFaultPipeline

RESULT_SCHEMA_VERSION = "kri-fault-suite-result/1.0"
ESTIMATED_RESULT_SCHEMA_VERSION = "kri-fault-suite-result/1.1"


def _profile_environment() -> ProximityEnvironment:
    return ProximityEnvironment(
        EnvironmentConfig(
            dt_s=1.0,
            min_range_m=1.0,
            goal_min_range_m=5.0,
            goal_max_range_m=8.0,
            goal_max_speed_mps=0.06,
            max_steps=500,
            max_acceleration_mps2=0.05,
            propellant_cost_per_mps2=0.0015,
            propellant_reserve=0.10,
        )
    )


@dataclass(frozen=True, slots=True)
class FaultCaseResult:
    case_id: str
    case_sha256: str
    fault_sequence: tuple[str, ...]
    success: bool
    collision: bool
    steps: int
    commands: int
    degraded_observation_steps: int
    missing_observation_steps: int
    actuator_modified_steps: int
    final_range_m: float
    final_speed_mps: float
    propellant_remaining: float
    command_trace_sha256: str
    navigation: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "case_id": self.case_id,
            "case_sha256": self.case_sha256,
            "fault_sequence": list(self.fault_sequence),
            "success": self.success,
            "collision": self.collision,
            "steps": self.steps,
            "commands": self.commands,
            "degraded_observation_steps": self.degraded_observation_steps,
            "missing_observation_steps": self.missing_observation_steps,
            "actuator_modified_steps": self.actuator_modified_steps,
            "final_range_m": self.final_range_m,
            "final_speed_mps": self.final_speed_mps,
            "propellant_remaining": self.propellant_remaining,
            "command_trace_sha256": self.command_trace_sha256,
        }
        if self.navigation is not None:
            result["navigation"] = self.navigation
        return result


@dataclass(frozen=True, slots=True)
class FaultSuiteRunResult:
    suite_id: str
    suite_sha256: str
    runtime_profile: str
    controller: ControllerIdentity
    cases: tuple[FaultCaseResult, ...]
    navigation: dict[str, object] | None = None
    result_schema_version: str = RESULT_SCHEMA_VERSION

    def identity_payload(self) -> dict[str, object]:
        result: dict[str, object] = {
            "result_schema_version": self.result_schema_version,
            "suite_id": self.suite_id,
            "suite_sha256": self.suite_sha256,
            "runtime_profile": self.runtime_profile,
            "controller": self.controller.to_dict(),
            "cases": [case.to_dict() for case in self.cases],
        }
        if self.navigation is not None:
            result["navigation"] = self.navigation
        return result

    @property
    def result_sha256(self) -> str:
        return hashlib.sha256(canonical_json(self.identity_payload())).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {**self.identity_payload(), "result_sha256": self.result_sha256}


def _trace_digest(trace: list[dict[str, int | float]]) -> str:
    return hashlib.sha256(canonical_json(trace)).hexdigest()


def _validate_state(state: SpacecraftState) -> None:
    if type(state.step) is not int or state.step < 0:
        raise FaultApplicationError("runtime state step must be a non-negative integer")
    for name, value in (
        ("range_m", state.range_m),
        ("relative_velocity_mps", state.relative_velocity_mps),
        ("propellant", state.propellant),
    ):
        if not math.isfinite(value):
            raise FaultApplicationError(f"runtime state {name} became non-finite")
    if not 0.0 <= state.propellant <= 1.0:
        raise FaultApplicationError("runtime state propellant left [0, 1]")


def _validated_suite(suite: FaultSuite) -> FaultSuite:
    if type(suite) is not FaultSuite:
        raise FaultSpecError("suite must be a FaultSuite")
    return fault_suite_from_dict(suite.to_dict())


def _run_case(
    adapter: ControllerAdapter,
    suite: FaultSuite,
    case: FaultCase,
    environment: ProximityEnvironment,
    navigation,
    packet_fault,
) -> FaultCaseResult:
    cfg = environment.config
    pipeline = DeterministicFaultPipeline(case)
    context = ControllerContext(
        command_period_s=cfg.dt_s,
        minimum_acceleration_mps2=-cfg.max_acceleration_mps2,
        maximum_acceleration_mps2=cfg.max_acceleration_mps2,
    )
    state = SpacecraftState(
        step=0,
        range_m=suite.initial_state.range_m,
        relative_velocity_mps=suite.initial_state.relative_velocity_mps,
        propellant=suite.initial_state.propellant_fraction,
    )
    _validate_state(state)
    navigation.validate_initial_navigation(state.range_m, state.relative_velocity_mps)
    navigation.reset(context)
    adapter.reset(context)
    trace: list[dict[str, int | float]] = []
    degraded_steps = 0
    missing_steps = 0
    actuator_modified_steps = 0

    for _ in range(cfg.max_steps):
        if environment.is_collision(state) or environment.is_goal(state):
            break
        observed = pipeline.apply_observation(environment.observe(state))
        public_observation = navigation.observe(observed, packet_fault)
        if public_observation.status is not ObservationStatus.NOMINAL:
            degraded_steps += 1
        if public_observation.status is ObservationStatus.MISSING:
            missing_steps += 1
        command = adapter.command(public_observation)
        requested = Action(command.acceleration_mps2)
        navigation.accept_command(requested.acceleration_mps2)
        executed = pipeline.apply_action(state.step, requested)
        if executed.acceleration_mps2 != requested.acceleration_mps2:
            actuator_modified_steps += 1
        trace.append(
            {
                "step": state.step,
                "requested_acceleration_mps2": requested.acceleration_mps2,
                "executed_acceleration_mps2": executed.acceleration_mps2,
            }
        )
        state = environment.step(state, executed)
        _validate_state(state)

    navigation_diagnostics = navigation.diagnostics()
    return FaultCaseResult(
        case_id=case.case_id,
        case_sha256=case.sha256,
        fault_sequence=tuple(fault.fault_id for fault in case.faults),
        success=environment.is_goal(state) and not environment.is_collision(state),
        collision=environment.is_collision(state),
        steps=state.step,
        commands=len(trace),
        degraded_observation_steps=degraded_steps,
        missing_observation_steps=missing_steps,
        actuator_modified_steps=actuator_modified_steps,
        final_range_m=state.range_m,
        final_speed_mps=state.relative_velocity_mps,
        propellant_remaining=state.propellant,
        command_trace_sha256=_trace_digest(trace),
        navigation=(
            None if navigation_diagnostics is None else navigation_diagnostics.to_dict()
        ),
    )


def run_loaded_fault_suite(
    adapter: ControllerAdapter,
    suite: FaultSuite,
    *,
    navigation_profile: str = "direct",
    navigation_fault_plan=None,
    repository_root: str | Path = ".",
) -> FaultSuiteRunResult:
    """Run a validated suite through the unchanged public controller adapter."""

    if type(adapter) is not ControllerAdapter:
        raise FaultSpecError("adapter must be a ControllerAdapter")
    checked = _validated_suite(suite)
    if checked.runtime_profile != RUNTIME_PROFILE:
        raise FaultSpecError(f"runtime_profile must be {RUNTIME_PROFILE!r}")
    from kri_space_autonomy.navigation_profiles import (
        NavigationFaultPlan,
        NavigationFaultPlanError,
        NavigationProfileName,
        build_navigation_profile,
        load_navigation_fault_plan,
        navigation_profile_name,
    )

    selected = navigation_profile_name(navigation_profile)
    plan = navigation_fault_plan
    if plan is not None and type(plan) is not NavigationFaultPlan:
        plan = load_navigation_fault_plan(plan)
    if selected is NavigationProfileName.DIRECT and plan is not None:
        raise NavigationFaultPlanError(
            "navigation fault plans require the estimated profile"
        )
    if plan is not None:
        plan.validate_suite(
            suite_id=checked.suite_id,
            suite_sha256=checked.sha256,
            case_ids={case.case_id for case in checked.cases},
        )
    navigation = build_navigation_profile(
        selected, repository_root=repository_root
    )
    environment = _profile_environment()
    results = tuple(
        _run_case(
            adapter,
            checked,
            case,
            environment,
            navigation,
            None if plan is None else plan.fault_for(case.case_id),
        )
        for case in checked.cases
    )
    navigation_record = None
    result_schema_version = RESULT_SCHEMA_VERSION
    if navigation.identity is not None:
        result_schema_version = ESTIMATED_RESULT_SCHEMA_VERSION
        navigation_record = {
            "profile": selected.value,
            "identity": navigation.identity.to_dict(),
            "fault_plan": (
                None
                if plan is None
                else {**plan.to_dict(), "plan_sha256": plan.sha256}
            ),
            "controller_input_contract": {
                "fields": [
                    "step",
                    "time_s",
                    "range_m",
                    "relative_velocity_mps",
                    "propellant_fraction",
                    "sensor_quality",
                ],
                "excludes": [
                    "simulator truth",
                    "realized process disturbance",
                    "fault labels and schedules",
                    "evaluator outputs",
                    "covariance and NEES",
                ],
            },
            "harness_evaluator_outputs": [
                "success",
                "collision",
                "final_range_m",
                "final_speed_mps",
                "propellant_remaining",
                "steps",
            ],
            "classification": "illustrative_product_stress_run_not_scientific_evidence",
        }
    return FaultSuiteRunResult(
        suite_id=checked.suite_id,
        suite_sha256=checked.sha256,
        runtime_profile=checked.runtime_profile,
        controller=adapter.identity,
        cases=results,
        navigation=navigation_record,
        result_schema_version=result_schema_version,
    )


def run_fault_suite(
    plugin_spec: str,
    suite: FaultSuite | str | Path,
    *,
    navigation_profile: str = "direct",
    navigation_fault_plan=None,
    repository_root: str | Path = ".",
) -> FaultSuiteRunResult:
    """Load an external controller and run a suite from Python without internal edits."""

    loaded_suite = suite if isinstance(suite, FaultSuite) else load_fault_suite(suite)
    return run_loaded_fault_suite(
        load_controller(plugin_spec),
        loaded_suite,
        navigation_profile=navigation_profile,
        navigation_fault_plan=navigation_fault_plan,
        repository_root=repository_root,
    )


def replay_fault_suite(
    plugin_spec: str,
    suite: FaultSuite | str | Path,
    *,
    navigation_profile: str = "direct",
    navigation_fault_plan=None,
    repository_root: str | Path = ".",
) -> dict[str, object]:
    """Run two fresh adapter passes and require exact machine-result replay."""

    loaded_suite = suite if isinstance(suite, FaultSuite) else load_fault_suite(suite)
    first = run_fault_suite(
        plugin_spec,
        loaded_suite,
        navigation_profile=navigation_profile,
        navigation_fault_plan=navigation_fault_plan,
        repository_root=repository_root,
    )
    second = run_fault_suite(
        plugin_spec,
        loaded_suite,
        navigation_profile=navigation_profile,
        navigation_fault_plan=navigation_fault_plan,
        repository_root=repository_root,
    )
    if first.to_dict() != second.to_dict():
        raise FaultApplicationError(
            "controller declares deterministic=True but fault-suite replay differed"
        )
    return {
        "passed": True,
        "replay_match": True,
        "result": first.to_dict(),
    }
