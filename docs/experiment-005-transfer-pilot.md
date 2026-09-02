# Experiment 005 nonlinear-truth transfer-pilot design

Experiment 005 transfers the frozen Experiment 004 HCW autonomy mechanics to nonlinear two-body
physical truth. This additive design package contains prospective partition-51 mechanics
calibration and freezes a future partition-52 non-inferential pilot. It contains no partition-52
seed, episode, or analysis row. Partition 53 is untouched.

## Smallest useful matrix

The matrix in
[`experiments/005-transfer-pilot/case-matrix.json`](../experiments/005-transfer-pilot/case-matrix.json)
contains ten domains: nominal transfer, isolated truth-model mismatch, a nonlinear truth-space event
fixture, primary bias and dropout, monitor bias and false trip, shared navigation bias, actuation
loss, and disturbance burst. Each root will run the primary reference and independent monitor-gated
configuration as plumbing diagnostics only.

Two roots per case are the smallest outcome-blind count that places both configurations once in each
within-block order position while covering every case. The frozen future campaign is therefore 20
complete blocks and 40 episodes. Replicate 0 in every case forms a 10-block/20-episode replay
subset. The count is not based on power, hazards, or an observed architecture effect.

## Calibration boundary

Partition 51 checks mechanics only: nonlinear nominal feasibility, finite covariance, continuous
truth-event classification, no-fault mismatch observability, fault/domain routing, actuation and
disturbance path sensitivity, order balance, and deterministic replay. Every attempt is preserved.
It computes no architecture configuration contrast and uses no E004 campaign outcome.

Transferred fault magnitudes are byte-bound to the pre-outcome E004 pilot design inputs. The E005
ordinary initial-state envelope starts at `y=-100 m`, rather than the historical E004 pilot's
`-105 m`, because the prospectively corrected E005 truth geometry correctly treats positions below
`-100 m` as outside the admissible set.

## Frozen reporting boundary

Future outputs are descriptive mechanics diagnostics. Nonlinear-minus-HCW residuals prove that
model mismatch is visible but have no favorable/unfavorable acceptance threshold. P-values,
architecture confidence intervals, superiority/noninferiority, hazard-rate claims, rankings,
replacement roots, and outcome-dependent extensions are prohibited.

## Execution state

- Foundation freeze: `921c481726d6f078621ff3a355a7803af803bdc61a8a2da07ffb974a433b3be8`
- Foundation readiness: `9ec734543fd3580e9a2990a16dc56747a0f75334f76bd2c7ae1fdc3647732e67`
- Partition 51: mechanics calibration evidence only
- Partition 52: future write-once generator authorized after verified design freeze; unmaterialized
- Partition 53: untouched, unmaterialized, and without a generator
- Partition 951: deterministic fixtures only

The next task is exactly one partition-52 pilot materialization and checkpoint-safe execution after
the design freeze is merged. It is not a confirmatory campaign.
