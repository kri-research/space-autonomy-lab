"""Post hoc audit freeze; identity construction performs no numerical audit."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import subprocess
import sys
from .schema import strict_json, identity, require
from .reader import load_dataset, safe_name

ROOT = Path(__file__).resolve().parent
SCIENTIFIC_COMMIT = "b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8"
ORIGINAL_FILES = (
    "campaign_v2/recorded/manifest.json",
    "campaign_v2/recorded/inputs.json",
    "campaign_v2/recorded/raw_records.jsonl",
    "evaluation_v2/frozen/freeze.json",
    "evaluation_v2/frozen/reserve.json",
    "evaluation_v2/frozen/protocol.json",
    "specification/property_contract.json",
    "candidate/information.py",
    "candidate/affine.py",
    "candidate/certify.py",
    "adjudication/flow.py",
    "evaluation_v2/receipts.py",
    "evaluation_v2/generator.py",
    "evaluation/episode.py",
    "qualification_repair_v1/core.py",
    "evaluation/qualification.py",
)
SETTINGS = {
    "workers": 1,
    "job_timeout_s": 30,
    "phase_timeout_s": 1800,
    "phase_limit_meaning": "Stop launching new jobs after1800s per invocation; the final in-flight job is limited to30s. Explicit resume may process unstarted jobs only.",
    "numerical": {"max_cells_per_prefix": 16384, "minimum_time_width_s": "1/65536"},
    "precision_bits": 192,
    "response_series_terms": 10,
    "maximum_time_s": "3",
    "qualification": "Check every saved singleton prefix for all768selected cases, including original unresolved/late cases; no re-selection or library search.",
    "original_unknowns": "Retain the nine unresolved and three late records as no_on_time_certificate, regardless of any internal late proof.",
    "outcomes": [
        "verified_prefix",
        "verified_obstruction",
        "numerically_unresolved",
        "binding_invalid_evidence",
        "unsupported_assumptions",
        "contradicted_prefix",
        "no_on_time_certificate",
        "audit_timeout",
        "audit_interrupted",
        "audit_execution_failure",
    ],
    "resume": "Only unstarted jobs may execute. Existing valid receipts are read-only. Started-without-result is recorded as interrupted, not silently retried.",
    "amendments": "Any changed numerical method, resource setting or retried started job requires a new audit version/identity retaining the original attempt.",
    "online_budget": "Offline resource limits do not change the original one-second decision budget or coverage endpoint.",
    "historical_campaigns_or_policies_executed": False,
    "probability_claim": "Post hoc certificate audit of known outcomes; no blinded experiment or new population estimate.",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_inventory():
    files = [x for x in ROOT.rglob("*.py") if "__pycache__" not in x.parts]
    files += [
        ROOT / n
        for n in (
            "contract.json",
            "development_cases.json",
            "development_provenance.json",
            "reference_inputs/independent_hcw_results.json",
            "reference_inputs/independent_hcw_check.py.txt",
            "calibration_plan.json",
            "DERIVATION.md",
        )
    ]
    require(all(x.is_file() and not x.is_symlink() for x in files), "Missing/unsafe auditor source")
    return {x.relative_to(ROOT).as_posix(): sha(x) for x in sorted(set(files))}


def validate_document(doc, audit_id):
    require(
        type(doc) is dict and doc.get("schema") == "sal-independent-hcw-audit-freeze/1",
        "Audit schema",
    )
    require(
        doc.get("audit_id") == audit_id
        and identity({k: v for k, v in doc.items() if k != "audit_id"}) == audit_id,
        "Audit freeze identity",
    )
    require(doc.get("protocol") == SETTINGS, "Unreviewed protocol or resource settings")
    require(
        doc.get("scientific_source_commit") == SCIENTIFIC_COMMIT
        and doc.get("post_hoc") is True
        and doc.get("full_campaign_executed") is False,
        "Wrong original scope",
    )
    require(
        doc.get("python_version") == sys.version.split()[0] == "3.13.5",
        "Frozen Python version differs",
    )
    commit = doc.get("implementation_commit")
    require(
        type(commit) is str and len(commit) == 40 and all(c in "0123456789abcdef" for c in commit),
        "Full implementation commit identity required",
    )
    sources = doc.get("auditor_source_sha256")
    require(
        type(sources) is dict and sources == source_inventory(),
        "Incomplete or changed auditor source inventory",
    )
    require(
        set(doc.get("original_files_sha256", {})) == set(ORIGINAL_FILES),
        "Incomplete original input inventory",
    )
    rows = doc.get("case_bindings")
    require(
        type(rows) is list and len(rows) == 768 and len({r["key"] for r in rows}) == 768,
        "Original selected case membership",
    )
    for row in rows:
        require(
            set(row) == {"key", "input_sha256", "episode_sha256", "qualification_sha256"},
            "Case binding fields",
        )
        safe_name(row["key"])
        for key in ("input_sha256", "episode_sha256", "qualification_sha256"):
            require(
                type(row[key]) is str
                and len(row[key]) == 64
                and all(c in "0123456789abcdef" for c in row[key]),
                "Malformed case digest",
            )
    return doc


def build(destination):
    destination = Path(destination)
    require(not destination.exists(), "Freeze already exists")
    study = ROOT.parent
    repo = study.parents[1]

    def git(*args):
        return subprocess.check_output(["git", "--no-replace-objects", "-C", str(repo), *args])

    commit = git("rev-parse", "HEAD").decode().strip()
    sources = source_inventory()
    for name, h in sources.items():
        original = git(
            "show", commit + ":studies/property-alignment-v1/independent_hcw_audit_v1/" + name
        )
        require(
            hashlib.sha256(original).hexdigest() == h, "Auditor must be committed before freeze"
        )
    originals = {}
    for name in ORIGINAL_FILES:
        raw = (study / name).read_bytes()
        require(
            raw == git("show", SCIENTIFIC_COMMIT + ":studies/property-alignment-v1/" + name),
            "Original source differs from Git",
        )
        originals[name] = hashlib.sha256(raw).hexdigest()
    cases, summary = load_dataset(study, originals)
    doc = {
        "schema": "sal-independent-hcw-audit-freeze/1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "implementation_commit": commit,
        "scientific_source_commit": SCIENTIFIC_COMMIT,
        "post_hoc": True,
        "full_campaign_executed": False,
        "python_version": sys.version.split()[0],
        "auditor_source_sha256": sources,
        "original_files_sha256": originals,
        "case_bindings": [{"key": x["key"], **x["bindings"]} for x in cases],
        "structural_reader_summary": summary,
        "protocol": SETTINGS,
    }
    doc["audit_id"] = identity(doc)
    validate_document(doc, doc["audit_id"])
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x") as f:
        f.write(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return {
        "audit_id": doc["audit_id"],
        "implementation_commit": commit,
        "source_files": len(sources),
        "selected_bindings": len(cases),
        "full_campaign_executed": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--create", type=Path)
    p.add_argument("--verify", type=Path)
    p.add_argument("--audit-id")
    a = p.parse_args()
    if a.create:
        require(a.verify is None, "One action only")
        result = build(a.create)
    else:
        require(
            a.verify is not None and a.audit_id is not None, "Verification needs exact identity"
        )
        doc = validate_document(strict_json(a.verify.read_bytes()), a.audit_id)
        cases, summary = load_dataset(ROOT.parent, doc["original_files_sha256"])
        require(
            [{"key": x["key"], **x["bindings"]} for x in cases] == doc["case_bindings"],
            "Case receipt bindings differ from frozen identity",
        )
        result = {
            "passed": True,
            "audit_id": a.audit_id,
            "reader": summary,
            "full_campaign_executed": False,
        }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
