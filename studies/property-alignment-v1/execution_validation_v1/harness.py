"""Bounded write-once host study using real clocks and a JSON subprocess service."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import importlib.metadata
import json
import os
import platform
import selectors
import subprocess
import sys
import time
from .protocol import encode, strict_load, identity, validate_request, delay_compatibility

ROOT = Path(__file__).resolve().parent
STUDY = ROOT.parent
REPO = STUDY.parents[1]


def write_new(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with path.open("x") as f:
        f.write(raw)


def source_inventory():
    from evaluation_v2.identity import inventory as previous
    from transfer_cart_v1.freeze import inventory as cart

    values = previous()
    values.update({"transfer_cart_v1/" + k: v for k, v in cart().items()})
    import hashlib

    for path in ROOT.rglob("*.py"):
        values[path.relative_to(STUDY).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(sorted(values.items()))


def inputs():
    from evaluation.generator import STRATA as orbital_strata, case_payload
    from transfer_cart_v1.schema import STRATA as cart_strata, make_case

    return {
        "spacecraft": [case_payload("calibration", s, i) for s in orbital_strata for i in range(2)],
        "cart": [make_case("calibration", s, i) for s in cart_strata for i in range(2)],
    }


def requests(plan, session):
    data = inputs()
    adapters = plan["adapters"]
    rows = []

    def add(adapter, case, phase, repetition):
        sequence = len(rows)
        req = {
            "schema": "sal-execution-request/1",
            "id": f"session{session:02d}-{sequence:04d}",
            "sequence": sequence,
            **adapter,
            "payload": case,
            "units": "SI",
            "mode": "host_only",
            "budget_ns": plan["policy_budget_ns"],
        }
        validate_request(req)
        rows.append({"phase": phase, "repetition": repetition, "request": req})

    for adapter in adapters:
        for j in range(plan["warmup_per_adapter_per_session"]):
            add(adapter, data[adapter["domain"]][j], "warmup", j)
    cart = [a for a in adapters if a["domain"] == "cart"]
    for rep in range(plan["repetitions_per_session"]):
        for i, case in enumerate(data["cart"]):
            shift = (session + rep + i) % len(cart)
            for a in cart[shift:] + cart[:shift]:
                add(a, case, "measured", rep)
        for case in data["spacecraft"]:
            add(adapters[-1], case, "measured", rep)
    return rows


def host_snapshot():
    def query(args):
        try:
            return subprocess.check_output(args, text=True, timeout=5).strip()
        except (OSError, subprocess.SubprocessError):
            return None

    power = query(["pmset", "-g", "batt"]) if sys.platform == "darwin" else None
    return {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "processor": query(["sysctl", "-n", "machdep.cpu.brand_string"])
        if sys.platform == "darwin"
        else platform.processor(),
        "model": query(["sysctl", "-n", "hw.model"]) if sys.platform == "darwin" else None,
        "logical_cores": os.cpu_count(),
        "load_average": list(os.getloadavg()) if hasattr(os, "getloadavg") else None,
        "power_source": "AC"
        if power and "AC Power" in power
        else "battery"
        if power and "Battery Power" in power
        else "unavailable",
        "thermal_measurement": None,
        "frequency_controlled": False,
        "other_host_load_controlled": False,
        "openblas_threads": os.environ.get("OPENBLAS_NUM_THREADS"),
        "packages": {
            n: importlib.metadata.version(n) for n in ("numpy", "scipy", "cvxpy", "clarabel")
        },
    }


def clock_record(count):
    info = time.get_clock_info("perf_counter")
    pairs = []
    for _ in range(count):
        a = time.perf_counter_ns()
        b = time.perf_counter_ns()
        pairs.append(b - a)
    return {
        "source": "perf_counter_ns",
        "implementation": info.implementation,
        "monotonic": info.monotonic,
        "adjustable": info.adjustable,
        "advertised_resolution_s": info.resolution,
        "back_to_back_ns": pairs,
        "absolute_accuracy_calibrated": False,
        "sensor_clock_alignment_measured": False,
        "overhead_subtracted": False,
        "resolution_is_accuracy": False,
    }


class Transport:
    def __init__(self, stderr, timeout=30):
        self.proc = None
        self.selector = selectors.DefaultSelector()
        self.buffer = b""
        started = time.perf_counter_ns()
        self.proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "execution_validation_v1.worker"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr,
            cwd=STUDY,
            env={**os.environ, "OPENBLAS_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"},
            bufsize=0,
        )
        self.selector.register(self.proc.stdout, selectors.EVENT_READ)
        try:
            ready = self.line(timeout)
            if ready.get("ready") is not True or ready.get("physical_backend") is not False:
                raise ValueError("Service handshake")
        except Exception:
            self.close()
            raise
        self.startup_ns = time.perf_counter_ns() - started

    def line(self, timeout):
        end = time.monotonic() + timeout
        while b"\n" not in self.buffer:
            remaining = end - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise TimeoutError("Service response deadline")
            raw = os.read(self.proc.stdout.fileno(), 65536)
            if not raw:
                raise RuntimeError("Service closed without response")
            self.buffer += raw
            if len(self.buffer) > 4194304:
                raise ValueError("Service response too large")
        line, self.buffer = self.buffer.split(b"\n", 1)
        return json.loads(line)

    def call(self, req, timeout):
        start = time.perf_counter_ns()
        raw = encode(req) + b"\n"
        encoded = time.perf_counter_ns()
        self.proc.stdin.write(raw)
        self.proc.stdin.flush()
        written = time.perf_counter_ns()
        reply = self.line(timeout)
        received = time.perf_counter_ns()
        if (
            reply.get("request_sha256") != identity(req)
            or reply.get("id") != req["id"]
            or reply.get("sequence") != req["sequence"]
        ):
            raise ValueError("Response binding mismatch")
        if reply.get("physical_actuation") is not False:
            raise ValueError("Unexpected physical action")
        done = time.perf_counter_ns()
        return reply, {
            "request_start_ns": start,
            "encoded_ns": encoded,
            "written_ns": written,
            "received_ns": received,
            "validated_ns": done,
            "roundtrip_ns": done - start,
        }

    def close(self):
        if self.proc is not None:
            if self.proc.stdin:
                self.proc.stdin.close()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=3)
        self.selector.close()


def freeze(output):
    import hashlib

    plan = strict_load((ROOT / "host_plan.json").read_bytes())
    source = source_inventory()
    commit = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    for name, digest in source.items():
        raw = subprocess.check_output(
            ["git", "-C", str(REPO), "show", commit + ":studies/property-alignment-v1/" + name]
        )
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Source not committed before measurement " + name)
    doc = {
        "schema": "sal-host-freeze/1",
        "source_commit": commit,
        "source_sha256": source,
        "plan": plan,
        "input_sha256": identity(inputs()),
        "schedule_sha256": [identity(requests(plan, s)) for s in range(plan["sessions"])],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "physical_trial_freeze": False,
    }
    doc["id"] = identity(doc)
    write_new(output, doc)
    return doc


def verify_freeze(path):
    doc = json.loads(Path(path).read_text())
    if doc["id"] != identity({k: v for k, v in doc.items() if k != "id"}):
        raise ValueError("Freeze identity")
    if doc["source_sha256"] != source_inventory():
        raise ValueError("Measurement source drift")
    if doc["plan"] != strict_load((ROOT / "host_plan.json").read_bytes()) or doc[
        "input_sha256"
    ] != identity(inputs()):
        raise ValueError("Plan or input drift")
    if doc["schedule_sha256"] != [
        identity(requests(doc["plan"], s)) for s in range(doc["plan"]["sessions"])
    ]:
        raise ValueError("Schedule drift")
    return doc


def run(frozen, output):
    doc = verify_freeze(frozen)
    plan = doc["plan"]
    output = Path(output).resolve()
    if output.is_relative_to(REPO) or output.exists():
        raise ValueError("Use a new private output directory")
    if os.environ.get("OPENBLAS_NUM_THREADS") != "1":
        raise ValueError("Frozen BLAS count")
    output.mkdir(parents=True)
    write_new(
        output / "header.json",
        {
            "id": doc["id"],
            "plan": plan,
            "environment": host_snapshot(),
            "started_at_utc": datetime.now(timezone.utc).isoformat(),
        },
    )
    write_new(output / "inputs.json", inputs())
    full_start = time.monotonic()
    count = 0
    for session in range(plan["sessions"]):
        dest = output / f"session{session:02d}"
        dest.mkdir()
        origin = time.perf_counter_ns()
        clocks = clock_record(plan["clock_pairs_per_session"])
        write_new(dest / "clock.json", clocks)
        before = host_snapshot()
        transport = None
        try:
            with (dest / "worker-stderr.txt").open("xb") as err:
                transport = Transport(err, plan["startup_watchdog_s"])
                write_new(
                    dest / "start.json",
                    {"session": session, "environment": before, "startup_ns": transport.startup_ns},
                )
                for spec in requests(plan, session):
                    if time.monotonic() - full_start > plan["total_watchdog_s"]:
                        raise TimeoutError("Total study resource budget")
                    req = spec["request"]
                    write_new(dest / "started" / (req["id"] + ".json"), spec)
                    reply, times = transport.call(req, plan["request_watchdog_s"])
                    timing = reply["timing"]
                    for key in (
                        "service_start_ns",
                        "policy_start_ns",
                        "policy_end_ns",
                        "service_end_ns",
                    ):
                        timing[key] -= origin
                    for key in (
                        "request_start_ns",
                        "encoded_ns",
                        "written_ns",
                        "received_ns",
                        "validated_ns",
                    ):
                        times[key] -= origin
                    row = {
                        **spec,
                        "session": session,
                        "response": reply,
                        "parent_timing": times,
                        "host_service_budget_exceeded": times["roundtrip_ns"]
                        > plan["policy_budget_ns"],
                        "delay_assessment": delay_compatibility(
                            times["roundtrip_ns"], reply["model_delay_ns"]
                        ),
                        "evidence_level": "host_computer_timing",
                        "physical_actuation": False,
                    }
                    write_new(dest / "samples" / (req["id"] + ".json"), row)
                    count += 1
        except Exception as exc:
            write_new(
                dest / "failure.json",
                {"type": type(exc).__name__, "completed_samples": count, "retried": False},
            )
            raise
        finally:
            if transport is not None:
                transport.close()
        write_new(
            dest / "end.json",
            {"session": session, "environment": host_snapshot(), "complete": True},
        )
    from .analysis import summarize_directory

    result = summarize_directory(output, doc)
    write_new(output / "summary.json", result)
    import hashlib

    inventory = {
        p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    write_new(
        output / "completion.json",
        {
            "id": doc["id"],
            "files": inventory,
            "samples": count,
            "elapsed_s": time.monotonic() - full_start,
            "physical_trials": 0,
        },
    )
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["freeze", "run", "verify"])
    p.add_argument("--freeze", type=Path)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    if a.mode == "freeze":
        result = freeze(a.output)
    elif a.mode == "verify":
        result = {"id": verify_freeze(a.freeze)["id"], "passed": True}
    else:
        result = run(a.freeze, a.output)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
