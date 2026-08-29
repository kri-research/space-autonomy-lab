import inspect

from kri_space_autonomy.experiment_002.config import load_config
from kri_space_autonomy.experiment_002.dynamics import TruthState, propagate_exact
from kri_space_autonomy.experiment_002b.config import load_amendment_config
from kri_space_autonomy.experiment_002b.numerical import HighAccuracyReference


def test_reference_implementation_does_not_call_production_propagator():
    source = inspect.getsource(HighAccuracyReference)
    assert "propagate_exact" not in source
    assert "DOP853" in source


def test_independent_reference_matches_exact_smooth_interval():
    amendment, production = load_amendment_config("experiments/002b/config.json")
    reference = HighAccuracyReference(
        production, amendment.reference_rtol, amendment.reference_atol
    )
    initial = TruthState(0.0, 20.0, -0.2, 0.9, 0.01)
    exact = propagate_exact(initial, 0.04, 0.7, -0.002, 0.25, production)
    observed = reference.propagate(initial, 0.04, 0.7, -0.002, 0.25)
    errors = [
        abs(exact.state.range_m - observed.state.range_m),
        abs(exact.state.relative_velocity_mps - observed.state.relative_velocity_mps),
        abs(
            exact.state.achieved_acceleration_mps2
            - observed.state.achieved_acceleration_mps2
        ),
        abs(exact.state.propellant - observed.state.propellant),
        abs(exact.minimum_range_m - observed.minimum_range_m),
    ]
    assert max(errors) <= amendment.numerical_error_tolerance


def test_reference_handles_collision_and_depletion_classes():
    config = load_config("experiments/002/config.json")
    amendment, _ = load_amendment_config("experiments/002b/config.json")
    reference = HighAccuracyReference(config, amendment.reference_rtol, amendment.reference_atol)
    collision_initial = TruthState(0.0, 1.01, -0.2, 0.9, 0.0)
    collision = reference.propagate(collision_initial, -0.05, 1.0, 0.0, 0.25)
    assert collision.collision_time_s is not None
    depletion_initial = TruthState(0.0, 20.0, 0.0, 1e-5, 0.05)
    depletion = reference.propagate(depletion_initial, 0.05, 1.0, 0.0, 0.25)
    assert depletion.propellant_depleted
    assert depletion.state.propellant == 0.0
