# SA02 observation consistency results

Source commit `5af11ace0e7d9ec7521b419e7f14a26372449a25`. All ten named development cases in the committed
protocol were executed once in the recorded attempt. These are engineering fixtures,
not a held-out comparison, operational sample or population safety estimate.

## Complete development outcomes

| Case | Updates | Nonempty exclusions | Unavailable sets | Maximum cells | Position hull area ratio, min to max |
| --- | ---: | ---: | ---: | ---: | --- |
| sa02_nominal | 60 | 0 | 0 | 16 | 0.649531183 to 0.99989915 |
| sa02_delayed_and_out_of_order | 16 | 0 | 0 | 10 | 0.999910467 to 1.0 |
| sa02_shared_and_channel_bias | 24 | 0 | 0 | 8 | 0.994753947 to 0.99989915 |
| sa02_bounded_actuator | 20 | 0 | 0 | 14 | 0.994873777 to 0.99989915 |
| sa02_outside_actuator_model | 20 | 3 | 0 | 14 | 0.994873741 to 0.99989915 |
| sa02_late_and_lost | 32 | 0 | 0 | 16 | 0.996105061 to 0.99989915 |
| sa02_invalid_sensor_packets | 24 | 0 | 0 | 14 | 0.99692484 to 0.99989915 |
| sa02_packet_capacity | 8 | 0 | 0 | 8 | 0.999570218 to 0.99989915 |
| sa02_coarse_representation | 24 | 0 | 0 | 4 | 0.994753947 to 0.99989915 |
| sa02_outside_sensor_model | 24 | 0 | 14 | 8 | 0.99692484 to 0.99989915 |

The eight cases within the declared dynamics and sensor-offset family retain the
numeric simulation state at all 208 observer updates. This finite observation is
corroboration of the conditional containment argument, not proof of coverage for
arbitrary sensors, noise, faults or spacecraft. State membership uses the binary64
simulator representation; the mathematical bound is defined in MATHEMATICS.md.

The 0.2-effectiveness case violates the declared [0.8,1] dynamics after 6 s and
has three nonempty true-state exclusions. Its four seconds of dynamics-assumption
failure remain reported. The two-metre sensor-bias case has fourteen unavailable
sets with latched inconsistency. Those empty outputs are not counted as nonempty
false exclusions, and inconsistency does not imply absence of a physical state.

The separate packet replay `unmodelled_bias_not_detected` has a nonempty output
that excludes the true state without detecting the unmodeled 0.5 m range bias.
This deliberately contrary result prevents a claim of universal fault detection.
The other five packet fixtures cover nominal, contradictory, future, unsupported
clock and missing input behaviour. Invalid packets in the end-to-end run are rejected
at the existing source interface and appear as missing observations; direct malformed
and unsupported observer inputs are exercised separately.

## Ambiguity and conservatism

Area ratios compare the projection hull with the independently propagated
unconditional prior for the same run. They do not measure the exact feasible-set
area or establish estimator superiority. Nominal minimum ratio is 0.649531183;
the shared-bias run retains almost all prior area (minimum 0.994753947). The nominal
case keeps all four hypotheses, while shared-bias and coarsened cases retain both
shared/channel-bias explanations. No posterior weights or independent-noise
averaging are used to eliminate them.

The four-cell coarsened case has the same reported area extrema and baseline
maximum position error as its eight-cell shared-bias counterpart. This result
does not establish equivalence for other inputs or preserved joint correlations.
Its main observed difference is representation size and measured update work.
The baseline point estimate has maximum position error 0.861365557 m in those
biased runs. It is the unchanged estimate actually used at decision time, with
its acquisition age; it is not an optimally retimed or independently tuned comparator.

The twelve exact static linear reference cases retain every feasible reference
vertex; box-width excess ranges from 29/60 to 37/30 on coordinate one and
7/15 to 13/20 on coordinate two. This explicitly measures remaining overapproximation.
For the constant-velocity example, the exact decision-position interval is
[-3/20,23/20] while the interval construction gives [-13/20,23/20]. Eight
independently specified rational matrix-tail HCW checks also pass. These checks
do not constitute a second full spacecraft observation-history implementation.

## Timing and execution limits

| Case | Observer median ms | Observer maximum ms | Updates over the modeled 50 ms whole path |
| --- | ---: | ---: | ---: |
| sa02_nominal | 91.711479 | 149.650750 | 55 |
| sa02_delayed_and_out_of_order | 60.754604 | 81.513917 | 15 |
| sa02_shared_and_channel_bias | 29.162063 | 50.997417 | 2 |
| sa02_bounded_actuator | 59.588521 | 155.390125 | 14 |
| sa02_outside_actuator_model | 58.691042 | 150.205166 | 12 |
| sa02_late_and_lost | 87.677188 | 152.860500 | 29 |
| sa02_invalid_sensor_packets | 52.569708 | 184.399792 | 17 |
| sa02_packet_capacity | 45.602542 | 76.359459 | 3 |
| sa02_coarse_representation | 23.496605 | 32.423291 | 0 |
| sa02_outside_sensor_model | 1.982708 | 58.340708 | 2 |

These are actual observer-only host measurements from one invocation on Darwin arm64,
using CPython 3.13.5. All 252 samples are retained, including 149 exceeding
the inherited modeled 50 ms decision path. The largest observed value is
184.399792 ms. This implementation has not demonstrated the required real-time
execution budget, target-processor performance, worst-case latency or energy savings.
Simulation continues to use its explicitly modeled clock; measured durations
are never silently substituted into certified application times.

All ten end-to-end cases retain unsuccessful mission-dwell results. Late/lost
decisions retain a 2.5 s protection gap. The out-of-sensor-model case retains
a 3.8 s lease gap. All guard and coast conclusions remain conditional on their
observation and dynamics assumptions. A dynamics-only coverage count cannot
establish whole-system protection when an observation assumption is violated.

## Provenance and reproduction

`recorded/` contains the packet inputs, all event traces, summaries, per-update
comparisons, exact reference outcomes, measured timing receipts and source manifest.
No case failed execution or was omitted from this attempt. Reproduction is
`python -m sa02.artifact verify sa02/recorded --replay` from the study root.
Deterministic scientific outputs must match exactly. Recorded timing samples
are checked for identity and accounting, not expected to repeat on another run.

Before recording, adversarial tests reproduced and corrected an inconsistency
latch bypass on resource exhaustion, missing estimate-schema validation, and
mutable fault-contract inputs. Their failures and corrections remain in the
private stage record. SA01 sources and both earlier fixture sets are unchanged.

SA02 establishes a bounded-model observation-conditioning component for further
offline research. Sensor calibration, unrestricted fault schedules, certified
attainable negative witnesses, hardware timing and external validation are not
delivered. SA03 may build within these limits; real-time readiness is not asserted.
