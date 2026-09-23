"""Profile only retired qualification inputs without changing production code."""

from pathlib import Path
from collections import Counter
from fractions import Fraction
import argparse
import cProfile
import hashlib
import importlib
import json
import pstats
import time

PACKAGE = Path(__file__).resolve().parent
STUDY = PACKAGE.parent


def read_protocol():
    return json.loads((PACKAGE / "protocol.json").read_text())


def validate_case(index):
    from evaluation.generator import case_payload
    from evaluation.safety import canonical_hash

    protocol = read_protocol()
    entries = [x for x in protocol["inputs"] if x["index"] == index]
    if len(entries) != 1:
        raise ValueError("Only six explicitly retired diagnostic inputs permitted")
    payload = case_payload("protected", "timing_bounded_pair", index)
    if canonical_hash(payload) != entries[0]["payload_sha256"]:
        raise ValueError("Retired input hash differs")
    return payload


def atomic_new(path, data):
    with Path(path).open("x") as handle:
        json.dump(data, handle, indent=2, allow_nan=False)
        handle.write("\n")


def profile_rows(profiler):
    result = []
    for (file, line, name), (primitive, calls, own, cumulative, _) in pstats.Stats(
        profiler
    ).stats.items():
        p = Path(file)
        label = p.relative_to(STUDY).as_posix() if p.is_relative_to(STUDY) else p.name
        result.append(
            {
                "source": label,
                "line": line,
                "function": name,
                "primitive_calls": primitive,
                "calls": calls,
                "self_s": own,
                "cumulative_s": cumulative,
            }
        )
    return sorted(result, key=lambda row: row["cumulative_s"], reverse=True)


def run(index, mode, output):
    begin, cpu_begin = time.perf_counter(), time.process_time()
    output = Path(output).expanduser().absolute()
    if (
        any(p.is_symlink() for p in (output, *output.parents))
        or output.is_relative_to(STUDY.parents[1])
        or output.is_relative_to(STUDY.parents[3] / ".research/tasks/08/protected-v1")
        or output.is_relative_to(STUDY.parents[3] / "evidence")
    ):
        raise ValueError("New nonsymlink output outside repository required")
    output.mkdir(parents=True, exist_ok=False)
    events = (output / "events.jsonl").open("x", buffering=1)

    def event(kind, **details):
        events.write(
            json.dumps(
                {
                    "event": kind,
                    "wall_s": time.perf_counter() - begin,
                    "cpu_s": time.process_time() - cpu_begin,
                    **details,
                },
                allow_nan=False,
            )
            + "\n"
        )

    event("process_entered", index=index, mode=mode)
    from evaluation.execute import verify_freeze
    from evaluation.runner import _information

    protocol = read_protocol()
    verify_freeze(STUDY / "evaluation/frozen/freeze.json", protocol["old_evaluation_id"])
    payload = validate_case(index)
    info = _information(payload)
    qual = importlib.import_module("evaluation.qualification")
    certify = importlib.import_module("candidate.certify")

    def forbidden(*args, **kwargs):
        raise AssertionError("Full-set policy or protected campaign prohibited in Task08A")

    qual.decide = forbidden
    certify.decide = forbidden
    input_record = {
        "evidence_class": "post_failure_development_diagnosis",
        "original_case": payload,
        "original_input_retired": True,
        "replacement_of_original_outcome": False,
        "mode": mode,
        "protocol_sha256": hashlib.sha256((PACKAGE / "protocol.json").read_bytes()).hexdigest(),
    }
    atomic_new(output / "input.json", input_record)
    event("imports_and_identity_ready")
    geometry_counts = Counter()
    if mode in ("trace", "profile"):
        engine = importlib.import_module("adjudication.engine")
        original_bounds = engine.bounds

        def counted_bounds(*args, **kwargs):
            value = original_bounds(*args, **kwargs)
            geometry_counts[(str(value["containment"]), str(value["hold"]))] += 1
            return value

        engine.bounds = counted_bounds
        original_flow, original_adjudicate = certify.propagate_schedule, certify.adjudicate

        def traced_flow(*args, **kwargs):
            start, cpu = time.perf_counter(), time.process_time()
            event("propagation_started")
            arcs = original_flow(*args, **kwargs)
            event(
                "propagation_ended",
                elapsed_s=time.perf_counter() - start,
                cpu_elapsed_s=time.process_time() - cpu,
                arcs=len(arcs),
            )
            return arcs

        def traced_adjudicate(arcs, prop, **kwargs):
            snapshots = []
            # Diagnostic inspection only; original arcs and arguments passed unchanged.
            for arc in arcs:
                t = (Fraction(arc.start) + Fraction(arc.end)) / 2
                box = arc.point(t)
                m = original_bounds(box, prop)
                snapshots.append(
                    {
                        "t_s": str(t),
                        "box": [[c.lo, c.hi] for c in box.coordinates],
                        "containment": str(m["containment"]),
                        "hold": str(m["hold"]),
                        "approach_residual_m": [
                            [str(v) for v in r] for r in m["approach_residual_m"]
                        ],
                    }
                )
            start, cpu = time.perf_counter(), time.process_time()
            event("adjudication_started", midpoint_enclosures=snapshots)
            value = original_adjudicate(arcs, prop, **kwargs)
            event(
                "adjudication_ended",
                elapsed_s=time.perf_counter() - start,
                cpu_elapsed_s=time.process_time() - cpu,
                result={
                    k: value.get(k)
                    for k in (
                        "status",
                        "components",
                        "range_evaluations",
                        "ambiguous_intervals",
                        "unresolved_reasons",
                        "complete_range_coverage",
                        "first_exit_bracket_s",
                    )
                },
            )
            return value

        certify.propagate_schedule, certify.adjudicate = traced_flow, traced_adjudicate
        original_action = qual.certify_action

        def traced_action(single, action, **kwargs):
            hypothesis = info.hypotheses.index(single.hypotheses[0])
            event("action_started", hypothesis=hypothesis, action=list(map(str, action)))
            start, cpu = time.perf_counter(), time.process_time()
            value = original_action(single, action, **kwargs)
            event(
                "action_ended",
                hypothesis=hypothesis,
                action=list(map(str, action)),
                elapsed_s=time.perf_counter() - start,
                cpu_elapsed_s=time.process_time() - cpu,
                status=value["status"],
            )
            return value

        qual.certify_action = traced_action
    profiler = cProfile.Profile() if mode == "profile" else None
    started, cpu = time.perf_counter(), time.process_time()
    event("qualification_started")
    if profiler:
        profiler.enable()
    try:
        result = qual.qualification(info)
    except Exception as exc:
        event("qualification_failed", exception=type(exc).__name__, message=str(exc))
        raise
    finally:
        if profiler:
            profiler.disable()
            profiler.dump_stats(str(output / "profile.pstats"))
            atomic_new(output / "profile_summary.json", profile_rows(profiler))
    wall, cpu_used = time.perf_counter() - started, time.process_time() - cpu
    event("qualification_ended", elapsed_s=wall, cpu_elapsed_s=cpu_used, result=result)
    atomic_new(
        output / "result.json",
        {
            **input_record,
            "qualification": result,
            "qualification_wall_s": wall,
            "qualification_cpu_s": cpu_used,
            "process_wall_s": time.perf_counter() - begin,
            "process_cpu_s": time.process_time() - cpu_begin,
            "geometry_counts": [
                {"containment": k[0], "hold": k[1], "calls": v} for k, v in geometry_counts.items()
            ],
            "original_evaluation_valid": False,
            "candidate_outcome_computed": False,
            "profile_overhead_present": mode == "profile",
        },
    )
    events.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--mode", choices=("plain", "trace", "profile"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.index, args.mode, args.output)


if __name__ == "__main__":
    main()
