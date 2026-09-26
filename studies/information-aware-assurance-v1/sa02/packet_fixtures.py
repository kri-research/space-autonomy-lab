"""Small explicit packet replays; all truth values are evaluation-only."""

from dataclasses import replace
from math import pi

from iaa.types import ObservationPacket, StateBox, primitive

from .estimator import Observer
from .intervals import interval
from .model import FaultHypothesis, HistorySegment, SensorContract


def evaluate():
    clean = SensorContract(
        hypotheses=(FaultHypothesis("no_bias", (interval(0),) * 4),), initial_splits=0
    )
    range_packet = ObservationPacket("range", 0, "range", 45.0, 0, 40)
    bearing = ObservationPacket("bearing", 0, "bearing", -pi / 2, 0, 70, unit="rad")
    box = StateBox.around((0, -45, 0, 0), (1, 1, 0, 0))
    history = (HistorySegment(0, 100, (0, 0)),)
    rows = []
    for name, packets, truth in (
        ("nominal", (range_packet, bearing), (0, -45, 0, 0)),
        (
            "contradictory_sensor",
            (range_packet, replace(range_packet, packet_id="conflict", value=100.0)),
            (0, -45, 0, 0),
        ),
        ("unmodelled_bias_not_detected", (replace(range_packet, value=45.5),), (0, -45, 0, 0)),
        (
            "future_data_ignored",
            (replace(range_packet, acquired_ms=500, available_ms=540),),
            (0, -45, 0, 0),
        ),
        (
            "unsupported_clock",
            (replace(range_packet, timestamp_uncertainty_ms=100),),
            (0, -45, 0, 0),
        ),
        ("missing_data", (), (0, -45, 0, 0)),
    ):
        out = Observer(box, clean).update(packets, history, 100)
        rows.append(
            {
                "name": name,
                "packets": primitive(packets),
                "initial": primitive(box),
                "history": primitive(history),
                "at_ms": 100,
                "estimate": primitive(out),
                "evaluation_truth": truth,
                "true_state_retained": out.contains_state(truth),
                "sensor_assumptions_deliberately_violated": name == "unmodelled_bias_not_detected",
            }
        )
    return {
        "schema": "iaa-sa02-packet-fixtures/1",
        "cases": rows,
        "contract": primitive(clean),
        "interpretation": (
            "The unmodelled-bias case intentionally excludes truth without detecting "
            "the violation; "
            "no universal bound-violation detection is claimed."
        ),
    }
