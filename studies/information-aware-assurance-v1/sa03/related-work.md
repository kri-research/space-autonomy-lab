# SA03 prior methods and reuse boundaries

Checked 26 September 2026. This implementation is an original, small integration
of established ideas. No general novelty, optimality or superiority to the methods
below is established. No third-party research code or data is incorporated.

## Primary material inspected

1. Ragan, Riviere, Hadaegh and Chung, *Online tree-based planning for active
   spacecraft fault estimation and collision avoidance*, Science Robotics 9,
   eadn4722 (2024), https://doi.org/10.1126/scirobotics.adn4722.
   The publisher search rendering supplied the main text, including active diagnosis,
   marginalized filtering, chance-constrained search, and the queued real-time
   execution discussion. Direct publisher opening returned 403. Some rendered
   equations and supplementary proofs were unavailable; the authors' experiments
   and safety probabilities were not independently reproduced.
2. Brunke, Zhou and Schoellig, *Robust Predictive Output-Feedback Safety Filter
   for Uncertain Nonlinear Control Systems*, CDC 2022,
   https://arxiv.org/pdf/2212.08900. The complete parsed nine-page paper was
   inspected, especially the bounded-error observer assumptions, optimization (18),
   Algorithm 1 and recursive-feasibility/constraint-satisfaction result. This phase
   does not inherit that theorem without its observer and terminal conditions.
3. Laine, Chiu and Tomlin, *Eyes-Closed Safety Kernels: Safety of Autonomous Systems
   Under Loss of Observability*, RSS 2020, DOI 10.15607/RSS.2020.XVI.096,
   https://www.roboticsproceedings.org/rss16/p096.html and
   https://arxiv.org/pdf/2005.07144. The parsed full paper's problem formulation
   and blackout-control construction were inspected. Its differential-game/Hamilton-
   Jacobi solutions are not implemented or treated as numerically reproduced here.
   Public PDF screenshot retrieval failed; no visual assessment is claimed.

## Comparison of obligations and implementation

| Method | Information and choices | Native protection and timing | Relationship to SA03 |
| --- | --- | --- | --- |
| s-FEAST | Joint state/fault beliefs, active actions and simulated observation branches | Stochastic/chance-constrained planning, constant fault hypotheses, real-time queued action implementation | Already studies safe active diagnosis. SA03's complete bounded reading cover and fixed finite control menu are a different engineering specialization, not a stronger substitute. |
| RPOF-SF | Output measurements, a robust observer and protective modification of a proposed input | Recursive feasibility and continuing constraints require stated observer, model and terminal conditions | SA03's one hold plus finite coast has a much narrower obligation. Sensor selection is an added experimental question, not grounds for controller-superiority claims. |
| Eyes-Closed Safety Kernels | Controlled self-state with lost observation of an external factor | Offline game-based safety under observation loss, with the specified blackout and reachable-set assumptions | Establishes prior art for protection while blind. SA03 checks one prescribed waiting input, not a maximal blackout viability kernel. |
| SA03 candidate | SA02 outer state/bias cells; no extra sensor, one range, or one bearing | Complete interval reading tree, missing-reading branch and continuous finite hold/coast checks; modeled timing | The supported contribution is an inspectable composition and refutation examples. No published method is relabelled as a new theorem. |

The development comparators are explicitly simple fixed-range, fixed-bearing and
uncertainty-triggered schedules sharing this same finite obligation, initial information,
command menu and resource budget. They are validated on their own goal-eligible fixtures.
They are not implementations of the three published methods and cannot establish
state-of-the-art superiority. A like-for-like native comparison would require separate
model/observer/terminal choices and a new protocol; it is not manufactured by weakening
a published method's guarantees to this short horizon.

## Licence and dependencies

The s-FEAST LICENSE was rechecked through the GitHub connector at
https://github.com/treyra/s-FEAST/blob/master/LICENSE, Git blob
c5302702b0f9f627636c536997fcf6f6ee1bcfd8. It permits personal and educational use and
requires written permission for further use. No permission was obtained; no code/data
was copied. The independently written mathematics and algorithms here are attributed
to their established context without reproducing restricted implementation content.

The scientific runtime uses Python's standard library and unchanged KRI components.
CPython 3.13.5, pytest 9.1.1 and Ruff 0.16.5 are the inherited isolated test environment.
Official package metadata is checked before the source freeze; no historical dependency
lock or global environment is changed. Source identities and implementation adaptations
are listed in source-map.json. Existing SA01/SA02 records remain separate evidence.
