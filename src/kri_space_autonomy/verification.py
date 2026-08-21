from __future__ import annotations

import itertools

from .controllers import DeterministicSafetyController
from .environment import ProximityEnvironment
from .safety import RuntimeAssuranceMonitor, SafetyEnvelope
from .types import Action, PolicyDecision, SpacecraftState


def bounded_gate_check() -> dict:
    """Exercise the runtime gate over a finite grid of states and actions.

    The property checked is narrow: whenever the gate permits a proposed action, the predicted
    next state must remain inside the configured Safe Flight Envelope. This is regression evidence,
    not formal reachability analysis or proof of KRI-STD-001 conformance.
    """

    environment = ProximityEnvironment()
    envelope = SafetyEnvelope(propellant_reserve=environment.config.propellant_reserve)
    fallback = DeterministicSafetyController(environment.config)
    monitor = RuntimeAssuranceMonitor(environment, fallback, envelope)

    ranges = [2.1, 3.0, 5.1, 7.0, 8.1, 10.0, 12.1, 20.0, 25.1, 40.0, 60.1, 100.0]
    velocities = [-0.7, -0.4, -0.22, -0.12, -0.07, -0.02, 0.0, 0.2]
    propellants = [0.10, 0.20, 0.75, 1.0]
    actions = [Action(a) for a in (-0.05, -0.025, 0.0, 0.025, 0.05)]

    checked = 0
    permitted = 0
    overridden = 0
    violations: list[dict] = []

    for range_m, velocity, propellant, action in itertools.product(
        ranges, velocities, propellants, actions
    ):
        state = SpacecraftState(0, range_m, velocity, propellant)
        if not envelope.contains(state):
            continue
        checked += 1
        obs = environment.observe(state)
        decision = PolicyDecision(action, 1.0, action.acceleration_mps2, "verification-fixture")
        gated = monitor.gate(state, obs, decision)
        if gated.overridden:
            overridden += 1
            continue
        permitted += 1
        next_state = environment.step(state, gated.executed)
        if not envelope.contains(next_state):
            violations.append(
                {
                    "state": state.to_dict(),
                    "action": action.to_dict(),
                    "next_state": next_state.to_dict(),
                }
            )

    return {
        "checked_state_action_pairs": checked,
        "permitted_pairs": permitted,
        "overridden_pairs": overridden,
        "violations": violations,
        "passed": not violations,
        "scope": "finite bounded grid; not formal verification",
    }
