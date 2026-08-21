from kri_space_autonomy.controllers import DeterministicSafetyController
from kri_space_autonomy.environment import ProximityEnvironment
from kri_space_autonomy.safety import RuntimeAssuranceMonitor
from kri_space_autonomy.types import Action, PolicyDecision, SpacecraftState


def test_gate_rejects_low_confidence_policy():
    env = ProximityEnvironment()
    fallback = DeterministicSafetyController()
    monitor = RuntimeAssuranceMonitor(env, fallback)
    state = SpacecraftState(0, 10.0, -0.05, 1.0)
    obs = env.observe(state)
    decision = PolicyDecision(Action(-0.05), 0.1, -0.05, "model")
    gated = monitor.gate(state, obs, decision)
    assert gated.overridden
    assert gated.reason == "LOW_CONFIDENCE"


def test_gate_rejects_action_that_exits_envelope():
    env = ProximityEnvironment()
    fallback = DeterministicSafetyController()
    monitor = RuntimeAssuranceMonitor(env, fallback)
    state = SpacecraftState(0, 5.1, -0.06, 1.0)
    obs = env.observe(state)
    decision = PolicyDecision(Action(-0.05), 1.0, -0.05, "model")
    gated = monitor.gate(state, obs, decision)
    assert gated.overridden
    assert gated.reason == "SAFE_FLIGHT_ENVELOPE"


def test_gate_rejects_unexpected_model_hash():
    env = ProximityEnvironment()
    fallback = DeterministicSafetyController()
    monitor = RuntimeAssuranceMonitor(env, fallback, expected_model_hash="expected")
    state = SpacecraftState(0, 20.0, -0.1, 1.0)
    obs = env.observe(state)
    decision = PolicyDecision(Action(0.0), 1.0, 0.0, "unexpected")
    gated = monitor.gate(state, obs, decision)
    assert gated.overridden
    assert gated.reason == "MODEL_INTEGRITY"
