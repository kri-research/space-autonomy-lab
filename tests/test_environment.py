from kri_space_autonomy.environment import ProximityEnvironment
from kri_space_autonomy.types import Action, SpacecraftState


def test_positive_acceleration_reduces_closing_rate():
    env = ProximityEnvironment()
    state = SpacecraftState(0, 20.0, -0.2, 1.0)
    next_state = env.step(state, Action(0.05))
    assert next_state.relative_velocity_mps > state.relative_velocity_mps
    assert next_state.step == 1
