"""Execution failures are attributed, preserved and never converted to ineligibility."""

from pathlib import Path
from copy import deepcopy
import fcntl
import hashlib
import pytest
from evaluation.safety import strict_json, atomic_json, canonical_hash
from qualification_repair_v1.fixtures import inputs
from qualification_repair_v1.jobs import run_jobs, _missing, _validate


def safe_inputs():
    return inputs()[:2]


def hashes(output):
    return {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in (output / "cases").glob("*.json")
    }


def test_checkpoint_preserves_completed_receipts(tmp_path):
    payloads = safe_inputs()
    out = tmp_path / "run"
    first = run_jobs(payloads, out, workers=1, max_new=1)
    old = hashes(out)
    assert not first["complete"] and first["completed"] == 1
    second = run_jobs(payloads, out, workers=1)
    assert second["complete"] and second["new_attempts"] == 1 and not second["blockers"]
    assert all(hashes(out)[k] == v for k, v in old.items())
    assert run_jobs(payloads, out, workers=1)["new_attempts"] == 0


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("forced_timeout", "qualification_timeout"),
        ("forced_crash", "qualification_process_failure"),
    ],
)
def test_real_watchdog_and_process_failure_have_case_and_phase(tmp_path, mode, expected):
    payloads = safe_inputs()[:1]
    out = tmp_path / "failure"
    limit = 0.2 if mode == "forced_timeout" else 15.0
    batch = run_jobs(payloads, out, workers=1, case_limit_s=limit, test_mode=mode)
    assert batch["complete"] and batch["blockers"] == 1
    row = strict_json(next((out / "cases").glob("*.json")))
    assert row["qualification"]["status"] == expected and row["qualification"]["eligible"] is None
    assert row["failure"]["case_key"] == payloads[0]["key"] and row["failure"]["phase"]
    before = hashes(out)
    again = run_jobs(payloads, out, workers=1, case_limit_s=limit, test_mode=mode)
    assert again["new_attempts"] == 0 and hashes(out) == before


def test_started_missing_is_retained_as_unknown(tmp_path):
    payloads = safe_inputs()
    out = tmp_path / "run"
    run_jobs(payloads, out, workers=1, max_new=0)
    p = payloads[0]
    atomic_json(
        out / "started" / (p["key"] + ".json"), {"key": p["key"], "input_sha256": canonical_hash(p)}
    )
    batch = run_jobs(payloads, out, workers=1, max_new=0)
    row = strict_json(out / "cases" / (p["key"] + ".json"))
    assert batch["new_attempts"] == 0 and row["qualification"]["eligible"] is None
    assert row["qualification"]["status"] == "interrupted_qualification"


def test_header_drift_rejected(tmp_path):
    p = safe_inputs()
    out = tmp_path / "run"
    run_jobs(p, out, workers=1, max_new=0)
    with pytest.raises(ValueError):
        run_jobs(p, out, workers=2)
    with pytest.raises(ValueError):
        run_jobs(p, out, workers=1, case_limit_s=30)


def test_concurrent_coordinator_refused(tmp_path):
    out = tmp_path / "run"
    lockpath = tmp_path / ".run.qualification.lock"
    with lockpath.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            run_jobs(safe_inputs(), out)
    assert not out.exists()


def test_unknown_or_fresh_protected_input_refused(tmp_path):
    payload = deepcopy(safe_inputs()[0])
    payload["namespace"] = "protected"
    with pytest.raises(ValueError):
        run_jobs([payload], tmp_path / "bad")
    assert not (tmp_path / "bad").exists()


def test_receipt_corruption_not_silently_resumed(tmp_path):
    p = safe_inputs()[:1]
    out = tmp_path / "run"
    run_jobs(p, out, workers=1)
    path = next((out / "cases").glob("*.json"))
    row = strict_json(path)
    row["input_sha256"] = "bad"
    path.write_text(__import__("json").dumps(row))
    with pytest.raises(ValueError):
        run_jobs(p, out, workers=1)


def test_missing_flag_cannot_be_cast_as_excluded():
    p = safe_inputs()[0]
    row = _missing(p, "qualification_timeout", Path("/nonexistent/test-events"))
    row["qualification"]["eligible"] = False
    with pytest.raises(ValueError):
        _validate(row, p)


def test_repository_output_refused():
    repo = Path(__file__).resolve().parents[4]
    with pytest.raises(ValueError):
        run_jobs(safe_inputs(), repo / "never-created-by-test")


def test_serial_and_parallel_verdicts_agree(tmp_path):
    p = safe_inputs()
    a = run_jobs(p, tmp_path / "a", workers=1)
    b = run_jobs(p, tmp_path / "b", workers=2)
    assert a["complete"] and b["complete"] and a["blockers"] == b["blockers"] == 0
    for payload in p:
        name = payload["key"] + ".json"
        x = strict_json(tmp_path / "a/cases" / name)["qualification"]
        y = strict_json(tmp_path / "b/cases" / name)["qualification"]
        for k in ("wall_s",):
            x.pop(k)
            y.pop(k)
        assert x == y
