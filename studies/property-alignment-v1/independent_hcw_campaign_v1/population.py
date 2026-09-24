"""Structural reconstruction of the original reserve, selection and receipt bindings.

No generator, qualification search, policy or trajectory function is called.
"""

from collections import Counter
from copy import deepcopy
from pathlib import Path
import math
from independent_hcw_audit_v1.schema import strict_json, identity, canonical, require
from independent_hcw_audit_v1.reader import (
    STRATA,
    read_case,
    read_pair,
    receipt_binding,
    raw_records,
    sha,
    stem,
)
from independent_hcw_audit_v1.protocol import validate_document

ROOT = Path(__file__).resolve().parent
STUDY = ROOT.parent
AUDIT_ID = "bc472385b582d0f5d6ee9e7a3e4d5f250d316f2c6c9a4c8e31be21f838577f53"
SCIENCE = "b2ff0cc3e0c5c0a524d248fa62d0f8ffc24d65b8"
EXPECTED_ORIGINAL = {
    "certified_common_prefix": 725,
    "proved_no_common_held_command": 31,
    "unresolved": 9,
    "unresolved_budget": 3,
}


def first_qualifying(payloads, qualifications, target=192, strata=STRATA):
    keys = [stem(p) for p in payloads]
    require(
        len(set(keys)) == len(keys) and set(qualifications) == set(keys),
        "Reserve receipt membership",
    )
    require(type(target) is int and target > 0, "Selection target")
    selected = {}
    for s in strata:
        group = [p for p in payloads if p["stratum"] == s]
        ids = [p["index"] for p in group]
        require(
            all(type(i) is int and i >= 0 for i in ids) and ids == sorted(set(ids)),
            "Reserve index order",
        )
        eligible = []
        for p in group:
            q = qualifications[stem(p)]["qualification"]
            require(type(q.get("eligible")) is bool, "Unknown qualification blocks selection")
            require(
                q.get("status")
                in ("qualified", "not_certified_by_library", "proved_precommand_violation"),
                "Unrecognized qualification",
            )
            require((q["status"] == "qualified") is q["eligible"], "Qualification status mismatch")
            if q["eligible"]:
                eligible.append(p["index"])
        require(len(eligible) >= target, "Insufficient eligible reserve")
        selected[s] = eligible[:target]
    return selected


def check_episode_semantics(episode):
    c, primary = episode["candidate"], episode["primary"]
    status = c.get("status")
    require(status in EXPECTED_ORIGINAL, "Original status not recognized")
    wall, late = c.get("wall_s"), c.get("deadline_exceeded")
    require(
        type(wall) in (int, float) and math.isfinite(wall) and wall >= 0 and type(late) is bool,
        "Original timing type/value",
    )
    require(
        late is (wall > 1) and (status == "unresolved_budget") is late,
        "Original deadline consistency",
    )
    decisive = status in ("certified_common_prefix", "proved_no_common_held_command")
    proof = episode["certificate_recheck"]
    require(
        primary.get("eligible") is True
        and primary.get("decisive") is decisive
        and primary.get("on_time") is (not late),
        "Original primary interpretation",
    )
    require(
        primary.get("valid_certificate") is True
        and primary.get("on_time_decisive_valid") is (decisive and not late),
        "Original endpoint consistency",
    )
    require(proof.get("checked") is decisive, "Original check accounting")
    if decisive:
        require(proof.get("valid") is True, "Original definite receipt lacks its stated recheck")
    require(
        (c.get("action") is not None) is (status == "certified_common_prefix"),
        "Original delivered action accounting",
    )


def load_original(study=STUDY):
    study = Path(study)
    freeze_path = study / "independent_hcw_audit_v1/frozen/protocol.json"
    frozen = validate_document(strict_json(freeze_path.read_bytes()), AUDIT_ID)
    for name, digest in frozen["original_files_sha256"].items():
        path = study / name
        require(
            path.is_file() and not any(x.is_symlink() for x in (path, *path.parents)),
            "Unsafe original input",
        )
        require(sha(path.read_bytes()) == digest, "Changed original input " + name)
    folder = study / "campaign_v2/recorded"
    manifest = strict_json((folder / "manifest.json").read_bytes())
    raw = raw_records(folder / "raw_records.jsonl", manifest["raw_members"])
    inputs = strict_json((folder / "inputs.json").read_bytes())
    reserve = strict_json((study / "evaluation_v2/frozen/reserve.json").read_bytes())
    design = strict_json((study / "evaluation_v2/frozen/protocol.json").read_bytes())
    require(
        design["target_per_stratum"] == 192
        and design["reserve_per_stratum"] == 288
        and design["strata"] == list(STRATA),
        "Original population design",
    )
    require(
        type(inputs) is list and len(inputs) == 1152 and len(reserve["cases"]) == 1152,
        "Original reserve denominator",
    )
    require(reserve["namespace"] == "protected", "Original reserve namespace")
    by_key, qualifications, ledger = {}, {}, []
    selection = strict_json(raw["selection.json"])
    require(selection["identity"] == manifest["evaluation_id"], "Selection identity")
    for payload, bound in zip(inputs, reserve["cases"], strict=True):
        info = read_case(payload)
        key = stem(payload)
        require(
            key not in by_key and payload["namespace"] == "protected",
            "Duplicate or nonprotected input",
        )
        by_key[key] = payload
        unordered = deepcopy(payload["information"])
        unordered["hypotheses"] = sorted(unordered["hypotheses"], key=canonical)
        require(
            bound
            == {
                "stratum": payload["stratum"],
                "index": payload["index"],
                "payload_sha256": identity(payload),
                "information_sha256": identity(unordered),
            },
            "Reserve content identity",
        )
        name = "qualification/cases/" + key + ".json"
        require(name in raw, "Missing reserve qualification")
        qrow = receipt_binding(strict_json(raw[name]), payload, "qualification")
        q = qrow["qualification"]
        require(
            q.get("schema") == "sal-repaired-qualification/1"
            and q.get("information_sha256") == info.identity(),
            "Qualification information",
        )
        require(
            qrow.get("qualification_recheck", {}).get("passed") is True,
            "Original qualification recheck missing",
        )
        require(
            selection["qualification_sha256"].get(key + ".json") == sha(raw[name]),
            "Selection qualification digest",
        )
        qualifications[key] = qrow
        ledger.append(
            {
                "key": key,
                "stratum": payload["stratum"],
                "index": payload["index"],
                "input_sha256": identity(payload),
                "information_sha256": info.identity(),
                "reserve_unordered_information_sha256": identity(unordered),
                "qualification_sha256": sha(raw[name]),
                "original_eligible": q["eligible"],
                "original_qualification_status": q["status"],
            }
        )
    qnames = {"qualification/cases/" + k + ".json" for k in by_key}
    require(
        {n for n in raw if n.startswith("qualification/cases/")} == qnames,
        "Qualification archive membership",
    )
    require(
        set(selection["qualification_sha256"]) == {k + ".json" for k in by_key},
        "Qualification selection inventory",
    )
    require(
        [p["stratum"] for p in inputs] == [s for s in STRATA for _ in range(288)],
        "Reserve group order",
    )
    reconstructed = first_qualifying(inputs, qualifications)
    require(
        selection["selected"] == reconstructed,
        "Recorded selection differs from first qualifying indices",
    )
    for s in STRATA:
        kept = {p["index"] for p in inputs if p["stratum"] == s}
        retired = [x for x in reserve["retired"] if x["stratum"] == s]
        retired_ids = {x["index"] for x in retired}
        require(
            len(retired_ids) == len(retired)
            and not kept & retired_ids
            and kept | retired_ids == set(range(max(kept) + 1)),
            "Retired/kept index accounting",
        )
    records = []
    for s in STRATA:
        for index in reconstructed[s]:
            key = s + "__" + format(index, "05d")
            payload, qrow = by_key[key], qualifications[key]
            ename = "episodes/cases/" + key + ".json"
            require(ename in raw, "Missing selected episode")
            episode = strict_json(raw[ename])
            info, candidate, actions = read_pair(payload, episode, qrow)
            check_episode_semantics(episode)
            records.append(
                {
                    "key": key,
                    "payload": payload,
                    "episode": episode,
                    "qualification": qrow,
                    "bindings": {
                        "input_sha256": identity(payload),
                        "episode_sha256": sha(raw[ename]),
                        "qualification_sha256": sha(raw["qualification/cases/" + key + ".json"]),
                    },
                }
            )
    require(
        [{"key": x["key"], **x["bindings"]} for x in records] == frozen["case_bindings"],
        "Independent freeze case binding",
    )
    chosen = {x["key"] for x in records}
    require(
        {n for n in raw if n.startswith("episodes/cases/")}
        == {"episodes/cases/" + k + ".json" for k in chosen},
        "Selected episode archive membership",
    )
    for row in ledger:
        row["selected"] = row["key"] in chosen
        row["independent_numerical_scope"] = (
            "saved_singleton_witnesses" if row["selected"] else "not_numerically_rechecked"
        )
    original_counts = dict(Counter(x["episode"]["candidate"]["status"] for x in records))
    require(original_counts == EXPECTED_ORIGINAL, "Original counts changed")
    groups = []
    for s in STRATA:
        g = [x for x in ledger if x["stratum"] == s]
        groups.append(
            {
                "stratum": s,
                "reserve": len(g),
                "selected": sum(x["selected"] for x in g),
                "qualification_statuses": dict(
                    Counter(x["original_qualification_status"] for x in g)
                ),
            }
        )
    return (
        frozen,
        records,
        ledger,
        {
            "schema": "sal-original-population-audit/1",
            "reserve": len(inputs),
            "qualification_records": len(qualifications),
            "selected": len(records),
            "retired_before_reserve": reserve["retired"],
            "original_statuses": original_counts,
            "selected_singleton_witnesses": sum(
                len(x["payload"]["information"]["hypotheses"]) for x in records
            ),
            "groups": groups,
            "selection_rule_reconstructed": True,
            "all_raw_members_checked": len(raw),
            "original_policy_or_qualification_search_executed": False,
            "unselected_qualification_proofs_independently_rechecked": False,
        },
    )
