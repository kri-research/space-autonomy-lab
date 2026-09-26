"""Prospectively bounded host evidence. Synthetic sensors, no physical actuator."""

import json
import os
import platform
import statistics
import sys
from time import get_clock_info, monotonic_ns, sleep

from iaa.types import identity, primitive, rational

from .compute import initial_arm, proposal_action
from .fixtures import METHODS, at_time, delivered_packet, initial_input
from .gate import Gate
from .legacy import protocol
from .service import peak_rss_bytes
from .transport import Client

NS_MS = 1_000_000


def logging_cost(file, data):
    start = monotonic_ns()
    file.write(json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n")
    file.flush()
    return monotonic_ns() - start


def diagnostic(planner_client, checker_client, kind, method, log):
    start = monotonic_ns()
    raw, truth = initial_input(kind)
    preparation_ns = monotonic_ns() - start
    prearm_start = monotonic_ns()
    arm = initial_arm(raw)
    prearm_ns = monotonic_ns() - prearm_start
    response, transport = planner_client.call(dict(input=raw, method=method))
    planner_logging = logging_cost(log, dict(stage="plan", transport=transport))
    first_path = preparation_ns + transport["roundtrip_ns"] + planner_logging
    select_start = monotonic_ns()
    proposal = response["result"] if response else None
    receipts = delivered_packet(raw, truth, proposal["channel"] if proposal else None)
    action = proposal_action(proposal, receipts) if proposal else (0, 0)
    checker_payload = dict(input=at_time(raw, 650, receipts), action=primitive(action))
    selection_ns = monotonic_ns() - select_start
    checked, checking_transport = checker_client.call(checker_payload)
    checker_logging = logging_cost(log, dict(stage="check", transport=checking_transport))
    # No diagnostic result receives actual timed-dispatch authority.
    gate_start = monotonic_ns()
    gate = Gate(raw, arm)
    admission = (
        gate.admit(checked["result"], checker_payload, 675) if checked else dict(scheduled=False)
    )
    gate_ns = monotonic_ns() - gate_start
    total = (
        first_path + selection_ns + checking_transport["roundtrip_ns"] + checker_logging + gate_ns
    )
    elapsed_compute = monotonic_ns() - start - prearm_ns
    return dict(
        kind=kind,
        method=method,
        input_preparation_ns=preparation_ns,
        offline_initialization_ns=prearm_ns,
        planner_transport=transport,
        planner_components=response["components_ns"] if response else None,
        planner_cpu_ns=response["worker_cpu_ns"] if response else None,
        planner_peak_rss_bytes=response["peak_rss_bytes"] if response else None,
        planner_logging_ns=planner_logging,
        selection_and_simulated_sensor_ns=selection_ns,
        checker_transport=checking_transport,
        checker_components=checked["components_ns"] if checked else None,
        checker_cpu_ns=checked["worker_cpu_ns"] if checked else None,
        checker_peak_rss_bytes=checked["peak_rss_bytes"] if checked else None,
        checker_logging_ns=checker_logging,
        admission_ns=gate_ns,
        compute_path_ns=elapsed_compute,
        summed_components_ns=total,
        unattributed_python_overhead_ns=elapsed_compute - total,
        planner_phase_over_50ms=first_path > 50 * NS_MS,
        checker_phase_over_50ms=selection_ns
        + checking_transport["roundtrip_ns"]
        + checker_logging
        + gate_ns
        > 50 * NS_MS,
        shadow_admission=admission,
        diagnostic_only=True,
        actual_dispatch=False,
        physical_delays=protocol.delay_compatibility(elapsed_compute, 600 * NS_MS),
        parent_peak_rss_bytes=peak_rss_bytes(),
        load_average=list(os.getloadavg()),
    )


def wait_until(origin, logical_ms):
    target = origin + logical_ms * NS_MS
    while True:
        left = target - monotonic_ns()
        if left <= 0:
            return monotonic_ns()
        sleep(left / 1e9)


def measured_admission(gate, checked, payload, origin):
    before = monotonic_ns() - origin
    admitted = gate.admit(checked, payload, (before + NS_MS - 1) // NS_MS)
    complete = monotonic_ns() - origin
    if admitted["scheduled"] and complete > 700 * NS_MS:
        # Finite preloaded coast remains available; this candidate gets no authority.
        gate.pending = None
        admitted = dict(scheduled=False, reasons=["admission_finished_after_deadline"])
    return admitted, before, complete


def enforced(kind, method, log):
    raw, truth = initial_input(kind)
    before = monotonic_ns()
    arm = initial_arm(raw)
    preflight_ns = monotonic_ns() - before
    gate = Gate(raw, arm)
    with Client("plan") as planner_client, Client("check") as checker_client:
        startup = dict(plan_ns=planner_client.startup_ns, check_ns=checker_client.startup_ns)
        # The future simulated initial condition is installed only at this epoch.
        # This is not permission to freeze a live spacecraft during startup.
        origin = monotonic_ns() - 100 * NS_MS
        planned, plan_transport = planner_client.call(dict(input=raw, method=method), 50 * NS_MS)
        plan_logging_ns = logging_cost(log, dict(stage="enforced_plan", transport=plan_transport))
        plan_ready = monotonic_ns() - origin
        plan_ok = planned is not None and plan_ready <= 150 * NS_MS and arm["valid"]
        proposal = planned["result"] if plan_ok else None
        channel = proposal["channel"] if proposal else None
        # The sensor source is simulated; it is not exposed before availability.
        generated = delivered_packet(raw, truth, channel)
        check_start = wait_until(origin, 650)
        receipts = tuple(p for p in generated if origin + p.available_ms * NS_MS <= check_start)
        action = proposal_action(proposal, receipts) if proposal else (0, 0)
        payload = dict(input=at_time(raw, 650, receipts), action=primitive(action))
        remaining = origin + 700 * NS_MS - monotonic_ns()
        checked, check_transport = checker_client.call(payload, max(1, remaining))
        check_logging_ns = logging_cost(
            log, dict(stage="enforced_check", transport=check_transport)
        )
        ready = monotonic_ns() - origin
        if checked and plan_ok:
            admission, admission_before, admission_complete = measured_admission(
                gate, checked["result"], payload, origin
            )
        else:
            admission = dict(scheduled=False, reasons=["no_timely_plan_or_check"])
            admission_before = admission_complete = monotonic_ns() - origin
        before_dispatch = wait_until(origin, 700) - origin
        tick = gate.tick(
            (before_dispatch + NS_MS - 1) // NS_MS, live_binding_sha256=identity(payload)
        )
        append_start = monotonic_ns() - origin
        signal = primitive(tick)
        after_dispatch = monotonic_ns() - origin
        actual = bool(
            tick["newly_applied"]
            and 700 * NS_MS <= before_dispatch <= append_start <= after_dispatch <= 710 * NS_MS
        )
        if tick["newly_applied"] and not actual:
            gate.invalidate()
        return dict(
            kind=kind,
            method=method,
            offline_initialization_ns=preflight_ns,
            worker_startup=startup,
            plan_transport=plan_transport,
            check_transport=check_transport,
            plan_logging_ns=plan_logging_ns,
            check_logging_ns=check_logging_ns,
            plan_ready_offset_ns=plan_ready,
            check_start_offset_ns=check_start - origin,
            check_ready_offset_ns=ready,
            admission_before_offset_ns=admission_before,
            admission_complete_offset_ns=admission_complete,
            dispatch_before_offset_ns=before_dispatch,
            dispatch_after_offset_ns=after_dispatch,
            signal_copy_ns=after_dispatch - append_start,
            planner_on_time=plan_ok,
            admission=admission,
            candidate_signal_emitted=actual,
            nonzero_candidate_signal_emitted=actual and any(rational(v) for v in signal["action"]),
            logical_signal=signal,
            physical_signal_emitted=False,
            scheduler_lateness_ns=max(0, before_dispatch - 700 * NS_MS),
            clock="single_parent_monotonic",
            sensor_timestamps="simulated_assumptions",
            target_validation=False,
            load_average=list(os.getloadavg()),
        )


def record(output):
    protocol_path = __import__("pathlib").Path(__file__).with_name("host-protocol.json")
    design = json.loads(protocol_path.read_text())
    result = dict(
        schema="iaa-host-execution/4",
        design=design,
        environment=dict(
            python=sys.version.split()[0],
            os=platform.system(),
            architecture=platform.machine(),
            logical_cpus=os.cpu_count(),
            ambient_load=list(os.getloadavg()),
            monotonic_clock=vars(get_clock_info("monotonic")),
            energy_measured=False,
            physical_sensor_transport_measured=False,
        ),
        diagnostic_sessions=[],
        enforced_runs=[],
    )
    with (output / "host-logging.jsonl").open("x") as log:
        for session in range(design["sessions"]):
            with Client("plan") as p, Client("check") as c:
                item = dict(
                    session=session,
                    plan_startup_ns=p.startup_ns,
                    check_startup_ns=c.startup_ns,
                    warmups=[],
                    samples=[],
                )
                for method in METHODS:
                    item["warmups"].append(diagnostic(p, c, "adequate", method, log))
                for repeat in range(design["repetitions"]):
                    for kind in design["contexts"]:
                        for method in METHODS:
                            row = diagnostic(p, c, kind, method, log)
                            row["repeat"] = repeat
                            item["samples"].append(row)
                result["diagnostic_sessions"].append(item)
                print(
                    "host_diagnostic_session", session, "samples", len(item["samples"]), flush=True
                )
        for repeat in range(design["enforced_repetitions"]):
            for kind in ("ambiguity", "adequate"):
                for method in METHODS:
                    row = enforced(kind, method, log)
                    row["repeat"] = repeat
                    result["enforced_runs"].append(row)
                    print(
                        "host_enforced",
                        repeat,
                        kind,
                        method,
                        row["candidate_signal_emitted"],
                        flush=True,
                    )
    (output / "host.json").write_text(
        json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    )
    return summarize(result)


def distribution(xs):
    ordered = sorted(xs)
    return dict(
        n=len(xs),
        minimum_ns=min(xs),
        median_ns=statistics.median(xs),
        p95_nearest_rank_ns=ordered[max(0, (__import__("math").ceil(0.95 * len(xs)) - 1))],
        maximum_ns=max(xs),
    )


def summarize(result):
    rows = [r for s in result["diagnostic_sessions"] for r in s["samples"]]
    runs = result["enforced_runs"]
    return dict(
        diagnostic_requests=len(rows),
        warmup_requests=sum(len(s["warmups"]) for s in result["diagnostic_sessions"]),
        planner_roundtrip=distribution([r["planner_transport"]["roundtrip_ns"] for r in rows]),
        checker_roundtrip=distribution([r["checker_transport"]["roundtrip_ns"] for r in rows]),
        complete_compute_path=distribution([r["compute_path_ns"] for r in rows]),
        planner_phase_overruns=sum(r["planner_phase_over_50ms"] for r in rows),
        checker_phase_overruns=sum(r["checker_phase_over_50ms"] for r in rows),
        diagnostic_transport_failures=sum(
            r[k]["status"] != "completed"
            for r in rows
            for k in ("planner_transport", "checker_transport")
        ),
        enforced_runs=len(runs),
        enforced_planner_timeouts=sum(
            r["plan_transport"]["status"] == "TimeoutError" for r in runs
        ),
        enforced_checker_timeouts=sum(
            r["check_transport"]["status"] == "TimeoutError" for r in runs
        ),
        emitted_candidate_signals=sum(r["candidate_signal_emitted"] for r in runs),
        emitted_nonzero_signals=sum(r["nonzero_candidate_signal_emitted"] for r in runs),
        no_out_of_window_emission=all(
            not r["candidate_signal_emitted"]
            or 700 * NS_MS
            <= r["dispatch_before_offset_ns"]
            <= r["dispatch_after_offset_ns"]
            <= 710 * NS_MS
            for r in runs
        ),
        physical_validation=False,
        worst_case_execution_proved=False,
        energy_measured=False,
    )
