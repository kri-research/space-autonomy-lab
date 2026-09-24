"""Data binding and non-retrying orchestration checks on exposed fixtures only."""

from pathlib import Path
from copy import deepcopy
import json
import tempfile
import unittest
from unittest.mock import patch
import subprocess
from independent_hcw_audit_v1.reader import read_case, read_pair, raw_records, safe_name
from independent_hcw_audit_v1.schema import identity, strict_json, InvalidEvidence
from independent_hcw_audit_v1.calibration import SETTINGS
from independent_hcw_audit_v1.runner import run_jobs, write_new, verify_freeze, ROOT


def cases():
    return strict_json((ROOT / "development_cases.json").read_bytes())


def calibration():
    return next(j for j in cases() if j["kind"] == "recorded_episode")


def example():
    return next(j for j in cases() if j["key"] == "named-midpoint_known")


def reseal(row):
    row["receipt_sha256"] = identity({k: v for k, v in row.items() if k != "receipt_sha256"})


class ReaderTests(unittest.TestCase):
    def test_eight_exposed_original_receipts(self):
        selected = [j for j in cases() if j["kind"] == "recorded_episode"]
        self.assertEqual(len(selected), 8)
        for job in selected:
            info, candidate, actions = read_pair(
                job["payload"], job["episode"], job["qualification"]
            )
            self.assertEqual(len(actions), len(info.hypotheses))

    def test_wrong_receipt_bytes(self):
        j = calibration()
        j["episode"]["index"] += 1
        with self.assertRaises(InvalidEvidence):
            read_pair(j["payload"], j["episode"], j["qualification"])

    def test_resealed_wrong_case_is_not_same_binding(self):
        j = calibration()
        j["episode"]["case_id"] = "0" * 64
        reseal(j["episode"])
        with self.assertRaises(InvalidEvidence):
            read_pair(j["payload"], j["episode"], j["qualification"])

    def test_resealed_wrong_qualification_identity(self):
        j = calibration()
        j["qualification"]["qualification"]["information_sha256"] = "0" * 64
        reseal(j["qualification"])
        with self.assertRaises(InvalidEvidence):
            read_pair(j["payload"], j["episode"], j["qualification"])

    def test_index_boolean_not_integer(self):
        j = calibration()
        j["payload"]["index"] = False
        with self.assertRaises(InvalidEvidence):
            read_case(j["payload"])

    def test_queue_change_invalidates_information_hash(self):
        j = next(
            j
            for j in cases()
            if j["kind"] == "recorded_episode" and j["payload"]["stratum"] == "timing_bounded_pair"
        )
        j["payload"]["information"]["queue"][0] = ["1/100", "0"]
        with self.assertRaises(InvalidEvidence):
            read_pair(j["payload"], j["episode"], j["qualification"])

    def test_wrong_witness_index_not_silently_reordered(self):
        j = calibration()
        j["qualification"]["qualification"]["hypotheses"].reverse()
        j["episode"]["qualification"] = deepcopy(j["qualification"]["qualification"])
        reseal(j["qualification"])
        reseal(j["episode"])
        with self.assertRaises(InvalidEvidence):
            read_pair(j["payload"], j["episode"], j["qualification"])

    def test_nonalibrary_qualification_not_accepted(self):
        j = calibration()
        j["qualification"]["qualification"]["hypotheses"][0]["witness_action"] = ["1/1000", "0"]
        j["episode"]["qualification"] = deepcopy(j["qualification"]["qualification"])
        reseal(j["qualification"])
        reseal(j["episode"])
        with self.assertRaises(InvalidEvidence):
            read_pair(j["payload"], j["episode"], j["qualification"])

    def test_unsafe_archive_paths(self):
        for name in ("../x", "/x", "a//b", "a/../b", "a/./b", "a\0b", "", "."):
            with self.assertRaises(ValueError):
                safe_name(name)

    def test_duplicate_raw_member_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "data.jsonl"
            entry = json.dumps({"path": "x.json", "raw_utf8": "{}"}) + "\n"
            path.write_text(entry * 2)
            with self.assertRaises(ValueError):
                raw_records(path)

    def test_empty_locks_are_preserved_not_parsed_as_json(self):
        import hashlib

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "data.jsonl"
            path.write_text(json.dumps({"path": ".lock", "raw_utf8": ""}) + "\n")
            self.assertEqual(
                raw_records(path, {".lock": hashlib.sha256(b"").hexdigest()}), {".lock": b""}
            )

    def test_raw_member_modified_without_trusted_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "data.jsonl"
            path.write_text(json.dumps({"path": "x", "raw_utf8": "changed"}) + "\n")
            with self.assertRaises(ValueError):
                raw_records(path, {"x": "0" * 64})

    def test_unknown_metadata_fields_rejected(self):
        j = calibration()
        j["payload"]["extra"] = "not in original schema"
        with self.assertRaises(ValueError):
            read_case(j["payload"])


class RunnerTests(unittest.TestCase):
    def test_real_worker_checkpoint_and_readonly_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / "audit"
            jobs = [example(), calibration()]
            first = run_jobs(jobs, SETTINGS, out, "test-id", max_new=1)
            self.assertEqual(first["completed"], 1)
            self.assertFalse(first["complete"])
            old = {p.name: p.read_bytes() for p in (out / "receipts").iterdir()}
            final = run_jobs(jobs, SETTINGS, out, "test-id", resume=True)
            self.assertTrue(final["complete"])
            self.assertEqual(final["new_jobs"], 1)
            for name, raw in old.items():
                self.assertEqual((out / "receipts" / name).read_bytes(), raw)
            self.assertEqual(run_jobs(jobs, SETTINGS, out, "test-id", resume=True)["new_jobs"], 0)

    def test_started_missing_job_is_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / "audit"
            job = example()
            run_jobs([job], SETTINGS, out, "id", max_new=0)
            binding = {"audit_id": "id", "job_sha256": identity(job), "key": job["key"]}
            write_new(out / "started" / (job["key"] + ".json"), {"binding": binding})
            with patch(
                "independent_hcw_audit_v1.runner.subprocess.run",
                side_effect=AssertionError("MUST NOT RETRY"),
            ):
                result = run_jobs([job], SETTINGS, out, "id", resume=True)
            self.assertEqual(result["statuses"], {"audit_interrupted": 1})

    def test_existing_result_alteration_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / "audit"
            job = example()
            run_jobs([job], SETTINGS, out, "id")
            file = next((out / "receipts").iterdir())
            row = strict_json(file.read_bytes())
            row["result"]["claim"]["status"] = "fake"
            file.write_text(json.dumps(row))
            with self.assertRaises(ValueError):
                run_jobs([job], SETTINGS, out, "id", resume=True)

    def test_wrong_header_or_resource_limit_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / "audit"
            job = example()
            run_jobs([job], SETTINGS, out, "id", max_new=0)
            with self.assertRaises(ValueError):
                run_jobs([job], SETTINGS, out, "id", resume=True, job_timeout_s=100)
            with self.assertRaises(ValueError):
                run_jobs([job], SETTINGS, out, "new-id", resume=True)

    def test_timeout_retained_without_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / "audit"
            with patch(
                "independent_hcw_audit_v1.runner.subprocess.run",
                side_effect=subprocess.TimeoutExpired("fixture", 30),
            ):
                result = run_jobs([example()], SETTINGS, out, "id")
            self.assertEqual(result["statuses"], {"audit_timeout": 1})
            with patch(
                "independent_hcw_audit_v1.runner.subprocess.run",
                side_effect=AssertionError("MUST NOT RETRY"),
            ):
                self.assertEqual(
                    run_jobs([example()], SETTINGS, out, "id", resume=True)["new_jobs"], 0
                )

    def test_worker_failure_not_scientific_obstruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch(
                "independent_hcw_audit_v1.runner.subprocess.run",
                return_value=subprocess.CompletedProcess("fixture", 2),
            ):
                result = run_jobs([example()], SETTINGS, Path(tmp).resolve() / "audit", "id")
            self.assertEqual(result["statuses"], {"audit_execution_failure": 1})

    def test_duplicate_jobs_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                run_jobs([example(), example()], SETTINGS, Path(tmp).resolve() / "audit", "id")

    def test_git_evidence_output_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / ".git").mkdir()
            with self.assertRaises(ValueError):
                run_jobs([example()], SETTINGS, root / "audit", "id")

    def test_changed_freeze_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "freeze.json"
            doc = {"auditor_source_sha256": {}, "protocol": {"workers": 1}}
            doc["audit_id"] = identity(doc)
            path.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                verify_freeze(path, doc["audit_id"])
            with self.assertRaises(ValueError):
                verify_freeze(path, "0" * 64)

    def test_changed_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp).resolve() / "freeze.json"
            doc = {"auditor_source_sha256": {"hcw.py": "0" * 64}, "protocol": {"workers": 1}}
            doc["audit_id"] = identity(doc)
            path.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                verify_freeze(path, doc["audit_id"])


if __name__ == "__main__":
    unittest.main()
