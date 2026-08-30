from __future__ import annotations

import importlib
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from kri_space_autonomy.assurance_report import (
    AssessmentCompatibilityError,
    AssessmentPolicyLoadError,
    AssessmentPolicySpecError,
    AssessmentResultLoadError,
    AssessmentResultSpecError,
    assess_controller,
    assess_fault_suite_result,
    assessment_policy_from_dict,
    fault_suite_result_from_dict,
    load_assessment_policy,
    loads_assessment_policy,
    loads_fault_suite_result,
    render_report_json,
    render_report_markdown,
)
from kri_space_autonomy.assurance_report.cli import main
from kri_space_autonomy.fault_suite import load_fault_suite, run_fault_suite

EXAMPLE_CONTROLLER = "kri_space_autonomy.examples.proportional_controller:controller"
EXAMPLE_SUITE = Path("fault-suites/example-rpo.json")
EXAMPLE_POLICY = Path("assessment-policies/example-rpo.json")


@pytest.fixture(scope="module")
def suite():
    return load_fault_suite(EXAMPLE_SUITE)


@pytest.fixture(scope="module")
def run_result(suite):
    return run_fault_suite(EXAMPLE_CONTROLLER, suite)


def _policy_dict(suite_sha256: str) -> dict[str, object]:
    return {
        "schema_version": "kri-assessment-policy/1.0",
        "policy_id": "test-policy",
        "description": "Test-harness acceptance criteria.",
        "suite": {"id": "example-rpo-faults", "sha256": suite_sha256},
        "default_case_requirement": "required",
        "criteria": {
            "require_success": True,
            "require_zero_collision": True,
            "minimum_propellant_remaining": {"value": 0.995, "unit": "ratio"},
        },
        "case_overrides": [],
    }


def _policy_with_threshold(suite_sha256: str, threshold: float):
    data = _policy_dict(suite_sha256)
    data["criteria"]["minimum_propellant_remaining"]["value"] = threshold
    return assessment_policy_from_dict(data)


def test_example_policy_validates_and_hash_is_format_and_override_order_stable(suite):
    checked = load_assessment_policy(EXAMPLE_POLICY)
    assert checked.suite_id == suite.suite_id
    assert checked.suite_sha256 == suite.sha256
    assert checked.policy_id == "example-rpo-acceptance"

    first = _policy_dict(suite.sha256)
    first["case_overrides"] = [
        {"case_id": "range-bias", "requirement": "informational"},
        {"case_id": "nominal", "requirement": "required"},
    ]
    second = deepcopy(first)
    second["case_overrides"].reverse()
    assert assessment_policy_from_dict(first).sha256 == assessment_policy_from_dict(
        second
    ).sha256
    assert loads_assessment_policy(json.dumps(first)).sha256 == loads_assessment_policy(
        json.dumps(first, indent=2)
    ).sha256

    changed = deepcopy(first)
    changed["criteria"]["minimum_propellant_remaining"]["value"] = 0.996
    assert assessment_policy_from_dict(first).sha256 != assessment_policy_from_dict(
        changed
    ).sha256


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda data: data.update({"unknown": True}), "unknown keys"),
        (
            lambda data: data["criteria"].update({"require_success": 1}),
            "must be a boolean",
        ),
        (
            lambda data: data["criteria"]["minimum_propellant_remaining"].update(
                {"value": float("nan")}
            ),
            "must be finite",
        ),
        (
            lambda data: data["criteria"]["minimum_propellant_remaining"].update(
                {"value": 1.01}
            ),
            r"in \[0, 1\]",
        ),
        (
            lambda data: data.update({"default_case_requirement": "advisory"}),
            "required.*informational",
        ),
        (
            lambda data: data.update(
                {
                    "case_overrides": [
                        {"case_id": "nominal", "requirement": "required"},
                        {"case_id": "nominal", "requirement": "informational"},
                    ]
                }
            ),
            "duplicate case id",
        ),
    ],
)
def test_policy_validation_rejects_malformed_unknown_and_nonfinite_values(
    suite, mutation, message
):
    data = _policy_dict(suite.sha256)
    mutation(data)
    with pytest.raises(AssessmentPolicySpecError, match=message):
        assessment_policy_from_dict(data)


def test_policy_json_rejects_duplicate_keys_and_nonfinite_constants():
    with pytest.raises(AssessmentPolicyLoadError, match="duplicate JSON key"):
        loads_assessment_policy('{"policy_id":"a","policy_id":"b"}')
    with pytest.raises(AssessmentPolicyLoadError, match="non-finite JSON constant"):
        loads_assessment_policy('{"value":NaN}')
    with pytest.raises(AssessmentPolicyLoadError, match="non-finite JSON constant"):
        loads_assessment_policy('{"value":Infinity}')


def test_example_end_to_end_passes_and_reports_all_required_product_evidence(
    suite, run_result
):
    report = assess_fault_suite_result(run_result, suite, EXAMPLE_POLICY)
    payload = report.to_dict()
    assert report.decision == "PASS"
    assert payload["overall"] == {
        "decision": "PASS",
        "required_case_count": 4,
        "informational_case_count": 1,
        "passed_required_case_count": 4,
        "failed_required_case_count": 0,
        "incomplete_case_count": 0,
    }
    assert payload["controller"]["controller_id"] == "example.proportional"
    assert payload["fault_suite"]["suite_sha256"] == suite.sha256
    assert payload["fault_suite"]["result_sha256"] == run_result.result_sha256
    assert len(payload["assessment_policy"]["policy_sha256"]) == 64
    assert len(payload["report_fingerprint_sha256"]) == 64
    assert len(payload["cases"]) == 5
    for case in payload["cases"]:
        assert len(case["case_result_sha256"]) == 64
        assert len(case["command_trace_sha256"]) == 64
        assert set(case["evidence"]) == {
            "success",
            "collision",
            "final_range_m",
            "final_speed_mps",
            "propellant_remaining",
            "steps",
            "commands",
            "degraded_observation_steps",
            "missing_observation_steps",
            "actuator_modified_steps",
        }
    by_id = {case["case_id"]: case for case in payload["cases"]}
    assert by_id["navigation-dropout"]["evidence"]["missing_observation_steps"] == 16
    assert by_id["actuator-degradation"]["evidence"]["actuator_modified_steps"] > 0
    assert by_id["dropout-plus-degradation"]["assessment"] == "INFORMATIONAL"


@pytest.mark.parametrize(
    ("threshold", "expected"),
    [(0.995, "PASS"), (1.0, "FAIL")],
)
def test_valid_assessments_distinguish_acceptance_pass_from_fail(
    suite, run_result, threshold, expected
):
    report = assess_fault_suite_result(
        run_result, suite, _policy_with_threshold(suite.sha256, threshold)
    )
    assert report.decision == expected
    if expected == "FAIL":
        assert report.to_dict()["failures"]
        assert all(item["affects_overall"] for item in report.to_dict()["failures"])


def test_missing_declared_case_is_incomplete_not_pass(suite, run_result):
    partial = replace(run_result, cases=run_result.cases[:-1])
    report = assess_fault_suite_result(partial, suite, EXAMPLE_POLICY)
    payload = report.to_dict()
    assert report.decision == "INCOMPLETE"
    assert payload["overall"]["incomplete_case_count"] == 1
    assert payload["cases"][-1]["assessment"] == "INCOMPLETE"
    assert payload["failures"][-1]["criterion_id"] == "case_result_present"


def test_per_case_requirement_and_threshold_overrides_control_only_declared_cases(
    suite, run_result
):
    baseline = _policy_dict(suite.sha256)
    baseline["criteria"]["minimum_propellant_remaining"]["value"] = 0.999
    assert (
        assess_fault_suite_result(
            run_result, suite, assessment_policy_from_dict(baseline)
        ).decision
        == "FAIL"
    )

    overridden = deepcopy(baseline)
    overridden["case_overrides"] = [
        {
            "case_id": "nominal",
            "requirement": "required",
            "criteria": {
                "minimum_propellant_remaining": {"value": 0.999, "unit": "ratio"}
            },
        },
        {"case_id": "navigation-dropout", "requirement": "informational"},
        {
            "case_id": "dropout-plus-degradation",
            "requirement": "informational",
        },
    ]
    report = assess_fault_suite_result(
        run_result, suite, assessment_policy_from_dict(overridden)
    )
    assert report.decision == "PASS"
    assert {
        item["case_id"] for item in report.to_dict()["informational_findings"]
    } == {"navigation-dropout", "dropout-plus-degradation"}


def test_nominal_comparison_uses_fault_free_case_and_reports_exact_deltas(
    suite, run_result
):
    report = assess_fault_suite_result(run_result, suite, EXAMPLE_POLICY).to_dict()
    by_id = {case["case_id"]: case for case in report["cases"]}
    nominal = next(case for case in run_result.cases if case.case_id == "nominal")
    degraded = next(
        case for case in run_result.cases if case.case_id == "actuator-degradation"
    )
    assert by_id["nominal"]["nominal_comparison"] == {
        "available": False,
        "reason": "case is the nominal reference",
    }
    comparison = by_id["actuator-degradation"]["nominal_comparison"]
    assert comparison["available"] is True
    assert comparison["reference_case_id"] == "nominal"
    assert comparison["propellant_remaining_delta"] == (
        degraded.propellant_remaining - nominal.propellant_remaining
    )
    assert comparison["steps_delta"] == degraded.steps - nominal.steps


def test_report_fingerprint_json_markdown_and_controller_replay_are_deterministic():
    first = assess_controller(EXAMPLE_CONTROLLER, EXAMPLE_SUITE, EXAMPLE_POLICY)
    second = assess_controller(EXAMPLE_CONTROLLER, EXAMPLE_SUITE, EXAMPLE_POLICY)
    assert first.to_dict() == second.to_dict()
    assert first.fingerprint == second.fingerprint
    assert render_report_json(first) == render_report_json(second)
    assert render_report_markdown(first) == render_report_markdown(second)


def test_result_loader_rejects_unknown_nonfinite_and_identity_tampering(run_result):
    unknown = run_result.to_dict()
    unknown["unknown"] = True
    with pytest.raises(AssessmentResultSpecError, match="unknown keys"):
        fault_suite_result_from_dict(unknown)

    tampered = run_result.to_dict()
    tampered["cases"][0]["steps"] += 1
    with pytest.raises(AssessmentResultSpecError, match="result_sha256"):
        fault_suite_result_from_dict(tampered)

    with pytest.raises(AssessmentResultLoadError, match="non-finite JSON constant"):
        loads_fault_suite_result('{"value":NaN}')
    with pytest.raises(AssessmentResultLoadError, match="duplicate JSON key"):
        loads_fault_suite_result('{"suite_id":"a","suite_id":"b"}')


def test_suite_policy_and_result_identity_mismatches_fail_closed(suite, run_result):
    bad_policy = _policy_dict(suite.sha256)
    bad_policy["suite"]["id"] = "other-suite"
    with pytest.raises(AssessmentCompatibilityError, match="does not identify"):
        assess_fault_suite_result(
            run_result, suite, assessment_policy_from_dict(bad_policy)
        )

    unknown_case = _policy_dict(suite.sha256)
    unknown_case["case_overrides"] = [
        {"case_id": "not-in-suite", "requirement": "required"}
    ]
    with pytest.raises(AssessmentCompatibilityError, match="unknown suite cases"):
        assess_fault_suite_result(
            run_result, suite, assessment_policy_from_dict(unknown_case)
        )


def test_markdown_leads_with_decision_identity_and_explicit_evidence_boundary(
    suite, run_result, tmp_path
):
    report = assess_fault_suite_result(run_result, suite, EXAMPLE_POLICY)
    markdown = render_report_markdown(report)
    payload = render_report_json(report)
    assert markdown.startswith("# Test-harness assessment: PASS\n")
    assert "**Controller:** `example.proportional`" in markdown
    assert "**Fault suite:** `example-rpo-faults`" in markdown
    assert "**Assessment policy:** `example-rpo-acceptance`" in markdown
    assert "simplified one-dimensional RPO test harness" in markdown
    assert "not a full GNC assessment" in markdown
    assert "not formal verification, certification, or a flight-safety claim" in markdown
    assert str(tmp_path) not in markdown
    assert str(tmp_path) not in payload
    assert "runtime_assurance_intervention_count" not in report.to_dict()
    assert "model_corruption_evidence" not in report.to_dict()


def test_cli_assess_report_outputs_and_fail_closed_exit_codes(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    suite,
    run_result,
):
    json_output = tmp_path / "assessment.json"
    markdown_output = tmp_path / "assessment.md"
    assert (
        main(
            [
                "assess",
                EXAMPLE_CONTROLLER,
                str(EXAMPLE_SUITE),
                str(EXAMPLE_POLICY),
                "--json-output",
                str(json_output),
                "--markdown-output",
                str(markdown_output),
                "--stdout",
                "none",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == ""
    assert json.loads(json_output.read_text(encoding="utf-8"))["overall"][
        "decision"
    ] == "PASS"
    assert markdown_output.read_text(encoding="utf-8").startswith(
        "# Test-harness assessment: PASS"
    )

    result_path = tmp_path / "suite-result.json"
    result_path.write_text(
        json.dumps(run_result.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "report",
                str(result_path),
                str(EXAMPLE_SUITE),
                str(EXAMPLE_POLICY),
                "--stdout",
                "json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["overall"]["decision"] == "PASS"

    failing_policy = tmp_path / "failing-policy.json"
    failing_policy.write_text(
        json.dumps(_policy_with_threshold(suite.sha256, 1.0).to_dict()),
        encoding="utf-8",
    )
    assert (
        main(
            [
                "report",
                str(result_path),
                str(EXAMPLE_SUITE),
                str(failing_policy),
                "--stdout",
                "json",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["overall"]["decision"] == "FAIL"

    assert (
        main(
            [
                "assess",
                "missing.module:controller",
                str(EXAMPLE_SUITE),
                str(EXAMPLE_POLICY),
            ]
        )
        == 2
    )
    error = json.loads(capsys.readouterr().err)
    assert error["assessment_status"] == "INVALID"
    assert error["error_type"] == "invalid_controller"
    assert "PASS" not in error.values()

    assert (
        main(
            [
                "assess",
                EXAMPLE_CONTROLLER,
                "missing-suite.json",
                str(EXAMPLE_POLICY),
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error_type"] == "invalid_fault_suite"

    assert (
        main(
            [
                "assess",
                EXAMPLE_CONTROLLER,
                str(EXAMPLE_SUITE),
                "missing-policy.json",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error_type"] == (
        "invalid_assessment_policy"
    )

    nondeterministic_source = """
from kri_space_autonomy.controller_adapter import ControllerCommand, ControllerMetadata

class Controller:
    metadata = ControllerMetadata(controller_id="test.replay-drift", controller_version="1.0")

    def __init__(self):
        self.run = 0

    def reset(self, context):
        self.run += 1

    def command(self, observation):
        return ControllerCommand(min(0.04, self.run * 0.001))

controller = Controller()
"""
    (tmp_path / "replay_drift_controller.py").write_text(
        nondeterministic_source, encoding="utf-8"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    assert (
        main(
            [
                "assess",
                "replay_drift_controller:controller",
                str(EXAMPLE_SUITE),
                str(EXAMPLE_POLICY),
            ]
        )
        == 2
    )
    execution_error = json.loads(capsys.readouterr().err)
    assert execution_error["assessment_status"] == "INVALID"
    assert execution_error["error_type"] == "execution"

    assert (
        main(
            [
                "report",
                str(result_path),
                str(EXAMPLE_SUITE),
                str(EXAMPLE_POLICY),
                "--json-output",
                str(tmp_path),
                "--stdout",
                "none",
            ]
        )
        == 2
    )
    infrastructure_error = json.loads(capsys.readouterr().err)
    assert infrastructure_error["assessment_status"] == "INVALID"
    assert infrastructure_error["error_type"] == "infrastructure"

    assert main(["assess"]) == 2
    usage_error = json.loads(capsys.readouterr().err)
    assert usage_error["assessment_status"] == "INVALID"
    assert usage_error["error_type"] == "invalid_cli_arguments"
