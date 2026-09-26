from dataclasses import replace

from iaa.types import ObservationPacket, encode
from sa03.development import Case, prepare, run
from sa03.policy import decide, dispatch


def test_unavailable_packet_cannot_change_even_online_status():
    context = prepare(Case("boundary"))
    policy = decide(context, "fixed_range")
    future = ObservationPacket(
        "sa03-" + context.identity()[:16] + "-range", 1, "range", 40.6, 250, 850
    )
    absent = dispatch(context, policy, (), 700)
    for value in (39.4, 40.6):
        actual = dispatch(context, policy, (replace(future, value=value),), 700)
        assert encode(actual) == encode(absent)


def test_simulation_only_delivers_available_receipts_to_dispatch(monkeypatch):
    import sa03.development as development

    original = development.dispatch

    def guarded(context, policy, packets, now_ms):
        assert all(p.available_ms <= now_ms for p in packets)
        return original(context, policy, packets, now_ms)

    monkeypatch.setattr(development, "dispatch", guarded)
    result, events, _ = run(Case("underestimated", actual_range_delay_ms=600), "fixed_range")
    assert result["realized_dispatch"]["credited"]
