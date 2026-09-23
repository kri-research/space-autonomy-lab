"""Read-only source, design and runtime identity checks. No scientific trials."""

from pathlib import Path
import hashlib
from evaluation.safety import strict_json, canonical_hash, safe_path
from evaluation.freeze import source_inventory as old_inventory
from evaluation.execute import verify_freeze as verify_old, check_runtime

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
PARENT_ID = "63eb088857849237bb9a4d42ac5ae38053c54335134a187c72d370f4a65d7ebd"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def inventory():
    result = old_inventory()
    for directory in ("qualification_repair_v1", "runtime_diagnosis_v1", "evaluation_v2"):
        for p in sorted((ROOT / directory).rglob("*.py")):
            result[p.relative_to(ROOT).as_posix()] = sha(p)
    for name in (
        "evaluation_v2/design.json",
        "qualification_repair_v1/protocol.json",
        "qualification_repair_v1/validation_seal.json",
    ):
        p = ROOT / name
        result[name] = sha(p)
    return dict(sorted(result.items()))


def identity_fields(doc):
    return {k: v for k, v in doc.items() if k not in ("evaluation_id", "task08d_execution_command")}


def verify(path, evaluation_id=None, *, runtime=False):
    path = safe_path(path)
    doc = strict_json(path)
    expected = canonical_hash(identity_fields(doc))
    if (
        doc.get("schema") != "sal-replacement-freeze/1"
        or doc.get("evaluation_id") != expected
        or (evaluation_id and evaluation_id != expected)
    ):
        raise ValueError("Replacement evaluation identity differs")
    if (
        doc.get("protected_campaign_executed") is not False
        or doc.get("parent_evaluation_id") != PARENT_ID
    ):
        raise ValueError("Not a prospective replacement of the preserved failed attempt")
    if inventory() != doc["source_sha256"]:
        raise ValueError("Replacement source inventory changed")
    for name, digest in doc["component_sha256"].items():
        if Path(name).name != name or sha(path.parent / name) != digest:
            raise ValueError("Frozen component mismatch")
    for name, digest in doc["preserved_artifact_sha256"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or sha(ROOT / relative) != digest:
            raise ValueError("Preserved prior artifact changed")
    verify_old(ROOT / "evaluation/frozen/freeze.json", PARENT_ID)
    from .freeze import command, PRESERVED, check_calibration
    from .reserve import build_reserve

    design = strict_json(PACKAGE / "design.json")
    if doc.get("design") != design or doc.get("resources") != design["resources"]:
        raise ValueError("Frozen design/resource specification differs")
    if set(doc["preserved_artifact_sha256"]) != set(PRESERVED):
        raise ValueError("Required prior artifact binding omitted")
    if doc.get("task08d_execution_command") != command(expected):
        raise ValueError("Executable command differs from canonical frozen command")
    required = {
        "protocol.json",
        "analysis_plan.json",
        "reserve.json",
        "amendment.json",
        "exposure.json",
        "integration_receipt.json",
    }
    if set(doc["component_sha256"]) != required:
        raise ValueError("Frozen component set differs")
    if strict_json(path.parent / "reserve.json") != build_reserve():
        raise ValueError("Fresh-identity retirement or reserve membership changed")
    integration = PACKAGE / "recorded_integration"
    if sha(integration / "manifest.json") != doc["integration_manifest_sha256"]:
        raise ValueError("Integration calibration identity changed")
    if check_calibration(integration) != strict_json(path.parent / "integration_receipt.json"):
        raise ValueError("Calibration receipt differs")
    if runtime:
        check_runtime(doc)
    return doc
