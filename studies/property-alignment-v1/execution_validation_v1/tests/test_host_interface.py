import json
import tempfile
import pytest
from execution_validation_v1.protocol import (
    strict_load,
    validate_request,
    check_action,
    SimulatedCommandSink,
    delay_compatibility,
    identity,
)
from execution_validation_v1.harness import ROOT, requests, Transport, clock_record
from execution_validation_v1.physical import readiness, metrology_adjudicate
from execution_validation_v1.analysis import stats


def request():
    plan = json.loads((ROOT / "host_plan.json").read_text())
    return requests(plan, 0)[0]["request"]


@pytest.mark.parametrize(
    "raw", ['{"a":1,"a":2}', '{"v":NaN}', '{"v":Infinity}', "not json", "x" * 262145]
)
def test_bad_wire_payload(raw):
    with pytest.raises((ValueError, TypeError)):
        strict_load(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", "wrong"),
        ("mode", "physical"),
        ("sequence", True),
        ("sequence", -1),
        ("budget_ns", True),
        ("budget_ns", 2),
        ("units", "imperial"),
        ("domain", "unknown"),
        ("method", "unknown"),
        ("id", ""),
    ],
)
def test_invalid_request(field, value):
    req = request()
    req[field] = value
    with pytest.raises((ValueError, TypeError, PermissionError)):
        validate_request(req)


def test_protected_input_not_a_host_trial():
    req = request()
    req["payload"]["namespace"] = "protected"
    with pytest.raises(PermissionError):
        validate_request(req)


@pytest.mark.parametrize("u", [("0.4", "0.001"), (True, 0), ("NaN", 0), [0], [0, 0, 0]])
def test_exact_actuator_norm(u):
    assert not check_action(u, "0.4")


def test_wire_roundtrip_actual_calibration_service():
    with tempfile.TemporaryFile() as err:
        t = Transport(err)
        try:
            req = request()
            reply, times = t.call(req, 15)
            assert reply["request_sha256"] == identity(req) and reply["physical_actuation"] is False
            assert times["roundtrip_ns"] > 0 and reply["result"]["status"] == "prefix"
        finally:
            t.close()


def test_planned_membership_and_order():
    plan = json.loads((ROOT / "host_plan.json").read_text())
    allrows = [r for s in range(3) for r in requests(plan, s)]
    assert len(allrows) == 216 and sum(r["phase"] == "measured" for r in allrows) == 192
    assert len({r["request"]["id"] for r in allrows}) == 216
    assert {r["request"]["payload"]["namespace"] for r in allrows} == {"calibration"}
    for s in range(3):
        assert requests(plan, s) == requests(plan, s)


def test_clock_has_raw_samples_not_accuracy_bound():
    result = clock_record(20)
    assert len(result["back_to_back_ns"]) == 20 and result["resolution_is_accuracy"] is False
    assert result["absolute_accuracy_calibrated"] is False


@pytest.mark.parametrize(
    "host,delay,status",
    [
        (1, 0, "incompatible_host_lower_bound"),
        (100, 100, "unknown_physical_delays"),
        (50, 100, "unknown_physical_delays"),
    ],
)
def test_unmeasured_physical_delays_stay_unknown(host, delay, status):
    r = delay_compatibility(host, delay)
    assert r["status"] == status and not r["physical_compatibility_established"]


def test_bounded_clock_and_device_delay_included():
    r = delay_compatibility(
        20,
        100,
        sensor_upper_ns=30,
        actuator_upper_ns=40,
        alignment_upper_ns=10,
        clock_interval_upper_ns=1,
    )
    assert r["status"] == "late" and r["total_delay_upper_ns"] == 101
    r = delay_compatibility(
        20,
        100,
        sensor_upper_ns=30,
        actuator_upper_ns=30,
        alignment_upper_ns=10,
        clock_interval_upper_ns=1,
    )
    assert r["status"] == "compatible_with_supplied_bounds" and r["wait_until_model_application"]


def submit(sink, **changes):
    args = dict(
        request_id="id1",
        decision={"status": "prefix", "action": ["0.1", "0"]},
        earliest_arrival_ns=20,
        latest_arrival_ns=30,
        apply_at_ns=40,
        authority="0.4",
        same_clock=True,
        estop=False,
        proof_checked=True,
    )
    args.update(changes)
    return sink.submit(**args)


def test_early_command_waits_until_model_application():
    s = SimulatedCommandSink()
    r = submit(s)
    assert r["scheduled"] and s.actions[0]["apply_at_ns"] == 40 and not r["physical_actuation"]


@pytest.mark.parametrize(
    "args",
    [
        {"latest_arrival_ns": 41},
        {"same_clock": False},
        {"proof_checked": False},
        {"decision": {"status": "unresolved", "action": None}},
        {"decision": {"status": "obstruction", "action": None}},
        {"decision": {"status": "prefix", "action": [".5", 0]}},
        {"estop": True},
    ],
)
def test_sink_rejects_unsafe_transport_semantics(args):
    s = SimulatedCommandSink()
    assert not submit(s, **args)["scheduled"] and not s.actions and s.aborts


def test_stop_is_latched_and_duplicates_rejected():
    s = SimulatedCommandSink()
    submit(s, estop=True)
    assert not submit(s, request_id="later")["scheduled"]
    s = SimulatedCommandSink()
    assert submit(s)["scheduled"]
    assert not submit(s)["scheduled"]


def test_blank_lab_configuration_never_authorizes_motion():
    config = json.loads((ROOT / "physical_configuration.json").read_text())
    result = readiness(config)
    assert not result["structural_readiness"] and not result["may_energize_equipment"]
    assert "operator_id" in result["missing"] and "independent_metrology_model" in result["missing"]


def judge(points, **kw):
    settings = dict(
        position_error_m=".001",
        alignment_error_s=".001",
        speed_bound_mps=".2",
        maximum_gap_s=".1",
        expected_start_s=0,
        expected_end_s=".1",
    )
    settings.update(kw)
    return metrology_adjudicate(points, **settings)


def test_metrology_nominal_complete_interval():
    pts = [{"time_s": 0, "position_m": [0, 0]}, {"time_s": ".1", "position_m": [0, 0]}]
    assert judge(pts)["status"] == "contained"


def test_metrology_boundary_gap_and_intervention_preserved():
    pts = [{"time_s": 0, "position_m": [".999", 0]}, {"time_s": ".1", "position_m": [".999", 0]}]
    result = judge(pts, maximum_gap_s=".05", guard_events=[{"reason": "operator_abort"}])
    assert (
        result["status"] == "unresolved"
        and result["guard_events"]
        and "metrology_gap" in result["reasons"]
    )


def test_metrology_definite_violation():
    pts = [{"time_s": 0, "position_m": ["1.1", 0]}, {"time_s": ".1", "position_m": ["1.1", 0]}]
    result = judge(pts)
    assert result["status"] == "violation" and result["witnesses"]


@pytest.mark.parametrize(
    "settings",
    [
        {"position_error_m": -1},
        {"clock_alignment_bound_s": -1},
        {"speed_bound_mps": True},
        {"expected_end_s": 0},
    ],
)
def test_bad_metrology_settings(settings):
    pts = [{"time_s": 0, "position_m": [0, 0]}, {"time_s": ".1", "position_m": [0, 0]}]
    with pytest.raises((ValueError, TypeError)):
        judge(pts, **settings)


def test_all_stats_retained_including_outlier():
    s = stats([1, 2, 100])
    assert (
        s["n"] == 3 and s["median_ns"] == 2 and s["maximum_ns"] == 100 and not s["maximum_is_wcet"]
    )


@pytest.mark.parametrize("samples", [[True], [float("nan")], [-1], [1.5]])
def test_bad_clock_samples(samples):
    with pytest.raises(ValueError):
        stats(samples)


def test_transport_timeout_and_truncated_stream():
    import os
    import selectors
    from types import SimpleNamespace

    reader, writer = os.pipe()
    t = Transport.__new__(Transport)
    t.buffer = b""
    t.selector = selectors.DefaultSelector()
    output = os.fdopen(reader, "rb", buffering=0)
    t.proc = SimpleNamespace(stdout=output)
    t.selector.register(output, selectors.EVENT_READ)
    try:
        with pytest.raises(TimeoutError):
            t.line(0.001)
        os.write(writer, b'{"partial":')
        os.close(writer)
        writer = None
        with pytest.raises(RuntimeError):
            t.line(0.1)
    finally:
        if writer is not None:
            os.close(writer)
        output.close()
        t.selector.close()


def test_source_bound_virtual_application_with_real_method():
    from execution_validation_v1.worker import service
    from execution_validation_v1.adapters import verify_fixed

    req = request()
    req["payload"]["delay"] = "0.25"  # Synthetic interface fixture, not a protected case.
    reply = service(req)
    assert reply["result"]["status"] == "prefix"
    checked = verify_fixed(req, reply["result"]["prediction"])
    assert checked is True
    sink = SimulatedCommandSink()
    result = sink.submit(
        req["id"],
        reply["result"],
        earliest_arrival_ns=100000000,
        latest_arrival_ns=150000000,
        apply_at_ns=250000000,
        authority="0.4",
        proof_checked=checked,
    )
    assert result["scheduled"] and sink.actions[0]["apply_at_ns"] == 250000000
    assert result["physical_actuation"] is False


def test_worker_rejects_duplicate_request_id_sequence():
    with tempfile.TemporaryFile() as err:
        t = Transport(err)
        try:
            req = request()
            t.call(req, 15)
            with pytest.raises(ValueError):
                t.call(req, 15)
        finally:
            t.close()
