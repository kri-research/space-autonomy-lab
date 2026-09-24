"""Identity-bound prospective transfer design; no qualification screening."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import platform
import subprocess
from .schema import ROOT, STRATA, read, digest, make_case

REPO = ROOT.parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory():
    return {
        p.relative_to(ROOT).as_posix(): sha(p)
        for p in sorted(ROOT.rglob("*.py"))
        if "recorded" not in p.parts
    }


def runtime():
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {n: importlib.metadata.version(n) for n in ("numpy", "scipy")},
        "processor_model": subprocess.check_output(["sysctl", "-n", "hw.model"], text=True).strip()
        if platform.system() == "Darwin"
        else platform.machine(),
    }


def freeze(output, calibration):
    from .experiment import atomic

    output = Path(output)
    if output.exists():
        raise ValueError("Freeze already deposited")
    result = read(Path(calibration) / "completion.json")
    if result["cases"] != 8 or any(t["exit_code"] != 0 for t in result["attempts"]):
        raise ValueError("Incomplete technical calibration")
    source = inventory()
    header = read(Path(calibration) / "header.json")
    if header["source_sha256"] != source:
        raise ValueError("Calibration used another source revision")
    for name, h in result["files"].items():
        if sha(Path(calibration) / name) != h:
            raise ValueError("Calibration bytes changed " + name)
    commit = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    for name, h in source.items():
        raw = subprocess.check_output(
            [
                "git",
                "-C",
                str(REPO),
                "show",
                commit + ":studies/property-alignment-v1/transfer_cart_v1/" + name,
            ]
        )
        if hashlib.sha256(raw).hexdigest() != h:
            raise ValueError("Source not committed before freeze " + name)
    cases = [make_case("protected", s, i) for s in STRATA for i in range(32)]
    if len({digest(c) for c in cases}) != 128:
        raise ValueError("Duplicate case identity")
    output.mkdir()
    atomic(output / "inputs.json", cases)
    components = {n: sha(ROOT / n) for n in ("design.json", "exposure.json", "method_sources.json")}
    doc = {
        "schema": "sal-cart-transfer-freeze/1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_commit": commit,
        "source_sha256": source,
        "component_sha256": components,
        "inputs_sha256": sha(output / "inputs.json"),
        "calibration_receipt_sha256": sha(Path(calibration) / "completion.json"),
        "runtime": runtime(),
        "count": 128,
        "candidate_task08_results_known": True,
        "cart_family_preselected_in_task02": True,
        "cart_numerical_plan_set_after_task08": True,
        "protected_outcomes_executed": False,
        "physical_validation": False,
    }
    doc["transfer_id"] = digest(doc)
    atomic(output / "freeze.json", doc)
    return doc


def verify(path, runtime=False):
    path = Path(path)
    doc = read(path)
    if doc["transfer_id"] != digest({k: v for k, v in doc.items() if k != "transfer_id"}):
        raise ValueError("Transfer identity mismatch")
    if doc["source_sha256"] != inventory():
        raise ValueError("Frozen transfer source changed")
    if doc["inputs_sha256"] != sha(path.parent / "inputs.json"):
        raise ValueError("Transfer inputs changed")
    for n, h in doc["component_sha256"].items():
        if sha(ROOT / n) != h:
            raise ValueError("Transfer specification changed")
    if runtime and globals()["runtime"]() != doc["runtime"]:
        raise ValueError("Bound runtime changed")
    return doc
