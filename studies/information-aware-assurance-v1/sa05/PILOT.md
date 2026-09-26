# Development exposure and sample-size decision

The complete pilot used source bd12049a316ad816187240ab8d1c183edd6b0986 and the
public development seed in design.py. Its nine units (three per stratum) and all
36 method runs are retained under development_recorded/. All completed without
infrastructure failure. None acquired new two-second goal dwell; the initial-
eligibility successes remain distinct. Candidate acquisition discordance with
both primary comparators was zero in this small pilot.

No method, command menu, threshold, scenario distribution or latent error rule
was tuned using the pilot. Its purpose was to estimate computational cost and
identify analysis/execution defects before final source freeze. The mean child
cell duration was 2.4294 s and the maximum was 5.3308 s. The full pilot ledger
finished at 87.6708 s, excluding subsequent analysis and plotting.

The fixed evaluation size is 48 nominal units, 48 within-assumption challenge
units and 16 deliberate assumption-violation units, each evaluated by four
methods: 112 paired units and 448 method runs. Mean-time extrapolation is about
1088 s, below the frozen 1800 s overall allowance. A 45 s per-cell bound prevents
a single stalled worker consuming the entire allocation. These observations do
not guarantee the runtime of a later sample; any missing or unfinished cells
remain in the accounting. Sampling is not extended to improve a result.

There is insufficient pilot discordance to claim power for a small method effect.
For 48 independent artificial units, zero observed marginal events would still
have a two-sided exact 95% upper bound of about 7.4%. Simultaneous conservative
paired-difference intervals are wider. This is a bounded comparative study, not
an operational reliability or equivalence demonstration.

One analysis interpretation was corrected before final freeze: the deterministic
four-type mixture in the outside-assumption stratum is descriptive, so its final
summary has no binomial confidence interval. The original pilot report contained
a generic interval field for that mixture. Its bytes remain unchanged and that
field must not be used inferentially. No underlying outcome was altered. All
nominal/within-assumption inferential calculations and all policy definitions are
unchanged. The pilot's host measurements are not pooled with held-out timings.

The final master seed and latent input file are generated once after this sample-
size decision. No final latent outcome is executed before the public protocol and
source deposit. Exposed unit tests and pilot inputs do not enter the held-out set.

A pre-freeze plot-regeneration test also exposed dependence on global matplotlib
settings changed by another imported package. Rendering now runs inside isolated
default settings. The regression reproduces all original pilot plot/table bytes;
no stored data, plotted quantity or pilot figure was edited.
