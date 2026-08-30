# ruff: noqa: E501  # Embedded standalone HTML/CSS is kept readable in its generated form.
from __future__ import annotations

import hashlib
import html
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kri_space_autonomy.assurance_report import assess_controller

DEMO_SCHEMA_VERSION = "kri-space-autonomy-demo/1.0"
BUNDLE_SCHEMA_VERSION = "kri-space-autonomy-demo-bundle/1.0"
DEFAULT_CONTROLLER = "kri_space_autonomy.examples.proportional_controller:controller"
DEFAULT_SUITE = Path("fault-suites/example-rpo.json")
DEFAULT_POLICY = Path("assessment-policies/example-rpo.json")
DEFAULT_OUTPUT = Path("demo/rpo-benchmark")

_CAMPAIGNS = (
    {
        "experiment_id": "experiment-002-confirmatory",
        "label": "Experiment 002 final confirmatory",
        "boundary": "Direct measurements in the simplified one-dimensional synthetic benchmark.",
        "expected_schema": "experiment-002-confirmatory-1.0",
        "expected_decision": "favorable",
        "analysis_path": Path("results/experiment-002-confirmatory/analysis.json"),
        "manifest_path": Path("results/experiment-002-confirmatory/run-manifest.json"),
        "checksums_path": Path("results/experiment-002-confirmatory/SHA256SUMS"),
        "freeze_path": Path("experiments/002-confirmatory/freeze-manifest.json"),
    },
    {
        "experiment_id": "experiment-003-confirmatory",
        "label": "Experiment 003 final confirmatory",
        "boundary": (
            "Estimator in the loop in the simplified one-dimensional synthetic benchmark."
        ),
        "expected_schema": "experiment-003-confirmatory-1.0",
        "expected_decision": "inconclusive",
        "analysis_path": Path("results/experiment-003-confirmatory/analysis.json"),
        "manifest_path": Path("results/experiment-003-confirmatory/run-manifest.json"),
        "checksums_path": Path("results/experiment-003-confirmatory/SHA256SUMS"),
        "freeze_path": Path("experiments/003-confirmatory/freeze-manifest.json"),
    },
)


class DemoBuildError(ValueError):
    """Raised when demo inputs are missing, inconsistent, or outside the frozen contract."""


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise DemoBuildError(f"could not hash required demo input {path.name}: {exc}") from exc
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DemoBuildError(f"could not load required demo input {path.name}: {exc}") from exc
    if type(value) is not dict:
        raise DemoBuildError(f"required demo input {path.name} must contain a JSON object")
    return value


def _checksum_map(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise DemoBuildError(f"could not read frozen checksum file {path.name}: {exc}") from exc
    result: dict[str, str] = {}
    for line in lines:
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise DemoBuildError(f"malformed frozen checksum entry in {path.as_posix()}") from exc
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise DemoBuildError(f"malformed SHA-256 in {path.as_posix()}")
        if name in result:
            raise DemoBuildError(f"duplicate checksum entry {name!r} in {path.as_posix()}")
        result[name] = digest
    return result


def _mapping(value: object, label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise DemoBuildError(f"{label} must be an object in the frozen aggregate analysis")
    return value


def _primary_result(analysis: Mapping[str, Any]) -> dict[str, object]:
    gate = _mapping(analysis.get("primary_gatekeeping"), "primary_gatekeeping")
    h1 = _mapping(gate.get("H1"), "primary_gatekeeping.H1")
    h2 = _mapping(gate.get("H2"), "primary_gatekeeping.H2")
    h1_interval = h1.get("two_sided_95_interval")
    h2_interval = h2.get("two_sided_95_interval")
    if not isinstance(h1_interval, list) or len(h1_interval) != 2:
        raise DemoBuildError("H1 two-sided interval is missing from frozen aggregate analysis")
    if not isinstance(h2_interval, list) or len(h2_interval) != 2:
        raise DemoBuildError("H2 two-sided interval is missing from frozen aggregate analysis")
    return {
        "contrast": "PD-D",
        "H1": {
            "endpoint": "analysis_hazard risk difference",
            "estimate": h1.get("estimate"),
            "two_sided_95_interval": h1_interval,
            "passed": h1.get("passed"),
            "rule": h1.get("rule"),
            "stratum_estimates": h1.get("stratum_estimates"),
        },
        "H2": {
            "endpoint": "sustained_success risk difference",
            "estimate": h2.get("estimate"),
            "two_sided_95_interval": h2_interval,
            "margin": h2.get("margin"),
            "status": h2.get("status"),
            "passed": h2.get("passed"),
            "stratum_estimates": h2.get("stratum_estimates"),
        },
    }


def _hazard_strata(analysis: Mapping[str, Any]) -> list[dict[str, object]]:
    summaries = _mapping(analysis.get("arm_summaries"), "arm_summaries")
    records: list[dict[str, object]] = []
    for stratum_id, arms_value in summaries.items():
        arms = _mapping(arms_value, f"arm_summaries.{stratum_id}")
        record: dict[str, object] = {"stratum_id": stratum_id}
        for arm_id in ("D", "PD"):
            arm = _mapping(arms.get(arm_id), f"arm_summaries.{stratum_id}.{arm_id}")
            hazard = _mapping(
                arm.get("analysis_hazard"),
                f"arm_summaries.{stratum_id}.{arm_id}.analysis_hazard",
            )
            record[f"{arm_id}_risk"] = hazard.get("risk")
        records.append(record)
    return records


def _validate_frozen_campaign(root: Path, spec: Mapping[str, object]) -> dict[str, object]:
    analysis_relative = Path(str(spec["analysis_path"]))
    manifest_relative = Path(str(spec["manifest_path"]))
    checksums_relative = Path(str(spec["checksums_path"]))
    freeze_relative = Path(str(spec["freeze_path"]))
    analysis_path = root / analysis_relative
    manifest_path = root / manifest_relative
    checksums_path = root / checksums_relative
    freeze_path = root / freeze_relative

    analysis = _load_json(analysis_path)
    manifest = _load_json(manifest_path)
    freeze = _load_json(freeze_path)
    checksums = _checksum_map(checksums_path)

    analysis_sha256 = _file_sha256(analysis_path)
    manifest_sha256 = _file_sha256(manifest_path)
    checksum_sha256 = _file_sha256(checksums_path)
    freeze_sha256 = _file_sha256(freeze_path)
    for name, observed in (
        (analysis_path.name, analysis_sha256),
        (manifest_path.name, manifest_sha256),
    ):
        if checksums.get(name) != observed:
            raise DemoBuildError(
                f"frozen checksum mismatch for {(analysis_relative.parent / name).as_posix()}"
            )

    expected_schema = spec["expected_schema"]
    expected_decision = spec["expected_decision"]
    if analysis.get("schema_version") != expected_schema:
        raise DemoBuildError(f"unexpected schema for {analysis_relative.as_posix()}")
    if analysis.get("decision") != expected_decision:
        raise DemoBuildError(f"unexpected decision for {analysis_relative.as_posix()}")
    if manifest.get("decision") != analysis.get("decision"):
        raise DemoBuildError(f"decision mismatch for {manifest_relative.as_posix()}")
    freeze_id = manifest.get("freeze_id")
    if not isinstance(freeze_id, str) or len(freeze_id) != 64:
        raise DemoBuildError(f"invalid freeze ID in {manifest_relative.as_posix()}")
    if freeze.get("freeze_id") != freeze_id:
        raise DemoBuildError(
            f"result/freeze identity mismatch for {spec['experiment_id']}"
        )
    output_hashes = _mapping(manifest.get("output_hashes"), "run-manifest.output_hashes")
    if output_hashes.get(analysis_relative.as_posix()) != analysis_sha256:
        raise DemoBuildError(
            f"run manifest does not bind {analysis_relative.as_posix()} to its bytes"
        )

    counts = _mapping(analysis.get("counts"), "counts")
    if counts.get("completeness_passed") is not True or counts.get("exact_expected_cells") is not True:
        raise DemoBuildError(
            f"frozen aggregate completeness did not pass for {spec['experiment_id']}"
        )
    primary = _primary_result(analysis)
    hazard_strata = _hazard_strata(analysis)
    evidence: dict[str, object] = {
        "experiment_id": spec["experiment_id"],
        "label": spec["label"],
        "measurement_boundary": spec["boundary"],
        "decision": analysis["decision"],
        "freeze_id": freeze_id,
        "aggregate_scope": {
            "complete_four_arm_blocks": counts.get("complete_four_arm_blocks"),
            "episode_rows": counts.get("episode_rows"),
            "complete": True,
            "selection": "complete frozen aggregate; no historical root or episode selection",
        },
        "primary_gatekeeping": primary,
        "traceability": {
            "aggregate_result_path": analysis_relative.as_posix(),
            "aggregate_result_sha256": analysis_sha256,
            "run_manifest_path": manifest_relative.as_posix(),
            "run_manifest_sha256": manifest_sha256,
            "freeze_manifest_path": freeze_relative.as_posix(),
            "freeze_manifest_sha256": freeze_sha256,
            "checksums_path": checksums_relative.as_posix(),
            "checksums_sha256": checksum_sha256,
        },
    }

    if spec["experiment_id"] == "experiment-002-confirmatory":
        if primary["H1"]["passed"] is not True or primary["H2"]["passed"] is not True:  # type: ignore[index]
            raise DemoBuildError("Experiment 002 frozen favorable gate decisions are inconsistent")
        evidence["interpretation"] = (
            "Favorable under the frozen serial gates in this direct-measurement benchmark. "
            "This does not establish the same result with navigation estimation in the loop."
        )
    else:
        h1 = primary["H1"]
        h2 = primary["H2"]
        assert isinstance(h1, dict) and isinstance(h2, dict)
        all_zero = all(
            record["D_risk"] == 0.0 and record["PD_risk"] == 0.0
            for record in hazard_strata
        )
        if (
            analysis["decision"] != "inconclusive"
            or h1["estimate"] != 0.0
            or h1["two_sided_95_interval"] != [0.0, 0.0]
            or h1["passed"] is not False
            or h2["status"] != "not_tested_gate_closed"
            or h2["passed"] is not None
            or not all_zero
        ):
            raise DemoBuildError("Experiment 003 frozen gate decisions are inconsistent")
        h2_strata = _mapping(h2.get("stratum_estimates"), "H2.stratum_estimates")
        expected_strata = {f"E{index}_" for index in range(7)}
        if not all(any(key.startswith(prefix) for key in h2_strata) for prefix in expected_strata):
            raise DemoBuildError("Experiment 003 H2 stratum aggregates are incomplete")
        evidence["analysis_hazard_D_PD_by_stratum"] = hazard_strata
        evidence["mission_success_stress"] = {
            "status": "descriptive_only_H2_gate_closed",
            "overall_PD_minus_D": h2["estimate"],
            "E5_monitor_range_bias_PD_minus_D": h2_strata.get("E5_monitor_range_bias"),
            "E6_shared_range_bias_PD_minus_D": h2_strata.get("E6_shared_range_bias"),
            "all_stratum_estimates": h2_strata,
        }
        evidence["interpretation"] = (
            "Inconclusive. H1 did not pass because D and PD each had zero analysis-hazard "
            "risk in every E0-E6 stratum, giving PD-D = 0 with 95% interval [0, 0]. H2 was "
            "not tested under the serial gate. Its descriptive sustained-success estimate was "
            "strongly negative overall and concentrated in E5/E6."
        )
    return evidence


def load_frozen_architecture_evidence(repository_root: str | Path = ".") -> list[dict[str, object]]:
    """Load only complete final aggregate artifacts; never historical episode/root records."""

    root = Path(repository_root)
    return [_validate_frozen_campaign(root, spec) for spec in _CAMPAIGNS]


def _input_identity(report: Mapping[str, Any], evidence: list[dict[str, object]]) -> dict[str, object]:
    controller = _mapping(report.get("controller"), "report.controller")
    suite = _mapping(report.get("fault_suite"), "report.fault_suite")
    policy = _mapping(report.get("assessment_policy"), "report.assessment_policy")
    return {
        "controller": {
            "plugin_spec": controller["plugin_spec"],
            "controller_id": controller["controller_id"],
            "controller_version": controller["controller_version"],
            "contract_version": controller["contract_version"],
            "plugin_module_sha256": controller["plugin_module_sha256"],
        },
        "fault_suite": {
            "suite_id": suite["suite_id"],
            "suite_sha256": suite["suite_sha256"],
        },
        "assessment_policy": {
            "policy_id": policy["policy_id"],
            "policy_sha256": policy["policy_sha256"],
        },
        "frozen_architecture_evidence": [
            {
                "experiment_id": item["experiment_id"],
                "freeze_id": item["freeze_id"],
                "aggregate_result_sha256": item["traceability"]["aggregate_result_sha256"],  # type: ignore[index]
                "run_manifest_sha256": item["traceability"]["run_manifest_sha256"],  # type: ignore[index]
                "freeze_manifest_sha256": item["traceability"]["freeze_manifest_sha256"],  # type: ignore[index]
                "checksums_sha256": item["traceability"]["checksums_sha256"],  # type: ignore[index]
            }
            for item in evidence
        ],
    }


def build_demo_payload(
    controller_spec: str = DEFAULT_CONTROLLER,
    *,
    repository_root: str | Path = ".",
    suite_path: str | Path = DEFAULT_SUITE,
    policy_path: str | Path = DEFAULT_POLICY,
) -> dict[str, object]:
    """Run the public product APIs and combine them with read-only frozen aggregate evidence."""

    root = Path(repository_root)
    suite_relative = Path(suite_path)
    policy_relative = Path(policy_path)
    report = assess_controller(controller_spec, root / suite_relative, root / policy_relative)
    report_payload = report.to_dict()
    evidence = load_frozen_architecture_evidence(root)
    inputs = _input_identity(report_payload, evidence)
    input_fingerprint = _fingerprint(inputs)
    unsigned: dict[str, object] = {
        "schema_version": DEMO_SCHEMA_VERSION,
        "title": "Space Autonomy Lab deterministic RPO controller demo",
        "positioning": (
            "A simplified autonomous rendezvous/proximity-operations controller test harness "
            "for repeatable faults and evidence reports."
        ),
        "evidence_boundary": (
            "The harness example is illustrative product output, not scientific evidence. Frozen "
            "architecture results are historical synthetic-benchmark evidence and are not full "
            "GNC, formal verification, certification, operational prevalence, or flight-safety evidence."
        ),
        "input_identity": inputs,
        "input_fingerprint_sha256": input_fingerprint,
        "workflow": [
            "bring an importable deterministic controller",
            "validate the public observation/command contract",
            "apply the checked-in deterministic fault suite",
            "assess the declared policy and emit stable evidence",
        ],
        "try_the_harness": {
            "classification": "illustrative_product_example_not_scientific_evidence",
            "report": report_payload,
        },
        "frozen_architecture_evidence": {
            "classification": "frozen_historical_complete_aggregate_evidence",
            "comparison_rule": (
                "Keep the direct-measurement and estimator-in-loop boundaries separate; do not "
                "combine decisions into a single safety or architecture claim."
            ),
            "campaigns": evidence,
        },
        "commands": {
            "rebuild_example": "uv run python -m kri_space_autonomy.demo build",
            "build_and_open": "uv run python -m kri_space_autonomy.demo build --open",
            "try_own_controller": (
                "uv run python -m kri_space_autonomy.demo build "
                "--controller my_controller:controller --output demo/my-controller"
            ),
            "controller_guide": "docs/controller-adapter.md",
        },
        "limitations": [
            "Simplified deterministic one-dimensional relative-motion environment; not a full GNC stack.",
            "Fault cases are declared stress tests, not estimates of operational fault prevalence.",
            "Local Python controllers run in process and should be trusted code.",
            "A PASS means only that required cases met the checked-in policy in this harness.",
            "Frozen Experiment 002 and 003 results have different measurement boundaries.",
            "No formal verification, certification, hardware, timing, or flight-safety claim is made.",
        ],
    }
    return {**unsigned, "demo_fingerprint_sha256": _fingerprint(unsigned)}


def render_demo_json(payload: Mapping[str, object]) -> str:
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _number(value: object, digits: int = 6) -> str:
    if value is None:
        return "—"
    return f"{float(value):.{digits}f}"


def _interval(value: object) -> str:
    if not isinstance(value, list) or len(value) != 2:
        return "—"
    return f"[{_number(value[0])}, {_number(value[1])}]"


def _campaigns(payload: Mapping[str, object]) -> list[dict[str, Any]]:
    architecture = _mapping(payload.get("frozen_architecture_evidence"), "frozen evidence")
    campaigns = architecture.get("campaigns")
    if not isinstance(campaigns, list):
        raise DemoBuildError("frozen evidence campaigns must be an array")
    return campaigns


def render_demo_markdown(payload: Mapping[str, object]) -> str:
    harness = _mapping(payload.get("try_the_harness"), "try_the_harness")
    report = _mapping(harness.get("report"), "try_the_harness.report")
    overall = _mapping(report.get("overall"), "report.overall")
    controller = _mapping(report.get("controller"), "report.controller")
    suite = _mapping(report.get("fault_suite"), "report.fault_suite")
    policy = _mapping(report.get("assessment_policy"), "report.assessment_policy")
    cases = report.get("cases")
    if not isinstance(cases, list):
        raise DemoBuildError("report cases must be an array")
    campaigns = _campaigns(payload)

    lines = [
        "# Space Autonomy Lab: deterministic RPO controller demo",
        "",
        "A compact, repeatable path from **your controller** to **declared faults** to a "
        "**traceable criteria report** in a simplified one-dimensional rendezvous/proximity-operations "
        "(RPO) harness.",
        "",
        "> **Evidence boundary:** The run below is an illustrative product example, not scientific "
        "evidence. The historical results are frozen synthetic-benchmark evidence. Nothing here is "
        "a full GNC assessment, formal verification, certification, operational fault-prevalence "
        "estimate, or flight-safety claim.",
        "",
        "## Try the harness — product example",
        "",
        "`controller plugin → public adapter → deterministic fault suite → declared policy → stable report`",
        "",
        f"- **Result:** `{overall['decision']}` within the checked-in policy only",
        f"- **Controller:** `{controller['controller_id']}` v`{controller['controller_version']}`",
        f"- **Fault suite:** `{suite['suite_id']}` · `{suite['suite_sha256']}`",
        f"- **Assessment policy:** `{policy['policy_id']}` · `{policy['policy_sha256']}`",
        f"- **Harness report fingerprint:** `{report['report_fingerprint_sha256']}`",
        "",
        "| Case | Faults | Role / result | Success | Collision | Final range (m) | "
        "Final speed (m/s) | Propellant | Degraded / missing obs. | Actuator-modified |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for case in cases:
        row = _mapping(case, "report case")
        evidence = _mapping(row.get("evidence"), f"case {row.get('case_id')} evidence")
        faults = row.get("fault_sequence")
        fault_text = ", ".join(f"`{item}`" for item in faults) if faults else "none"
        lines.append(
            f"| `{row['case_id']}` | {fault_text} | {row['requirement']} / "
            f"**{row['assessment']}** | {evidence['success']} | {evidence['collision']} | "
            f"{_number(evidence['final_range_m'])} | {_number(evidence['final_speed_mps'])} | "
            f"{_number(evidence['propellant_remaining'], 9)} | "
            f"{evidence['degraded_observation_steps']} / {evidence['missing_observation_steps']} | "
            f"{evidence['actuator_modified_steps']} |"
        )

    lines.extend(
        [
            "",
            "A `PASS` here means only that every required example case met the checked-in criteria. "
            "The composed case is explicitly informational.",
            "",
            "## Frozen architecture evidence — keep the boundaries separate",
            "",
            "Both rows below come from each campaign's **complete frozen aggregate** `analysis.json`; "
            "no historical root or episode was selected. The campaigns must not be combined into one "
            "architecture or safety claim.",
            "",
            "| Campaign | Measurement boundary | Frozen decision | H1: PD-D analysis-hazard RD "
            "(95% interval) | H2: PD-D sustained-success RD |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    interpretations: list[str] = []
    for campaign in campaigns:
        primary = _mapping(campaign["primary_gatekeeping"], "campaign primary")
        h1 = _mapping(primary["H1"], "campaign H1")
        h2 = _mapping(primary["H2"], "campaign H2")
        h2_status = f"{_number(h2['estimate'])}; {h2['status']}"
        lines.append(
            f"| **{campaign['label']}** | {campaign['measurement_boundary']} | "
            f"**{campaign['decision']}** | {_number(h1['estimate'])} "
            f"{_interval(h1['two_sided_95_interval'])}; passed `{h1['passed']}` | "
            f"{h2_status}; passed `{h2['passed']}` |"
        )
        interpretations.append(
            f"- **{campaign['label']}:** {campaign['interpretation']}"
        )
    lines.extend(["", *interpretations, ""])

    experiment_003 = next(
        item for item in campaigns if item["experiment_id"] == "experiment-003-confirmatory"
    )
    stress = _mapping(experiment_003["mission_success_stress"], "Experiment 003 stress")
    strata = _mapping(stress["all_stratum_estimates"], "Experiment 003 strata")
    lines.extend(
        [
            "### Experiment 003 descriptive sustained-success contrast by stratum",
            "",
            "H2 was **not tested** because H1 closed the serial gate. These complete per-stratum "
            "aggregate PD-D estimates are descriptive; E5/E6 contain the observed degradation.",
            "",
            "| Stratum | PD-D sustained-success risk difference |",
            "| --- | ---: |",
        ]
    )
    lines.extend(f"| `{name}` | {_number(value)} |" for name, value in strata.items())

    lines.extend(["", "## Traceability", ""])
    lines.append("| Campaign | Freeze ID | Aggregate result SHA-256 | Complete aggregate source |")
    lines.append("| --- | --- | --- | --- |")
    for campaign in campaigns:
        trace = _mapping(campaign["traceability"], "campaign traceability")
        lines.append(
            f"| {campaign['label']} | `{campaign['freeze_id']}` | "
            f"`{trace['aggregate_result_sha256']}` | `{trace['aggregate_result_path']}` |"
        )
    lines.extend(
        [
            "",
            f"- **Demo input fingerprint:** `{payload['input_fingerprint_sha256']}`",
            f"- **Demo substantive fingerprint:** `{payload['demo_fingerprint_sha256']}`",
            "",
            "## Try another controller",
            "",
            "Implement the small contract in [`docs/controller-adapter.md`](../../docs/controller-adapter.md), "
            "then run:",
            "",
            "```bash",
            "uv run python -m kri_space_autonomy.demo build \\",
            "  --controller my_controller:controller \\",
            "  --output demo/my-controller",
            "```",
            "",
            "Open `demo/my-controller/index.html`. The command reuses the same public adapter, fault-suite, "
            "and assessment-report APIs.",
            "",
            "## Limitations",
            "",
        ]
    )
    limitations = payload.get("limitations")
    if not isinstance(limitations, list):
        raise DemoBuildError("limitations must be an array")
    lines.extend(f"- {item}" for item in limitations)
    lines.extend(
        [
            "",
            "Machine-readable payload: [`demo.json`](demo.json) · Standalone page: "
            "[`index.html`](index.html)",
            "",
        ]
    )
    return "\n".join(lines)


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_demo_html(payload: Mapping[str, object]) -> str:
    harness = _mapping(payload.get("try_the_harness"), "try_the_harness")
    report = _mapping(harness.get("report"), "try_the_harness.report")
    overall = _mapping(report.get("overall"), "report.overall")
    controller = _mapping(report.get("controller"), "report.controller")
    suite = _mapping(report.get("fault_suite"), "report.fault_suite")
    policy = _mapping(report.get("assessment_policy"), "report.assessment_policy")
    cases = report.get("cases")
    if not isinstance(cases, list):
        raise DemoBuildError("report cases must be an array")
    campaigns = _campaigns(payload)
    experiment_003 = next(
        item for item in campaigns if item["experiment_id"] == "experiment-003-confirmatory"
    )
    stress = _mapping(experiment_003["mission_success_stress"], "Experiment 003 stress")
    strata = _mapping(stress["all_stratum_estimates"], "Experiment 003 strata")

    case_rows: list[str] = []
    for case in cases:
        row = _mapping(case, "report case")
        evidence = _mapping(row.get("evidence"), f"case {row.get('case_id')} evidence")
        faults = row.get("fault_sequence")
        fault_text = ", ".join(_esc(item) for item in faults) if faults else "None"
        result_class = "ok" if row["assessment"] in {"PASS", "INFORMATIONAL"} else "warn"
        case_rows.append(
            "<tr>"
            f"<td><code>{_esc(row['case_id'])}</code><small>{fault_text}</small></td>"
            f"<td>{_esc(row['requirement'])}<br><strong class='{result_class}'>{_esc(row['assessment'])}</strong></td>"
            f"<td>{_esc(evidence['success'])} / {_esc(evidence['collision'])}</td>"
            f"<td>{_number(evidence['final_range_m'])}<small>{_number(evidence['final_speed_mps'])} m/s</small></td>"
            f"<td>{_number(evidence['propellant_remaining'], 9)}</td>"
            f"<td>{_esc(evidence['degraded_observation_steps'])} / {_esc(evidence['missing_observation_steps'])}</td>"
            f"<td>{_esc(evidence['actuator_modified_steps'])}</td>"
            "</tr>"
        )

    campaign_rows: list[str] = []
    cards: list[str] = []
    trace_rows: list[str] = []
    for campaign in campaigns:
        primary = _mapping(campaign["primary_gatekeeping"], "campaign primary")
        h1 = _mapping(primary["H1"], "campaign H1")
        h2 = _mapping(primary["H2"], "campaign H2")
        status_class = "favorable" if campaign["decision"] == "favorable" else "inconclusive"
        campaign_rows.append(
            "<tr>"
            f"<td><strong>{_esc(campaign['label'])}</strong></td>"
            f"<td>{_esc(campaign['measurement_boundary'])}</td>"
            f"<td><span class='status {status_class}'>{_esc(campaign['decision'])}</span></td>"
            f"<td>{_number(h1['estimate'])}<small>95% {_esc(_interval(h1['two_sided_95_interval']))}; "
            f"passed {_esc(h1['passed'])}</small></td>"
            f"<td>{_number(h2['estimate'])}<small>{_esc(h2['status'])}; passed {_esc(h2['passed'])}</small></td>"
            "</tr>"
        )
        cards.append(
            f"<article class='evidence-card {status_class}'>"
            f"<p class='eyebrow'>{_esc(campaign['label'])}</p>"
            f"<h3>{_esc(campaign['decision']).title()}</h3>"
            f"<p>{_esc(campaign['interpretation'])}</p>"
            f"<p class='mono-label'>Freeze <code>{_esc(campaign['freeze_id'])}</code></p>"
            "</article>"
        )
        trace = _mapping(campaign["traceability"], "campaign traceability")
        trace_rows.append(
            "<tr>"
            f"<td>{_esc(campaign['label'])}</td>"
            f"<td><code>{_esc(campaign['freeze_id'])}</code></td>"
            f"<td><code>{_esc(trace['aggregate_result_sha256'])}</code></td>"
            f"<td><code>{_esc(trace['aggregate_result_path'])}</code></td>"
            "</tr>"
        )

    stratum_rows = "".join(
        "<tr>"
        f"<td><code>{_esc(name)}</code></td>"
        f"<td class='number {'negative' if float(value) < -0.03 else ''}'>{_number(value)}</td>"
        "</tr>"
        for name, value in strata.items()
    )
    limitations = payload.get("limitations")
    if not isinstance(limitations, list):
        raise DemoBuildError("limitations must be an array")
    limitation_items = "".join(f"<li>{_esc(item)}</li>" for item in limitations)

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Space Autonomy Lab · Deterministic RPO demo</title>
<style>
:root{{--ink:#172033;--muted:#5d6878;--line:#dce2ea;--paper:#f5f7fa;--card:#fff;--navy:#0b2948;--cyan:#34c6c8;--lime:#b8d96b;--amber:#f3b64e;--red:#bb4d55}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}}
a{{color:#075d75}} code{{font:0.84em ui-monospace,SFMono-Regular,Consolas,monospace;overflow-wrap:anywhere}} .shell{{max-width:1160px;margin:auto;padding:0 24px 72px}}
.hero{{margin:0 -24px 34px;padding:58px max(24px,calc((100vw - 1112px)/2));background:linear-gradient(125deg,#071d33,#0d3558 58%,#116064);color:#fff}}
.hero-grid{{display:grid;grid-template-columns:1.6fr .8fr;gap:30px;align-items:end}} .eyebrow{{margin:0 0 10px;color:#298087;font-size:.76rem;font-weight:800;letter-spacing:.12em;text-transform:uppercase}} .hero .eyebrow{{color:#78e1df}}
h1{{max-width:820px;margin:.15em 0;font-size:clamp(2.15rem,5vw,4.35rem);line-height:1.02;letter-spacing:-.045em}} h2{{margin:50px 0 10px;font-size:clamp(1.6rem,3vw,2.25rem);letter-spacing:-.025em}} h3{{margin:.25em 0;font-size:1.35rem}} .lead{{max-width:760px;color:#dbeaf1;font-size:1.1rem}} .fingerprint{{border-left:2px solid var(--cyan);padding-left:15px;color:#cce5ea}}
.badge{{display:inline-block;border:1px solid #75d5d3;border-radius:99px;padding:5px 10px;color:#dfffff;font-size:.78rem;font-weight:700}} .boundary{{margin:26px 0;padding:17px 19px;border:1px solid #edc775;border-left:5px solid var(--amber);border-radius:10px;background:#fff8e8}}
.flow{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:22px 0}} .flow div{{position:relative;padding:16px;border:1px solid var(--line);border-radius:10px;background:var(--card);font-weight:700}} .flow div:not(:last-child)::after{{content:"→";position:absolute;right:-10px;top:18px;color:#248c91;z-index:2}}
.summary{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}} .metric{{padding:16px;border-radius:12px;background:var(--navy);color:#fff}} .metric small{{display:block;color:#b8cadd}} .metric strong{{display:block;margin-top:4px;font-size:1.05rem}}
.table-wrap{{overflow-x:auto;border:1px solid var(--line);border-radius:12px;background:var(--card)}} table{{width:100%;border-collapse:collapse}} th,td{{padding:12px 13px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}} th{{background:#eef3f7;color:#455266;font-size:.76rem;letter-spacing:.05em;text-transform:uppercase}} tr:last-child td{{border-bottom:0}} td small{{display:block;color:var(--muted)}} .ok{{color:#167148}} .warn{{color:#9a6308}}
.cards{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:20px 0}} .evidence-card{{padding:22px;border:1px solid var(--line);border-top:5px solid var(--lime);border-radius:14px;background:var(--card)}} .evidence-card.inconclusive{{border-top-color:var(--amber)}} .status{{display:inline-block;padding:4px 9px;border-radius:99px;background:#e9f5e7;color:#315e35;font-weight:800}} .status.inconclusive{{background:#fff2d6;color:#815915}}
.mono-label{{color:var(--muted);font-size:.82rem}} .number{{font-variant-numeric:tabular-nums}} .negative{{color:var(--red);font-weight:800}} .two-col{{display:grid;grid-template-columns:1.1fr .9fr;gap:18px;align-items:start}} .note{{padding:18px;border-radius:12px;background:#eaf4f6}} pre{{overflow:auto;padding:16px;border-radius:12px;background:#0a2239;color:#dff6f4;font-size:.85rem}} ul{{padding-left:1.25rem}} footer{{margin-top:52px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted)}}
@media(max-width:820px){{.hero-grid,.cards,.two-col{{grid-template-columns:1fr}}.summary{{grid-template-columns:1fr 1fr}}.flow{{grid-template-columns:1fr 1fr}}.flow div::after{{display:none}}}} @media(max-width:520px){{.summary,.flow{{grid-template-columns:1fr}}.shell{{padding-left:14px;padding-right:14px}}}}
@media print{{body{{background:#fff}}.hero{{background:#fff;color:#111;border-bottom:2px solid #111}}.hero .lead,.hero .eyebrow,.fingerprint{{color:#333}}.table-wrap{{overflow:visible}}}}
</style>
</head>
<body>
<header class="hero"><div class="hero-grid"><div><p class="eyebrow">Space Autonomy Lab</p><h1>Bring a controller.<br>Stress the boundary.</h1><p class="lead">A deterministic, simplified RPO test harness that turns an importable controller, declared observation/actuator faults, and an explicit policy into a traceable report.</p><span class="badge">Product example · not scientific evidence</span></div><div class="fingerprint"><strong>Substantive demo identity</strong><br><code>{_esc(payload['demo_fingerprint_sha256'])}</code></div></div></header>
<main class="shell">
<div class="boundary"><strong>Evidence boundary.</strong> The example run is illustrative product output. Frozen architecture results below are historical synthetic-benchmark evidence. This is not full GNC, formal verification, certification, operational fault-prevalence, or flight-safety evidence.</div>
<section><p class="eyebrow">Layer A · run it</p><h2>Try the harness</h2><div class="flow"><div>1 · Controller plugin</div><div>2 · Public adapter</div><div>3 · Deterministic faults</div><div>4 · Criteria report</div></div>
<div class="summary"><div class="metric"><small>Example result</small><strong>{_esc(overall['decision'])}</strong></div><div class="metric"><small>Controller</small><strong>{_esc(controller['controller_id'])} v{_esc(controller['controller_version'])}</strong></div><div class="metric"><small>Suite</small><strong>{_esc(suite['suite_id'])}</strong></div><div class="metric"><small>Policy</small><strong>{_esc(policy['policy_id'])}</strong></div></div>
<div class="table-wrap"><table><thead><tr><th>Case / faults</th><th>Role / result</th><th>Success / collision</th><th>Final range / speed</th><th>Propellant</th><th>Degraded / missing obs.</th><th>Actuator-modified</th></tr></thead><tbody>{''.join(case_rows)}</tbody></table></div>
<p class="note"><strong>Read PASS narrowly:</strong> every required example case met the checked-in policy in this harness. The composed case is informational. This result is not a safety claim.</p></section>
<section><p class="eyebrow">Layer B · what is known</p><h2>Frozen architecture evidence</h2><p>Two final confirmatory campaigns, two different measurement boundaries. Each summary uses the complete frozen aggregate result—no historical root or episode selection—and the decisions are not combined into one claim.</p><div class="cards">{''.join(cards)}</div>
<div class="table-wrap"><table><thead><tr><th>Campaign</th><th>Measurement boundary</th><th>Decision</th><th>H1 · PD-D hazard RD</th><th>H2 · PD-D sustained-success RD</th></tr></thead><tbody>{''.join(campaign_rows)}</tbody></table></div></section>
<section class="two-col"><div><h2>Where Experiment 003 stressed</h2><p>H1 produced exactly zero PD-D risk difference with 95% interval [0, 0], so it did not pass. H2 was therefore not tested under the serial gate. The table shows every descriptive sustained-success stratum estimate; E5/E6 contain the strong negative effect.</p></div><div class="table-wrap"><table><thead><tr><th>Experiment 003 stratum</th><th>PD-D sustained success</th></tr></thead><tbody>{stratum_rows}</tbody></table></div></section>
<section><h2>Try your controller</h2><p>Implement the small public contract in <code>docs/controller-adapter.md</code>, then run:</p><pre>uv run python -m kri_space_autonomy.demo build \\
  --controller my_controller:controller \\
  --output demo/my-controller</pre><p>Open <code>demo/my-controller/index.html</code>. The same controller adapter, fault-suite, and assessment-report APIs generate the result.</p></section>
<section><h2>Traceability</h2><div class="table-wrap"><table><thead><tr><th>Campaign</th><th>Freeze ID</th><th>Aggregate SHA-256</th><th>Source</th></tr></thead><tbody>{''.join(trace_rows)}</tbody></table></div><p class="mono-label">Input fingerprint <code>{_esc(payload['input_fingerprint_sha256'])}</code><br>Harness report fingerprint <code>{_esc(report['report_fingerprint_sha256'])}</code><br>Demo substantive fingerprint <code>{_esc(payload['demo_fingerprint_sha256'])}</code></p></section>
<section><h2>Limitations</h2><ul>{limitation_items}</ul></section>
<footer><a href="demo.json">Stable JSON</a> · <a href="demo.md">Concise Markdown</a><br>Generated deterministically with no timestamps or external page dependencies.</footer>
</main></body></html>
"""


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(content)
            temporary = handle.name
        os.replace(temporary, path)
    except OSError:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
        raise


def build_demo_bundle(
    output_dir: str | Path = DEFAULT_OUTPUT,
    *,
    controller_spec: str = DEFAULT_CONTROLLER,
    repository_root: str | Path = ".",
    suite_path: str | Path = DEFAULT_SUITE,
    policy_path: str | Path = DEFAULT_POLICY,
) -> dict[str, object]:
    """Build deterministic JSON, Markdown, HTML, and a file-identity manifest."""

    root = Path(repository_root)
    destination = Path(output_dir)
    if not destination.is_absolute():
        destination = root / destination
    payload = build_demo_payload(
        controller_spec,
        repository_root=root,
        suite_path=suite_path,
        policy_path=policy_path,
    )
    rendered = {
        "demo.json": render_demo_json(payload),
        "demo.md": render_demo_markdown(payload),
        "index.html": render_demo_html(payload),
    }
    files: list[dict[str, object]] = []
    for name, content in rendered.items():
        encoded = content.encode("utf-8")
        files.append(
            {
                "path": name,
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "bytes": len(encoded),
            }
        )
        _atomic_write(destination / name, content)
    manifest: dict[str, object] = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "input_fingerprint_sha256": payload["input_fingerprint_sha256"],
        "demo_fingerprint_sha256": payload["demo_fingerprint_sha256"],
        "files": files,
    }
    _atomic_write(destination / "bundle-manifest.json", render_demo_json(manifest))
    return manifest
