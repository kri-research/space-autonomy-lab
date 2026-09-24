"""Independent known-answer and adversarial tests; all dependencies are stdlib."""

from pathlib import Path
from fractions import Fraction as Q
from dataclasses import replace
from itertools import product
import json
import unittest
from independent_hcw_audit_v1.arithmetic import Interval, SCALE, dot, mm
from independent_hcw_audit_v1.hcw import N, maps, response, advance, state_range, validate_segments
from independent_hcw_audit_v1.schema import read_info, identity, strict_json, InvalidEvidence
from independent_hcw_audit_v1.certificates import (
    check_prefix,
    check_obstruction,
    geometry,
    halfspaces_valid,
    labels,
    necessary_row,
    residual_certificate,
    trajectory_witness,
    schedule,
    audit_claim,
)

ROOT = Path(__file__).resolve().parents[1]


def jobs():
    return json.loads((ROOT / "development_cases.json").read_text())


def named(key):
    return next(x for x in jobs() if x["key"] == key)


def point_info(state=(0, -50, 0, 0), **changes):
    doc = named("named-midpoint_known")["information"]
    doc["hypotheses"] = [{"lower": list(map(str, state)), "upper": list(map(str, state))}]
    doc.update(changes)
    return read_info(doc)


def oracle(t, n=N):
    """Independent augmented matrix exponential with rational norm tail.

    This TEST oracle is not used by the auditor. A direct matrix-power series
    for the ODE gives the four-state/constant-forcing map. The infinity-norm
    tail is bounded geometrically beyond order80, not by trig identities.
    """
    t = Q(t)
    n = Q(n)
    A = [[Q(0) for _ in range(6)] for _ in range(6)]
    A[0][2] = A[1][3] = Q(1)
    A[2][0] = 3 * n * n
    A[2][3] = 2 * n
    A[3][2] = -2 * n
    A[2][4] = A[3][5] = Q(1)
    X = [[v * t for v in row] for row in A]
    M = [[Q(i == j) for j in range(6)] for i in range(6)]
    T = [row[:] for row in M]
    for k in range(1, 81):
        T = [
            [sum((T[i][q] * X[q][j] for q in range(6) if X[q][j]), Q(0)) / k for j in range(6)]
            for i in range(6)
        ]
        M = [
            [a + b for a, b in zip(row, term, strict=True)] for row, term in zip(M, T, strict=True)
        ]
    norm = max(sum(abs(x) for x in row) for row in X)
    from math import factorial

    tail = norm**81 / Q(factorial(81)) / (1 - norm / Q(82))
    return [[Interval.bounds(v - tail, v + tail) for v in row] for row in M[:4]]


class ArithmeticTests(unittest.TestCase):
    def test_exact_arithmetic_hulls(self):
        for a, b, c, d in [
            (-2, 3, -4, 5),
            (Q(1, 3), Q(2, 3), Q(1, 7), Q(4, 7)),
            (-8, -1, 2, 7),
            (0, 0, 3, 3),
        ]:
            a, b, c, d = map(Q, (a, b, c, d))
            x, y = Interval.bounds(a, b), Interval.bounds(c, d)
            for p, q in product((a, (a + b) / 2, b), (c, (c + d) / 2, d)):
                self.assertTrue((x + y).contains(p + q))
                self.assertTrue((x * y).contains(p * q))
                if not c <= 0 <= d:
                    self.assertTrue((x / y).contains(p / q))

    def test_square_across_zero(self):
        x = Interval.bounds(-2, 3).square()
        self.assertEqual(x.lower, 0)
        self.assertEqual(x.upper, 9)

    def test_division_zero_rejected(self):
        with self.assertRaises(ZeroDivisionError):
            Interval.value(1) / Interval.bounds(-1, 1)

    def test_inverted_interval_rejected(self):
        with self.assertRaises(ValueError):
            Interval.bounds(2, 1)

    def test_boolean_rejected(self):
        with self.assertRaises(ValueError):
            Interval.value(True)

    def test_subresolution_bounds_are_outward(self):
        x = Q(1, 3 * SCALE)
        self.assertTrue(Interval.value(x).contains(x))
        self.assertGreater(Interval.value(x).upper, 0)

    def test_dot_dimension_not_silently_truncated(self):
        with self.assertRaises(ValueError):
            dot((1, 2), (3,))


class MapTests(unittest.TestCase):
    def test_exact_represented_mean_motion(self):
        self.assertEqual(N, Q(0.0011313666536110223))
        self.assertNotEqual(N, Q("0.0011313666536110223"))

    def test_zero_time_is_identity(self):
        a, b = maps(0, 0)
        for i in range(4):
            for j in range(4):
                self.assertEqual(a[i][j], Interval.value(int(i == j)))
            for j in range(2):
                self.assertEqual(b[i][j], Interval.value(0))

    def test_zero_mean_motion_double_integrator(self):
        for t in (Q(0), Q(1, 7), Q(3)):
            y = advance(
                tuple(map(Interval.value, (1, 2, 3, 4))), (Q(1, 100), Q(-1, 100)), t, n=Q(0)
            )
            expected = (
                1 + 3 * t + t * t / Q(200),
                2 + 4 * t - t * t / Q(200),
                3 + t / Q(100),
                4 - t / Q(100),
            )
            self.assertTrue(all(z.contains(v) for z, v in zip(y, expected, strict=True)))

    def test_all_state_input_coefficients_independent_ode_oracle(self):
        for t, n in [(Q(1, 8), N), (Q(1), N), (Q(3), N), (Q(3), Q(1, 100)), (Q(1, 2), Q(0))]:
            a, b = maps(t, t, n)
            ref = oracle(t, n)
            for i in range(4):
                for j, x in enumerate((*a[i], *b[i])):
                    self.assertTrue(x.overlaps(ref[i][j]), (t, n, i, j))

    def test_time_intervals_enclose_point_oracle(self):
        a, b = maps(Q(1, 5), Q(3))
        for t in (Q(1, 5), Q(1), Q(2), Q(3)):
            ref = oracle(t)
            for i in range(4):
                for j, x in enumerate((*a[i], *b[i])):
                    # The norm-tail oracle encloses structural zeros with a small interval.
                    # Exact zero/one columns need reciprocal containment, not the false
                    # requirement that an exact singleton contain an oracle overapproximation.
                    self.assertTrue(
                        ref[i][j].contains(x) if x.lo == x.hi else x.contains(ref[i][j]), (i, j)
                    )

    def test_semigroup_all_rows(self):
        for a, b in [(Q(1, 7), Q(2, 9)), (Q(1), Q(2))]:
            pa, ga = maps(a, a)
            pb, gb = maps(b, b)
            pc, gc = maps(a + b, a + b)
            p = mm(pb, pa)
            g = tuple(
                tuple(x + y for x, y in zip(row, add, strict=True))
                for row, add in zip(mm(pb, ga), gb, strict=True)
            )
            self.assertTrue(
                all(
                    x.overlaps(y)
                    for X, Y in [(p, pc), (g, gc)]
                    for rx, ry in zip(X, Y, strict=True)
                    for x, y in zip(rx, ry, strict=True)
                )
            )

    def test_unequal_piecewise_inputs_and_velocity(self):
        segs = validate_segments(
            [
                (0, Q(1, 7), (Q(1, 100), 0)),
                (Q(1, 7), Q(7, 9), (0, Q(-1, 100))),
                (Q(7, 9), 3, (Q(-1, 100), Q(1, 100))),
            ]
        )
        initial = tuple(map(Interval.value, (1, -60, Q(1, 10), 0)))
        y = initial
        for a, b, u in segs:
            y = advance(y, u, b - a)
        direct = state_range(initial, segs, 3, 3)
        self.assertTrue(all(x.overlaps(z) for x, z in zip(y, direct, strict=True)))

    def test_unsupported_time_and_series_domain(self):
        for a, b, n in [(0, 4, N), (-1, 1, N), (2, 1, N), (0, 3, Q(1, 10))]:
            with self.assertRaises(ValueError):
                maps(a, b, n)
        with self.assertRaises(ValueError):
            response(Interval.bounds(0, Q(1, 16)), 1)

    def test_schedule_gaps_overlaps(self):
        for seq in [
            [(1, 2, (0, 0))],
            [(0, 1, (0, 0)), (2, 3, (0, 0))],
            [(0, 2, (0, 0)), (1, 3, (0, 0))],
        ]:
            with self.assertRaises(ValueError):
                validate_segments(seq)

    def test_range_cannot_cross_unrepresented_event(self):
        seq = validate_segments([(0, 1, (0, 0)), (1, 2, (0, 0))])
        with self.assertRaises(ValueError):
            state_range(tuple(map(Interval.value, (0, -50, 0, 0))), seq, 0, 2)


class CertificateTests(unittest.TestCase):
    def test_all_supplied_pairwise_commands(self):
        for suffix in ("01", "02", "12"):
            job = named("pair-three_face_pair_" + suffix)
            info = read_info(job["information"])
            self.assertEqual(audit_claim(info, job["candidate"])["status"], "verified_prefix")

    def test_original_saved_triple_dual(self):
        job = named("named-three_face_conflict")
        r = check_obstruction(read_info(job["information"]), job["candidate"]["negative"])
        self.assertEqual(r["status"], "verified_obstruction")
        self.assertGreater(Q(r["independent_dual"]["margin_lower"]), 0)

    def test_reference_simple_weights(self):
        job = named("named-three_face_conflict")
        info = read_info(job["information"])
        lab = list(labels(info))
        target = [
            ((Q(0), Q(-1)), (Q(0), Q("-99.99905"), Q(0), Q("-.001")), Q(1, 11)),
            ((Q(1), Q(1, 10)), (Q("7.99905"), Q(-80), Q(".001"), Q(0)), Q(5, 11)),
            ((Q(-1), Q(1, 10)), (Q("-7.99905"), Q(-80), Q("-.001"), Q(0)), Q(5, 11)),
        ]
        chosen = []
        for normal, state, w in target:
            label = next(
                x
                for x in lab
                if x.get("time_after_application") == "1"
                and tuple(map(Q, x["normal"])) == normal
                and tuple(map(Q, x["origin"])) == state
            )
            row, rhs = necessary_row(info, label)
            chosen.append((row, rhs, w))
        result = residual_certificate(
            [x[0] for x in chosen], [x[1] for x in chosen], [x[2] for x in chosen], info.authority
        )
        self.assertTrue(result["proved"])
        self.assertAlmostEqual(float(Q(result["margin_lower"])), 6.396160160886677e-5, places=15)

    def test_exact_closed_boundaries_and_stationary_tangent(self):
        for state in [(0, -27, 0, 0), (0, -100, 0, 0), (3, -30, 0, 0)]:
            info = point_info(state)
            self.assertEqual(check_prefix(info, (0, 0), n=Q(0))["status"], "verified_prefix")

    def test_nonconvex_relaxation_is_not_safety(self):
        info = point_info((Q("2.9"), -29, 0, 0))
        self.assertTrue(halfspaces_valid())
        self.assertEqual(check_prefix(info, (0, 0))["status"], "contradicted_prefix")

    def test_corridor_to_ellipse_overlap_is_allowed(self):
        info = point_info((Q("2.2"), Q("-30.5"), Q("-.6"), Q(1)))
        self.assertEqual(check_prefix(info, (0, 0), n=Q(0))["status"], "verified_prefix")

    def test_narrow_between_endpoint_excursion(self):
        y = Q(-27) - Q(1, 4000) + Q(1, 10**10)
        info = point_info((0, y, 0, Q(1, 1000)))
        result = check_prefix(info, (0, Q(-1, 500)), n=Q(0))
        self.assertEqual(result["status"], "contradicted_prefix")
        self.assertTrue(result["witness"]["proved"])
        for t in (0, 1):
            self.assertEqual(
                geometry(
                    state_range(
                        info.hypotheses[0].intervals(),
                        schedule(info, (0, Q(-1, 500))),
                        Q(t),
                        Q(t),
                        n=Q(0),
                    )
                ),
                "contained",
            )

    def test_whole_box_not_only_center(self):
        info = point_info()
        doc = info.payload()
        doc["hypotheses"][0]["upper"][1] = "-26"
        info = read_info(doc)
        self.assertEqual(check_prefix(info, (0, 0))["status"], "contradicted_prefix")

    def test_delayed_command_cannot_repair_queue(self):
        info = point_info(
            (0, Q("-27.001"), 0, Q(".01")), age=1, delay=1, queue=[["0", "0"], ["0", "0"]]
        )
        self.assertEqual(check_prefix(info, (0, Q("-.02")))["status"], "contradicted_prefix")

    def test_independent_segment_uncertainties_not_single_constant(self):
        info = point_info(
            (0, -50, 0, 0),
            age=1,
            delay=1,
            queue=[["0", "0"], ["0", "0"]],
            disturbance="1/100000",
            effectiveness=["0", "1"],
        )
        seq = schedule(info, (Q(1, 100), 0))
        self.assertEqual(len(seq), 12)
        realizations = [
            (Q(j % 2), (Q((-1) ** j, 100000), Q((-1) ** (j + 1), 100000))) for j in range(12)
        ]
        pointseq = schedule(info, (Q(1, 100), 0), realizations)
        for (a, b, big), (c, d, small) in zip(seq, pointseq, strict=True):
            self.assertTrue(all(x.contains(y) for x, y in zip(big, small, strict=True)))
        self.assertEqual(check_prefix(info, (Q(1, 100), 0))["status"], "verified_prefix")

    def test_zero_effectiveness(self):
        info = point_info((0, -27, 0, Q("0.001")), effectiveness=["0", "0"])
        self.assertEqual(
            check_prefix(info, (0, Q("-.02")), n=Q(0))["status"], "contradicted_prefix"
        )

    def test_exact_authority(self):
        info = point_info()
        self.assertEqual(check_prefix(info, (Q(1, 50), 0))["status"], "verified_prefix")
        with self.assertRaises(InvalidEvidence):
            check_prefix(info, (Q(1, 50), Q(1, 10**30)))

    def test_unresolved_is_not_refutation(self):
        info = point_info((Q("2.9"), -29, 0, 0))
        r = check_prefix(info, (0, 0), max_cells=1, seek_witness=False)
        self.assertEqual(r["status"], "numerically_unresolved")
        self.assertIsNone(r["witness"])

    def test_fake_witness_outside_original_box_rejected(self):
        info = point_info()
        w = {
            "origin": ["0", "-20", "0", "0"],
            "time_s": "1",
            "realizations": [{"effectiveness": "1", "disturbance": ["0", "0"]}] * 4,
        }
        with self.assertRaises(InvalidEvidence):
            trajectory_witness(info, (0, 0), w)

    def test_nonzero_residual_prevents_false_obstruction(self):
        r = residual_certificate(
            [(Interval.value(1), Interval.value(0))], [Interval.value(Q("-0.01"))], [1], Q(".02")
        )
        self.assertFalse(r["proved"])

    def test_tiny_positive_margin_and_row_rescaling(self):
        epsilon = Q(1, 10**40)
        rows = [(Interval.value(1), Interval.value(0)), (Interval.value(-1), Interval.value(0))]
        rhs = [Interval.value(-epsilon), Interval.value(-epsilon)]
        result = residual_certificate(rows, rhs, [Q(1, 2), Q(1, 2)], Q(".02"))
        self.assertTrue(result["proved"])
        scales = (Q(3, 7), Q(5, 2))
        result2 = residual_certificate(
            [tuple(v * s for v in row) for row, s in zip(rows, scales, strict=True)],
            [v * s for v, s in zip(rhs, scales, strict=True)],
            [Q(1, 2) / s for s in scales],
            Q(".02"),
        )
        self.assertTrue(result2["proved"])

    def test_wrong_dual_and_row_correspondence(self):
        job = named("named-three_face_conflict")
        info = read_info(job["information"])
        for kind in ("negative", "zero", "swap", "hypothesis", "model"):
            c = json.loads(json.dumps(job["candidate"]["negative"]))
            if kind == "negative":
                c["weights"][0] = "-1"
            if kind == "zero":
                c["weights"] = ["0"] * len(c["weights"])
            if kind == "swap":
                c["weights"] = list(reversed(c["weights"]))
            if kind == "hypothesis":
                c["information_sha256"] = "0" * 64
            if kind == "model":
                c["model"] = "nonlinear"
            candidate = {**job["candidate"], "negative": c}
            self.assertIn(
                audit_claim(info, candidate)["status"],
                ("binding_invalid_evidence", "unsupported_assumptions"),
            )

    def test_saved_margin_is_not_trusted(self):
        job = named("named-three_face_conflict")
        info = read_info(job["information"])
        c = job["candidate"]["negative"]
        c["checked"] = {"margin_lower": "-1000000", "proved": False}
        self.assertEqual(check_obstruction(info, c)["status"], "verified_obstruction")

    def test_positive_monotonicity_and_binding_distinct(self):
        info = point_info()
        doc = info.payload()
        doc["hypotheses"][0] = {
            "lower": ["-1", "-51", "-1/100", "-1/100"],
            "upper": ["1", "-49", "1/100", "1/100"],
        }
        big = read_info(doc)
        self.assertTrue(
            all(
                a <= c <= d <= b
                for a, b, c, d in zip(
                    big.hypotheses[0].lower,
                    big.hypotheses[0].upper,
                    info.hypotheses[0].lower,
                    info.hypotheses[0].upper,
                    strict=True,
                )
            )
        )
        self.assertEqual(check_prefix(big, (0, 0))["status"], "verified_prefix")
        self.assertEqual(check_prefix(info, (0, 0))["status"], "verified_prefix")
        self.assertNotEqual(info.identity(), big.identity())

    def test_obstruction_monotonicity_uses_attainable_witness_inclusion(self):
        job = named("named-three_face_conflict")
        info = read_info(job["information"])
        c = job["candidate"]["negative"]
        bigger = replace(info, hypotheses=info.hypotheses + (point_info().hypotheses[0],))
        lab = list(labels(info))
        weights = list(map(Q, c["weights"]))
        selected = [(x, w) for x, w in zip(lab, weights, strict=True) if w]
        for x, w in selected:
            self.assertTrue(any(h.contains(tuple(map(Q, x["origin"]))) for h in bigger.hypotheses))
        rows = [necessary_row(bigger, x) for x, w in selected]
        self.assertTrue(
            residual_certificate(
                [a for a, b in rows], [b for a, b in rows], [w for x, w in selected], info.authority
            )["proved"]
        )
        with self.assertRaises(InvalidEvidence):
            check_obstruction(bigger, c)

    def test_outer_information_never_becomes_attainable(self):
        job = named("named-three_face_conflict")
        info = replace(read_info(job["information"]), kind="outer_enclosure_only")
        self.assertEqual(
            check_obstruction(info, job["candidate"]["negative"])["status"],
            "unsupported_assumptions",
        )

    def test_original_late_and_unknown_are_retained(self):
        for status in ("unresolved", "unresolved_budget"):
            c = {
                "status": status,
                "action": None,
                "deadline_exceeded": status == "unresolved_budget",
                "wall_s": 2 if status == "unresolved_budget" else 1,
            }
            self.assertEqual(audit_claim(point_info(), c)["status"], "no_on_time_certificate")


class SchemaTests(unittest.TestCase):
    def test_exact_payload_identity(self):
        for j in jobs():
            doc = j.get("information", j.get("payload", {}).get("information"))
            info = read_info(doc)
            self.assertEqual(identity(doc), info.identity())

    def test_malformed_numeric_json(self):
        for raw in (
            '{"x":NaN}',
            '{"x":Infinity}',
            '{"x":1e999}',
            '{"x":1,"x":2}',
            "not json",
            "[" * 70 + "0" + "]" * 70,
        ):
            with self.assertRaises(ValueError):
                strict_json(raw)

    def test_wrong_units_order_and_period(self):
        for field, value in [
            ("units", ["m/s", "m", "m", "m/s"]),
            ("command_period_s", True),
            ("age", True),
            ("delay", -1),
            ("observation_pattern", "earlier measurement"),
            ("authority", True),
            ("disturbance", "nan"),
            ("queue", [["0", "0"]]),
        ]:
            doc = point_info().payload()
            doc[field] = value
            with self.assertRaises(ValueError):
                read_info(doc)

    def test_reversed_or_incomplete_box(self):
        for shape in (
            {"lower": ["1"] * 4, "upper": ["0"] * 4},
            {"lower": ["0"] * 3, "upper": ["1"] * 4},
        ):
            doc = point_info().payload()
            doc["hypotheses"] = [shape]
            with self.assertRaises(ValueError):
                read_info(doc)

    def test_extra_unrecognized_information(self):
        doc = point_info().payload()
        doc["model"] = "nonlinear"
        with self.assertRaises(ValueError):
            read_info(doc)

    def test_changed_queue_cannot_reuse_certificate(self):
        job = named("named-three_face_conflict")
        info = read_info(job["information"])
        info = replace(info, age=1, queue=((Q(0), Q(0)),))
        self.assertEqual(audit_claim(info, job["candidate"])["status"], "binding_invalid_evidence")

    def test_covariance_only_is_unsupported(self):
        info = replace(point_info(), kind="covariance_only")
        self.assertEqual(check_prefix(info, (0, 0))["status"], "unsupported_assumptions")

    def test_inconsistent_positive_command(self):
        job = named("pair-three_face_pair_01")
        job["candidate"]["action"] = ["0", "0"]
        self.assertEqual(
            audit_claim(read_info(job["information"]), job["candidate"])["status"],
            "binding_invalid_evidence",
        )


if __name__ == "__main__":
    unittest.main()
