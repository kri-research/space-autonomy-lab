# Endpoint convention for fixed-segment HCW superposition

Dated correction, 25 September 2026. This clarifies the expression in
`independent_hcw_audit_v1/DERIVATION.md` at the scientific revision
`67776ed310ad648f267c79f27d7ffffbd35ab7bf`. That derivation is part of the frozen
auditor source inventory and remains unchanged. This notice is additive.

## Correct expression

Let successive forcing segments be `[a_j,b_j]`, with `b_j=a_(j+1)`, and let `k`
be the current segment. For a query entirely within that segment, use

```text
z(t) = Phi(t) z(0)
     + sum_(j < k) Phi(t - b_j) Gamma(b_j - a_j) f_j
     + Gamma(t - a_k) f_k,             a_k <= t <= b_k.
```

Only segments strictly preceding `k` occur in the sum. At `t=b_k`, segment `k`
is still counted only in the last term. Equivalently, it may be treated as
completed at the start of segment `k+1`, whose current contribution is zero
because `Gamma(0)=0`. The two conventions agree at the shared boundary since
`Phi(0)=I`. At the final endpoint use the last segment, without adding another
copy of its forcing. A range crossing an event must be split at that event.

The older expression used `b_j <= t` and separately added the current forcing
term without saying which segment was current at equality. Reading both terms
inclusively at the right endpoint can double-count a segment. The implementation
`hcw.py::state_range` and the supplementary `j<k` expression already count every
segment once. This correction changes no numerical method or frozen result.

## Verification

A quarter-second segment with radial forcing `0.01 m/s^2` contributes approximately
`0.0003124999979166821 m` radially. Counting it twice gives approximately
`0.0006249999958333642 m`; separately enclosed intervals are disjoint. This
example isolates the forced response and illustrates two different formulas,
not a false certificate emitted by the existing kernel.

The accompanying regression suite compares the unchanged kernel with the
augmented-matrix response at zero, internal and final endpoints, for single and
multiple segments, including the double-integrator limit. It also retains the
nominal and uniformly shifted triple checks and the three named stress witnesses.
No original policy, candidate search, qualification selection or online timing
experiment is rerun.
