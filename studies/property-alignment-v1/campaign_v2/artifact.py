"""Package exact completed records or verify them without repeating scientific trials."""

from pathlib import Path
import argparse
import json
from .audit import audit, Records, sha, decode, require, FREEZE
from .report import make_report


def write_new(path, raw):
    with Path(path).open("xb") as f:
        f.write(raw)


def json_bytes(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def pack(run, dest):
    """Publish readable text while retaining every original UTF-8 byte."""
    records = Records(run)
    try:
        before = records.inventory()
        with Path(dest).open("xb") as stream:
            for name in sorted(records.names):
                entry = {"path": name, "raw_utf8": records.raw(name).decode("utf-8")}
                stream.write(
                    (
                        json.dumps(
                            entry,
                            sort_keys=True,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                        + "\n"
                    ).encode("utf-8")
                )
        require(before == records.inventory(), "Raw records changed while packaging")
        return before
    finally:
        records.close()


def build(run, execution_path, output):
    output = Path(output)
    require(not output.exists(), "Artifact is write-once")
    execution = decode(Path(execution_path).read_bytes())
    require(
        execution.get("exit_code") == 0 and execution.get("outer_watchdog_reached") is False,
        "The frozen invocation did not finish successfully",
    )
    checked, analysis, qs, rows, inputs, selected = audit(run)
    require(execution["evaluation_id"] == checked["evaluation_id"], "Wrong launcher identity")
    summary, tables = make_report(checked, analysis, qs, rows, inputs, selected, execution)
    output.mkdir(parents=True)
    raw_members = pack(run, output / "raw_records.jsonl")
    for name, doc in [
        ("audit.json", checked),
        ("analysis.json", analysis),
        ("summary.json", summary),
        ("inputs.json", inputs),
        ("execution_receipt.json", execution),
    ]:
        write_new(output / name, json_bytes(doc))
    for name, text in tables.items():
        write_new(output / name, text.encode())
    files = {p.name: sha(p.read_bytes()) for p in sorted(output.iterdir()) if p.is_file()}
    manifest = {
        "schema": "sal-replacement-campaign-artifact/2",
        "evaluation_id": checked["evaluation_id"],
        "freeze_sha256": sha(FREEZE.read_bytes()),
        "files": files,
        "raw_members": raw_members,
        "raw_bytes_preserved": True,
        "new_scientific_trials_performed_during_packaging": False,
        "clock_values_preserved": True,
        "contains_manuscript_sources": False,
    }
    write_new(output / "manifest.json", json_bytes(manifest))
    return verify_artifact(output)


def verify_artifact(output):
    output = Path(output)
    manifest = decode((output / "manifest.json").read_bytes())
    files = {
        p.name: sha(p.read_bytes())
        for p in sorted(output.iterdir())
        if p.is_file() and p.name != "manifest.json"
    }
    require(manifest["files"] == files, "Exported artifact files differ")
    require(
        manifest["freeze_sha256"] == sha(FREEZE.read_bytes()), "Exported freeze identity differs"
    )
    records = Records(output / "raw_records.jsonl")
    try:
        require(records.inventory() == manifest["raw_members"], "Archived raw bytes differ")
    finally:
        records.close()
    checked, analysis, qs, rows, inputs, selected = audit(output / "raw_records.jsonl")
    execution = decode((output / "execution_receipt.json").read_bytes())
    summary, tables = make_report(checked, analysis, qs, rows, inputs, selected, execution)
    for name, expected in [
        ("audit.json", checked),
        ("analysis.json", analysis),
        ("summary.json", summary),
        ("inputs.json", inputs),
    ]:
        require(decode((output / name).read_bytes()) == expected, "Saved report disagrees " + name)
    for name, text in tables.items():
        require((output / name).read_text() == text, "Saved table disagrees " + name)
    return {
        "passed": True,
        "evaluation_id": checked["evaluation_id"],
        "qualification_receipts": len(qs),
        "selected_receipts": len(rows),
        "raw_files": checked["raw_files"],
        "on_time_verified_diagnostics": analysis["on_time_decisive_valid"],
        "campaign_complete": analysis["campaign_complete"],
        "validity_claim_gate_passed": analysis["validity_claim_gate_passed"],
        "frozen_analysis_reproduced": True,
        "policy_or_qualification_rerun": False,
        "new_numerical_replay": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path)
    p.add_argument("--execution", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verify", action="store_true")
    a = p.parse_args()
    if a.verify:
        result = verify_artifact(a.output)
    else:
        if a.run is None or a.execution is None:
            p.error("Supply --run and --execution to build")
        result = build(a.run, a.execution, a.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
