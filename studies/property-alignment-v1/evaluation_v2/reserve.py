"""Identity-only retirement of previously exposed and duplicate information sets.

No state membership, qualification, dynamics, candidate or comparator is called.
"""

from copy import deepcopy
import json
from .generator import STRATA, case_payload
from .identity import ROOT
from evaluation.generator import case_payload as original_payload
from evaluation.safety import canonical_hash, strict_json


def information_identity(info):
    info = deepcopy(info)
    info["hypotheses"] = sorted(
        info["hypotheses"], key=lambda h: json.dumps(h, sort_keys=True, separators=(",", ":"))
    )
    return canonical_hash(info)


def known_information():
    known = set()
    for namespace, extent in (("protected", 320), ("development", 32), ("calibration", 32)):
        for s in STRATA:
            for i in range(extent):
                known.add(information_identity(original_payload(namespace, s, i)["information"]))

    def collect(value):
        if isinstance(value, dict):
            if value.get("schema") == "sal-common-information/1":
                known.add(information_identity(value))
            for v in value.values():
                collect(v)
        elif isinstance(value, list):
            for v in value:
                collect(v)

    for name in (
        "qualification_repair_v1/recorded/inputs.json",
        "candidate/recorded_development/fixture_inputs.json",
        "candidate/recorded_development/grid.json",
    ):
        collect(strict_json(ROOT / name))
    return known


def build_reserve():
    known = known_information()
    seen = set()
    rows = []
    retired = []
    for s in STRATA:
        kept = 0
        for i in range(4096):
            payload = case_payload("protected", s, i)
            ident = information_identity(payload["information"])
            entry = {
                "stratum": s,
                "index": i,
                "payload_sha256": canonical_hash(payload),
                "information_sha256": ident,
            }
            if ident in known or ident in seen:
                retired.append(
                    {
                        **entry,
                        "reason": "previously_exposed_information"
                        if ident in known
                        else "duplicate_in_new_reserve",
                    }
                )
                continue
            rows.append(entry)
            seen.add(ident)
            kept += 1
            if kept == 288:
                break
        if kept != 288:
            raise ValueError("Fresh-identity reserve exhausted without scientific execution")
    return {
        "schema": "sal-fresh-reserve/1",
        "namespace": "protected",
        "cases_per_stratum": 288,
        "first_proposed_index": 0,
        "known_information_count": len(known),
        "known_information_sha256": canonical_hash(sorted(known)),
        "cases": rows,
        "retired": retired,
        "scientific_outcomes_computed": False,
        "scope": "Identity-only exposure control; no membership, qualification, dynamics or protected endpoint.",
    }
