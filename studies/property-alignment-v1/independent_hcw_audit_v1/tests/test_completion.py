"""Pre-freeze independent-oracle, protocol and real process-failure tests."""

from copy import deepcopy
from fractions import Fraction as Q
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from independent_hcw_audit_v1.arithmetic import Interval, mv, rational
from independent_hcw_audit_v1.hcw import N, state_range, validate_segments
from independent_hcw_audit_v1.certificates import audit_claim, labels, geometry
from independent_hcw_audit_v1.schema import exact, identity, read_info
from independent_hcw_audit_v1.protocol import (
    SETTINGS,
    ORIGINAL_FILES,
    SCIENTIFIC_COMMIT,
    ROOT,
    source_inventory,
    validate_document,
)
from independent_hcw_audit_v1.runner import run_jobs
from independent_hcw_audit_v1.worker import DependencyBoundary
from independent_hcw_audit_v1.tests.test_core import oracle, point_info, named

NUMERICAL = SETTINGS["numerical"]


def candidate():
    return named("named-midpoint_known")


def document():
    d = {
        "schema": "sal-independent-hcw-audit-freeze/1",
        "post_hoc": True,
        "full_campaign_executed": False,
        "python_version": "3.13.5",
        "implementation_commit": "a" * 40,
        "scientific_source_commit": SCIENTIFIC_COMMIT,
        "auditor_source_sha256": source_inventory(),
        "protocol": deepcopy(SETTINGS),
        "original_files_sha256": {n: "0" * 64 for n in ORIGINAL_FILES},
        "case_bindings": [
            {
                "key": f"test-{i}",
                "input_sha256": "0" * 64,
                "episode_sha256": "0" * 64,
                "qualification_sha256": "0" * 64,
            }
            for i in range(768)
        ],
    }
    d["audit_id"] = identity(d)
    return d


class CompletionTests(unittest.TestCase):
    def test_large_exponents_rejected_before_fraction_expansion(self):
        for v in ("1e999999999", "1e-999999999", "+1e99999", "1_000", "1/0", "--2"):
            with self.assertRaises(ValueError):
                exact(v)
            with self.assertRaises(ValueError):
                rational(v)

    def test_noncanonical_rational_evidence_rejected(self):
        for v in ("01", "+1", "1.0", "-0", "2/4", " 1", "1/1"):
            with self.assertRaises(ValueError):
                exact(v)
        self.assertEqual(exact("-1/200"), Q(-1, 200))

    def test_inconsistent_old_timing_flags_rejected(self):
        info = point_info()
        for status, wall, flag in [
            ("unresolved", 2, False),
            ("unresolved_budget", 0.1, True),
            ("unresolved", 0.1, True),
            ("unresolved_budget", 2, False),
        ]:
            c = {"status": status, "wall_s": wall, "deadline_exceeded": flag, "action": None}
            self.assertEqual(audit_claim(info, c)["status"], "binding_invalid_evidence")

    def test_unknown_not_reclassified_from_nested_late_proof(self):
        j = candidate()
        c = deepcopy(j["candidate"])
        c.update(status="unresolved_budget", wall_s=2, deadline_exceeded=True, action=None)
        self.assertEqual(
            audit_claim(read_info(j["information"]), c)["status"], "no_on_time_certificate"
        )

    def test_committed_contract_matches_implemented_exact_constants(self):
        from independent_hcw_audit_v1.arithmetic import BITS
        from independent_hcw_audit_v1.hcw import SERIES_TERMS, MAX_TIME, MAX_ARGUMENT

        c = json.loads((ROOT / "contract.json").read_text())
        self.assertEqual(Q(c["mean_motion_exact"]), N)
        self.assertEqual(c["numerical"]["dyadic_fraction_bits"], BITS)
        self.assertEqual(c["numerical"]["series_terms"], SERIES_TERMS)
        self.assertEqual(Q(c["numerical"]["maximum_duration_s"]), MAX_TIME)
        self.assertEqual(Q(c["numerical"]["maximum_abs_nt"]), MAX_ARGUMENT)

    def test_independent_augmented_oracle_for_unequal_queues(self):
        seq = validate_segments(
            [
                (0, Q(1, 7), (Q(1, 100), Q(-1, 200))),
                (Q(1, 7), Q(3, 5), (Q(-1, 100), Q(1, 200))),
                (Q(3, 5), 3, (Q(1, 1000), Q(-1, 1000))),
            ]
        )
        initial = tuple(map(Interval.value, (1, -70, Q(1, 100), Q(-1, 50))))
        value = initial
        for a, b, u in seq:
            # This oracle uses matrix powers of the differential equations,
            # not the closed-form coefficient functions used in the auditor.
            value = mv(oracle(b - a), (*value, *u))
        result = state_range(initial, seq, Q(3), Q(3))
        for a, b in zip(value, result, strict=True):
            self.assertTrue(a.overlaps(b))

    def test_negative_row_order_has_actual_vertex_cap(self):
        d = point_info().payload()
        d["hypotheses"] = [
            {
                "lower": [str(i), "-70", "-1/100", "-1/100"],
                "upper": [str(i + 1), "-69", "1/100", "1/100"],
            }
            for i in range(10)
        ]
        d["effectiveness"] = ["0", "1"]
        d["disturbance"] = "1/100000"
        info = read_info(d)
        ls = list(labels(info))
        self.assertEqual(len(ls), 64 * 2 * 4 * 2 * 6 + 4)
        expected = sorted({x for h in info.hypotheses for x in h.vertices()})[:64]
        got = sorted({tuple(map(Q, x["origin"])) for x in ls[:-4]})
        self.assertEqual(got, expected)
        self.assertEqual(
            ls[-4:],
            [{"outer_actuator_box_coordinate": j, "sign": s} for j in range(2) for s in (-1, 1)],
        )

    def test_union_enclosure_can_be_unresolved_without_false_refutation(self):
        box = (
            Interval.bounds(Q("1.8"), Q("2.2")),
            Interval.bounds(Q("-30.5"), Q("-29.5")),
            Interval.value(0),
            Interval.value(0),
        )
        self.assertEqual(geometry(box), "unresolved")

    def test_narrow_excursion_between_every_quarter_second_sample(self):
        from independent_hcw_audit_v1.certificates import check_prefix, trajectory_witness, schedule

        center = Q(1, 3)
        accel = Q(1, 500)
        epsilon = Q(1, 10**10)
        info = point_info((0, Q(-27) - accel * center**2 / 2 + epsilon, 0, accel * center))
        u = (Q(0), -accel)
        seq = schedule(info, u)
        for t in (Q(k, 4) for k in range(5)):
            self.assertEqual(
                geometry(state_range(info.hypotheses[0].intervals(), seq, t, t, n=Q(0))),
                "contained",
            )
        # Continuous validation must not certify the grid-invisible excursion.
        self.assertNotEqual(check_prefix(info, u, n=Q(0))["status"], "verified_prefix")
        witness = {
            "origin": list(map(str, info.hypotheses[0].lower)),
            "time_s": str(center),
            "realizations": [{"effectiveness": "1", "disturbance": ["0", "0"]} for _ in range(4)],
        }
        self.assertTrue(trajectory_witness(info, u, witness, n=Q(0))["proved"])

    def test_source_boundary_blocks_original_module_before_import(self):
        b = DependencyBoundary()
        for name in ("candidate.affine", "adjudication.flow", "protective", "numpy", "scipy"):
            with self.assertRaises(ModuleNotFoundError):
                b.find_spec(name)
        self.assertIsNone(b.find_spec("fractions"))
        self.assertIsNone(b.find_spec("independent_hcw_audit_v1.hcw"))

    def test_valid_freeze_structure_before_corruption(self):
        d = document()
        self.assertEqual(validate_document(d, d["audit_id"]), d)
        # Structural validation alone does not authenticate these synthetic
        # hashes; the real build/runner separately binds the full raw dataset.

    def test_changed_precision_rejected_even_with_new_self_hash(self):
        d = document()
        d["protocol"]["precision_bits"] = 53
        d["audit_id"] = identity({k: v for k, v in d.items() if k != "audit_id"})
        with self.assertRaises(ValueError):
            validate_document(d, d["audit_id"])

    def test_changed_runtime_rejected(self):
        d = document()
        d["python_version"] = "3.14.0"
        d["audit_id"] = identity({k: v for k, v in d.items() if k != "audit_id"})
        with self.assertRaises(ValueError):
            validate_document(d, d["audit_id"])

    def test_changed_actual_core_source_digest_rejected(self):
        d = document()
        d["auditor_source_sha256"]["hcw.py"] = "0" * 64
        d["audit_id"] = identity({k: v for k, v in d.items() if k != "audit_id"})
        with self.assertRaises(ValueError):
            validate_document(d, d["audit_id"])

    def test_old_trusted_audit_id_rejects_changed_input_binding(self):
        d = document()
        old = d["audit_id"]
        d["case_bindings"][0]["input_sha256"] = "1" * 64
        d["audit_id"] = identity({k: v for k, v in d.items() if k != "audit_id"})
        with self.assertRaises(ValueError):
            validate_document(d, old)

    def test_full_campaign_cli_requires_separate_authorization(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp).resolve() / "must-not-exist"
            cp = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    "-B",
                    "-m",
                    "independent_hcw_audit_v1.runner",
                    "--freeze",
                    str(output / "absent.json"),
                    "--audit-id",
                    "0" * 64,
                    "--output",
                    str(output),
                ],
                cwd=ROOT.parent,
                capture_output=True,
                text=True,
                timeout=5,
            )
            self.assertNotEqual(cp.returncode, 0)
            self.assertIn("requires explicit R03 execution", cp.stderr)
            self.assertFalse(output.exists())

    def test_real_child_timeout_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            fake = base / "worker-source"
            fake.mkdir()
            (fake / "worker.py").write_text("import time; time.sleep(30)\n")
            with patch("independent_hcw_audit_v1.runner.ROOT", fake):
                result = run_jobs(
                    [candidate()], NUMERICAL, base / "out", "timeout-fixture", job_timeout_s=0.05
                )
                self.assertEqual(result["statuses"], {"audit_timeout": 1})
                again = run_jobs(
                    [candidate()],
                    NUMERICAL,
                    base / "out",
                    "timeout-fixture",
                    resume=True,
                    job_timeout_s=0.05,
                )
                self.assertEqual(again["new_jobs"], 0)

    def test_real_child_crash_is_not_a_certificate(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            fake = base / "worker-source"
            fake.mkdir()
            (fake / "worker.py").write_text("import os; os._exit(7)\n")
            with patch("independent_hcw_audit_v1.runner.ROOT", fake):
                result = run_jobs([candidate()], NUMERICAL, base / "out", "crash-fixture")
            self.assertEqual(result["statuses"], {"audit_execution_failure": 1})

    def test_actual_malformed_worker_response_not_counted_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp).resolve()
            fake = base / "worker-source"
            fake.mkdir()
            (fake / "worker.py").write_text("print('{broken')\n")
            with patch("independent_hcw_audit_v1.runner.ROOT", fake):
                result = run_jobs([candidate()], NUMERICAL, base / "out", "malformed-fixture")
            self.assertEqual(result["statuses"], {"audit_execution_failure": 1})

    def test_resealed_receipt_cannot_override_actual_worker_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / "run"
            job = candidate()
            run_jobs([job], NUMERICAL, out, "receipt-fixture")
            path = next((out / "receipts").glob("*.json"))
            doc = json.loads(path.read_text())
            doc["result"]["claim"]["status"] = "verified_obstruction"
            doc["receipt_sha256"] = identity(
                {k: v for k, v in doc.items() if k != "receipt_sha256"}
            )
            path.write_text(json.dumps(doc))
            with self.assertRaises(ValueError):
                run_jobs([job], NUMERICAL, out, "receipt-fixture", resume=True)

    def test_worker_stdout_mutation_is_detected_on_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / "run"
            job = candidate()
            run_jobs([job], NUMERICAL, out, "stdout-fixture")
            f = out / "worker-output" / (job["key"] + ".json")
            f.write_bytes(f.read_bytes() + b" ")
            with self.assertRaises(ValueError):
                run_jobs([job], NUMERICAL, out, "stdout-fixture", resume=True)

    def test_nonfinite_watchdog_and_boolean_checkpoint_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp).resolve() / "run"
            for v in (float("inf"), float("nan"), True, -1):
                with self.assertRaises(ValueError):
                    run_jobs([candidate()], NUMERICAL, out, "bad", job_timeout_s=v)
            with self.assertRaises(ValueError):
                run_jobs([candidate()], NUMERICAL, out, "bad", max_new=True)


if __name__ == "__main__":
    unittest.main()
