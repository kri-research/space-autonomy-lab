from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import fields
from pathlib import Path
from unittest.mock import patch

import pytest

from kri_space_autonomy.controller_adapter import ControllerObservation
from kri_space_autonomy.demo import (
    DEFAULT_CONTROLLER,
    build_demo_bundle,
    build_demo_payload,
    load_frozen_architecture_evidence,
    render_demo_html,
    render_demo_markdown,
)
from kri_space_autonomy.demo.cli import main

EXPECTED_FREEZE_IDS = {
    "experiment-002-confirmatory": (
        "15eb6b3b552e130f7b983930fda10d7d1c0841943408ec8586b51619d9076c15"
    ),
    "experiment-003-confirmatory": (
        "61d9f5b9657875b24759b4cad8eb83f60a655c09ef68d6892c49731887d505e6"
    ),
}
EXPECTED_ANALYSIS_HASHES = {
    "experiment-002-confirmatory": (
        "f59cebb40562e8af7c28a0ca39b56744d155a994b07c422935e0d18731f14898"
    ),
    "experiment-003-confirmatory": (
        "daec0cd91683c709d4a56b06846ec96c025ec097030ad292c7dc481aec576516"
    ),
}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bundle_files(path: Path) -> dict[str, bytes]:
    return {item.name: item.read_bytes() for item in sorted(path.iterdir()) if item.is_file()}


def test_demo_build_is_byte_deterministic_and_output_hashes_match(tmp_path: Path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first_manifest = build_demo_bundle(first)
    second_manifest = build_demo_bundle(second)

    assert first_manifest == second_manifest
    assert _bundle_files(first) == _bundle_files(second)
    assert len(first_manifest["input_fingerprint_sha256"]) == 64
    assert len(first_manifest["demo_fingerprint_sha256"]) == 64
    for record in first_manifest["files"]:
        assert record["sha256"] == _file_hash(first / record["path"])
        assert record["bytes"] == (first / record["path"]).stat().st_size

    payload = json.loads((first / "demo.json").read_text(encoding="utf-8"))
    assert payload["demo_fingerprint_sha256"] == first_manifest["demo_fingerprint_sha256"]
    assert payload["input_fingerprint_sha256"] == first_manifest["input_fingerprint_sha256"]
    all_text = "\n".join(
        (first / name).read_text(encoding="utf-8")
        for name in ("demo.json", "demo.md", "index.html", "bundle-manifest.json")
    )
    assert str(tmp_path) not in all_text
    assert '"timestamp"' not in all_text.lower()
    assert '"created_at"' not in all_text.lower()


def test_demo_reuses_assessment_api_instead_of_reimplementing_product_logic():
    from kri_space_autonomy.demo import bundle

    with patch.object(bundle, "assess_controller", wraps=bundle.assess_controller) as assess:
        payload = build_demo_payload(DEFAULT_CONTROLLER)
    assess.assert_called_once()
    args = assess.call_args.args
    assert args[0] == DEFAULT_CONTROLLER
    assert payload["try_the_harness"]["report"]["overall"]["decision"] == "PASS"

    source = Path(bundle.__file__).read_text(encoding="utf-8")
    assert "ProximityEnvironment" not in source
    assert "DeterministicFaultPipeline" not in source
    assert "def run_fault_suite" not in source


def test_frozen_evidence_uses_exact_complete_aggregate_artifacts_and_decisions():
    campaigns = load_frozen_architecture_evidence()
    assert [item["experiment_id"] for item in campaigns] == [
        "experiment-002-confirmatory",
        "experiment-003-confirmatory",
    ]
    by_id = {item["experiment_id"]: item for item in campaigns}
    assert by_id["experiment-002-confirmatory"]["decision"] == "favorable"
    assert by_id["experiment-003-confirmatory"]["decision"] == "inconclusive"

    for experiment_id, campaign in by_id.items():
        assert campaign["freeze_id"] == EXPECTED_FREEZE_IDS[experiment_id]
        assert campaign["aggregate_scope"]["complete"] is True
        trace = campaign["traceability"]
        assert trace["aggregate_result_path"] == f"results/{experiment_id}/analysis.json"
        assert trace["aggregate_result_sha256"] == EXPECTED_ANALYSIS_HASHES[experiment_id]
        assert trace["run_manifest_path"] == f"results/{experiment_id}/run-manifest.json"
        assert trace["checksums_path"] == f"results/{experiment_id}/SHA256SUMS"
        assert not any(str(value).endswith("episodes.jsonl") for value in trace.values())

    encoded = json.dumps(campaigns, sort_keys=True)
    assert '"root_id"' not in encoded
    assert '"episode_id"' not in encoded
    assert '"selected_root"' not in encoded


def test_experiment_002_and_003_gate_results_are_rendered_without_overstatement():
    by_id = {
        item["experiment_id"]: item for item in load_frozen_architecture_evidence()
    }
    experiment_002 = by_id["experiment-002-confirmatory"]
    h1_002 = experiment_002["primary_gatekeeping"]["H1"]
    h2_002 = experiment_002["primary_gatekeeping"]["H2"]
    assert h1_002["estimate"] == -0.04125
    assert h1_002["two_sided_95_interval"] == [-0.045, -0.037625]
    assert h1_002["passed"] is True
    assert h2_002["status"] == "tested"
    assert h2_002["passed"] is True
    assert "direct-measurement benchmark" in experiment_002["interpretation"]

    experiment_003 = by_id["experiment-003-confirmatory"]
    h1_003 = experiment_003["primary_gatekeeping"]["H1"]
    h2_003 = experiment_003["primary_gatekeeping"]["H2"]
    assert h1_003["estimate"] == 0.0
    assert h1_003["two_sided_95_interval"] == [0.0, 0.0]
    assert h1_003["passed"] is False
    assert h2_003["status"] == "not_tested_gate_closed"
    assert h2_003["passed"] is None
    assert h2_003["estimate"] == -0.184
    assert all(
        record["D_risk"] == 0.0 and record["PD_risk"] == 0.0
        for record in experiment_003["analysis_hazard_D_PD_by_stratum"]
    )
    stress = experiment_003["mission_success_stress"]
    assert stress["E5_monitor_range_bias_PD_minus_D"] == pytest.approx(-0.6893333333333334)
    assert stress["E6_shared_range_bias_PD_minus_D"] == pytest.approx(-0.6333333333333333)
    assert list(stress["all_stratum_estimates"]) == [
        "E0_nominal",
        "E1_primary_range_bias",
        "E2_primary_dropout",
        "E3_primary_stale",
        "E4_primary_covariance_underreporting",
        "E5_monitor_range_bias",
        "E6_shared_range_bias",
    ]


def test_html_and_markdown_state_both_evidence_layers_and_boundaries():
    payload = build_demo_payload()
    markdown = render_demo_markdown(payload)
    page = render_demo_html(payload)
    combined = markdown + page

    assert "Try the harness" in markdown
    assert "Frozen architecture evidence" in combined
    assert "illustrative product example" in combined
    assert "not scientific evidence" in combined
    assert "complete frozen aggregate" in combined
    assert "no historical root or episode" in combined
    assert "Direct measurements" in combined
    assert "Estimator in the loop" in combined
    assert "inconclusive" in combined
    assert "[0, 0]" in combined
    assert "not tested" in combined
    assert "E5_monitor_range_bias" in combined
    assert "E6_shared_range_bias" in combined
    assert "not a safety claim" in combined
    assert "formal verification" in combined
    assert "certification" in combined
    assert "flight-safety" in combined
    assert "<script" not in page.lower()
    assert "http://" not in page and "https://" not in page


def test_cli_builds_default_bundle_and_invalid_controller_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    output = tmp_path / "bundle"
    assert main(["build", "--output", str(output)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["status"] == "built"
    assert status["files"] == ["demo.json", "demo.md", "index.html"]
    assert (output / "index.html").is_file()
    assert (output / "bundle-manifest.json").is_file()

    assert (
        main(
            [
                "build",
                "--controller",
                "missing.demo.controller:controller",
                "--output",
                str(tmp_path / "invalid"),
            ]
        )
        == 2
    )
    error = json.loads(capsys.readouterr().err)
    assert error["status"] == "invalid"
    assert "PASS" not in error.values()


def test_demo_path_exposes_only_public_observation_contract_to_controller(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    source = '''
from dataclasses import fields
from kri_space_autonomy.controller_adapter import (
    ControllerCommand, ControllerMetadata, ObservationStatus,
)

seen_fields = []

class RecordingController:
    metadata = ControllerMetadata(controller_id="test.demo-observer", controller_version="1.0")

    def reset(self, context):
        self.minimum = context.minimum_acceleration_mps2
        self.maximum = context.maximum_acceleration_mps2

    def command(self, observation):
        seen_fields.append(tuple(item.name for item in fields(observation)))
        if observation.status is ObservationStatus.MISSING:
            return ControllerCommand(self.maximum)
        target = -min(0.30, 0.04 * max(0.0, observation.range_m - 6.5))
        command = 0.8 * (target - observation.relative_velocity_mps)
        if observation.status is ObservationStatus.DEGRADED:
            command = max(0.0, command)
        return ControllerCommand(min(self.maximum, max(self.minimum, command)))

controller = RecordingController()
'''
    module_path = tmp_path / "demo_recording_controller.py"
    module_path.write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()

    build_demo_bundle(
        tmp_path / "recording-bundle",
        controller_spec="demo_recording_controller:controller",
    )
    module = importlib.import_module("demo_recording_controller")
    expected = tuple(item.name for item in fields(ControllerObservation))
    assert module.seen_fields
    assert set(module.seen_fields) == {expected}
    assert "true_range_m" not in expected
    assert "true_relative_velocity_mps" not in expected
    assert "achieved_acceleration_mps2" not in expected
    assert "active_fault_ids" not in expected
