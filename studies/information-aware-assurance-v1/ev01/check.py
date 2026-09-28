"""Offline public-interface exercise. Never certifies who ran it or performs actuation."""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import sys
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vectors():
    from kri_assurance_eval import api
    from kri_assurance_eval.examples import examples

    cases = deepcopy(examples())
    base = cases[0]["request"]

    def add(name, status, request):
        cases.append(dict(name=name, expected_status=status, request=request))

    request = deepcopy(base)
    request["contract"]["component_version"] = "0.1.0"
    add("old_component_version", "unsupported_input", request)
    request = deepcopy(base)
    request["contract"]["model"]["frame"] = "inertial"
    add("incompatible_frame", "unsupported_input", request)
    packet = api.observation_packet("bounded-value", 0, "range", 45.0, 0, 40)
    packet["value"] = "1e10000"
    request = deepcopy(base)
    request["current_input"]["packets"] = [packet]
    add("A1_exponent_rejected", "unsupported_input", request)
    for uncertainty in (2, 3):
        request = deepcopy(base)
        request["current_input"]["packets"] = [
            api.observation_packet("future", 1, "range", 45.0, 250, 1000, uncertainty)
        ]
        add("future_" + str(uncertainty), "unsupported_input", request)
    request = deepcopy(base)
    request["current_input"]["packets"] = [api.observation_packet("stale", 0, "range", 45.0, 0, 40)]
    add("stale_prediction", "supported_prefix", request)
    request = deepcopy(base)
    request["apply_ms"] = 4201
    add("expired_credit", "missed_application_window", request)
    return cases


def exercise(controller=None):
    from kri_assurance_eval import api
    from kri_assurance_eval.integrity import verify_installation

    protocol = json.loads((HERE / "protocol.json").read_text())
    provenance = verify_installation()
    if (
        api.contract()["component_version"] != protocol["component_version"]
        or provenance["source_commit"] != protocol["component_source"]
    ):
        raise ValueError("Wrong installed component version or source")
    cases = vectors()
    if len(cases) != protocol["reference_vectors_expected"]:
        raise ValueError("Unexpected reference vector population")
    results = []
    for case in cases:
        row = dict(name=case["name"], expected_status=case["expected_status"])
        try:
            receipt = api.record(case["request"])
            result = receipt["result"]
            passed = result["status"] == case["expected_status"] and api.replay(receipt)
            if case["name"] == "expired_credit":
                passed = passed and not result["simulated_output"]["credited"]
            if case["name"] == "stale_prediction":
                passed = passed and result["checked"]["uncertainty"]["status"] == (
                    "prediction_only_missing_or_stale"
                )
            row.update(passed=passed, receipt=receipt)
        except Exception as error:
            row.update(passed=False, error=type(error).__name__)
        results.append(row)
    integrations = []
    if controller is not None:
        lookup = {case["name"]: case for case in cases}
        for name in protocol["controller_cases"]:
            request = deepcopy(lookup[name]["request"])
            row = dict(name=name)
            try:
                action = controller(deepcopy(request["current_input"]))
                # Restrict the exercise output to plain JSON, without executing serializers.
                json.dumps(action, allow_nan=False)
                if not isinstance(action, (list, tuple)) or len(action) != 2:
                    raise ValueError("Two command components required")
                if any(type(x) not in (str, int, float) for x in action):
                    raise ValueError("Plain command scalars required")
                request["proposed_action"] = list(action)
                receipt = api.record(request)
                row.update(
                    proposed_action=list(action),
                    receipt=receipt,
                    replayed=api.replay(receipt),
                    executed=True,
                )
            except Exception as error:
                row.update(executed=False, error=type(error).__name__)
            integrations.append(row)
    verify_installation()
    return dict(
        protocol_id=protocol["protocol_id"],
        component_source=provenance["source_commit"],
        component_version=protocol["component_version"],
        reference_vectors=results,
        reference_vectors_pass=all(r["passed"] for r in results),
        controller_cases=integrations,
        controller_attempted=controller is not None,
        independence_not_assessed=True,
        external_integration_confirmed=False,
        physical_validation=False,
        mission_efficacy_assessed=False,
    )


def execute(output, controller_path=None):
    output = Path(output).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)
    environment = dict(
        schema="kri-ev01-run/1",
        started_utc=datetime.now(UTC).isoformat(),
        python=platform.python_version(),
        os=platform.system(),
        architecture=platform.machine(),
        component_version=importlib.metadata.version("kri-assurance-eval"),
        runner_sha256=digest(__file__),
        protocol_sha256=digest(HERE / "protocol.json"),
        controller_sha256=digest(controller_path) if controller_path else None,
        external_execution_attestation=None,
        publication_permission=None,
    )
    (output / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")
    result = None
    try:
        controller = None
        if controller_path is not None:
            # Only explicitly supplied, locally reviewed participant code is executed.
            path = Path(controller_path).resolve()
            spec = importlib.util.spec_from_file_location("ev01_participant_controller", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            controller = module.propose
            if not callable(controller):
                raise TypeError("propose must be callable")
        result = exercise(controller)
    except Exception as error:
        result = dict(fatal_error=type(error).__name__, external_integration_confirmed=False)
    (output / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    manifest = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    (output / "checksums.json").write_text(json.dumps(manifest, indent=2) + "\n")
    controller_ok = (
        not controller_path
        or all(r.get("executed") and r.get("replayed") for r in result.get("controller_cases", []))
        and len(result.get("controller_cases", [])) == 2
    )
    good = result.get("reference_vectors_pass", False) and controller_ok
    print(
        json.dumps(
            dict(
                reference_vectors_pass=result.get("reference_vectors_pass", False),
                controller_attempted=controller_path is not None,
                check_completed=good,
                independent_validation=False,
            )
        )
    )
    return 0 if good else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--controller", type=Path)
    arguments = parser.parse_args()
    try:
        raise SystemExit(execute(arguments.output, arguments.controller))
    except (ValueError, OSError) as error:
        print(type(error).__name__, file=sys.stderr)
        raise SystemExit(2) from None
