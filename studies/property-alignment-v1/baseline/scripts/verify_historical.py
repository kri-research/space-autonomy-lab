"""Read-only audit of pinned campaign bytes; writes separate retrospective diagnostics."""

from pathlib import Path, PurePosixPath
import argparse
import csv
import hashlib
import io
import json
import math
import platform
import subprocess
import sys
import tarfile
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.records import aggregate, PRIMARY, ARMS
from validation.properties import inside_union
from validation.paths import evidence_root

COMMIT = "5539de5753092b09fd78351095292e7627047794"
E4 = "results/experiment-004-replacement-confirmatory/confirmatory-episodes.jsonl"
ARCHIVE = "supplements/2026-09-09-evidence-reconciliation/e005-original-records.tar.gz"
E5 = "results/experiment-005-confirmatory/campaign/confirmatory-episodes.jsonl"
HASHES = {
    E4: "bf1754d89edc2bb06f9b3176e3b29a99bb610412a0437404ddc7b1286432233e",
    ARCHIVE: "3f0f71990c65159bfda70b79f24ca364bfaf12a736f2d1721844e032e9697b03",
    E5: "d27d53e71ec28ffd7ab830f870226f6231ddf7c0d1e4df8a872d88678d12798a",
}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def parse(b):
    def reject(value):
        raise ValueError("Nonfinite JSON token: " + value)

    return [json.loads(line, parse_constant=reject) for line in b.splitlines() if line.strip()]


def write_csv(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def checked(repo, path):
    b = (repo / path).read_bytes()
    if sha(b) != HASHES[path]:
        raise ValueError("Source digest mismatch: " + path)
    return b


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", type=Path, default=evidence_root())
    ap.add_argument("--output", type=Path, default=ROOT / "data/historical_audit")
    args = ap.parse_args()
    repo = args.repo.resolve()
    out = args.output.resolve()
    if out.is_relative_to(repo):
        raise ValueError("Output inside frozen repository")

    def git(*a):
        return subprocess.check_output(
            ["git", "--no-replace-objects", "-C", str(repo), *a], text=True
        ).strip()

    if git("rev-parse", "HEAD") != COMMIT:
        raise ValueError("Incorrect source commit")
    before = git("status", "--porcelain", "--untracked-files=no")
    if before:
        raise ValueError("Historical tracked files are modified")
    raw4 = checked(repo, E4)
    archive = checked(repo, ARCHIVE)
    members = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tf:
        for m in tf.getmembers():
            path = PurePosixPath(m.name)
            if path.is_absolute() or ".." in path.parts or not m.isfile() or m.name in members:
                raise ValueError("Unsafe or duplicate archive member: " + m.name)
            members[m.name] = tf.extractfile(m).read()
    raw5 = members[E5]
    if sha(raw5) != HASHES[E5]:
        raise ValueError("E005 campaign digest mismatch")
    rows = {"E004": parse(raw4), "E005": parse(raw5)}
    result = {s: aggregate(s, rr) for s, rr in rows.items()}
    campaign = {
        (r["root_seed_id"], r["configuration_id"]): line
        for line in raw5.splitlines()
        for r in [json.loads(line)]
    }
    replay = members["results/experiment-005-confirmatory/replay/confirmatory-episodes.jsonl"]
    if len(parse(replay)) != 32:
        raise ValueError("Wrong stored replay size")
    for line in replay.splitlines():
        r = json.loads(line)
        if campaign.get((r["root_seed_id"], r["configuration_id"])) != line:
            raise ValueError("Replay mismatch")
    summaries = [r for d in result.values() for r in d["summary"]]
    old = ROOT / "evidence/prior_aggregates"
    if not old.is_dir():
        raise ValueError("Prior aggregate inputs are required")
    for e in csv.DictReader((old / "historical_common_property.csv").open()):
        a = next(
            r
            for r in summaries
            if r["study"] == e["study"]
            and r["arm"] == e["arm"]
            and r["role"] == "primary"
            and ("bias" if "bias" in r["case"] else "dropout") == e["case"]
        )
        for k in ["minimum_episode_minimum_m", "maximum_episode_minimum_m"]:
            if a[k] != float(e[k]):
                raise ValueError("Earlier range disagrees: " + str(e))
        if a["closed_union_witness_count"] != int(e["witness_count"]):
            raise ValueError("Earlier witness count disagrees")
    for e in csv.DictReader((old / "historical_engagement.csv").open()):
        a = next(
            r
            for r in summaries
            if r["study"] == e["study"]
            and r["arm"] == ARMS[1]
            and r["role"] == "primary"
            and ("bias" if "bias" in r["case"] else "dropout") == e["case"]
        )
        for k in [
            "episodes_with_override",
            "override_decisions",
            "quality_reason_decisions",
            "geometry_reason_decisions",
        ]:
            if a[k] != int(e[k]):
                raise ValueError("Earlier engagement disagrees: " + str(e))
    out.mkdir(parents=True, exist_ok=True)
    for name in result["E004"]:
        write_csv(out / (name + ".csv"), [r for d in result.values() for r in d[name]])
    joint = []
    initial = []
    seed_members = {}
    seed4 = "experiments/004-replacement-confirmatory/seeds/confirmatory.jsonl"
    seed5 = "experiments/005-confirmatory/seeds/confirmatory.jsonl"
    seed_bytes = {"E004": (repo / seed4).read_bytes(), "E005": members[seed5]}
    for study, rr in rows.items():
        seeds = {r["root_seed_id"]: r for r in parse(seed_bytes[study])}
        root_set = {r["root_seed_id"] for r in rr}
        if seeds.keys() != root_set:
            raise ValueError("Materialized seed membership disagrees")
        seed_members[study] = {"roots": len(seeds), "sha256": sha(seed_bytes[study])}
        reference = {r["root_seed_id"]: r for r in rr if r["configuration_id"] == ARMS[0]}
        for row in rr:
            seed = seeds[row["root_seed_id"]]
            for field in [
                "case_id",
                "case_code",
                "replicate",
                "scenario_hash",
                "stream_hashes",
                "design_freeze_id",
            ]:
                if row[field] != seed[field]:
                    raise ValueError("Seed/episode identity mismatch: " + field)
            if (
                row["run_order"]
                != seed["configuration_run_order"].index(row["configuration_id"]) + 1
            ):
                raise ValueError("Seed/episode arm order mismatch")
        for root, s in seeds.items():
            state = s["initial_state"] if study == "E004" else s["initial_relative_state"]
            if any(not math.isfinite(v) for v in state):
                raise ValueError("Nonfinite seed state")
            initial.append(
                dict(
                    study=study,
                    case=s["case_id"],
                    root_seed_id=root,
                    role="primary" if s["case_id"] in PRIMARY[study] else "descriptive",
                    initial_x_m=state[0],
                    initial_y_m=state[1],
                    initial_inside_union=inside_union(state),
                    fault_onset_s=s["fault_onset_s"],
                    fault_end_s=s["fault_end_s"],
                )
            )
        for g in rr:
            if g["configuration_id"] != ARMS[1] or g["case_id"] not in PRIMARY[study]:
                continue
            r = reference[g["root_seed_id"]]
            joint.append(
                dict(
                    study=study,
                    case=g["case_id"],
                    root_seed_id=g["root_seed_id"],
                    no_override=g["monitor_override_commands"] == 0,
                    equal_trace=r["trace_digest"] == g["trace_digest"],
                    equal_final=r.get("final_state", r.get("final_truth_relative_state"))
                    == g.get("final_state", g.get("final_truth_relative_state")),
                )
            )
    write_csv(out / "initial_states.csv", initial)
    write_csv(out / "paired_engagement.csv", joint)
    joint_counts = []
    initial_counts = []
    for study in rows:
        jj = [r for r in joint if r["study"] == study]
        for no in [False, True]:
            for eq in [False, True]:
                joint_counts.append(
                    dict(
                        study=study,
                        no_override=no,
                        equal_trace=eq,
                        pairs=sum(r["no_override"] == no and r["equal_trace"] == eq for r in jj),
                    )
                )
        for role in ["primary", "descriptive"]:
            ii = [r for r in initial if r["study"] == study and r["role"] == role]
            if ii:
                initial_counts.append(
                    dict(
                        study=study,
                        role=role,
                        roots=len(ii),
                        inside=sum(r["initial_inside_union"] for r in ii),
                        outside=sum(not r["initial_inside_union"] for r in ii),
                    )
                )
    write_csv(out / "paired_engagement_counts.csv", joint_counts)
    write_csv(out / "initial_membership_counts.csv", initial_counts)
    common = []
    engagement = []
    paired = []
    for r in summaries:
        if r["role"] != "primary":
            continue
        case = "bias" if "bias" in r["case"] else "dropout"
        common.append(
            dict(
                study=r["study"],
                case=case,
                arm=r["arm"],
                episodes=r["episodes"],
                minimum_episode_minimum_m=r["minimum_episode_minimum_m"],
                maximum_episode_minimum_m=r["maximum_episode_minimum_m"],
                witness_count=r["closed_union_witness_count"],
            )
        )
        if r["arm"] == ARMS[1]:
            engagement.append(
                dict(
                    study=r["study"],
                    case=case,
                    episodes=r["episodes"],
                    **{
                        k: r[k]
                        for k in [
                            "episodes_with_override",
                            "override_decisions",
                            "quality_reason_decisions",
                            "geometry_reason_decisions",
                        ]
                    },
                )
            )
    write_csv(ROOT / "data/historical_common_property.csv", common)
    write_csv(ROOT / "data/historical_engagement.csv", engagement)
    for study, d in result.items():
        q = d["pair_tables"][0]
        paired.append({k: q[k] for k in ["study", "n00", "n10", "n01", "n11"]})
    write_csv(ROOT / "data/paired_counts.csv", paired)
    if git("status", "--porcelain", "--untracked-files=no") != before:
        raise ValueError("Historical tracked files changed")
    manifest = dict(
        commit=COMMIT,
        checked_at_utc=datetime.now(timezone.utc).isoformat(),
        raw_rows_read=sum(map(len, rows.values())),
        input_sha256=HASHES,
        archive_members=len(members),
        archive_uncompressed_bytes=sum(map(len, members.values())),
        stored_replay_rows_matched=32,
        seed_inputs=seed_members,
        prior_aggregate_comparison="exact agreement",
        historical_simulation_executed=False,
        historical_endpoints_changed=False,
        tracked_repository_status="clean",
        python=platform.python_version(),
        platform=platform.platform(),
    )
    (out / "verification.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))
    print("INITIAL MEMBERSHIP", initial_counts)
    print("JOINT ENGAGEMENT", joint_counts)


if __name__ == "__main__":
    main()
