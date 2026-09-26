# Primary sources and reuse boundaries

Checked 27 September 2026. This phase evaluates existing KRI components and does
not claim a new active-sensing theorem or superiority to native published methods.

- Basilisk official documentation, https://avslab.github.io/basilisk/ and its
  installation, spacecraft and extForceTorque pages, explains the spacecraft,
  force-frame and integration interfaces. Cached documentation displayed differing
  version headers. The actual selected PyPI wheel and upstream tag are **2.12.0**;
  version selection is bound to those artifacts rather than a cached page header.
  The v2.12.0 scenarioBasicOrbit source was inspected for central-body setup and SI
  state conventions. No example source is copied into KRI.
- Basilisk ISC licence was inspected in the upstream repository. The software is
  installed as a dependency; KRI distributes its own adapter. Applicable upstream
  copyright and permission notices remain in the installed distribution.
- Brunke, Zhou and Schoellig, *Robust Predictive Output-Feedback Safety Filter for
  Uncertain Nonlinear Control Systems*, CDC 2022, https://arxiv.org/abs/2212.08900.
  Its observer and terminal assumptions support a stronger continuing-control
  obligation than this finite manoeuvre. SA05 does not reconstruct that method or
  transfer its recursive-feasibility theorem to a finite prefix.
- Ragan, Riviere, Hadaegh and Chung, *Online tree-based planning for active spacecraft
  fault estimation and collision avoidance*, Science Robotics 9, eadn4722 (2024),
  https://doi.org/10.1126/scirobotics.adn4722. Direct publisher access returned 403;
  prior-stage source inspections and their access limits remain recorded. Its
  active diagnosis already addresses information/control coupling. The currently
  inspected s-FEAST licence, blob c5302702b0f9f627636c536997fcf6f6ee1bcfd8 at
  https://github.com/treyra/s-FEAST/blob/master/LICENSE, restricts further use without
  permission. No permission was obtained and no code or data is incorporated.
- Laine, Chiu and Tomlin, *Eyes-Closed Safety Kernels*, RSS 2020,
  https://arxiv.org/abs/2005.07144, provides prior work on protection during loss of
  observation. The present preloaded finite coast is not a maximal safety kernel.
- SciPy official binomtest documentation,
  https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.binomtest.html,
  describes exact binomial testing and confidence intervals. SA05 separately tests
  its direct combinatorial paired calculation against the library implementation.

Consequently, the four schedules are matched engineering alternatives sharing
KRI's finite obligation, not labelled implementations of these published controllers.
A native established active-sensing comparator is not included: the closest available
code has restricted reuse, and no verified like-for-like implementation with the
same assumptions was identified for this stage. This prevents a state-of-the-art
ranking claim, but not the declared internal comparative question.
