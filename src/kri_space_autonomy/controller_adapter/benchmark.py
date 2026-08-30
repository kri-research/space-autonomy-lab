from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from numbers import Real
from pathlib import Path

from kri_space_autonomy.environment import EnvironmentConfig, ProximityEnvironment
from kri_space_autonomy.scenario import Scenario, load_scenario
from kri_space_autonomy.types import Action

from .adapter import ControllerAdapter, load_controller
from .contract import ControllerContext, ObservationStatus
from .errors import ControllerContractError, UnsupportedScenarioError


@dataclass(frozen=True, slots=True)
class ExternalEpisodeResult:
    scenario_id: str
    scenario_fault: str
    controller_id: str
    controller_version: str
    contract_version: str
    plugin_module_sha256: str
    success: bool
    collision: bool
    steps: int
    commands: int
    degraded_observation_steps: int
    missing_observation_steps: int
    final_range_m: float
    final_speed_mps: float
    propellant_remaining: float
    command_trace_sha256: str
    navigation: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        if self.navigation is None:
            result.pop("navigation")
        return result


def _trace_digest(trace: list[dict[str, int | float]]) -> str:
    payload = json.dumps(
        trace,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_runtime(config: EnvironmentConfig) -> None:
    values = {
        "dt_s": config.dt_s,
        "min_range_m": config.min_range_m,
        "goal_min_range_m": config.goal_min_range_m,
        "goal_max_range_m": config.goal_max_range_m,
        "goal_max_speed_mps": config.goal_max_speed_mps,
        "max_acceleration_mps2": config.max_acceleration_mps2,
        "propellant_cost_per_mps2": config.propellant_cost_per_mps2,
        "propellant_reserve": config.propellant_reserve,
    }
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ControllerContractError(f"environment {name} must be a finite real scalar")
    if config.dt_s <= 0.0:
        raise ControllerContractError("environment dt_s must be positive")
    if config.min_range_m < 0.0:
        raise ControllerContractError("environment min_range_m must be non-negative")
    if not config.min_range_m < config.goal_min_range_m < config.goal_max_range_m:
        raise ControllerContractError(
            "environment ranges must satisfy min_range_m < goal_min_range_m < goal_max_range_m"
        )
    if config.goal_max_speed_mps < 0.0:
        raise ControllerContractError("environment goal speed must be non-negative")
    if config.max_acceleration_mps2 <= 0.0:
        raise ControllerContractError("environment acceleration bound must be positive")
    if type(config.max_steps) is not int or config.max_steps <= 0:
        raise ControllerContractError("environment max_steps must be a positive integer")
    if config.propellant_cost_per_mps2 < 0.0:
        raise ControllerContractError("environment propellant cost must be non-negative")
    if not 0.0 <= config.propellant_reserve <= 1.0:
        raise ControllerContractError("environment propellant reserve must be in [0, 1]")


def _validate_scenario(scenario: Scenario) -> None:
    if type(scenario) is not Scenario:
        raise ControllerContractError("scenario must be a Scenario")
    if not isinstance(scenario.scenario_id, str) or not scenario.scenario_id:
        raise ControllerContractError("scenario_id must be a non-empty string")
    state = scenario.initial_state
    if type(state.step) is not int or state.step != 0:
        raise ControllerContractError("scenario initial step must be integer zero")
    values = {
        "initial range_m": state.range_m,
        "initial relative_velocity_mps": state.relative_velocity_mps,
        "initial propellant": state.propellant,
    }
    for name, value in values.items():
        if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
            raise ControllerContractError(f"scenario {name} must be a finite real scalar")
    if not 0.0 <= state.propellant <= 1.0:
        raise ControllerContractError("scenario initial propellant must be in [0, 1]")


def run_loaded_controller(
    adapter: ControllerAdapter,
    scenario: Scenario,
    config: EnvironmentConfig | None = None,
    *,
    navigation_profile: str = "direct",
    repository_root: str | Path = ".",
) -> ExternalEpisodeResult:
    """Run one simplified RPO episode without exposing internal state to the controller."""

    cfg = EnvironmentConfig() if config is None else config
    if type(cfg) is not EnvironmentConfig:
        raise ControllerContractError("config must be an EnvironmentConfig")
    _validate_runtime(cfg)
    _validate_scenario(scenario)
    environment = ProximityEnvironment(cfg)
    fault = copy.deepcopy(scenario.fault)
    fault_name = str(getattr(fault, "name", "unknown"))
    if fault_name == "model_seu":
        raise UnsupportedScenarioError(
            "model_seu targets the built-in learned-policy representation and is not part of "
            "the external controller contract"
        )
    context = ControllerContext(
        command_period_s=cfg.dt_s,
        minimum_acceleration_mps2=-cfg.max_acceleration_mps2,
        maximum_acceleration_mps2=cfg.max_acceleration_mps2,
    )
    from kri_space_autonomy.navigation_profiles import build_navigation_profile

    navigation = build_navigation_profile(
        navigation_profile, repository_root=repository_root
    )
    navigation.validate_initial_navigation(
        scenario.initial_state.range_m,
        scenario.initial_state.relative_velocity_mps,
    )
    navigation.reset(context)
    adapter.reset(context)

    state = scenario.initial_state
    command_trace: list[dict[str, int | float]] = []
    degraded_steps = 0
    missing_steps = 0
    for _ in range(cfg.max_steps):
        if environment.is_collision(state) or environment.is_goal(state):
            break
        observable = fault.apply_observation(environment.observe(state))
        public_observation = navigation.observe(observable)
        if public_observation.status is not ObservationStatus.NOMINAL:
            degraded_steps += 1
        if public_observation.status is ObservationStatus.MISSING:
            missing_steps += 1
        command = adapter.command(public_observation)
        navigation.accept_command(command.acceleration_mps2)
        command_trace.append(
            {
                "step": public_observation.step,
                "acceleration_mps2": command.acceleration_mps2,
            }
        )
        executed = fault.apply_action(state.step, Action(command.acceleration_mps2))
        state = environment.step(state, executed)

    identity = adapter.identity
    navigation_diagnostics = navigation.diagnostics()
    navigation_record = None
    if navigation_diagnostics is not None and navigation.identity is not None:
        navigation_record = {
            "identity": navigation.identity.to_dict(),
            "diagnostics": navigation_diagnostics.to_dict(),
            "information_boundary": {
                "controller_inputs": "ControllerObservation fields only",
                "harness_evaluator_outputs": (
                    "success, collision, final range/speed, propellant, and step counts; "
                    "never passed to the controller"
                ),
            },
        }
    return ExternalEpisodeResult(
        scenario_id=scenario.scenario_id,
        scenario_fault=fault_name,
        controller_id=identity.controller_id,
        controller_version=identity.controller_version,
        contract_version=identity.contract_version,
        plugin_module_sha256=identity.plugin_module_sha256,
        success=environment.is_goal(state) and not environment.is_collision(state),
        collision=environment.is_collision(state),
        steps=state.step,
        commands=len(command_trace),
        degraded_observation_steps=degraded_steps,
        missing_observation_steps=missing_steps,
        final_range_m=state.range_m,
        final_speed_mps=state.relative_velocity_mps,
        propellant_remaining=state.propellant,
        command_trace_sha256=_trace_digest(command_trace),
        navigation=navigation_record,
    )


def run_external_controller(
    plugin_spec: str,
    scenario_path: str | Path,
    config: EnvironmentConfig | None = None,
    *,
    navigation_profile: str = "direct",
    repository_root: str | Path = ".",
) -> ExternalEpisodeResult:
    """Load an external controller and run one scenario through the public facade."""

    adapter = load_controller(plugin_spec)
    scenario = load_scenario(scenario_path)
    return run_loaded_controller(
        adapter,
        scenario,
        config,
        navigation_profile=navigation_profile,
        repository_root=repository_root,
    )


def replay_external_controller(
    plugin_spec: str,
    scenario_path: str | Path,
    config: EnvironmentConfig | None = None,
    *,
    navigation_profile: str = "direct",
    repository_root: str | Path = ".",
) -> dict[str, object]:
    """Run two load/reset passes and fail if deterministic episode results differ."""

    first = run_external_controller(
        plugin_spec,
        scenario_path,
        config,
        navigation_profile=navigation_profile,
        repository_root=repository_root,
    )
    second = run_external_controller(
        plugin_spec,
        scenario_path,
        config,
        navigation_profile=navigation_profile,
        repository_root=repository_root,
    )
    first_record = first.to_dict()
    if first_record != second.to_dict():
        raise ControllerContractError(
            "controller declares deterministic=True but episode reset replay differed"
        )
    return {
        "passed": True,
        "replay_match": True,
        "result": first_record,
    }
