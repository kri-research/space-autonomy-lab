# Prospective evaluation design

This subproject is the Task 07 bridge between development and the separately
authorized Task 08 protected run. Task 07 may execute only the development
and calibration namespaces. The protected namespace is generated from a
disjoint deterministic seed domain and is not evaluated here.

The primary quantity is balanced benchmark coverage: among cases for which
every hidden hypothesis has a separately validated one-second HCW prefix,
what fraction receives, within the one-second decision budget, either a
validated common-prefix action or a residual-checked HCW first-command
obstruction? A finite prefix is not full recoverability. A negative HCW
certificate does not imply that every hidden state is individually unsafe.

Four equally weighted synthetic strata are fixed before the pilot:

- interior_pair: ordinary paired ambiguity with substantial corridor margin.
- radial_boundary: paired ambiguity close to opposing corridor side walls.
- three_face_boundary: three hypotheses near two side walls and the outer
  approach boundary, designed to expose higher-order shared-action conflicts.
- timing_bounded_pair: bounded-state ambiguity with one second of data age,
  one second of command delay, a fixed zero queue and bounded disturbance.

The generator is not an operational prevalence model. Historical E004/E005
episodes, the known midpoint diagnostic and all Task 04-06 cases are excluded
from the new protected denominator. The fixed stress cases are diagnostic
assumption checks only and never enter the primary estimate.
