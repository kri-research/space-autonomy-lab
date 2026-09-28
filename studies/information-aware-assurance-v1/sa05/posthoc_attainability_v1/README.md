# Post-hoc attainable-opportunity analysis

Dated **28 September 2026**, after the frozen SA05 evaluation. This is a new
derived-evidence analysis of unchanged inputs, not a new policy experiment,
preregistered endpoint, replacement analysis, or basis for deleting a case.

## Result and interpretation

| In-model stratum | Units | Initially eligible | Entry excluded by 2.2 s | Ineligible not excluded |
| --- | ---: | ---: | ---: | ---: |
| Nominal | 48 | 6 | 41 | 1 |
| Bounded faults | 48 | 9 | 39 | 0 |
| Total | 96 | 15 | 80 | 1 |

**80 of 81 initially ineligible in-model units cannot attain the frozen primary
endpoint under the stated control schedule and mathematical envelope, even with
perfect information and more control freedom than the implemented action menu.**
The sole unexcluded input is `held_out-nominal-019`; it is not proved feasible.
The 15 initially eligible units cannot count as new acquisitions by the original
endpoint definition. The 16 outside-assumption units are not covered by this screen.
The smallest strict coordinate gap is exactly `3382729/2500000000 m`
(0.0013530916 m). Bounds that overlap the goal certify nothing about feasible entry.

This sharply limits the acquisition comparison's opportunity to distinguish sensing
strategies. The original zero counts and statistical arithmetic remain correct.
Containment, workload, request-count, modeled-cost and measured host-timing
observations retain their separate scope. No superiority, equivalence, physical
safety or general futility of active sensing follows. The opportunity check should
have been included before freezing the mission-utility evaluation.

## Mathematical assumptions

The assurance inclusion is

    x'' = 3 n^2 x + 2 n y' + eta u_x + w_x
    y'' = -2 n x' + eta u_y + w_y

with n = 11/10000 s^-1, eta in [0.8,1], command norm <= 0.02 m/s^2,
and |w_j| <= 1e-5 m/s^2. The disturbance envelope includes the nonlinear/force-hold
residual under the separately stated SA05 assumptions; this is not new physical
calibration or a floating-point error proof. A successful contained trajectory
must remain in [-8,8] x [-60,-30] m. Initial component speeds are <=0.042 m/s.
These initial conditions and actuator bounds are checked on every included input.

A first-hitting-time bootstrap proves |v_j| < 0.2 m/s for such a successful
trajectory: while that bound holds, the drift excluding control is at most

    a_d = 3 n^2 (8) + 2 n (0.2) + 1e-5 = 0.00047904 m/s^2.

Even granting maximum thrust for the full horizon gives

    0.042 + (0.02 + a_d) (4.2) = 0.128011968 < 0.2.

A first hit at 0.2 is therefore impossible. Geometry also keeps position norm below
100 m, the domain of the previously stated nonlinear mismatch envelope.

Two seconds of continuous goal dwell by 4.2 s requires goal entry by T=2.2 s.
The actual control is zero before a start in [0.700,0.710] s and after 1.2 s.
Grant independently bounded axis inputs throughout [0.7,1.2], including variable
inputs not in the finite command menu. This is a superset of the permitted control
class. Missing/late decisions produce no larger pulse and are covered too.

For either coordinate q and any t in [0,T], define

    b(t) = 0.02 integral_[0.7,min(t,1.2)] (t-s) ds + a_d t^2 / 2,

with zero pulse term before 0.7. Then q0 + v0 t - b(t) <= q(t) <= q0 + v0 t + b(t).
The upper envelope is convex and the lower concave over the complete interval,
including pulse boundaries. Consequently

    q([0,T]) subset [min(q0,q0+v0 T-b(T)), max(q0,q0+v0 T+b(T))].

At T=2.2 the pulse contribution is 0.0125 m and b(T)=0.0136592768 m.
Strict disjointness from either goal coordinate interval excludes entry throughout
[0,T], not merely at sampled times. The goal intervals are [-0.35,0.35] and
[-40.35,-39.65] m. Ignoring the additional speed requirement only enlarges the
possible-entry set. None of this establishes feasibility for an unexcluded state.

## Source and reproduction

`audit.py` uses standard-library exact rational arithmetic and no study policy,
optimizer, simulator, estimator or primary-analysis imports. It validates the
input SHA-256 `72b8c3ed9552804c48e23f825aea5d99e9f8bf23a6765e61cb1f9e2c7f39a6e0`
and uses original source commit `9d921566a919ee81cc4fb2b5391069b545667ff2`.
The new correction's source/result manifest binds this derived output separately.

From `studies/information-aware-assurance-v1/`:

```sh
python -m sa05.posthoc_attainability_v1.audit sa05/held-inputs.json --output /tmp/kri-new-posthoc-result.json
python -m post_audit_v1.verify
```

Use a new output path. All 112 original inputs, 448 method outcomes, primary tests,
original denominators and negative findings remain unchanged. No new campaign,
filtering, retuning or outcome-driven replacement is authorized by these commands.
