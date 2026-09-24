# Fixed-witness robustness results

The registered post hoc study completed 122 distinct parameter evaluations in twelve fixed searches, with all noncertified bounds retained. The three original states, original pair commands, one-second hold, exact nominal mean motion and original spacecraft campaign are unchanged.

## Two different conclusions

The information-box result retains nominal centers as obstruction witnesses. The stronger all-shifted-triples result bounds every actual shifted state in each box. Both require complete continuous pairwise containment and initial membership; they are not interchangeable.

| Family | Statement | Position bound (micrometres) | Velocity bound (micrometres/s) | Relative n bound (%) | Known zero queue (ms) |
|---|---|---:|---:|---:|---:|
| position | Full information boxes | 208.9 | 0 | 0 | 0 |
| position | Every shifted triple | 58.59 | 0 | 0 | 0 |
| velocity | Full information boxes | 0 | 208.8 | 0 | 0 |
| velocity | Every shifted triple | 0 | 58.59 | 0 | 0 |
| joint_state | Full information boxes | 104.4 | 104.4 | 0 | 0 |
| joint_state | Every shifted triple | 29.29 | 29.29 | 0 | 0 |
| mean_motion | Full information boxes | 0 | 0 | 100.0 | 0 |
| mean_motion | Every shifted triple | 0 | 0 | 100.0 | 0 |
| known_delay | Full information boxes | 0 | 0 | 0 | 222.2 |
| known_delay | Every shifted triple | 0 | 0 | 0 | 222.2 |
| combined | Full information boxes | 99.16 | 99.16 | 0.9916 | 9.916 |
| combined | Every shifted triple | 29.21 | 29.21 | 0.2921 | 2.921 |

Each row gives simultaneous componentwise bounds, with other parameters zero. Joint state uses one dimensionless radius multiplying separate position and velocity scales; meters are never added to meters per second. Displayed values are rounded down; exact rational lower radii, failed upper brackets and every intermediate result are in recorded/.

The mean-motion search reached its declared cap: the mathematical interval includes n=0, the double-integrator limit, up to2n0. This is not a calibrated orbit uncertainty or a maximal admissible interval. The delay result is a new known zero-command queue followed by the unchanged one-second hold, not a claim about unmeasured hardware latency or the original online deadline.

## Scope and retained limits

The nominal-model all-shifted-triples result is certified simultaneously for position and velocity bounds 3/102400 m and 3/102400 m/s, respectively. This is a small, nonzero neighborhood of the existing example, not broad operational practicality. The weaker information-box result allows a larger neighborhood because the incompatible nominal states remain possible.

All three separately declared larger stress realizations begin inside the region and have independently enclosed departures for the fixed pair command or zero queue. They do not contradict the smaller certified region, rule out other pair commands, or estimate failure prevalence. Failed bisection upper bounds are only failures of this sufficient calculation.

The systematic run took 15.303 seconds on the available host, excluding tests and later fixed-output reproduction. This is computational cost, not worst-case execution time, online controller timing or physical validation.

The entire fixed sensitivity calculation was reproduced separately. R02 and R03 source/record identities were rechecked without rerunning the original protected policies. The proof applies established affine-support and residual-verification principles. No new general theorem, nonlinear guarantee, recovery guarantee or human peer-review claim is made.
