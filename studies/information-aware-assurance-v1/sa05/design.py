"""Independent paired initial/latent units; no policy sees these truth records."""

import hashlib
from fractions import Fraction as Q

METHODS = ("fixed_range", "fixed_bearing", "uncertainty_triggered", "decision_aware")
STRATA = ("nominal", "bounded_faults", "outside_assumptions")
DEVELOPMENT_SEED = "KRI-SA05-public-development-20260927-v1"


def integer(seed, label, low, high):
    # Rejection sampling removes modulo bias. Different labels are separate streams.
    width = high - low + 1
    if width <= 0 or width > 2**64:
        raise ValueError("Invalid discrete range")
    limit = 2**64 - 2**64 % width
    for counter in range(100):
        data = f"{seed}|{label}|{counter}".encode()
        x = int.from_bytes(hashlib.sha256(data).digest()[:8], "big")
        if x < limit:
            return low + x % width
    raise RuntimeError("Hash rejection limit")


def make_case(seed, split, stratum, index):
    if split not in ("development", "held_out") or stratum not in STRATA:
        raise ValueError("Explicit split and stratum required")
    uid = f"{split}-{stratum}-{index:03d}"
    key = seed + "|" + uid

    def draw(label, lo, hi, scale=1000000):
        return Q(integer(key, label, round(lo * scale), round(hi * scale)), scale)

    # The mixture is defined independently of outcomes or of any policy preference.
    band = integer(key, "task_band", 0, 1)
    center = (
        draw("cx", -0.6, 0.6) if band == 0 else draw("cx", -2, 2),
        -40 + (draw("cy", -0.6, 0.6) if band == 0 else draw("cy", -6, 5)),
        draw("cvx", -0.04, 0.04),
        draw("cvy", -0.04, 0.04),
    )
    radial_wide = integer(key, "wide_axis", 0, 1) == 0
    radii = (
        Q(3, 5) if radial_wide else Q(1, 10),
        Q(1, 10) if radial_wide else Q(3, 5),
        Q(1, 500),
        Q(1, 500),
    )
    state = tuple(
        x + r * draw("state" + str(j), -1, 1)
        for j, (x, r) in enumerate(zip(center, radii, strict=True))
    )
    bias = [Q(0)] * 4
    eta = Q(1)
    disturbance = [Q(0)] * 2
    if stratum != "nominal":
        bias = [
            draw("bias-x", -0.3, 0.3),
            draw("bias-y", -0.3, 0.3),
            draw("bias-range", -0.25, 0.25),
            draw("bias-bearing", -0.01, 0.01),
        ]
        eta = draw("effectiveness", 0.8, 1.0)
        disturbance = [
            draw("wx", -0.000002, 0.000002, 10**9),
            draw("wy", -0.000002, 0.000002, 10**9),
        ]
    outside_type = None
    actual_apply = 700 + 5 * integer(key, "dispatch_jitter", 0, 2)
    if stratum == "outside_assumptions":
        outside_type = ("sensor_bias", "actuator_loss", "unsafe_entry", "missed_window")[index % 4]
        if outside_type == "sensor_bias":
            bias[2] = Q(3, 2)
        elif outside_type == "actuator_loss":
            eta = Q(1, 5)
        elif outside_type == "unsafe_entry":
            center = (Q(0), Q(-3003, 100), Q(0), Q(1, 4))
            radii = (Q(1, 100000),) * 4
            state = center
        else:
            actual_apply = 715

    def noise(channel, epoch):
        return (
            draw(f"noise-{channel}-{epoch}", -0.004, 0.004)
            if channel == "range"
            else draw(f"noise-{channel}-{epoch}", -0.0004, 0.0004, 10**9)
        )

    warm_channel = (None, "range", "bearing")[integer(key, "warm_channel", 0, 2)]
    # No different policy is assigned more favourable latent faults or noise draws.
    return dict(
        schema="iaa-sa05-latent/1",
        unit=uid,
        split=split,
        stratum=stratum,
        index=index,
        task_band="near_station" if band == 0 else "approach",
        prior_center=[str(x) for x in center],
        prior_radii=[str(x) for x in radii],
        initial_state=[str(x) for x in state],
        biases=[str(x) for x in bias],
        effectiveness=str(eta),
        disturbance=[str(x) for x in disturbance],
        warm_channel=warm_channel,
        measurement_noise={
            f"{c}-{t}": str(noise(c, t)) for c in ("range", "bearing") for t in (0, 250)
        },
        timestamp_offset_ms=0 if stratum == "nominal" else integer(key, "timestamp_offset", -2, 2),
        range_lost=False if stratum == "nominal" else integer(key, "range_lost", 0, 9) == 0,
        bearing_lost=False if stratum == "nominal" else integer(key, "bearing_lost", 0, 9) == 0,
        planner_ready_ms=151
        if stratum == "bounded_faults" and integer(key, "plan_late", 0, 9) == 0
        else 145,
        checker_ready_ms=701
        if stratum == "bounded_faults" and integer(key, "check_late", 0, 9) == 0
        else 675,
        application_ms=actual_apply,
        outside_type=outside_type,
        method_order=sorted(
            METHODS, key=lambda m: hashlib.sha256((key + "|order|" + m).encode()).hexdigest()
        ),
    )


def population(seed, split, counts):
    if set(counts) != set(STRATA) or any(
        type(n) is not int or not 1 <= n <= 64 for n in counts.values()
    ):
        raise ValueError("Bounded declared population required")
    return [make_case(seed, split, s, i) for s in STRATA for i in range(counts[s])]
