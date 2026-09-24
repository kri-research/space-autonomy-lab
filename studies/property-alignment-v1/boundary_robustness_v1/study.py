"""One bounded post hoc sensitivity execution; no policy or old audit is run."""

from pathlib import Path
from datetime import datetime, timezone
from fractions import Fraction as Q
import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from .core import ROOT, Parameters, evaluate, family_parameters, check_stress, require
from independent_hcw_audit_v1.schema import identity, strict_json


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as f:
        f.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def inventory():
    paths = [x for x in ROOT.rglob("*.py") if "__pycache__" not in x.parts]
    paths += [ROOT / x for x in ("protocol.json", "anchors.json", "DERIVATION.md", "sources.json")]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(paths)}


def freeze(output):
    repo = ROOT.parents[2]
    prefix = ROOT.relative_to(repo).as_posix()
    commit = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repo), "rev-parse", "HEAD"], text=True
    ).strip()
    sources = inventory()
    for name, h in sources.items():
        raw = subprocess.check_output(
            [
                "git",
                "--no-replace-objects",
                "-C",
                str(repo),
                "show",
                commit + ":" + prefix + "/" + name,
            ]
        )
        require(hashlib.sha256(raw).hexdigest() == h, "Uncommitted study source")
    anchors = strict_json((ROOT / "anchors.json").read_bytes())
    for name, h in anchors["source_files"].items():
        require(sha(ROOT.parent / name) == h, "Prior numerical evidence changed")
    doc = {
        "schema": "sal-robustness-freeze/1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "post_hoc": True,
        "source_commit": commit,
        "source_sha256": sources,
        "protocol": strict_json((ROOT / "protocol.json").read_bytes()),
        "python_version": sys.version.split()[0],
        "prior_sources": anchors["source_files"],
    }
    doc["study_id"] = identity(doc)
    write_new(output, doc)
    return doc


def verify_freeze(path, study_id):
    doc = strict_json(Path(path).read_bytes())
    require(
        doc.get("study_id")
        == study_id
        == identity({k: v for k, v in doc.items() if k != "study_id"}),
        "Freeze identity",
    )
    require(doc["schema"] == "sal-robustness-freeze/1" and doc["post_hoc"] is True, "Freeze scope")
    require(doc["source_sha256"] == inventory(), "Study source changed")
    require(
        doc["protocol"] == strict_json((ROOT / "protocol.json").read_bytes()), "Protocol changed"
    )
    require(doc["python_version"] == sys.version.split()[0], "Python version changed")
    require(doc["protocol"]["anchors_sha256"] == sha(ROOT / "anchors.json"), "Anchor identity")
    for name, h in doc["prior_sources"].items():
        require(sha(ROOT.parent / name) == h, "Frozen numerical source changed")
    return doc


def bisect_gate(family, gate, query, steps):
    probes = []

    def admitted(rho):
        result = query(family_parameters(family, rho))
        verdict = result["gates"][gate]
        probes.append(
            {"rho": str(rho), "evaluation_id": identity(result["parameters"]), "admitted": verdict}
        )
        return verdict

    require(admitted(Q(0)), "Nominal construction not certified")
    lo, hi = Q(0), Q(1)
    if admitted(hi):
        return {
            "family": family["name"],
            "gate": gate,
            "lower_radius": "1",
            "noncertified_upper": None,
            "cap_passed": True,
            "probes": probes,
        }
    for _ in range(steps):
        mid = (lo + hi) / 2
        if admitted(mid):
            lo = mid
        else:
            hi = mid
    return {
        "family": family["name"],
        "gate": gate,
        "lower_radius": str(lo),
        "noncertified_upper": str(hi),
        "cap_passed": False,
        "probes": probes,
    }


def execute(output, frozen, study_id):
    doc = verify_freeze(frozen, study_id)
    plan = doc["protocol"]
    output = Path(output).expanduser().absolute()
    require(
        not output.exists() and not any(p.is_symlink() for p in (output, *output.parents)),
        "New nonsymlink output required",
    )
    require(
        not any((p / ".git").exists() for p in (output, *output.parents)),
        "Output overlaps repository",
    )
    output.mkdir(parents=True)
    write_new(
        output / "header.json",
        {
            "study_id": study_id,
            "source_commit": doc["source_commit"],
            "protocol": plan,
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
            "original_campaign_executed": False,
        },
    )
    started = time.monotonic()
    cache = {}
    searches = []

    def timeout(signum, frame):
        raise TimeoutError("Registered evaluation budget")

    previous = signal.signal(signal.SIGALRM, timeout)

    def query(parameters):
        key = identity(parameters.payload())
        if key in cache:
            return cache[key]
        require(len(cache) < plan["limits"]["max_unique_evaluations"], "Evaluation count limit")
        if time.monotonic() - started > plan["limits"]["run_seconds"]:
            raise TimeoutError("Registered study budget")
        write_new(
            output / "started" / (key + ".json"),
            {"parameters": parameters.payload(), "study_id": study_id},
        )
        begin = time.monotonic()
        signal.setitimer(signal.ITIMER_REAL, plan["limits"]["per_evaluation_seconds"])
        try:
            result = evaluate(parameters)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        write_new(
            output / "evaluations" / (key + ".json"),
            {"study_id": study_id, "result": result, "elapsed_s": time.monotonic() - begin},
        )
        cache[key] = result
        return result

    try:
        for family in plan["families"]:
            for gate in plan["search"]["gates"]:
                answer = bisect_gate(family, gate, query, plan["search"]["bisection_steps"])
                answer["lower_parameters"] = family_parameters(
                    family, Q(answer["lower_radius"])
                ).payload()
                searches.append(answer)
                write_new(output / "searches" / (family["name"] + "-" + gate + ".json"), answer)
        stress = [check_stress(x) for x in plan["stress"]]
        write_new(output / "stress.json", stress)
        summary = {
            "schema": "sal-robustness-summary/1",
            "study_id": study_id,
            "unique_evaluations": len(cache),
            "searches": searches,
            "stress": stress,
            "nominal": query(Parameters()),
            "elapsed_s": time.monotonic() - started,
            "fixed_commands_unchanged": True,
            "original_campaigns_executed": False,
            "independent_human_review": False,
            "physical_validation": False,
        }
        write_new(output / "summary.json", summary)
        verify_freeze(frozen, study_id)
        files = {
            p.relative_to(output).as_posix(): sha(p)
            for p in sorted(output.rglob("*"))
            if p.is_file()
        }
        write_new(
            output / "completion.json",
            {
                "study_id": study_id,
                "files": files,
                "complete": True,
                "unique_evaluations": len(cache),
            },
        )
        return summary
    except Exception as exc:
        write_new(
            output / "failure.json",
            {
                "type": type(exc).__name__,
                "message": str(exc),
                "completed_evaluations": len(cache),
                "retry": False,
            },
        )
        raise
    finally:
        signal.signal(signal.SIGALRM, previous)


def verify_results(output, frozen, study_id, recompute=False):
    doc = verify_freeze(frozen, study_id)
    output = Path(output)
    done = strict_json((output / "completion.json").read_bytes())
    require(done["study_id"] == study_id and done["complete"] is True, "Incomplete study")
    actual = {
        p.relative_to(output).as_posix(): sha(p)
        for p in output.rglob("*")
        if p.is_file() and p.name != "completion.json"
    }
    require(actual == done["files"], "Recorded bytes changed")
    summary = strict_json((output / "summary.json").read_bytes())
    results = {}
    for path in (output / "evaluations").glob("*.json"):
        row = strict_json(path.read_bytes())
        result = row["result"]
        require(row["study_id"] == study_id, "Evaluation study binding")
        require(
            result["result_sha256"]
            == identity({k: v for k, v in result.items() if k != "result_sha256"}),
            "Result digest",
        )
        key = identity(result["parameters"])
        require(path.stem == key and key not in results, "Evaluation identity")
        p = Parameters(**result["parameters"])
        if recompute:
            require(evaluate(p) == result, "Independent recorded calculation changed")
        results[key] = result
    require(
        len(results) == summary["unique_evaluations"] == done["unique_evaluations"],
        "Denominator changed",
    )
    require(
        {p.stem for p in (output / "started").glob("*.json")} == set(results),
        "Unaccounted evaluation start",
    )
    searches = []

    def query(p):
        key = identity(p.payload())
        require(key in results, "Missing prescribed evaluation")
        return results[key]

    for family in doc["protocol"]["families"]:
        for gate in doc["protocol"]["search"]["gates"]:
            ans = bisect_gate(family, gate, query, doc["protocol"]["search"]["bisection_steps"])
            ans["lower_parameters"] = family_parameters(family, Q(ans["lower_radius"])).payload()
            searches.append(ans)
    require(searches == summary["searches"], "Search schedule/output changed")
    if recompute:
        require(
            [check_stress(x) for x in doc["protocol"]["stress"]] == summary["stress"],
            "Stress replay differs",
        )
    return {
        "passed": True,
        "evaluations": len(results),
        "searches": len(searches),
        "recomputed": recompute,
        "original_campaign_executed": False,
        "study_id": study_id,
    }


def main():
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("mode", choices=["freeze", "run", "verify"])
    a.add_argument("--output", type=Path, required=True)
    a.add_argument("--freeze", type=Path)
    a.add_argument("--study-id")
    a.add_argument("--recompute", action="store_true")
    args = a.parse_args()
    if args.mode == "freeze":
        answer = freeze(args.output)
    elif args.mode == "run":
        answer = execute(args.output, args.freeze, args.study_id)
    else:
        answer = verify_results(args.output, args.freeze, args.study_id, args.recompute)
    print(json.dumps(answer, indent=2))


if __name__ == "__main__":
    main()
