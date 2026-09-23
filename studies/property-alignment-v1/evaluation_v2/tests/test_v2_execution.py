"""Calibration-only integration guards, never a protected scientific trial."""

from copy import deepcopy
import pytest
from evaluation.generator import case_payload as old_payload
from evaluation.safety import atomic_json, strict_json, canonical_hash
from evaluation.runner import _information
from qualification_repair_v1.core import qualify
from evaluation_v2.jobs import run_batch
from evaluation_v2.receipts import key, seal, validate, missing
from evaluation_v2.pipeline import file_inventory
from evaluation_v2.execute import run


def payload():
    return old_payload("calibration", "interior_pair", 0)


def test_v2_explicit_authorization_precedes_all_work(tmp_path):
    with pytest.raises(PermissionError):
        run(tmp_path / "absent", "x", tmp_path / "new")
    assert not (tmp_path / "new").exists()


def test_v2_protected_jobs_cannot_leak_through_test_hooks(tmp_path):
    p = payload()
    p["namespace"] = "protected"
    with pytest.raises(PermissionError):
        run_batch([p], tmp_path / "p", kind="qualification", context_id="test")
    with pytest.raises(PermissionError):
        run_batch(
            [p],
            tmp_path / "p",
            kind="qualification",
            context_id="test",
            authorize_task08d=True,
            test_mode="crash",
        )
    assert not (tmp_path / "p").exists()


@pytest.mark.parametrize("workers", [True, 0, 5, 1.5])
def test_v2_invalid_workers(tmp_path, workers):
    with pytest.raises(ValueError):
        run_batch(
            [payload()], tmp_path / "p", kind="qualification", context_id="x", workers=workers
        )


@pytest.mark.parametrize("limit", [True, 0, -1, float("nan"), float("inf"), 61])
def test_v2_invalid_limits(tmp_path, limit):
    with pytest.raises(ValueError):
        run_batch(
            [payload()], tmp_path / "p", kind="qualification", context_id="x", case_limit_s=limit
        )


def test_v2_digest_prevents_silent_receipt_mutation(tmp_path):
    p = payload()
    row = missing(p, "qualification", "test", tmp_path / "events")
    assert validate(row, p, "qualification")["qualification"]["eligible"] is None
    row["qualification"]["eligible"] = False
    with pytest.raises(ValueError):
        validate(row, p, "qualification")


def test_v2_unknown_cannot_be_relabelled_ineligible(tmp_path):
    p = payload()
    row = missing(p, "qualification", "worker_wall_timeout", tmp_path / "events")
    del row["receipt_sha256"]
    row["qualification"]["eligible"] = False
    row = seal(row)
    with pytest.raises(ValueError):
        validate(row, p, "qualification")


@pytest.mark.parametrize("kind", ["qualification", "episode"])
@pytest.mark.parametrize("mode", ["crash", "timeout"])
def test_v2_attributed_failures_are_retained(tmp_path, kind, mode):
    p = payload()
    qual = qualify(_information(p))
    kwargs = {"qualifications": {canonical_hash(p): qual}} if kind == "episode" else {}
    path = tmp_path / "batch"
    batch = run_batch(
        [p],
        path,
        kind=kind,
        context_id="failure-test",
        workers=1,
        test_mode=mode,
        case_limit_s=0.01 if mode == "timeout" else 15,
        **kwargs,
    )
    assert batch["complete"]
    row = strict_json(path / "cases" / (key(p) + ".json"))
    assert row["failure"]["case_key"] == key(p)
    if kind == "qualification":
        assert row["qualification"]["eligible"] is None and batch["blockers"] == 1
    else:
        assert (
            row["qualification"]["eligible"] is True
            and row["primary"]["on_time_decisive_valid"] is False
        )
    before = file_inventory(path)
    again = run_batch(
        [p],
        path,
        kind=kind,
        context_id="failure-test",
        workers=1,
        test_mode=mode,
        case_limit_s=0.01 if mode == "timeout" else 15,
        **kwargs,
    )
    assert again["new_attempts"] == 0 and file_inventory(path) == before


def test_v2_resume_finishes_only_unstarted_cases(tmp_path):
    inputs = [old_payload("calibration", "interior_pair", i) for i in range(2)]
    path = tmp_path / "batch"
    first = run_batch(inputs, path, kind="qualification", context_id="resume", workers=1, max_new=1)
    assert first["completed"] == 1 and not first["complete"]
    before = (path / "cases" / (key(inputs[0]) + ".json")).read_bytes()
    second = run_batch(inputs, path, kind="qualification", context_id="resume", workers=1)
    assert second["complete"] and second["new_attempts"] == 1 and second["blockers"] == 0
    assert (path / "cases" / (key(inputs[0]) + ".json")).read_bytes() == before
    with pytest.raises(ValueError):
        run_batch(inputs, path, kind="qualification", context_id="another", workers=1)


def test_v2_interrupted_marker_is_unknown_not_retry(tmp_path):
    p = payload()
    path = tmp_path / "batch"
    run_batch([p], path, kind="qualification", context_id="interrupted", workers=1, max_new=0)
    atomic_json(
        path / "started" / (key(p) + ".json"),
        {"case_id": canonical_hash(p), "kind": "qualification"},
    )
    result = run_batch([p], path, kind="qualification", context_id="interrupted", workers=1)
    assert result["new_attempts"] == 0 and result["blockers"] == 1


def test_v2_no_candidate_before_complete_qualified_selection(tmp_path, monkeypatch):
    import evaluation_v2.pipeline as module

    calls = []

    def blocked(*args, **kwargs):
        calls.append(kwargs["kind"])
        return {"complete": True, "blockers": 1}

    monkeypatch.setattr(module, "run_batch", blocked)
    result = module.pipeline(
        [payload()],
        tmp_path / "p",
        identity="x",
        resources={"workers": 1, "case_wall_limit_s": 15, "phase_wall_limit_s": 15},
        target_per_stratum=2,
    )
    assert result["status"] == "qualification_blocked" and calls == ["qualification"]


def test_v2_qualified_record_rejects_bad_metadata(tmp_path):
    p = payload()
    qual = qualify(_information(p))
    row = missing(p, "episode", "worker_wall_timeout", tmp_path / "events", qual)
    assert validate(row, p, "episode", qual)["primary"]["on_time_decisive_valid"] is False
    changed = deepcopy(qual)
    changed["wall_s"] += 1
    with pytest.raises(ValueError):
        validate(row, p, "episode", changed)


def test_v2_batch_lock_prevents_false_interruption(tmp_path):
    import fcntl

    path = tmp_path / "batch"
    with (tmp_path / ".batch.batch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            run_batch([payload()], path, kind="qualification", context_id="lock", workers=1)
    assert not path.exists()


def test_v2_extra_receipt_blocks_resume(tmp_path):
    p = payload()
    path = tmp_path / "batch"
    run_batch([p], path, kind="qualification", context_id="extra", workers=1, max_new=0)
    atomic_json(path / "cases" / "unexpected.json", {"synthetic": True})
    with pytest.raises(ValueError, match="Unexpected"):
        run_batch([p], path, kind="qualification", context_id="extra", workers=1)


def test_v2_completed_pipeline_never_reexecutes(tmp_path, monkeypatch):
    import evaluation_v2.pipeline as module

    path = tmp_path / "completed"
    path.mkdir()
    result = {"campaign_complete": True, "synthetic_fixture": True}
    atomic_json(path / "analysis.json", result)
    atomic_json(
        path / "completion.json", {"identity": "test", "files": module.file_inventory(path)}
    )
    monkeypatch.setattr(
        module,
        "run_batch",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("Unexpected execution")),
    )
    assert (
        module.pipeline([payload()], path, identity="test", resources={}, target_per_stratum=2)
        == result
    )
    (path / "analysis.json").write_text("{}")
    with pytest.raises(ValueError, match="changed"):
        module.pipeline([payload()], path, identity="test", resources={}, target_per_stratum=2)
