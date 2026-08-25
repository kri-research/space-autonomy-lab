from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from pathlib import Path

from .controllers import DeterministicSafetyController, LearnedPolicyController
from .environment import EnvironmentConfig, ProximityEnvironment
from .evidence import EvidenceLogger
from .safety import RuntimeAssuranceMonitor, SafetyEnvelope
from .scenario import Scenario
from .types import GateDecision, SpacecraftState


@dataclass(frozen=True)
class EpisodeResult:
    scenario_id: str
    controller: str
    success: bool
    collision: bool
    steps: int
    interventions: int
    unsafe_state_steps: int
    final_range_m: float
    final_speed_mps: float
    propellant_remaining: float
    recovered_after_fault: bool

    def to_dict(self) -> dict:
        return asdict(self)


def run_episode(
    scenario: Scenario,
    controller_name: str = "protected",
    evidence_path: str | Path | None = None,
    config: EnvironmentConfig | None = None,
) -> EpisodeResult:
    cfg = config or EnvironmentConfig()
    environment = ProximityEnvironment(cfg)
    safety_controller = DeterministicSafetyController(cfg)
    learned_controller = LearnedPolicyController(cfg)
    monitor = RuntimeAssuranceMonitor(
        environment,
        safety_controller,
        SafetyEnvelope(),
        expected_model_hash=learned_controller.model_hash,
    )
    logger = EvidenceLogger(scenario.scenario_id)
    fault = copy.deepcopy(scenario.fault)

    state: SpacecraftState = scenario.initial_state
    interventions = 0
    unsafe_steps = 0
    fault_seen = False

    for _ in range(cfg.max_steps):
        if environment.is_collision(state) or environment.is_goal(state):
            break

        monitor_observation = environment.observe(state)
        autonomy_observation = fault.apply_observation(monitor_observation)

        fault_event = fault.apply_model(state.step, learned_controller)
        if fault_event is not None or autonomy_observation != monitor_observation:
            fault_seen = True

        if controller_name == "deterministic":
            policy_decision = safety_controller.decide(autonomy_observation)
            gate_decision = GateDecision(
                proposed=policy_decision.action,
                executed=policy_decision.action,
                overridden=False,
                reason=None,
                active_constraints=monitor.envelope.constraints(state),
            )
        elif controller_name in {"learned", "protected"}:
            policy_decision = learned_controller.decide(autonomy_observation)
            if controller_name == "protected":
                gate_decision = monitor.gate(state, monitor_observation, policy_decision)
            else:
                gate_decision = GateDecision(
                    proposed=policy_decision.action,
                    executed=policy_decision.action,
                    overridden=False,
                    reason=None,
                    active_constraints=monitor.envelope.constraints(state),
                )
        else:
            raise ValueError("controller_name must be deterministic, learned, or protected")

        if gate_decision.overridden:
            interventions += 1

        actual_action = fault.apply_action(state.step, gate_decision.executed)
        if actual_action != gate_decision.executed:
            fault_seen = True
            fault_event = fault_event or "ACTUATOR_EFFECTIVENESS_CHANGED"

        logger.append(
            state=state,
            autonomy_observation=autonomy_observation,
            policy_decision=policy_decision,
            gate_decision=gate_decision,
            executed_acceleration_mps2=actual_action.acceleration_mps2,
            fault_event=fault_event,
        )

        state = environment.step(state, actual_action)
        if not monitor.envelope.contains(state):
            unsafe_steps += 1

    success = environment.is_goal(state) and not environment.is_collision(state)
    recovered = bool(fault_seen and success)

    if evidence_path is not None:
        logger.write_jsonl(evidence_path)

    return EpisodeResult(
        scenario_id=scenario.scenario_id,
        controller=controller_name,
        success=success,
        collision=environment.is_collision(state),
        steps=state.step,
        interventions=interventions,
        unsafe_state_steps=unsafe_steps,
        final_range_m=state.range_m,
        final_speed_mps=state.relative_velocity_mps,
        propellant_remaining=state.propellant,
        recovered_after_fault=recovered,
    )
