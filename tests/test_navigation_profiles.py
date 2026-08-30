from __future__ import annotations

import hashlib
import importlib
import json
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path

import pytest

from kri_space_autonomy.assurance_report import (
    ESTIMATED_REPORT_SCHEMA_VERSION,
    AssessmentResultSpecError,
    assess_controller,
    fault_suite_result_from_dict,
)
from kri_space_autonomy.controller_adapter import (
    ControllerContext,
    ControllerContractError,
    ControllerObservation,
    ObservationStatus,
    run_external_controller,
)
from kri_space_autonomy.controller_adapter.cli import main as controller_adapter_main
from kri_space_autonomy.demo import build_demo_bundle
from kri_space_autonomy.demo.cli import main as demo_main
from kri_space_autonomy.fault_suite import (
    ESTIMATED_RESULT_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    canonical_json,
    load_fault_suite,
    replay_fault_suite,
    run_fault_suite,
)
from kri_space_autonomy.navigation_profiles import (
    FOUNDATION_FREEZE_ID,
    EstimatedNavigationProfile,
    NavigationFaultPlanError,
    NavigationProfileError,
    build_navigation_profile,
    controller_observation_from_snapshot,
    load_frozen_navigation_assets,
    load_navigation_fault_plan,
    loads_navigation_fault_plan,
)

EXAMPLE = "kri_space_autonomy.examples.proportional_controller:controller"
DIRECT_SUITE = Path("fault-suites/example-rpo.json")
ESTIMATED_SUITE = Path("fault-suites/example-estimated-rpo.json")
ESTIMATED_PLAN = Path("navigation-fault-plans/example-estimated-rpo.json")
ESTIMATED_POLICY = Path("assessment-policies/example-estimated-rpo.json")
EXPECTED_CONFIG_SHA256 = "e83f59a5c3c86defab150285b1dc30d170b08f82c8f949a348944efe5963b4c9"
EXPECTED_ESTIMATOR_SHA256 = "3502d00eef9a4a34417775ca1e20fc609a2726797c7a30ddb564d5fc58a3d481"


@pytest.fixture(scope="module")
def estimated_result():
    return run_fault_suite(
        EXAMPLE,
        ESTIMATED_SUITE,
        navigation_profile="estimated",
        navigation_fault_plan=ESTIMATED_PLAN,
    )


def test_same_external_controller_runs_under_direct_and_estimated_profiles():
    direct = run_external_controller(EXAMPLE, "scenarios/nominal.json")
    estimated = run_external_controller(
        EXAMPLE,
        "scenarios/nominal.json",
        navigation_profile="estimated",
    )
    assert direct.controller_id == estimated.controller_id == "example.proportional"
    assert direct.success is True
    assert estimated.success is True
    assert "navigation" not in direct.to_dict()
    assert estimated.to_dict()["navigation"]["diagnostics"]["profile"] == "estimated"


def test_direct_profile_default_and_explicit_results_are_exactly_backwards_compatible():
    implicit = run_fault_suite(EXAMPLE, DIRECT_SUITE)
    explicit = run_fault_suite(EXAMPLE, DIRECT_SUITE, navigation_profile="direct")
    assert implicit.to_dict() == explicit.to_dict()
    assert implicit.result_schema_version == RESULT_SCHEMA_VERSION
    assert "navigation" not in implicit.to_dict()
    assert implicit.result_sha256 == (
        "22f48f4440eb9b2cb54e0a8dbbab36a9918499de11b5091fc39bedc2f7f4d0c4"
    )


def test_estimated_profile_reuses_exact_frozen_config_and_implementation_identity():
    study, production, identity = load_frozen_navigation_assets()
    frozen = identity.frozen_file_sha256
    assert identity.foundation_freeze_id == FOUNDATION_FREEZE_ID
    assert frozen["experiments/003/config.json"] == EXPECTED_CONFIG_SHA256
    assert (
        frozen["src/kri_space_autonomy/experiment_003/estimator.py"]
        == EXPECTED_ESTIMATOR_SHA256
    )
    assert identity.estimator_class.endswith("experiment_003.estimator.NavigationFilter")
    assert identity.measurement_factory.endswith("experiment_003.measurements.navigation_packet")
    assert study.nis_reject_threshold == 13.815510557964274
    assert study.covariance_underreporting_factor == 0.25
    assert study.degraded_after_prediction_only_s == 2.0
    assert production.command_period_s == 1.0
    assert production.actuator_time_constant_s == 0.5


def test_frozen_asset_hash_drift_fails_before_profile_execution(monkeypatch):
    import kri_space_autonomy.navigation_profiles.profile as profile_module

    original = profile_module._file_sha256

    def drift(path: Path) -> str:
        if path.as_posix().endswith("experiments/003/config.json"):
            return "0" * 64
        return original(path)

    monkeypatch.setattr(profile_module, "_file_sha256", drift)
    with pytest.raises(NavigationProfileError, match="asset hash mismatch"):
        build_navigation_profile("estimated")


def test_controller_receives_only_unchanged_public_fields_in_estimated_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module_name = "estimated_observation_recorder"
    source = '''
from dataclasses import fields
from kri_space_autonomy.controller_adapter import (
    ControllerCommand, ControllerMetadata, ObservationStatus,
)

class RecordingController:
    metadata = ControllerMetadata(controller_id="test.estimated-recorder", controller_version="1")

    def reset(self, context):
        self.maximum = context.maximum_acceleration_mps2
        self.seen = []

    def command(self, observation):
        self.seen.append(tuple(item.name for item in fields(observation)))
        command = self.maximum if observation.status is ObservationStatus.MISSING else 0.0
        return ControllerCommand(command)

controller = RecordingController()
'''
    (tmp_path / f"{module_name}.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    run_external_controller(
        f"{module_name}:controller",
        "scenarios/nominal.json",
        navigation_profile="estimated",
    )
    module = importlib.import_module(module_name)
    expected = tuple(field.name for field in fields(ControllerObservation))
    assert module.controller.seen
    assert set(module.controller.seen) == {expected}
    assert expected == (
        "step",
        "time_s",
        "range_m",
        "relative_velocity_mps",
        "propellant_fraction",
        "sensor_quality",
    )
    assert not {
        "truth_state",
        "realized_process_disturbance",
        "fault_label",
        "fault_schedule",
        "evaluator_output",
        "covariance",
        "nees",
    }.intersection(expected)


def test_estimated_replay_and_fingerprints_are_exact(estimated_result):
    replay = replay_fault_suite(
        EXAMPLE,
        ESTIMATED_SUITE,
        navigation_profile="estimated",
        navigation_fault_plan=ESTIMATED_PLAN,
    )
    assert replay["passed"] is True
    assert replay["replay_match"] is True
    assert replay["result"] == estimated_result.to_dict()
    assert estimated_result.result_schema_version == ESTIMATED_RESULT_SCHEMA_VERSION
    assert estimated_result.navigation is not None
    identity = estimated_result.navigation["identity"]
    assert len(identity["identity_sha256"]) == 64
    assert len(estimated_result.result_sha256) == 64


def test_bias_dropout_stale_and_covariance_examples_exercise_navigation(estimated_result):
    cases = {case.case_id: case for case in estimated_result.cases}
    bias = cases["range-bias"].navigation
    dropout = cases["navigation-dropout"].navigation
    stale = cases["stale-packet"].navigation
    covariance = cases["biased-covariance-underreporting"].navigation
    assert bias is not None and bias["innovation_rejections"] == 51
    assert bias["packet_disposition_counts"]["innovation_rejected"] == 51
    assert dropout is not None and dropout["missing_packet_steps"] == 16
    assert dropout["controller_observation_status_counts"] == {
        "nominal": 314,
        "degraded": 14,
        "missing": 0,
    }
    assert stale is not None and stale["packet_disposition_counts"]["duplicate"] == 16
    assert stale["invalid_packets"] == 16
    assert covariance is not None and covariance["innovation_rejections"] == 21
    assert covariance["packet_fault"]["type"] == "covariance_underreporting"
    assert all(case.navigation["final_health"] != "diverged" for case in cases.values())


def test_diverged_filter_maps_to_missing_controller_navigation_without_truth_fill():
    profile = EstimatedNavigationProfile()
    context = ControllerContext(1.0, -0.05, 0.05)
    profile.reset(context)
    diverged = profile.frozen_filter.advance(1e9, 1.0)
    public = controller_observation_from_snapshot(
        diverged,
        step=1,
        propellant_fraction=0.9,
        command_period_s=1.0,
    )
    assert public.status is ObservationStatus.MISSING
    assert public.range_m is None
    assert public.relative_velocity_mps is None
    assert public.sensor_quality == 0.0


def test_estimated_profile_rejects_incompatible_initial_state_before_controller_run():
    suite = load_fault_suite(ESTIMATED_SUITE)
    incompatible = replace(
        suite,
        initial_state=replace(suite.initial_state, range_m=20_000.0),
    )
    with pytest.raises(NavigationProfileError, match="state limits"):
        run_fault_suite(EXAMPLE, incompatible, navigation_profile="estimated")


def test_malformed_controller_output_still_fails_closed_in_estimated_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    module_name = "estimated_bad_output_controller"
    source = '''
from kri_space_autonomy.controller_adapter import ControllerMetadata
class BadController:
    metadata = ControllerMetadata(controller_id="test.bad-estimated", controller_version="1")
    def reset(self, context):
        return None
    def command(self, observation):
        return {"acceleration_mps2": 0.0}
controller = BadController()
'''
    (tmp_path / f"{module_name}.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    with pytest.raises(ControllerContractError, match="must return ControllerCommand"):
        run_external_controller(
            f"{module_name}:controller",
            "scenarios/nominal.json",
            navigation_profile="estimated",
        )


def test_navigation_fault_plan_is_strict_bound_and_estimated_only():
    plan = load_navigation_fault_plan(ESTIMATED_PLAN)
    suite = load_fault_suite(ESTIMATED_SUITE)
    plan.validate_suite(
        suite_id=suite.suite_id,
        suite_sha256=suite.sha256,
        case_ids={case.case_id for case in suite.cases},
    )
    with pytest.raises(NavigationFaultPlanError, match="estimated profile"):
        run_fault_suite(
            EXAMPLE,
            ESTIMATED_SUITE,
            navigation_profile="direct",
            navigation_fault_plan=plan,
        )
    with pytest.raises(NavigationFaultPlanError, match="unknown keys"):
        loads_navigation_fault_plan(
            ESTIMATED_PLAN.read_text(encoding="utf-8").replace(
                '"cases": [', '"unexpected": true, "cases": [', 1
            )
        )


def test_estimated_report_separates_controller_inputs_and_evaluator_outputs(
    estimated_result,
):
    report = assess_controller(
        EXAMPLE,
        ESTIMATED_SUITE,
        ESTIMATED_POLICY,
        navigation_profile="estimated",
        navigation_fault_plan=ESTIMATED_PLAN,
    ).to_dict()
    assert report["schema_version"] == ESTIMATED_REPORT_SCHEMA_VERSION
    assert report["navigation"]["profile"] == "estimated"
    assert report["information_boundaries"]["offline_truth_error_and_nees_reported"] is False
    for case in report["cases"]:
        assert case["controller_inputs"]["privileged_inputs_excluded"] is True
        assert case["controller_inputs"]["contract_fields"] == [
            "step",
            "time_s",
            "range_m",
            "relative_velocity_mps",
            "propellant_fraction",
            "sensor_quality",
        ]
        assert set(case["harness_evaluator_outputs"]) == {
            "success",
            "collision",
            "final_range_m",
            "final_speed_mps",
            "propellant_remaining",
            "steps",
        }
        assert "nees" not in case["navigation_diagnostics"]
        assert "truth_error" not in case["navigation_diagnostics"]
    assert report["fault_suite"]["result_sha256"] == estimated_result.result_sha256


def _replace_result_hash(payload: dict[str, object]) -> None:
    unsigned = dict(payload)
    unsigned.pop("result_sha256", None)
    payload["result_sha256"] = hashlib.sha256(canonical_json(unsigned)).hexdigest()


def test_estimated_result_parser_rejects_identity_and_plan_crosslink_tampering(
    estimated_result,
):
    wrong_case_identity = deepcopy(estimated_result.to_dict())
    wrong_case_identity["cases"][0]["navigation"]["identity_sha256"] = "0" * 64
    _replace_result_hash(wrong_case_identity)
    with pytest.raises(AssessmentResultSpecError, match="does not match result identity"):
        fault_suite_result_from_dict(wrong_case_identity)

    wrong_foundation = deepcopy(estimated_result.to_dict())
    identity = wrong_foundation["navigation"]["identity"]
    identity["foundation_freeze_id"] = "0" * 64
    unsigned_identity = dict(identity)
    unsigned_identity.pop("identity_sha256")
    identity["identity_sha256"] = hashlib.sha256(
        canonical_json(unsigned_identity)
    ).hexdigest()
    for case in wrong_foundation["cases"]:
        case["navigation"]["identity_sha256"] = identity["identity_sha256"]
    _replace_result_hash(wrong_foundation)
    with pytest.raises(AssessmentResultSpecError, match="foundation_freeze_id"):
        fault_suite_result_from_dict(wrong_foundation)

    wrong_packet_fault = deepcopy(estimated_result.to_dict())
    stale = next(
        case for case in wrong_packet_fault["cases"] if case["case_id"] == "stale-packet"
    )
    stale["navigation"]["packet_fault"]["activation"]["end_step"] = 266
    _replace_result_hash(wrong_packet_fault)
    with pytest.raises(AssessmentResultSpecError, match="does not match navigation plan"):
        fault_suite_result_from_dict(wrong_packet_fault)


def test_direct_demo_default_remains_byte_compatible(tmp_path: Path):
    rebuilt = tmp_path / "direct"
    build_demo_bundle(rebuilt)
    checked_in = Path("demo/rpo-benchmark")
    for name in ("demo.json", "demo.md", "index.html", "bundle-manifest.json"):
        assert (rebuilt / name).read_bytes() == (checked_in / name).read_bytes()


def test_public_clis_select_estimated_profile(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    assert (
        controller_adapter_main(
            [
                "run",
                EXAMPLE,
                "scenarios/nominal.json",
                "--navigation-profile",
                "estimated",
            ]
        )
        == 0
    )
    run_payload = json.loads(capsys.readouterr().out)
    assert run_payload["navigation"]["diagnostics"]["profile"] == "estimated"

    output = tmp_path / "estimated-demo"
    assert (
        demo_main(
            [
                "build",
                "--navigation-profile",
                "estimated",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "built"
    payload = json.loads((output / "demo.json").read_text(encoding="utf-8"))
    assert payload["input_identity"]["navigation"]["profile"] == "estimated"


def test_estimated_demo_is_byte_deterministic_and_keeps_frozen_evidence(
    tmp_path: Path,
):
    first = tmp_path / "first"
    second = tmp_path / "second"
    kwargs = {
        "suite_path": ESTIMATED_SUITE,
        "policy_path": ESTIMATED_POLICY,
        "navigation_profile": "estimated",
        "navigation_fault_plan": ESTIMATED_PLAN,
    }
    first_manifest = build_demo_bundle(first, **kwargs)
    second_manifest = build_demo_bundle(second, **kwargs)
    assert first_manifest == second_manifest
    for name in ("demo.json", "demo.md", "index.html", "bundle-manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    payload = json.loads((first / "demo.json").read_text(encoding="utf-8"))
    assert payload["input_identity"]["navigation"]["profile"] == "estimated"
    assert payload["try_the_harness"]["classification"] == (
        "illustrative_product_example_not_scientific_evidence"
    )
    campaigns = payload["frozen_architecture_evidence"]["campaigns"]
    assert [campaign["decision"] for campaign in campaigns] == [
        "favorable",
        "inconclusive",
    ]
    assert campaigns[1]["traceability"]["aggregate_result_sha256"] == (
        "daec0cd91683c709d4a56b06846ec96c025ec097030ad292c7dc481aec576516"
    )
    text = "\n".join(
        (first / name).read_text(encoding="utf-8")
        for name in ("demo.json", "demo.md", "index.html", "bundle-manifest.json")
    )
    assert str(tmp_path) not in text
    prohibited_terms = (
        "open" + "ai",
        "anth" + "ropic",
        "chat" + "gpt",
        "orchestration " + "tool",
    )
    for prohibited in prohibited_terms:
        assert prohibited not in text.lower()
    assert hashlib.sha256((first / "demo.json").read_bytes()).hexdigest() == next(
        item["sha256"] for item in first_manifest["files"] if item["path"] == "demo.json"
    )
