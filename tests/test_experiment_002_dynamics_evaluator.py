import math
from dataclasses import replace

from kri_space_autonomy.experiment_002.config import load_config
from kri_space_autonomy.experiment_002.dynamics import (
    PropagationResult,
    TruthState,
    propagate_exact,
)
from kri_space_autonomy.experiment_002.evaluator import (
    IndependentEvaluator,
    braking_margin_m,
    classify_recovery,
    reachable_stopping_distance_m,
)


def config():
    return load_config("experiments/002/config.json")


def test_analytical_actuator_response_and_dt_scaled_propellant():
    cfg = config()
    state = TruthState(0.0, 20.0, -0.2, 0.9, 0.02)
    result = propagate_exact(state, 0.02, 1.0, 0.0, 2.0, cfg)
    assert math.isclose(result.state.achieved_acceleration_mps2, 0.02, abs_tol=1e-14)
    assert math.isclose(
        result.state.propellant,
        0.9 - cfg.propellant_cost_per_delta_v * 0.02 * 2.0,
        abs_tol=1e-13,
    )


def test_continuous_collision_between_safe_endpoints():
    cfg = config()
    state = TruthState(0.0, 1.001, -0.02, 1.0, 0.05)
    endpoint_without_absorption = 1.001 - 0.02 + 0.5 * 0.05
    assert endpoint_without_absorption > cfg.collision_range_m
    result = propagate_exact(state, 0.05, 1.0, 0.0, 1.0, cfg)
    assert result.collision_time_s is not None
    assert math.isclose(result.state.range_m, cfg.collision_range_m, abs_tol=1e-12)


def test_propellant_depletion_disables_thrust_immediately():
    cfg = config()
    state = TruthState(0.0, 10.0, -0.1, 0.0001, 0.05)
    result = propagate_exact(state, 0.05, 1.0, 0.0, 1.0, cfg)
    assert result.propellant_depleted
    assert result.state.propellant == 0.0
    assert result.state.achieved_acceleration_mps2 == 0.0


def test_reachable_stopping_accounts_for_lag_effectiveness_and_propellant():
    cfg = config()
    equilibrium = cfg.max_acceleration_mps2
    ready = TruthState(0.0, 20.0, -0.2, 0.9, equilibrium)
    lagged = TruthState(0.0, 20.0, -0.2, 0.9, -equilibrium)
    degraded = TruthState(0.0, 20.0, -0.2, 0.9, equilibrium * 0.4)
    ready_distance = reachable_stopping_distance_m(ready, 1.0, cfg)
    assert lagged.relative_velocity_mps < 0
    assert reachable_stopping_distance_m(lagged, 1.0, cfg) > ready_distance
    assert reachable_stopping_distance_m(degraded, 0.4, cfg) > ready_distance
    depleted = replace(ready, propellant=0.0)
    assert math.isinf(reachable_stopping_distance_m(depleted, 1.0, cfg))


def test_evaluator_is_independent_of_gate_threshold():
    state = TruthState(0.0, 10.0, -0.1, 0.9, 0.0)
    base = config()
    mutated_gate = replace(base, gate_min_range_m=1000.0)
    assert braking_margin_m(state, 1.0, base) == braking_margin_m(state, 1.0, mutated_gate)


def test_final_sixty_seconds_must_be_continuously_in_goal():
    cfg = config()
    state = TruthState(540.0, 6.5, 0.0, 0.8, 0.0)
    evaluator = IndependentEvaluator(cfg, state, 1.0)
    end = TruthState(600.0, 6.5, 0.0, 0.79, 0.0)
    interval = PropagationResult(end, 5.5, 7.5, 0.05, None, False)
    evaluator.observe_interval(state, interval)
    summary = evaluator.finalize(end)
    assert summary.sustained_success
    bad = IndependentEvaluator(cfg, state, 1.0)
    bad.observe_interval(state, PropagationResult(end, 4.99, 7.5, 0.05, None, False))
    assert not bad.finalize(end).sustained_success


def test_recovery_precedence_and_persistent_upset_rule():
    cfg = config()
    samples = [(time, not (10.0 <= time < 50.0)) for time in range(0, 301)]
    recovered = classify_recovery(
        samples,
        5.0,
        20.0,
        False,
        True,
        False,
        False,
        "PD",
        cfg,
    )
    assert recovered["recovery_state"] == "RECOVERED"
    graceful = classify_recovery(
        samples,
        5.0,
        None,
        False,
        True,
        True,
        True,
        "PD",
        cfg,
    )
    assert graceful["recovery_state"] == "GRACEFUL_DEGRADED"
    failed = classify_recovery([(0.0, True)], 0.0, 1.0, True, True, False, False, "PD", cfg)
    assert failed["recovery_state"] == "FAILED"
