import numpy as np

from kri_space_autonomy.experiment_005.config import load_config
from kri_space_autonomy.experiment_005.dynamics import circular_chief_state, pair_from_relative
from kri_space_autonomy.experiment_005.geometry import (
    IndependentTruthEvaluator,
    NonlinearTruthSegment,
    admissible_position_excess_m,
    evaluate_truth_segment,
)


def config():
    return load_config("experiments/005/config.json")


def segment(relative, duration=1.0):
    study = config()
    chief = circular_chief_state(
        study.gravitational_parameter_m3_s2, study.reference_radius_m
    )
    return NonlinearTruthSegment(
        pair_from_relative(chief, np.asarray(relative, dtype=np.float64)),
        np.zeros(3),
        study,
        duration,
    )


def test_truth_space_detects_interior_collision_with_safe_endpoints():
    study = config()
    truth = segment([5.0, 0.0, 0.0, -10.0, 0.0, 0.0])
    result = evaluate_truth_segment(truth, study)
    assert np.linalg.norm(truth.relative_state_at(0.0)[:3]) > study.hard_body_radius_m
    assert np.linalg.norm(truth.relative_state_at(1.0)[:3]) > study.hard_body_radius_m
    assert result.collision
    assert result.keep_out_entry
    assert result.minimum_separation_m < 0.01
    assert 0.49 < result.minimum_separation_time_s < 0.51


def test_admissible_union_fails_closed_at_both_longitudinal_ends():
    study = config()
    below = evaluate_truth_segment(
        segment([0.0, -101.0, 0.0, 0.0, 0.0, 0.0], 0.1), study
    )
    above = evaluate_truth_segment(
        segment([0.0, -26.0, 0.0, 0.0, 0.0, 0.0], 0.1), study
    )
    hold = np.array([0.0, -29.0, 0.0, 0.0, 0.0, 0.0])
    assert below.corridor_departure
    assert above.corridor_departure
    assert admissible_position_excess_m(hold, study) <= 0.0


def test_independent_evaluator_consumes_only_truth_segment():
    study = config()
    evaluator = IndependentTruthEvaluator(study)
    evaluator.observe(segment([5.0, 0.0, 0.0, -10.0, 0.0, 0.0]))
    summary = evaluator.finalize()
    assert summary.collision
    assert summary.unauthorized_keep_out_entry
