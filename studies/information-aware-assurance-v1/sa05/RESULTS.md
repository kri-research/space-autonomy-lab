# SA05 prospective comparison results

## Post-audit qualification added 28 September 2026

The [separate exact-rational attainability analysis](posthoc_attainability_v1/README.md)
shows that 80 of 81 initially ineligible in-model inputs cannot enter the goal early
enough for the frozen primary endpoint under its control and mathematical envelope.
Only `held_out-nominal-019` is not excluded, and it is not proved feasible. Thus the
acquisition comparison had extremely limited opportunity to discriminate sensing
strategies, beyond the previously stated zero-event and power limitations.

This is a post-hoc interpretation correction, not a replacement evaluation. All 112
units, 448 method records, original denominators, endpoints and statistical results
remain unchanged. Containment, timing, request-count and modeled-cost observations
retain their separate scope. The original result account follows below.

## Primary result and scope

No schedule demonstrated a new two-second goal acquisition under the numerical
adjudication in this prospectively specified finite-manoeuvre evaluation. The decision-aware candidate therefore
has no demonstrated acquisition advantage over fixed-range or uncertainty-triggered
sensing. It avoided optional observation requests, but incurred more modeled total
work cost than the simpler schedules. This is a valid negative/inconclusive result
for the stated comparison, not evidence of equivalence or universal futility of
active sensing.

The experimental unit is one sampled initial state and its exogenous latent
conditions. Four schedules share that unit. The experiment concerns one 4.2-second
modeled manoeuvre, one held action and a finite coast. It does not establish full
inspection-mission performance, operational safety, recovery, physical validation,
real-time readiness or superiority to native published active-sensing methods.

## Prospective deposit and complete accounting

[PR #61](https://github.com/kri-research/space-autonomy-lab/pull/61) deposited the
protocol, source, dependencies and final latent population before outcome execution.
Its merged commit is `6d728de32f5662a26661a0a71a6d7578b969121c`; the frozen scientific
source is `9d921566a919ee81cc4fb2b5391069b545667ff2`. The freeze SHA-256 is
`6e705d8ed4ff02a3387a12f1aecc1bf0f2f8914cafa91e396637f3bf29350c53`.

GitHub records the prospective merge at 2026-09-26 23:46:48 UTC. The runner verified
the public deposit at 23:47:50.346120 UTC before starting the first outcome. This is
a timestamped public source deposit, not externally administered preregistration.
The frozen protocol's prospective/pending-deposit status describes its preparation
time; this result and deposit.json record the later completed stages without
rewriting that historical field.

The held-out execution completed all 112 units: 48 nominal, 48 within-assumption
challenge and 16 deliberate outside-assumption units. All **448 of 448 method runs**
completed in the single original attempt. There were no infrastructure failures,
timeouts, omitted cells or selectively repeated outcomes. The last ledger finish
was 1457.990877 seconds after the campaign clock began, within the frozen 1800-second
allowance. Per-cell timeout remained 45 seconds. No source, policy, population,
primary analysis or stopping rule was changed after the public freeze.

The earlier nine-unit, 36-run pilot remains separate under development_recorded/;
its exposed results and host timings are not pooled with held-out observations.
All final per-case trajectories, observations, decisions, checks, resource records,
analysis and plots are retained under recorded/. Its manifest SHA-256 is
`634b3e3343f579802ddaff38c2c6cc9faba99999ff4e06b8ce294461959abee8`.

## Absolute outcomes and modeled resources

Requests are additional observations, excluding the shared initial measurement
when present. Modeled mJ includes the declared planning, uncertainty reconstruction,
checking and sensing charges. It is not measured electrical energy. Mission dwell
counts below include already-eligible starts; the acquisition column excludes them.

| Stratum | Schedule | Runs | New acquisitions | Mission dwell | Requests | Mean modeled mJ |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| nominal | fixed_range | 48/48 | 0 | 5 | 48 | 12.518000 |
| nominal | fixed_bearing | 48/48 | 0 | 5 | 48 | 11.848854 |
| nominal | uncertainty_triggered | 48/48 | 0 | 5 | 32 | 12.575833 |
| nominal | decision_aware | 48/48 | 0 | 5 | 0 | 12.898563 |
| bounded_faults | fixed_range | 48/48 | 0 | 5 | 41 | 19.367000 |
| bounded_faults | fixed_bearing | 48/48 | 0 | 5 | 41 | 15.386313 |
| bounded_faults | uncertainty_triggered | 48/48 | 0 | 5 | 41 | 17.654042 |
| bounded_faults | decision_aware | 48/48 | 0 | 5 | 0 | 22.591729 |
| outside_assumptions | fixed_range | 16/16 | 0 | 3 | 12 | 18.309500 |
| outside_assumptions | fixed_bearing | 16/16 | 0 | 3 | 12 | 14.748812 |
| outside_assumptions | uncertainty_triggered | 16/16 | 0 | 3 | 12 | 17.244125 |
| outside_assumptions | decision_aware | 16/16 | 0 | 3 | 0 | 21.900562 |

All 384 in-model method runs were numerically contained, with zero observed
nonempty information-set exclusions and zero numerically established unsafe
admissions. These are 96 paired units, not 384 independent spacecraft trials.
No ambiguous constraint adjudications occurred in this retained set. Numerical
containment uses the documented reference-tested interpolation/integration
allowances; it is not a universal roundoff proof or physical reliability estimate.

In each in-model stratum, five units achieved dwell under all four schedules, all
from initially eligible states. Six nominal and nine bounded-fault units initially
met goal eligibility; eligibility alone therefore did not guarantee later dwell.
The primary outcome was zero for every method, with no discordant acquisition pair.
All four predeclared exact paired p-values and Holm-adjusted p-values are 1.0.
The conservative simultaneous signed-difference intervals are
[-0.459854, 0.459854], about +/-45.99 percentage points, for each comparison.
The supplementary exact marginal 95% acquisition interval for zero of 48 is
[0, 0.073973]. Neither result establishes equality, noninferiority or absence of
possible benefit on another distribution or a longer mission horizon.

## Benefits and contrary outcomes

The candidate requested no optional sensor in any of the 112 units. In 34 units
an existing action already met its conservative local usefulness criterion;
in 74 it evaluated sensing without finding an all-reading usefulness improvement;
in four unsafe-entry units it had no supported plan. These are descriptive
explanations from the recorded decisions, not new primary outcomes.

Request avoidance did not yield lower total modeled cost. Candidate mean modeled
cost exceeds both primary comparators in each in-model stratum. Its nominal median
change in squared target distance is -0.042558115 m2, versus -0.051545679 m2 for
uncertainty-triggered sensing. These descriptive medians do not constitute a new
significance test or a controller-ranking theorem. A conservative all-reading
criterion may avoid sensing that improves some realized cases without guaranteeing
improvement for all admitted readings.

Within-assumption challenges include seven late-planner units and five late-checker
units; their overlap leaves eleven protected-continuation uses per schedule.
A missed modeled decision receives no retimed candidate action. Real host execution
costs are separately adverse, as reported below.

The sixteen outside-assumption units form a deliberately constructed, descriptive
mixture. The four unsafe-entry units violate the geometry under all four methods,
yielding sixteen method-run violations, all without initial protection credit.
One unmodeled sensor-bias unit has nonempty information-set exclusions under fixed
range and uncertainty-triggered sensing. These two method outcomes are the same
latent unit, not two independent faults. No unsafe admission was numerically
established in this finite set. This does not imply that violated sensor bounds
are always detected or harmless. Four missed-window units are not silently moved
into an allowed initiation slot. The frozen outside-assumption summary has no
binomial inferential interval.

## Actual host costs and timing boundary

All 448 measured host trials are retained separately from simulated readiness
inputs. Each method has 112 samples. The planner measurement includes its
observation reconstruction; checker measurements concern the realized-action
path. The per-cell ledger duration includes startup, imports and transport in
addition to the separately timed offline trial. Startup is not isolated as its own
measurement.

| Schedule | Planner median ms | Planner maximum ms | Planner over 50 ms | Checker over 50 ms | Checker maximum ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| fixed_range | 943.317063 | 10843.283292 | 106 | 4 | 232.990250 |
| fixed_bearing | 512.895041 | 5650.553500 | 108 | 9 | 156.361375 |
| uncertainty_triggered | 955.261167 | 8599.547500 | 98 | 12 | 201.484208 |
| decision_aware | 976.074729 | 11484.646250 | 74 | 2 | 75.915125 |

Across the complete set, 386 planner calls and 27 checker calls exceeded 50 ms.
The maximum observed planner time was 11484.646250 ms. Candidate early returns
reduce its overrun count without establishing faster successful decision making.
Different contexts and outcomes must not be collapsed into an unsupported
throughput ranking. Maximum recorded process RSS was 200818688 bytes; this is a
host-process high-water mark, including imported software, not incremental onboard
memory demand. Maxima and these single-host measurements are not WCET proofs.

Physical acquisition, communication, clock alignment, actuation and energy were
not measured. Simulated completion times are fixed experimental inputs, not claims
that these measured computations can meet them. The prior SA04 deadline-enforced
failures remain unchanged. No real-time or hardware claim follows from SA05.

## Independent numerical checks and reproduction

Basilisk 2.12.0 supplies the nonlinear two-body plant. Its units, rotating frame,
force directions and switching were checked before freezing. The analytical
nonlinear/force-hold residual bound is 1.31041740293e-7 m/s2 over the declared domain;
with injected bounded disturbance it remains below the existing 1e-5 m/s2
allowance. Assumption-violating strata remain separately labeled.

A separately written relative-coordinate DOP853 audit subsequently checked all
448 stored trajectories and recomputed constraint categories, goal dwell and new
acquisition. It found zero mismatches. Maximum differences were 1.45046991640e-8 m
in position and 8.45313541387e-11 m/s in velocity, below the declared numerical
allowances. The source and complete audit are provided in
[sa05_validation](../sa05_validation/README.md). That audit shares model constants
and numerical allowances with the study; it is not external replication or a
second independently certified physical model. The audit does not retune policies.

Run the commands in README.md to verify committed bytes, actual source Git blobs,
full membership, frozen analysis and host accounting, and regenerate the tables
and figures. `--sample` replays the predeclared 24 cells; `--replay` reproduces all
448 successful cells without adding observations or replacing the original data.
Fresh computed host times are not expected to match retained measurements.
Original PNG byte hashes remain exact; portable regeneration checks exact decoded
pixels and DPI, with exact SVG and table bytes. The zero-height acquisition plot
is intentional: every recorded acquisition count is zero.

## Supported continuation

Carry the finite protective checker, context-bound execution boundary, conservative
observation interfaces and independent numerical adapter forward as research
components. Fixed-bearing is a simple benchmark reference with lower modeled mean
cost in this retained set; retain uncertainty-triggered sensing as the simple
adaptive comparison and the decision-aware implementation as an evaluated candidate.
No overall mission superiority is established for any schedule by these data.
Do not promote the candidate as the default operational controller or infer a
validated hybrid policy from this comparison.

SA06 can package and assess integration of these software components while
preserving the negative result and their finite-horizon assumptions. Calibrated
sensors, target deadlines, hardware energy, supervised physical tests and external
replication remain unperformed. No SA06 execution, external release, website change,
standard/checklist revision or manuscript modification is performed by SA05.
