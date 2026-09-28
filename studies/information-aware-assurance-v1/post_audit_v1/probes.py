"""Bounded correction probes and ten inherited examples, with no timing claims."""

import argparse
import json
from copy import deepcopy
from fractions import Fraction as Q
from importlib import import_module
from pathlib import Path
from unittest.mock import patch


def evaluate():
    from kri_assurance_eval import api
    from kri_assurance_eval.examples import examples
    from kri_assurance_eval.integrity import verify_installation

    numeric = import_module("kri_assurance_eval._numeric")
    wire = import_module("kri_assurance_eval._vendor.sa04.wire")
    template = examples()[0]["request"]
    packet = api.observation_packet("probe", 0, "range", 45.0, 0, 40)
    results = []
    for route in ("assess", "estimate_snapshot", "observation_packet", "packet_decoder"):
        request = deepcopy(template)
        bad = deepcopy(packet)
        bad["value"] = "1e10000"
        request["current_input"]["packets"] = [bad]
        calls = []

        def forbidden(*args, _calls=calls, **kwargs):
            _calls.append(len(args))
            raise AssertionError("Invalid observation reached Fraction")

        with patch.object(numeric, "Fraction", forbidden):
            try:
                if route == "assess":
                    status = api.assess(request)["status"]
                elif route == "estimate_snapshot":
                    status = api.estimate_snapshot(request["current_input"])["status"]
                elif route == "packet_decoder":
                    status = wire.packets([bad])
                else:
                    status = api.observation_packet("bad", 0, "range", "1e10000", 0, 40)
            except ValueError:
                status = "ValueError"
        expected = "unsupported_input" if route == "assess" else "ValueError"
        if status != expected or calls:
            raise ValueError("Early-rejection regression")
        results.append(dict(route=route, status=status, fractional_constructions=len(calls)))

    t = import_module("kri_assurance_eval._vendor.iaa.types")
    m = import_module("kri_assurance_eval._vendor.sa02.model")
    intervals = import_module("kri_assurance_eval._vendor.sa02.intervals")
    estimator = import_module("kri_assurance_eval._vendor.sa02.estimator")
    sensor = m.SensorContract(
        hypotheses=(m.FaultHypothesis("zero", (intervals.interval(0),) * 4),), initial_splits=0
    )
    prior = t.StateBox.around((0, -45, 0, 0), (Q(1, 20), Q(1, 20), Q(1, 1000), Q(1, 1000)))
    present = t.ObservationPacket("same", 0, "range", 45.0, 0, 40, 2, "m")
    future = t.ObservationPacket("same", 0, "range", 46.0, 250, 1000, 2, "m")
    future_bad = t.ObservationPacket("same", 0, "range", 46.0, 250, 1000, 3, "m")
    available_bad = t.ObservationPacket("other", 1, "range", 45.0, 0, 40, 3, "m")
    conflicting = t.ObservationPacket("same", 0, "range", 46.0, 0, 40, 2, "m")
    history = (m.HistorySegment(0, 100, (0, 0)),)
    batches = (
        (present,),
        (present, future),
        (present, future_bad),
        (present, available_bad),
        (present, conflicting),
    )
    outputs = [estimator.Observer(prior, sensor).update(batch, history, 100) for batch in batches]
    statuses = [out.status for out in outputs]
    expected = [
        "updated",
        "updated",
        "updated",
        "unsupported_packets_ignored",
        "inconsistent_observations",
    ]
    if statuses != expected or not outputs[0].cells == outputs[1].cells == outputs[2].cells:
        raise ValueError("Causal-observer regression")
    public_future = deepcopy(template)
    public_future["current_input"]["packets"] = [
        api.observation_packet("future", 1, "range", 45.0, 250, 1000)
    ]
    if api.assess(public_future)["status"] != "unsupported_input":
        raise ValueError("Public delivered-only boundary regressed")
    example_results = []
    for case in examples():
        receipt = api.record(case["request"])
        if receipt["result"]["status"] != case["expected_status"] or not api.replay(receipt):
            raise ValueError("Inherited example semantic failure")
        example_results.append(
            dict(name=case["name"], expected_status=case["expected_status"], receipt=receipt)
        )
    provenance = verify_installation()
    return dict(
        schema="kri-post-audit-probes/1",
        component_version=provenance["component_version"],
        source_commit=provenance["source_commit"],
        numeric=results,
        observer=dict(statuses=statuses, future_cells_equal=True, public_future_rejected=True),
        examples=example_results,
        physical_validation=False,
        external_replication=False,
        timing_claim=False,
        new_scientific_campaign=False,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate()
    with args.output.open("x") as file:
        json.dump(result, file, indent=2, sort_keys=True)
        file.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "examples"}, sort_keys=True))
