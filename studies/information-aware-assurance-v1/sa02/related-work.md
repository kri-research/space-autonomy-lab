# Primary-source basis for observation conditioning

Checked 26 September 2026. No claim of novel set-membership filtering is made.
No third-party implementation is incorporated.

- Jaulin and Walter, *Set inversion via interval analysis for nonlinear bounded-error
  estimation*, Automatica 29(4), 1053-1064 (1993), DOI
  https://doi.org/10.1016/0005-1098(93)90106-4. The publisher search rendering supplies
  the bounded-error consistency/set-inversion framing. Direct full-text access returned
  403. The present contractors are independently derived necessary interval constraints;
  no uninspected convergence or optimality theorem is inherited.
- Kieffer, Jaulin and Walter, *Guaranteed recursive non-linear state bounding using
  interval analysis*, International Journal of Adaptive Control and Signal Processing
  16, 193-218 (2002), https://doi.org/10.1002/acs.680. Publisher bibliographic material
  was checked; full algorithmic reproduction was not performed.
- Brunke, Zhou and Schoellig, *Robust Predictive Output-Feedback Safety Filter for
  Uncertain Nonlinear Control Systems*, https://arxiv.org/abs/2212.08900, CDC 2022.
  The current primary abstract explicitly connects bounded observation uncertainty and
  protective filtering. SA01's source note records its earlier full-PDF inspection.
  SA02 does not implement its robust observer or claim its recursive-feasibility theorem.
- Python Fraction semantics were checked against
  https://docs.python.org/3.13/library/fractions.html. Decimal-string interpretation and
  exact-binary-float interpretation differ; this phase explicitly retains SA01's
  decimal serialization contract and includes encoding error in the assumed sensor bound.
- The maintained development pins pytest 9.1.1 and Ruff 0.16.5 were verified through
  https://pypi.org/project/pytest/9.1.1/ and https://pypi.org/project/ruff/0.16.5/.
  No dependency change was needed. Runtime uses only the standard library.
- The s-FEAST licence was rechecked through the GitHub connector, blob
  c5302702b0f9f627636c536997fcf6f6ee1bcfd8 at
  https://github.com/treyra/s-FEAST/blob/master/LICENSE. Its restricted reuse terms
  remain. No s-FEAST code/data was copied or permission inferred.

MATHEMATICS.md gives the actual new containment argument, approximation boundaries
and exact small-system reference. Sources motivate the method; they do not replace
validation of this implementation. No physical calibration or external replication
is inferred from these literature checks.
