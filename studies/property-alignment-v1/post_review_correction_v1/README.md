# Post-review scientific clarifications

This additive package clarifies the frozen HCW derivation's endpoint notation
and supplies further exact-rational matrix/Bernstein checks of the existing
three-state example. See [the dated endpoint correction](ENDPOINT_CONVENTION.md).
The original frozen source and result records remain unchanged.

The project adaptations of author-provided corrected checking code retain the
same constants, commands, polynomial order and state-perturbation bounds.
`SOURCE.json` identifies the exact supplied source files and adaptations.
`REFERENCE.json` binds expected scientific fields extracted from the supplied
corrected results. Preliminary invalidated results are not scientific inputs.
The repository's existing Apache-2.0 license applies to this project adaptation.

## Mathematical and execution scope

The order-22 augmented matrix exponential uses exact rational coefficients and
an induced infinity-norm tail. Bernstein coefficients bound the complete
one-second interval and every initial state in each admitted position/velocity
box. Nominal and simultaneous `3/102400` SI state-shift cases are checked with
original pair commands and dual weights. The three larger stress realizations
only refute their specified fixed commands. The mean-motion/delay sensitivity
families and complete 768-case audit are not reimplemented by this package.

Source inspection preceded this adaptation. The formulation has no dependency
on the original numerical core, optimizer or trigonometric maps. Cross-check
tests separately import the unchanged HCW core to compare segment endpoints;
that comparison is absent from the matrix-check execution path. None of these
computations establishes hardware performance, unrestricted recovery or a new
sample of original online performance. Existing provenance records are retained.

## Reproduce the added checks

Use Python 3.13.5 and a full-history clone, from the study directory:

```sh
python -m post_review_correction_v1.checks --verify post_review_correction_v1/recorded
python -m pytest post_review_correction_v1/tests
```

The numerical checks use only the standard library; tests require pytest.
Verification recalculates the same fixed results without changing source or
records. A separate new recording requires a new output path and committed
source. It must not replace an earlier record or a historical timing verdict.

The companion private manuscript correction distinguishes the original audit
from the later fresh-environment replay, and names the cart comparator as a
re-derived predictive-prefix comparator. The 79-versus-77 positive comparison
and all original adverse, unresolved and late results are preserved. No private
manuscript, review report or workstation path is published by this package.
