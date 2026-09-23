"""Read-only membership, receipt and frozen-analysis audit. Never reruns a policy.

Proof checks here validate saved certificate structure and algebra. Numerical
trajectory/certificate recomputation is limited to the original in-episode checks.
"""

from pathlib import Path, PurePosixPath
from collections import Counter
from fractions import Fraction as Q
import hashlib
import json
import math
import tarfile
from evaluation.safety import canonical_hash
from evaluation.analysis import analyze_rows
from evaluation.runner import _information
from evaluation.qualification import QUALIFICATION_ACTIONS
from evaluation_v2.identity import verify
from evaluation_v2.generator import STRATA, case_payload
from evaluation_v2.receipts import validate, key

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "evaluation_v2/frozen/freeze.json"
DEFINITE = {"certified_common_prefix", "proved_no_common_held_command"}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_name(name):
    p = PurePosixPath(name)
    require(
        isinstance(name, str)
        and name
        and not p.is_absolute()
        and ".." not in p.parts
        and str(p) == name
        and "\\" not in name,
        "Unsafe archive member",
    )
    return name


def finite_tree(value):
    if isinstance(value, float):
        require(math.isfinite(value), "Nonfinite numeric field")
    elif isinstance(value, dict):
        for child in value.values():
            finite_tree(child)
    elif isinstance(value, list):
        for child in value:
            finite_tree(child)


def decode(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, "Duplicate JSON key")
            result[k] = v
        return result

    def reject(value):
        raise ValueError("Nonfinite JSON token " + value)

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)
    finite_tree(value)
    return value


class Records:
    """Directory, audit-only tar support, or lossless UTF-8 JSONL publication bundle."""

    def __init__(self, path):
        self.path = Path(path)
        self.archive = None
        self.text_members = None
        if self.path.is_dir():
            members = [p for p in self.path.rglob("*") if p.is_file()]
            require(not any(p.is_symlink() for p in self.path.rglob("*")), "Symlink in raw records")
            self.names = {safe_name(p.relative_to(self.path).as_posix()) for p in members}
        elif self.path.suffix == ".jsonl":
            self.text_members = {}
            total = 0
            with self.path.open("rb") as stream:
                for line in stream:
                    entry = decode(line)
                    require(
                        isinstance(entry, dict) and set(entry) == {"path", "raw_utf8"},
                        "Invalid text-bundle member",
                    )
                    name = safe_name(entry["path"])
                    require(
                        name not in self.text_members and isinstance(entry["raw_utf8"], str),
                        "Duplicate or nontext bundle member",
                    )
                    raw = entry["raw_utf8"].encode("utf-8")
                    require(len(raw) <= 16 * 1024**2, "Oversized bundled receipt")
                    total += len(raw)
                    require(total <= 512 * 1024**2, "Text bundle exceeds frozen receipt budget")
                    self.text_members[name] = raw
            self.names = set(self.text_members)
        else:
            self.archive = tarfile.open(self.path, "r:gz")
            members = self.archive.getmembers()
            require(all(m.isfile() for m in members), "Archive must contain regular files only")
            require(len({m.name for m in members}) == len(members), "Duplicate archive member")
            require(
                sum(m.size for m in members) <= 512 * 1024**2,
                "Archive exceeds frozen receipt budget",
            )
            require(all(0 <= m.size <= 16 * 1024**2 for m in members), "Oversized archived receipt")
            self.names = {safe_name(m.name) for m in members}

    def raw(self, name):
        safe_name(name)
        require(name in self.names, "Missing record " + name)
        if self.text_members is not None:
            return self.text_members[name]
        if self.archive is None:
            return (self.path / name).read_bytes()
        stream = self.archive.extractfile(name)
        require(stream is not None, "Unreadable archived member")
        return stream.read()

    def doc(self, name):
        return decode(self.raw(name))

    def inventory(self):
        return {n: sha(self.raw(n)) for n in sorted(self.names)}

    def close(self):
        if self.archive is not None:
            self.archive.close()


def bounded_action(action, info):
    require(isinstance(action, list) and len(action) == 2, "Wrong action dimension")
    require(
        all(isinstance(v, str) for v in action), "Action coordinates must retain rational strings"
    )
    v = tuple(Q(x) for x in action)
    require(sum(x * x for x in v) <= info.authority**2, "Overlimit action")
    return v


def qualification_claim(row, payload):
    require(type(row.get("index")) is int, "Qualification index must be an integer")
    validate(row, payload, "qualification")
    q = row["qualification"]
    info = _information(payload)
    require(type(q["eligible"]) is bool, "Qualification unknown blocks the selected population")
    require(q.get("full_recovery_claim") is False, "Unsupported recovery claim")
    if q["eligible"]:
        require(q.get("physical_impossibility_claim") is False, "Contradictory positive qualifier")
        hs = q["hypotheses"]
        require(
            [r["hypothesis"] for r in hs] == list(range(len(info.hypotheses))),
            "Missing/duplicate qualified hypothesis",
        )
        library = {tuple(Q(str(x)) for x in a) for a in QUALIFICATION_ACTIONS}
        for h in hs:
            require(h["qualified"] is True, "Unqualified hypothesis selected")
            require(
                bounded_action(h["witness_action"], info) in library, "Witness not in fixed library"
            )
    elif q["status"] == "proved_precommand_violation":
        w = q["queue_witness"]
        i = w["hypothesis"]
        origin = tuple(Q(v) for v in w["origin"])
        require(type(i) is int and 0 <= i < len(info.hypotheses), "Bad witness hypothesis")
        require(
            w["information_sha256"] == info.identity() and w["model"] == "hcw",
            "Queue witness identity",
        )
        require(info.hypotheses[i].contains(origin), "Unattainable queue origin")
        require(
            0 <= Q(w["time_s"]) <= info.application_time, "Queue witness after command application"
        )
        require(w["new_command_used"] is False, "New command used in queue witness")
        require(
            info.effectiveness[0] <= Q(w["effectiveness"]) <= info.effectiveness[1],
            "Queue witness effectiveness outside bounds",
        )
        require(
            len(w["disturbance"]) == 2
            and all(abs(Q(v)) <= info.disturbance for v in w["disturbance"]),
            "Queue witness disturbance outside bounds",
        )


def episode_claim(row, payload, qualification):
    require(type(row.get("index")) is int, "Episode index must be an integer")
    validate(row, payload, "episode", qualification)
    require(row.get("physical_validation") is False, "Unsupported physical validation")
    p = row["primary"]
    c = row["candidate"]
    info = _information(payload)
    require(p["eligible"] is True, "Selected input excluded after outcome")
    if c.get("action") is not None:
        bounded_action(c["action"], info)
    if not p["decisive"] or not p["valid_certificate"]:
        return
    proof = row["certificate_recheck"]
    require(
        proof.get("checked") is True and proof.get("valid") is True,
        "Missing in-episode proof check",
    )
    if c["status"] == "certified_common_prefix":
        d = c["positive"]
        require(proof["kind"] == "positive_fixed_action", "Wrong positive recheck kind")
        require(
            d["status"] == "certified_common_prefix"
            and d["information_sha256"] == info.identity()
            and d["model"] == "hcw",
            "Positive proof identity differs",
        )
        require(d["action"] == c["action"], "Delivered and checked action differ")
        require(
            Q(d["end_after_measurement_s"]) == info.application_time + 1, "Wrong prefix horizon"
        )
        require(len(d["hypotheses"]) == len(info.hypotheses), "Missing positive hypothesis")
        for h in d["hypotheses"]:
            require(h["status"] == "validated_containment", "Invalid positive prefix record")
            require(
                all(
                    h["components"].get(k) == "satisfied"
                    for k in ("containment", "collision_free", "keep_out_free")
                ),
                "Component disagreement",
            )
            require(
                len(h["enclosure_final"]) == 4
                and all(len(x) == 2 and x[0] <= x[1] for x in h["enclosure_final"]),
                "Invalid endpoint enclosure",
            )
    else:
        d = c["negative"]
        check = d["checked"]
        require(
            proof["kind"] == "negative_dual"
            and d["model"] == "hcw"
            and d["information_sha256"] == info.identity(),
            "Negative proof identity differs",
        )
        weights = [Q(v) for v in d["weights"]]
        require(weights and min(weights) >= 0 and max(weights) > 0, "Invalid dual weights")
        margin = Q(check["margin_lower"])
        residual = [Q(v) for v in check["coefficient_residual_upper"]]
        require(
            check["proved"] is True and margin > 0 and len(residual) == 2 and min(residual) >= 0,
            "Nonpositive or invalid saved obstruction margin",
        )
        require(
            margin == -Q(check["weighted_rhs_upper"]) - info.authority * sum(residual),
            "Saved dual residual algebra disagrees",
        )
        for a in d["active_obligations"]:
            require(Q(a["weight"]) > 0, "Inactive obligation incorrectly retained")
            if "origin" in a:
                require(
                    any(h.contains(tuple(Q(v) for v in a["origin"])) for h in info.hypotheses),
                    "Obstruction origin outside information set",
                )


def audit(source, freeze_path=FREEZE):
    freeze = verify(freeze_path, runtime=False)
    store = Records(source)
    try:
        complete = store.doc("completion.json")
        inv = store.inventory()
        expected = {
            n: h for n, h in inv.items() if n != "completion.json" and not n.endswith(".lock")
        }
        require(
            complete["identity"] == freeze["evaluation_id"] and complete["files"] == expected,
            "Completion identity or complete raw inventory differs",
        )
        header = store.doc("run_header.json")
        require(
            header["evaluation_id"] == freeze["evaluation_id"]
            and header["freeze_sha256"] == sha(Path(freeze_path).read_bytes())
            and header["source_commit"] == freeze["source_commit"]
            and header["workers"] == 4,
            "Run header differs",
        )
        reserve = decode((Path(freeze_path).parent / "reserve.json").read_bytes())
        payloads = [case_payload("protected", r["stratum"], r["index"]) for r in reserve["cases"]]
        require(len(payloads) == 1152, "Wrong qualification reserve size")
        qrows = {}
        selected = []
        selection = store.doc("selection.json")
        require(selection["identity"] == freeze["evaluation_id"], "Selection identity differs")
        qnames = {f"qualification/cases/{key(p)}.json" for p in payloads}
        require(
            {n for n in store.names if n.startswith("qualification/cases/")} == qnames,
            "Qualification membership incomplete or extra",
        )
        for p in payloads:
            q = store.doc(f"qualification/cases/{key(p)}.json")
            qualification_claim(q, p)
            qrows[canonical_hash(p)] = q
        for s in STRATA:
            group = [
                p
                for p in payloads
                if p["stratum"] == s and qrows[canonical_hash(p)]["qualification"]["eligible"]
            ]
            require(len(group) >= 192, "Reserve exhausted")
            chosen = group[:192]
            require(
                selection["selected"][s] == [p["index"] for p in chosen],
                "Not the first qualified inputs",
            )
            selected.extend(chosen)
        require(set(selection["selected"]) == set(STRATA), "Stratum identity differs")
        qhash = {Path(n).name: inv[n] for n in sorted(qnames)}
        require(
            selection["qualification_sha256"] == qhash,
            "Selection not bound to complete qualification receipts",
        )
        require(len(selected) == 768, "Fixed denominator changed")
        rows = []
        enames = {f"episodes/cases/{key(p)}.json" for p in selected}
        require(
            {n for n in store.names if n.startswith("episodes/cases/")} == enames,
            "Selected result membership differs",
        )
        for p in selected:
            r = store.doc(f"episodes/cases/{key(p)}.json")
            episode_claim(r, p, qrows[canonical_hash(p)]["qualification"])
            rows.append(r)
        for phase, ps, kind in [
            ("qualification", payloads, "qualification"),
            ("episodes", selected, "episode"),
        ]:
            bh = store.doc(f"{phase}/header.json")
            require(
                bh["context_id"] == freeze["evaluation_id"]
                and bh["kind"] == kind
                and bh["test_mode"] is None,
                "Wrong batch identity or synthetic test hook",
            )
            require(bh["inputs"] == [canonical_hash(p) for p in ps], "Wrong batch input order")
            for k1, k2 in [
                ("workers", "workers"),
                ("case_limit_s", "case_wall_limit_s"),
                ("phase_limit_s", "phase_wall_limit_s"),
            ]:
                require(bh[k1] == freeze["resources"][k2], "Frozen resource changed")
            required_markers = {f"{phase}/started/{key(p)}.json" for p in ps}
            require(
                {n for n in store.names if n.startswith(f"{phase}/started/")} == required_markers,
                "Missing or extra start markers",
            )
            for p in ps:
                marker = store.doc(f"{phase}/started/{key(p)}.json")
                require(
                    marker["case_id"] == canonical_hash(p) and marker["kind"] == kind,
                    "Start marker binding differs",
                )
        analysis = analyze_rows(
            rows, protected=True, expected_keys=[(p["stratum"], p["index"]) for p in selected]
        )
        analysis["replacement_evaluation_id"] = freeze["evaluation_id"]
        analysis["qualification_statuses"] = dict(
            sorted(Counter(q["qualification"]["status"] for q in qrows.values()).items())
        )
        analysis["evaluation_class"] = "protected_replacement"
        require(
            analysis == store.doc("analysis.json"), "Unchanged frozen analysis does not reproduce"
        )
        require(
            complete["campaign_complete"] == analysis["campaign_complete"]
            and complete["validity_claim_gate_passed"] == analysis["validity_claim_gate_passed"],
            "Completion gate mismatch",
        )
        x = sum(r["primary"]["on_time_decisive_valid"] for r in rows)
        n = len(rows)
        radius = math.sqrt(math.log(40) / (2 * n))
        interval = analysis["balanced_coverage"]
        require(
            interval["estimate"] == x / n
            and interval["lower"] == max(0, x / n - radius)
            and interval["upper"] == min(1, x / n + radius),
            "Independent interval arithmetic disagrees",
        )
        report = {
            "schema": "sal-replacement-campaign-audit/1",
            "passed": True,
            "evaluation_id": freeze["evaluation_id"],
            "qualification_receipts": len(qrows),
            "selected_receipts": n,
            "raw_files": len(inv),
            "frozen_analysis_reproduced": True,
            "independent_count_interval_arithmetic": True,
            "definite_outputs": sum(r["primary"]["decisive"] for r in rows),
            "invalid_definite_certificates": analysis["invalid_definite_certificates"],
            "campaign_complete": analysis["campaign_complete"],
            "validity_claim_gate_passed": analysis["validity_claim_gate_passed"],
            "policy_or_qualification_rerun": False,
            "new_numerical_replay": False,
            "physical_validation": False,
            "scope": "Exact raw accounting, input/receipt bindings, saved proof structure/algebra and unchanged analysis; numerical proof replay was performed only inside the frozen execution.",
        }
        return report, analysis, list(qrows.values()), rows, payloads, selected
    finally:
        store.close()
