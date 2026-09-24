"""Non-executing original input/receipt reader, independently reconstructed schemas."""

from pathlib import Path, PurePosixPath
from collections import Counter
import hashlib
from .schema import require, strict_json, identity, read_info, action

STRATA = ("interior_pair", "radial_boundary", "three_face_boundary", "timing_bounded_pair")
CASE_FIELDS = {"schema", "namespace", "stratum", "index", "generator_seed", "information"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_name(name):
    require(
        type(name) is str and bool(name) and name != "." and "\0" not in name, "Invalid member name"
    )
    path = PurePosixPath(name)
    require(
        not path.is_absolute()
        and path.as_posix() == name
        and ".." not in path.parts
        and "." not in path.parts,
        "Unsafe archive member",
    )
    return name


def read_case(doc):
    require(type(doc) is dict and set(doc) == CASE_FIELDS, "Case fields")
    require(
        doc["schema"] == "sal-protected-case/1"
        and doc["namespace"] in ("calibration", "development", "protected", "stress"),
        "Case schema/namespace",
    )
    require(
        doc["stratum"] in STRATA and type(doc["index"]) is int and doc["index"] >= 0,
        "Case index/stratum",
    )
    require(
        type(doc["generator_seed"]) is str
        and len(doc["generator_seed"]) <= 128
        and doc["generator_seed"].isascii()
        and doc["generator_seed"].isdigit()
        and str(int(doc["generator_seed"])) == doc["generator_seed"],
        "Generator seed encoding",
    )
    return read_info(doc["information"])


def stem(payload):
    return payload["stratum"] + "__" + format(payload["index"], "05d")


def receipt_binding(row, payload, kind):
    require(type(row) is dict, "Receipt dictionary")
    require(
        row.get("receipt_sha256")
        == identity({k: v for k, v in row.items() if k != "receipt_sha256"}),
        "Receipt self-hash",
    )
    require(row.get("case_id") == identity(payload), "Receipt input identity")
    for key in ("namespace", "stratum", "index", "generator_seed"):
        require(
            type(row.get(key)) is type(payload[key]) and row[key] == payload[key],
            "Receipt metadata differs",
        )
    expected = (
        "sal-evaluation-episode/1" if kind == "episode" else "sal-replacement-qualification/1"
    )
    require(row.get("schema") == expected, "Original receipt schema")
    return row


def read_pair(payload, episode, qualification):
    info = read_case(payload)
    receipt_binding(episode, payload, "episode")
    receipt_binding(qualification, payload, "qualification")
    q = qualification.get("qualification")
    require(
        type(q) is dict and q.get("schema") == "sal-repaired-qualification/1",
        "Qualification schema",
    )
    require(q.get("information_sha256") == info.identity(), "Qualification information identity")
    require(
        q.get("eligible") is True and q.get("status") == "qualified",
        "Selected qualification is not positive",
    )
    require(episode.get("qualification") == q, "Episode qualification changed")
    require(
        type(q.get("hypotheses")) is list and len(q["hypotheses"]) == len(info.hypotheses),
        "Incomplete qualification witnesses",
    )
    actions = []
    for i, row in enumerate(q["hypotheses"]):
        require(type(row) is dict, "Qualification witness object required")
        require(
            type(row.get("hypothesis")) is int
            and row["hypothesis"] == i
            and row.get("qualified") is True,
            "Qualification hypothesis mapping",
        )
        u = action(row.get("witness_action"), info.authority)
        library = (
            {(0, 0)}
            | {(v, 0) for v in ("-1/200", "1/200", "-1/100", "1/100", "-19/1000", "19/1000")}
            | {(0, v) for v in ("-1/200", "1/200", "-1/100", "1/100", "-19/1000", "19/1000")}
        )
        from fractions import Fraction as Q

        require(
            u in {tuple(Q(v) for v in x) for x in library},
            "Qualification command outside fixed library",
        )
        actions.append(u)
    require(episode.get("physical_validation") is False, "Unexpected physical-validation claim")
    require(type(episode.get("candidate")) is dict, "Missing candidate")
    return info, episode["candidate"], actions


def raw_records(path, expected_members=None):
    """Never extracts files or evaluates source. Original bytes remain byte-bound."""
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), "Unsafe raw record archive")
    require(path.stat().st_size <= 1024 * 1024 * 1024, "Archive size limit")
    members = {}
    total = 0
    with path.open("rb") as f:
        for line in f:
            row = strict_json(line)
            require(type(row) is dict and set(row) == {"path", "raw_utf8"}, "Archive entry fields")
            name = safe_name(row["path"])
            require(
                name not in members and type(row["raw_utf8"]) is str,
                "Duplicate member or invalid text",
            )
            raw = row["raw_utf8"].encode("utf8")
            total += len(raw)
            require(total <= 1024 * 1024 * 1024, "Archive expansion limit")
            members[name] = raw
    if expected_members is not None:
        require(
            {k: sha(v) for k, v in members.items()} == expected_members,
            "Full raw archive membership/content differs",
        )
    return members


def load_dataset(study, expected_files=None):
    """Binding/shape checks only. No trajectory, policy or certificate computation."""
    study = Path(study)
    if expected_files is not None:
        for name, expected in expected_files.items():
            safe_name(name)
            path = study / name
            require(
                path.is_file()
                and not path.is_symlink()
                and not any(x.is_symlink() for x in path.parents),
                "Unsafe bound input",
            )
            require(sha(path.read_bytes()) == expected, "Frozen original file changed: " + name)
    folder = study / "campaign_v2/recorded"
    manifest = strict_json((folder / "manifest.json").read_bytes())
    data = raw_records(folder / "raw_records.jsonl", manifest["raw_members"])
    inputs = strict_json((folder / "inputs.json").read_bytes())
    require(type(inputs) is list and len(inputs) == 1152, "Original input reserve size")
    by_key = {}
    for payload in inputs:
        read_case(payload)
        key = stem(payload)
        require(key not in by_key, "Duplicate original input")
        by_key[key] = payload
    selection = strict_json(data["selection.json"])
    selected = selection["selected"]
    require(set(selected) == set(STRATA), "Selection groups")
    require(selection["identity"] == manifest["evaluation_id"], "Selection evaluation binding")
    records = []
    covered = set()
    for st in STRATA:
        ids = selected[st]
        require(
            type(ids) is list
            and len(ids) == 192
            and all(type(i) is int and i >= 0 for i in ids)
            and ids == sorted(set(ids)),
            "Selection count/order",
        )
        for index in ids:
            key = st + "__" + format(index, "05d")
            require(key in by_key and key not in covered, "Selected input membership")
            covered.add(key)
            payload = by_key[key]
            ename = "episodes/cases/" + key + ".json"
            qname = "qualification/cases/" + key + ".json"
            require(ename in data and qname in data, "Missing original receipt")
            episode, qualification = (strict_json(data[name]) for name in (ename, qname))
            read_pair(payload, episode, qualification)
            require(
                selection["qualification_sha256"].get(key + ".json") == sha(data[qname]),
                "Selected qualification raw identity",
            )
            records.append(
                {
                    "key": key,
                    "payload": payload,
                    "episode": episode,
                    "qualification": qualification,
                    "bindings": {
                        "input_sha256": identity(payload),
                        "episode_sha256": sha(data[ename]),
                        "qualification_sha256": sha(data[qname]),
                    },
                }
            )
    actual = {name for name in data if name.startswith("episodes/cases/")}
    require(
        actual == {"episodes/cases/" + k + ".json" for k in covered},
        "Missing/extra selected receipts",
    )
    return records, {
        "schema": "sal-independent-reader/1",
        "selected": len(records),
        "reserve": len(inputs),
        "raw_members": len(data),
        "original_statuses": dict(Counter(x["episode"]["candidate"]["status"] for x in records)),
        "source_shapes_verified": True,
        "numerical_audit_executed": False,
    }
