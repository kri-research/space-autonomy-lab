import pytest

from sa04.fixtures import at_time, initial_input
from sa04.transport import Client


def payload():
    raw, _ = initial_input("adequate")
    return dict(input=at_time(raw, 650, ()), action=["0", "0"])


def test_real_pipe_roundtrip_and_memory_timing_accounting():
    with Client("check") as client:
        for _ in range(2):
            response, timing = client.call(payload())
            assert response and timing["status"] == "completed"
            assert response["result"]["status"] == "checked_window_prefix"
            assert response["worker_cpu_ns"] > 0 and response["peak_rss_bytes"] > 0
        assert client.startup_ns > 0
    assert client.process.poll() is not None


@pytest.mark.parametrize("fault", ["stall", "exit", "truncate", "corrupt"])
def test_real_faulted_child_never_returns_authority(fault):
    with Client("check", fault) as client:
        response, timing = client.call(
            payload(), 100_000_000 if fault == "stall" else 2_000_000_000
        )
        assert response is None and timing["status"] != "completed"
        assert client.closed and client.process.poll() is not None


def test_closed_worker_not_reused():
    client = Client("check")
    client.close()
    response, timing = client.call(payload())
    assert response is None and timing["status"] != "completed"


def test_enforced_host_gate_never_claims_physical_or_out_of_window_output():
    import io

    from sa04.host import enforced

    r = enforced("adequate", "decision_aware", io.StringIO())
    assert not r["physical_signal_emitted"]
    if r["candidate_signal_emitted"]:
        assert (
            700_000_000
            <= r["dispatch_before_offset_ns"]
            <= r["dispatch_after_offset_ns"]
            <= 710_000_000
        )
        assert r["planner_on_time"] and r["admission"]["scheduled"]


def test_planner_pipe_roundtrip():
    raw, _ = initial_input("adequate")
    with Client("plan") as c:
        response, timing = c.call(dict(input=raw, method="decision_aware"))
        assert response and timing["status"] == "completed"
        assert response["result"]["channel"] is None


@pytest.mark.parametrize("sequence", [0, 1])
def test_repeated_or_reordered_service_sequence_rejected(sequence):
    from sa04.wire import dumps, loads, request

    with Client("check") as c:
        first = request("check", 2, payload(), c.session)
        assert (
            loads(c.exchange(dumps(first) + b"\n", 2_000_000_000))["schema"]
            == "iaa-execution-response/4"
        )
        stale = request("check", sequence, payload(), c.session)
        assert (
            loads(c.exchange(dumps(stale) + b"\n", 2_000_000_000))["schema"] == "iaa-worker-error/4"
        )


def test_stale_session_cannot_reuse_process():
    from sa04.wire import dumps, loads, request

    with Client("check") as c:
        stale = request("check", 0, payload(), "different-session")
        response = loads(c.exchange(dumps(stale) + b"\n", 2_000_000_000))
        assert response["schema"] == "iaa-worker-error/4"
