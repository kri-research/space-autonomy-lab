import numpy as np
import pytest

from kri_space_autonomy.experiment_004.config import load_config
from kri_space_autonomy.experiment_004.evaluation import (
    IndependentPlanarEvaluator,
    TechnicalStatus,
)
from kri_space_autonomy.experiment_004.geometry import (
    HCWSegment,
    corridor_halfwidth_m,
    evaluate_hold_segment,
    evaluate_segment,
)


def config():
    return load_config("experiments/004/config.json")


def segment(state, command=None, duration=1.0):
    study = config()
    return HCWSegment(
        np.asarray(state, dtype=np.float64),
        np.zeros(2) if command is None else np.asarray(command, dtype=np.float64),
        study.mean_motion_rad_s,
        duration,
        maximum_duration_s=study.event_interval_max_s,
    )


def test_collision_is_detected_on_exact_hcw_arc_when_endpoints_are_safe():
    study = config()
    arc = segment([5.0, 0.0, -10.0, 0.0])
    result = evaluate_segment(arc, study)
    assert np.linalg.norm(arc.start_state[:2]) > study.hard_body_radius_m
    assert np.linalg.norm(arc.state_at(1.0)[:2]) > study.hard_body_radius_m
    assert result.collision
    assert result.keep_out_entry
    assert result.minimum_separation_m < 0.01
    assert 0.49 < result.minimum_separation_time_s < 0.51


def test_closed_boundary_and_near_boundary_semantics_are_explicit():
    study = config()
    boundary = evaluate_segment(
        segment([study.hard_body_radius_m, 0.0, 0.0, 0.0], duration=0.01),
        study,
    )
    outside = evaluate_segment(
        segment([study.keep_out_radius_m + 1e-6, 0.0, 0.0, 0.0], duration=0.01),
        study,
    )
    assert boundary.collision
    assert not outside.keep_out_entry


def test_tapered_vbar_corridor_has_frozen_widths_and_detects_departure():
    study = config()
    assert corridor_halfwidth_m(-100.0, study) == 10.0
    assert corridor_halfwidth_m(-30.0, study) == 3.0
    assert corridor_halfwidth_m(-65.0, study) == pytest.approx(6.5)
    inside = evaluate_segment(segment([0.0, -50.0, 0.0, 0.0]), study)
    outside = evaluate_segment(segment([8.0, -50.0, 0.0, 0.0]), study)
    assert not inside.corridor_departure
    assert outside.corridor_departure


def test_hold_dwell_uses_whole_exact_segment_not_endpoint_only():
    study = config()
    hold = segment([0.0, -30.0, 0.0, 0.0])
    outside = segment([3.0, -30.0, 0.0, 0.0])
    assert evaluate_hold_segment(hold, study).entirely_inside
    assert not evaluate_hold_segment(outside, study).entirely_inside
    evaluator = IndependentPlanarEvaluator(study)
    for _ in range(int(study.hold_required_dwell_s)):
        evaluator.observe(hold)
    summary = evaluator.finalize(TechnicalStatus())
    assert summary.mission.hold_acquired
    assert summary.mission.maximum_contiguous_hold_dwell_s == study.hold_required_dwell_s


def test_geometry_interval_must_be_split_at_frozen_event_period():
    study = config()
    with pytest.raises(ValueError, match="split"):
        HCWSegment(
            np.array([0.0, -50.0, 0.0, 0.0]),
            np.zeros(2),
            study.mean_motion_rad_s,
            1.1,
            maximum_duration_s=study.event_interval_max_s,
        )
