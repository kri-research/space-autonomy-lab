"""Identity and before-execution controls, using synthetic or exposed inputs only."""

from copy import deepcopy
import ast
import json
import pytest
from evaluation.generator import case_payload as old_payload, NAMESPACES as OLD
from evaluation.safety import canonical_hash, atomic_json
from evaluation_v2 import generator
from evaluation_v2.reserve import information_identity
from evaluation_v2.identity import inventory, identity_fields, verify, ROOT, PACKAGE
from evaluation_v2.freeze import command


def test_v2_sampler_distribution_code_is_unchanged():
    def function(path, name):
        tree = ast.parse(path.read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        return ast.dump(node, include_attributes=False)

    for name in ("make_case", "_rng", "_point", "_box", "case_payload"):
        assert function(ROOT / "evaluation/generator.py", name) == function(
            PACKAGE / "generator.py", name
        )
    assert set(generator.NAMESPACES) == set(OLD)
    assert not set(generator.NAMESPACES.values()) & set(OLD.values())


def test_v2_information_identity_ignores_hypothesis_order_only():
    p = old_payload("calibration", "interior_pair", 0)["information"]
    q = deepcopy(p)
    q["hypotheses"].reverse()
    assert information_identity(p) == information_identity(q)
    q["authority"] = "1/100"
    assert information_identity(p) != information_identity(q)


def test_v2_repair_and_analysis_are_in_frozen_inventory():
    items = inventory()
    for name in (
        "qualification_repair_v1/core.py",
        "qualification_repair_v1/recheck.py",
        "qualification_repair_v1/protocol.json",
        "evaluation/analysis.py",
        "evaluation/statistics.py",
        "candidate/certify.py",
        "evaluation_v2/jobs.py",
        "evaluation_v2/design.json",
    ):
        assert name in items and len(items[name]) == 64


def test_v2_design_retains_denominator_and_real_policy_budget():
    design = json.loads((PACKAGE / "design.json").read_text())
    assert (
        design["target_total"] == 768
        and design["target_per_stratum"] == 192
        and design["reserve_per_stratum"] == 288
    )
    assert design["analysis_module"] == "evaluation.analysis"
    assert design["resources"]["case_wall_limit_s"] == 15.0
    assert design["resources"]["workers"] == 4
    assert design["primary_endpoint"] == "on_time_decisive_valid"


def test_v2_malformed_identity_stops_before_generation(tmp_path, monkeypatch):
    import evaluation_v2.identity as module

    monkeypatch.setattr(
        module, "inventory", lambda: (_ for _ in ()).throw(AssertionError("too late"))
    )
    atomic_json(
        tmp_path / "freeze.json", {"schema": "sal-replacement-freeze/1", "evaluation_id": "bad"}
    )
    with pytest.raises(ValueError, match="identity"):
        verify(tmp_path / "freeze.json")


def test_v2_source_drift_stops_before_reserve_or_science(tmp_path, monkeypatch):
    import evaluation_v2.identity as module

    monkeypatch.setattr(module, "inventory", lambda: {"changed": "bytes"})
    doc = {
        "schema": "sal-replacement-freeze/1",
        "parent_evaluation_id": module.PARENT_ID,
        "protected_campaign_executed": False,
        "source_sha256": {},
    }
    doc["evaluation_id"] = canonical_hash(identity_fields(doc))
    atomic_json(tmp_path / "freeze.json", doc)
    with pytest.raises(ValueError, match="inventory"):
        verify(tmp_path / "freeze.json")


def test_v2_exact_command_has_new_path_and_separate_authorization():
    text = command("a" * 64)
    assert "evaluation_v2.execute --authorize-task08d" in text
    assert "/.research/tasks/08D/protected-v2" in text
    assert "evaluation.execute protected" not in text
    assert "/.research/tasks/08/protected-v1" not in text


def test_v2_protected_outcomes_not_called_by_identity_modules():
    for name in ("identity.py", "reserve.py", "freeze.py", "verify.py"):
        tree = ast.parse((PACKAGE / name).read_text())
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert not called & {
            "qualify",
            "qualification",
            "decide",
            "run_case",
            "adjudicate",
            "propagate_schedule",
            "run_protected",
        }


def test_v2_retirement_is_identity_only_and_records_every_skip(monkeypatch):
    import evaluation_v2.reserve as module

    monkeypatch.setattr(module, "STRATA", ("synthetic",))

    def info(value):
        return {"hypotheses": [{"lower": [value], "upper": [value]}]}

    monkeypatch.setattr(module, "known_information", lambda: {module.information_identity(info(0))})

    def synthetic(namespace, stratum, index):
        value = 1 if index == 2 else index
        return {
            "namespace": namespace,
            "stratum": stratum,
            "index": index,
            "information": info(value),
        }

    monkeypatch.setattr(module, "case_payload", synthetic)
    result = module.build_reserve()
    assert len(result["cases"]) == 288
    assert [r["index"] for r in result["retired"]] == [0, 2]
    assert result["cases"][0]["index"] == 1
    assert result["scientific_outcomes_computed"] is False
