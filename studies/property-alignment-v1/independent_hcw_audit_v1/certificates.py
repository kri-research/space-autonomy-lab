"""Full-set positive checks and independently rebuilt saved HCW dual certificates.

No original transition map, interval engine, geometry classifier or optimizer is
imported. Stored status labels select a claim to test; they never prove it.
"""

from fractions import Fraction as Q
from itertools import product
from .arithmetic import Interval, dot, mv, rational
from .hcw import N, maps, state_range, validate_segments
from .schema import (
    Info,
    InvalidEvidence,
    UnsupportedAssumption,
    require,
    exact,
    vector,
    positive_binding,
)

NORMALS = (
    (Q(0), Q(-1)),
    (Q(0), Q(1)),
    (Q(1), Q(0)),
    (Q(-1), Q(0)),
    (Q(1), Q(1, 10)),
    (Q(-1), Q(1, 10)),
)
LIMITS = (Q(100), Q(-27), Q(10), Q(10), Q(0), Q(0))


def geometry(box):
    """Three-valued sufficient classification of the CLOSED nonconvex union.

    Both forms use exact integer coefficients to avoid spurious division at exact
    boundaries. 'outside' means every point of the enclosing box is outside.
    A mixed box is unresolved, even if every sampled point appears inside.
    """
    x, y = box[:2]
    corridor = (-100 - y, y + 30, 10 * x + y, -10 * x + y)
    ellipse = 9 * x.square() + 4 * (y + 30).square() - 36
    if all(v.hi <= 0 for v in corridor) or ellipse.hi <= 0:
        return "contained"
    if any(v.lo > 0 for v in corridor) and ellipse.lo > 0:
        return "outside"
    return "unresolved"


def halfspaces_valid():
    """Exact support proofs for all six original necessary positional rows."""
    vertices = ((Q(-10), Q(-100)), (Q(10), Q(-100)), (Q(-3), Q(-30)), (Q(3), Q(-30)))
    for (a, b), limit in zip(NORMALS, LIMITS, strict=True):
        require(max(a * x + b * y for x, y in vertices) <= limit, "Halfspace misses corridor")
        spare = limit + 30 * b
        require(spare >= 0 and (2 * a) ** 2 + (3 * b) ** 2 <= spare**2, "Halfspace misses ellipse")
    return True


def schedule(info, command, realizations=None):
    require(isinstance(info, Info), "Explicit information required")
    require(
        len(command) == 2 and sum(rational(x) ** 2 for x in command) <= info.authority**2,
        "Command authority",
    )
    result = []
    for k, u in enumerate((*info.queue, tuple(command))):
        for j in range(4):
            index = 4 * k + j
            if realizations is None:
                eta = Interval.bounds(*info.effectiveness)
                w = Interval.bounds(-info.disturbance, info.disturbance)
                force = tuple(eta * x + w for x in u)
            else:
                require(len(realizations) == 4 * (info.D + 1), "Realization schedule length")
                e, values = realizations[index]
                e = rational(e)
                values = tuple(map(rational, values))
                require(
                    info.effectiveness[0] <= e <= info.effectiveness[1]
                    and len(values) == 2
                    and all(abs(x) <= info.disturbance for x in values),
                    "Unattainable forcing",
                )
                force = tuple(Interval.value(e * x + d) for x, d in zip(u, values, strict=True))
            a = Q(k) + Q(j, 4)
            result.append((a, a + Q(1, 4), force))
    return validate_segments(result, end=info.D + 1)


def trajectory_witness(info, command, witness, n=N):
    """Validate a REAL initial point and piecewise realization before refutation."""
    require(info.kind == "declared_exact_information_set", "Attainable exact information required")
    require(
        type(witness) is dict and set(witness) == {"origin", "realizations", "time_s"},
        "Witness fields",
    )
    origin = vector(witness["origin"], 4)
    t = exact(witness["time_s"])
    require(any(h.contains(origin) for h in info.hypotheses), "Witness outside original hypotheses")
    require(0 <= t <= info.D + 1, "Witness time outside interval")
    values = witness["realizations"]
    require(type(values) is list, "Witness realizations")
    forcing = []
    for row in values:
        require(
            type(row) is dict and set(row) == {"effectiveness", "disturbance"},
            "Witness forcing fields",
        )
        forcing.append((exact(row["effectiveness"]), vector(row["disturbance"], 2)))
    seq = schedule(info, command, forcing)
    box = state_range(tuple(Interval.value(x) for x in origin), seq, t, t, n)
    return {
        "proved": geometry(box) == "outside",
        "time_s": str(t),
        "state_enclosure": [x.payload() for x in box],
        "witness": witness,
        "scope": "attainable HCW trajectory outside union at a verified time",
    }


def find_witness(info, command, times, n=N, limit=256):
    """Bounded deterministic search on admissible ORIGINAL points only.

    Constant realization sequences are an allowed subset. Failure to find one
    makes no safety claim and does not exhaust all segment-varying disturbances.
    """
    if info.kind != "declared_exact_information_set":
        return None
    origins = sorted(
        {
            x
            for h in info.hypotheses
            for x in (
                *h.vertices(),
                tuple((a + b) / 2 for a, b in zip(h.lower, h.upper, strict=True)),
            )
        }
    )
    ws = sorted(set(product((-info.disturbance, info.disturbance), repeat=2)))
    attempts = 0
    for t in dict.fromkeys(times):
        for origin, eta, w in product(origins, sorted(set(info.effectiveness)), ws):
            if attempts >= limit:
                return None
            attempts += 1
            witness = {
                "origin": list(map(str, origin)),
                "realizations": [
                    {"effectiveness": str(eta), "disturbance": list(map(str, w))}
                    for _ in range(4 * (info.D + 1))
                ],
                "time_s": str(t),
            }
            checked = trajectory_witness(info, command, witness, n)
            if checked["proved"]:
                return {**checked, "attempts": attempts}
    return None


def check_prefix(info, command, *, max_cells=16384, min_width=Q(1, 65536), n=N, seek_witness=True):
    """Sufficient continuous coverage of full initial boxes and all segment inputs."""
    if info.kind == "covariance_only":
        return {
            "status": "unsupported_assumptions",
            "reason": "covariance is not a deterministic information set",
        }
    require(
        type(max_cells) is int and 1 <= max_cells <= 1000000 and 0 < rational(min_width) <= Q(1, 4),
        "Invalid refinement budget",
    )
    command = tuple(map(rational, command))
    seq = schedule(info, command)
    cells = 0
    covered = []
    unknown = []
    for index, h in enumerate(info.hypotheses):
        initial = h.intervals()
        stack = [(a, b) for a, b, _ in reversed(seq)]
        intervals = 0
        while stack:
            a, b = stack.pop()
            if cells >= max_cells:
                unknown.append(
                    {"hypothesis": index, "interval": [str(a), str(b)], "reason": "cell_budget"}
                )
                break
            box = state_range(initial, seq, a, b, n)
            cells += 1
            if geometry(box) == "contained":
                intervals += 1
                continue
            if b - a <= min_width or geometry(box) == "outside":
                unknown.append(
                    {
                        "hypothesis": index,
                        "interval": [str(a), str(b)],
                        "reason": "range_not_contained",
                    }
                )
                break
            mid = (a + b) / 2
            stack.extend(((mid, b), (a, mid)))
        covered.append(
            {
                "hypothesis": index,
                "complete": not stack and not any(x["hypothesis"] == index for x in unknown),
                "continuous_cells": intervals,
            }
        )
        if unknown:
            break
    if not unknown and len(covered) == len(info.hypotheses) and all(x["complete"] for x in covered):
        return {
            "status": "verified_prefix",
            "range_cells": cells,
            "hypotheses": covered,
            "end_s": str(info.D + 1),
            "components": {
                "containment": "verified",
                "collision_free": "implied_by_union",
                "keep_out_free": "implied_by_union",
            },
            "separation_lower_m": "27",
            "full_recovery_claim": False,
        }
    times = []
    for x in unknown:
        a, b = map(Q, x["interval"])
        times.extend((a, (a + b) / 2, b))
    times.extend(b for a, b, u in seq)
    witness = find_witness(info, command, times, n) if seek_witness else None
    return {
        "status": "contradicted_prefix" if witness else "numerically_unresolved",
        "range_cells": cells,
        "incomplete": unknown,
        "witness": witness,
        "full_recovery_claim": False,
    }


def labels(info):
    """Retain ORIGINAL lexicographic vertices, truncation, realizations and row order."""
    require(
        info.kind == "declared_exact_information_set",
        "Negative claims require actual compatible origins",
    )
    origins = sorted({x for h in info.hypotheses for x in h.vertices()})[:64]
    ws = sorted(set(product((-info.disturbance, info.disturbance), repeat=2)))
    for origin, eta, w, t, (normal, bound) in product(
        origins,
        sorted(set(info.effectiveness)),
        ws,
        (Q(1, 2), Q(1)),
        zip(NORMALS, LIMITS, strict=True),
    ):
        yield {
            "origin": list(map(str, origin)),
            "effectiveness": str(eta),
            "disturbance": list(map(str, w)),
            "time_after_application": str(t),
            "normal": list(map(str, normal)),
        }
    for j, sign in product(range(2), (-1, 1)):
        yield {"outer_actuator_box_coordinate": j, "sign": sign}


def necessary_row(info, label, n=N):
    if "outer_actuator_box_coordinate" in label:
        j, sign = label["outer_actuator_box_coordinate"], label["sign"]
        require(
            type(j) is int and j in (0, 1) and type(sign) is int and sign in (-1, 1), "Actuator row"
        )
        return tuple(Interval.value(sign if k == j else 0) for k in range(2)), Interval.value(
            info.authority
        )
    origin = vector(label["origin"], 4)
    eta = exact(label["effectiveness"])
    w = vector(label["disturbance"], 2)
    t = exact(label["time_after_application"])
    normal = vector(label["normal"], 2)
    require(
        any(h.contains(origin) for h in info.hypotheses)
        and info.effectiveness[0] <= eta <= info.effectiveness[1]
        and all(abs(d) <= info.disturbance for d in w),
        "Invalid necessary witness",
    )
    require(t in (Q(1, 2), Q(1)) and normal in NORMALS, "Unknown row/time")
    total = info.D + t
    phi, gamma = maps(total, total, n)
    constant = tuple(a + b for a, b in zip(mv(phi, origin), mv(gamma, w), strict=True))
    # Contributions from known queued commands; the disturbance is constant over
    # the complete trajectory, a valid subset of independent segment realizations.
    for j, u in enumerate(info.queue):
        phi, _ = maps(total - j - 1, total - j - 1, n)
        _, one = maps(1, 1, n)
        contribution = mv(phi, mv(one, tuple(eta * v for v in u)))
        constant = tuple(a + b for a, b in zip(constant, contribution, strict=True))
    _, held = maps(t, t, n)
    row = tuple(dot(normal, tuple(held[i][j] for i in range(2))) * eta for j in range(2))
    rhs = Interval.value(LIMITS[NORMALS.index(normal)]) - dot(normal, constant[:2])
    return row, rhs


def residual_certificate(rows, rhs, weights, authority):
    require(len(rows) == len(rhs) == len(weights) and bool(rows), "Certificate dimensions")
    weights = tuple(map(rational, weights))
    U = rational(authority)
    require(
        U >= 0 and all(w >= 0 for w in weights) and any(weights),
        "Nonnegative nonzero dual required",
    )
    require(all(len(row) == 2 for row in rows), "Two command columns required")
    upper = sum(w * b.upper for w, b in zip(weights, rhs, strict=True))
    res = []
    for j in range(2):
        lo = sum(w * row[j].lower for w, row in zip(weights, rows, strict=True))
        hi = sum(w * row[j].upper for w, row in zip(weights, rows, strict=True))
        res.append(max(abs(lo), abs(hi)))
    delta = -upper - U * sum(res)
    return {
        "proved": delta > 0,
        "margin_lower": str(delta),
        "rhs_upper": str(upper),
        "residual_upper": list(map(str, res)),
    }


def check_obstruction(info, certificate, *, n=N):
    if info.kind != "declared_exact_information_set":
        return {
            "status": "unsupported_assumptions",
            "reason": "negative witness attainability not established",
        }
    require(
        type(certificate) is dict and certificate.get("status") == "proved_no_common_held_command",
        "Negative certificate kind",
    )
    if certificate.get("model") != "hcw":
        raise UnsupportedAssumption("HCW negative certificate only")
    require(certificate.get("information_sha256") == info.identity(), "Wrong information identity")
    halfspaces_valid()
    all_labels = list(labels(info))
    raw = certificate.get("weights")
    require(type(raw) is list and len(raw) == len(all_labels), "Saved dual row enumeration differs")
    weights = tuple(exact(x) for x in raw)
    require(all(x >= 0 for x in weights) and any(weights), "Invalid weights")
    active = [
        dict(weight=str(w), **label) for w, label in zip(weights, all_labels, strict=True) if w
    ]
    if "active_obligations" in certificate:
        require(
            certificate["active_obligations"] == active,
            "Active obligation and saved row correspondence differs",
        )
    rows = []
    rhs = []
    kept = []
    for w, label in zip(weights, all_labels, strict=True):
        if w:
            row, b = necessary_row(info, label, n)
            rows.append(row)
            rhs.append(b)
            kept.append(w)
    checked = residual_certificate(rows, rhs, kept, info.authority)
    return {
        "status": "verified_obstruction" if checked["proved"] else "numerically_unresolved",
        "independent_dual": checked,
        "enumerated_rows": len(all_labels),
        "nonzero_rows": len(rows),
        "recomputed_rows": [
            {"label": x, "coefficients": [v.payload() for v in row], "rhs": b.payload()}
            for x, row, b in zip(active, rows, rhs, strict=True)
        ],
        "solver_called": False,
        "scope": "no common HCW held command; not individual-state or unrestricted-policy impossibility",
    }


def audit_claim(info, candidate, *, max_cells=16384, min_width=Q(1, 65536)):
    """Explicit outcomes distinguish no on-time claim from failed independent proof."""
    try:
        require(type(candidate) is dict, "Candidate record")
        status = candidate.get("status")
        require(
            status
            in (
                "certified_common_prefix",
                "proved_no_common_held_command",
                "unresolved",
                "unresolved_budget",
            ),
            "Unknown original status",
        )
        require(type(candidate.get("deadline_exceeded")) is bool, "Missing Boolean timing outcome")
        wall = candidate.get("wall_s")
        require(
            type(wall) in (float, int) and wall >= 0 and wall < float("inf"),
            "Invalid recorded timing",
        )
        require(candidate["deadline_exceeded"] is (wall > 1), "Inconsistent original timing flag")
        if status in ("unresolved", "unresolved_budget"):
            require((status == "unresolved_budget") is (wall > 1), "Inconsistent late status")
            require(candidate.get("action") is None, "Original abstention has delivered action")
            return {
                "status": "no_on_time_certificate",
                "original_status": status,
                "original_timing_preserved": True,
            }
        require(
            not candidate["deadline_exceeded"] and wall <= 1, "Definite original claim was late"
        )
        if status == "certified_common_prefix":
            u = positive_binding(info, candidate.get("positive"), candidate.get("action"))
            return check_prefix(info, u, max_cells=max_cells, min_width=min_width)
        require(candidate.get("action") is None, "Obstruction unexpectedly delivers action")
        return check_obstruction(info, candidate.get("negative"))
    except UnsupportedAssumption as exc:
        return {"status": "unsupported_assumptions", "reason": str(exc)}
    except (InvalidEvidence, ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
        return {"status": "binding_invalid_evidence", "reason": str(exc)}
