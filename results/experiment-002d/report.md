# Experiment 002d combined-fault information study

> **Evidence boundary:** bounded nuisance and paired-information evidence for the frozen
> synthetic F7 generator only. This is not confirmatory superiority or flight-safety
> evidence.

## Decision

**`resolved_freeze_confirmatory_design`**.

- Complete paired root-seed blocks: `299`
- Episode rows: `598` (D and PD only)
- Confirmatory campaign executed: `false`
- Reserved confirmatory partition materialized: `false`

## F7 nuisance estimates

- D analysis-hazard risk: `0.000000` (0/299)
- Hazard discordance: `0.000000`; one-sided 95% upper `0.009969`
- Sustained-success discordance: `0.163880`; one-sided 95% upper `0.203228`
- Adverse-coded failure cells: `0`

## Eight-stratum marginal power

| Seeds/stratum | H1 power | H1 MC 95% lower | H2 power | H2 MC 95% lower | Pass |
| ---: | ---: | ---: | ---: | ---: | :---: |
| 1000 | 1.00000 | 0.99998 | 0.99979 | 0.99972 | yes |
| 1500 | 1.00000 | 0.99998 | 1.00000 | 0.99998 | yes |
| 2000 | 1.00000 | 0.99998 | 1.00000 | 0.99998 | yes |

Endpoint powers are marginal, not a claim about joint H1/H2 rejection probability.
Nuisance bounds are separate one-sided 95% bounds; no simultaneous-coverage claim is
made. Controller effects observed here are descriptive and are not progression gates.

## Exact next action

`freeze_separate_eight_stratum_confirmatory_preregistration_without_materializing_or_opening_reserved_seeds`.
