"""Execute the replacement campaign only when Task 08D is explicitly authorized."""

from pathlib import Path
import argparse
import fcntl
import json
import shutil
from evaluation.safety import safe_path, bind_run, atomic_json, strict_json, utc_now
from .identity import verify, sha, REPO
from .generator import case_payload
from .pipeline import pipeline


def run(freeze_path, evaluation_id, output, *, workers=4, authorize_task08d=False):
    if authorize_task08d is not True:
        raise PermissionError(
            "Task08D must be explicitly invoked; freezing alone does not authorize execution"
        )
    doc = verify(freeze_path, evaluation_id, runtime=True)
    if type(workers) is not int or workers != doc["resources"]["workers"]:
        raise ValueError("Frozen concurrency differs")
    output = safe_path(output)
    project = REPO.parents[1]
    evidence = project / "evidence/space-autonomy-lab"
    if (
        output != project / ".research/tasks/08D/protected-v2"
        or output.is_relative_to(REPO)
        or output.is_relative_to(evidence)
    ):
        raise ValueError("Use the exact new protected output location")
    ancestor = output
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < doc["resources"]["minimum_free_disk_bytes"]:
        raise RuntimeError("Insufficient free disk for frozen execution")
    bind_run(project / ".research/evaluation-identities", evaluation_id, output, sha(freeze_path))
    output.parent.mkdir(parents=True, exist_ok=True)
    lock_path = safe_path(output.parent / ("." + output.name + ".execution.lock"))
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        header = {
            "schema": "sal-replacement-run/1",
            "evaluation_id": evaluation_id,
            "freeze_sha256": sha(freeze_path),
            "source_commit": doc["source_commit"],
            "workers": workers,
        }
        if output.exists():
            saved = strict_json(output / "run_header.json")
            if any(saved.get(k) != v for k, v in header.items()):
                raise ValueError("Run header changed")
        else:
            output.mkdir()
            atomic_json(output / "run_header.json", {**header, "started_at_utc": utc_now()})
        reserve = strict_json(Path(freeze_path).parent / "reserve.json")
        payloads = [case_payload("protected", r["stratum"], r["index"]) for r in reserve["cases"]]
        return pipeline(
            payloads,
            output,
            identity=evaluation_id,
            resources=doc["resources"],
            target_per_stratum=192,
            protected=True,
        )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--freeze", type=Path, required=True)
    p.add_argument("--evaluation-id", required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--authorize-task08d", action="store_true")
    a = p.parse_args()
    result = run(
        a.freeze,
        a.evaluation_id,
        a.output,
        workers=a.workers,
        authorize_task08d=a.authorize_task08d,
    )
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    if not result.get("campaign_complete"):
        raise SystemExit(2)
    if not result.get("validity_claim_gate_passed"):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
