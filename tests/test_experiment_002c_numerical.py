import inspect
import math
from dataclasses import replace

from kri_space_autonomy.experiment_002.config import load_config
from kri_space_autonomy.experiment_002.dynamics import TruthState, propagate_exact, state_at
from kri_space_autonomy.experiment_002.evaluator import IndependentEvaluator
from kri_space_autonomy.experiment_002b.config import load_amendment_config
from kri_space_autonomy.experiment_002b.seeds import (
    materialize_exogenous_002b,
    materialize_scenario_002b,
)
from kri_space_autonomy.experiment_002c.config import load_numerical_amendment_config
from kri_space_autonomy.experiment_002c.numerical import (
    KinkAwareReference,
    ReferenceEvaluator,
    _comparison,
    _event_order,
    _trace_outcome,
)


def test_collision_terminal_extrema_exclude_post_collision_motion():
    config = load_config("experiments/002/config.json")
    initial = TruthState(0.0, 1.01, -0.2, 0.9, -0.05)
    result = propagate_exact(initial, -0.05, 1.0, 0.0, 1.0, config)
    untruncated = state_at(initial, -0.05, 1.0, 0.0, 1.0, config)

    assert result.collision_time_s is not None
    assert result.minimum_range_m == config.collision_range_m
    assert result.maximum_range_m == initial.range_m
    assert math.isclose(
        result.maximum_abs_velocity_mps,
        abs(result.state.relative_velocity_mps),
        abs_tol=1e-13,
    )
    assert result.maximum_abs_velocity_mps < abs(untruncated.relative_velocity_mps)
    assert abs(result.collision_residual_m or 0.0) <= 1e-10


def test_collision_terminal_extrema_retain_pre_collision_interior_maximum():
    config = load_config("experiments/002/config.json")
    initial = TruthState(0.0, 1.01, 0.1, 0.9, -0.05)
    result = propagate_exact(initial, -0.05, 1.0, 0.0, 5.0, config)

    assert result.collision_time_s is not None
    assert math.isclose(result.maximum_range_m, 1.11, abs_tol=1e-10)
    assert result.maximum_range_m > max(initial.range_m, result.state.range_m)
    assert result.minimum_range_m == config.collision_range_m


def test_production_reports_depletion_time_and_raw_residual():
    config = load_config("experiments/002/config.json")
    initial = TruthState(0.0, 10.0, -0.1, 0.0001, 0.05)
    result = propagate_exact(initial, 0.05, 1.0, 0.0, 1.0, config)

    assert result.propellant_depleted
    assert result.depletion_time_s is not None
    assert 0.0 < result.depletion_time_s < result.state.time_s
    assert abs(result.depletion_residual_fraction or 0.0) <= 1e-12


def test_reference_is_kink_aware_and_does_not_call_exact_propagator():
    source = inspect.getsource(KinkAwareReference)
    assert "propagate_exact" not in source
    assert "acceleration_zero_event" in source
    assert "phase_sign_value" in source

    amendment, config = load_numerical_amendment_config(
        "experiments/002c/config.json"
    )
    reference = KinkAwareReference(
        config,
        amendment.reference_fine_rtol,
        amendment.reference_fine_atol,
        amendment.reference_fine_max_step_fraction,
    )
    initial = TruthState(0.0, 20.0, -0.2, 0.9, 0.05)
    exact = propagate_exact(initial, -0.05, 1.0, 0.0, 2.0, config)
    observed = reference.propagate(initial, -0.05, 1.0, 0.0, 2.0)

    assert len(observed.acceleration_zero_crossings_s) == 1
    assert math.isclose(
        observed.acceleration_zero_crossings_s[0],
        config.actuator_time_constant_s * math.log(2.0),
        abs_tol=1e-12,
    )
    assert abs(exact.state.range_m - observed.state.range_m) <= 1e-12
    assert (
        abs(exact.state.relative_velocity_mps - observed.state.relative_velocity_mps)
        <= 1e-12
    )
    assert abs(exact.state.propellant - observed.state.propellant) <= 1e-12


def test_reference_coarse_fine_converges_on_kink_and_depletion_fixtures():
    amendment, config = load_numerical_amendment_config(
        "experiments/002c/config.json"
    )
    fine = KinkAwareReference(
        config,
        amendment.reference_fine_rtol,
        amendment.reference_fine_atol,
        amendment.reference_fine_max_step_fraction,
    )
    coarse = KinkAwareReference(
        config,
        amendment.reference_coarse_rtol,
        amendment.reference_coarse_atol,
        amendment.reference_coarse_max_step_fraction,
    )
    fixtures = (
        (TruthState(0.0, 20.0, -0.2, 0.9, 0.05), -0.05, 2.0),
        (TruthState(0.0, 10.0, -0.1, 0.0001, 0.05), 0.05, 1.0),
    )
    convergence = amendment.acceptance_bounds.scaled(
        amendment.convergence_bound_fraction
    )
    for initial, command, duration in fixtures:
        tight = fine.propagate(initial, command, 1.0, 0.0, duration)
        loose = coarse.propagate(initial, command, 1.0, 0.0, duration)
        assert abs(tight.state.range_m - loose.state.range_m) <= convergence.range_m
        assert (
            abs(tight.state.relative_velocity_mps - loose.state.relative_velocity_mps)
            <= convergence.velocity_mps
        )
        assert (
            abs(
                tight.state.achieved_acceleration_mps2
                - loose.state.achieved_acceleration_mps2
            )
            <= convergence.achieved_acceleration_mps2
        )
        assert (
            abs(tight.state.propellant - loose.state.propellant)
            <= convergence.propellant_fraction
        )


def test_reference_uses_a_distinct_evaluator_and_event_order_is_explicit():
    assert not issubclass(ReferenceEvaluator, IndependentEvaluator)
    assert inspect.getsource(ReferenceEvaluator) != inspect.getsource(IndependentEvaluator)
    assert _event_order(None, None, 1e-12) == ()
    assert _event_order(2.0, None, 1e-12) == ("collision",)
    assert _event_order(None, 1.0, 1e-12) == ("depletion",)
    assert _event_order(2.0, 1.0, 1e-12) == ("depletion", "collision")
    assert _event_order(1.0, 1.0 + 5e-13, 1e-12) == ("collision+depletion",)


def test_short_trace_compares_all_categories_without_a_shared_evaluator():
    amendment, production = load_numerical_amendment_config(
        "experiments/002c/config.json"
    )
    controller_amendment, _ = load_amendment_config("experiments/002b/config.json")
    short = replace(production, horizon_s=2.0)
    spec = materialize_scenario_002b(
        controller_amendment, short, "fixed_replay", "P0_nominal", 0
    )
    streams, _ = materialize_exogenous_002b(
        controller_amendment, short, "fixed_replay", "P0_nominal", 0
    )
    commands = [(0.0, 0.05), (1.0, -0.05)]
    reference = KinkAwareReference(
        short,
        amendment.reference_fine_rtol,
        amendment.reference_fine_atol,
        amendment.reference_fine_max_step_fraction,
    )
    production_outcome = _trace_outcome(
        "production_exact", amendment, short, spec, streams, commands, None
    )
    reference_outcome = _trace_outcome(
        "reference_fine", amendment, short, spec, streams, commands, reference
    )
    comparison = _comparison(
        production_outcome,
        reference_outcome,
        amendment.acceptance_bounds,
        require_raw_residual_bounds=True,
    )

    assert comparison["passed"], comparison
    assert set(comparison["category_maxima"]) == {
        "range_m",
        "velocity_mps",
        "achieved_acceleration_mps2",
        "propellant_fraction",
        "event_time_s",
        "dwell_fraction",
        "collision_residual_m",
        "depletion_residual_fraction",
    }
