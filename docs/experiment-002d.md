# Experiment 002d combined-fault information amendment

Experiment 002d is the smallest bounded step needed after the Experiment 002c numerical correction.
It samples only the original confirmatory `F7` stratum: primary-channel dropout combined with
actuator degradation. It does not run the confirmatory campaign.

The original eight-stratum map is frozen explicitly in
[`experiments/002d/confirmatory-stratum-map.json`](../experiments/002d/confirmatory-stratum-map.json).
Pilot `P1` supplies separate historical nuisance estimates for confirmatory F1 range bias and F2
dropout; the remaining pilot strata map one-to-one to F0 and F3-F6. Therefore F7 is the only wholly
missing stratum.

The amendment uses `299` new root seeds from partition code `25`, runs only D and PD, and preserves
paired exogenous draws with arm-specific truth. This yields `598` episodes. The size is the minimum
for which zero incomplete paired blocks has a one-sided exact 95% upper bound below the frozen 1%
incompleteness limit. Partition code `16` remains reserved for confirmation and is not materialized.

F7 uses the original combined-fault distributions: primary dropout onset `U(120,300) s`, duration
`U(5,30) s`, actuator onset gap `U(-30,30) s`, actuator duration `U(30,150) s`, and effectiveness
`U(0.25,0.75)`. The corrected Experiment 002c production dynamics and independent truth evaluator
remain in force. No controller or endpoint is redesigned.

The analysis estimates D/PD marginal risks, directional paired discordances, separate exact
one-sided 95% discordance bounds, adverse-coded failures, and completeness. It then recomputes
marginal H1/H2 power for eight equal-weight strata at the previously allowed fixed candidates of
1,000, 1,500, and 2,000 roots per stratum. A candidate must pass under both the historical-compatible
and conservative direct-risk scenarios, with the lower Monte Carlo 95% bound at least 95% for each
endpoint. The smallest passing candidate is selected.

A passing amendment resolves only the combined-fault information requirement and permits a separate
confirmatory preregistration/freeze. It does not authorize outcome-adaptive enlargement, open any
reserved confirmatory seed, establish superiority, or support a flight-safety claim.
