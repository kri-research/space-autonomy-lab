# Research basis and access record

Checked 26 September 2026. These sources informed the engineering scope; SA01 makes
no novelty or superiority claim. No third-party research implementation is copied.

| Source | Material actually obtained and relevance | Boundary |
| --- | --- | --- |
| [ESDI Space x Data](https://www.esdi.ch/data/) and [official technical call, Issue A](https://ideas.esa.int/core/apps/IMT/UploadedFiles/00/f_49c4b535b0fad1a5a38702c86c9acbc9/01_PSI_PhiLab_at_ESDI_-_Open_Call_Data__Issue_A.pdf?v=1778112389) | Public page and technical text, especially pp. 1-3, connect onboard decisions, heterogeneous observations, uncertainty, assurance, traceability and resource constraints. | The call is closed. This is technical motivation, not an application or an endorsed requirement for this demonstrator. The PDF's cover reference and template have different dates; neither is silently corrected. |
| Ragan, Riviere, Hadaegh and Chung, [Online tree-based planning for active spacecraft fault estimation and collision avoidance](https://doi.org/10.1126/scirobotics.adn4722), Science Robotics 9, eadn4722 (2024) | Publisher main-text search rendering supplied abstract, methods overview, results and discussion, including marginalized filtering, chance-constrained tree search, active diagnosis and a real-time queued-action implementation. | Direct DOI open returned 403; some rendered equations are missing. Supplementary proofs and experimental code were not independently reproduced. This is substantial prior art for safe active diagnosis, not an untouched KRI comparator. |
| Brunke, Zhou and Schoellig, [Robust Predictive Output-Feedback Safety Filter for Uncertain Nonlinear Control Systems](https://arxiv.org/abs/2212.08900), CDC 2022 | Full 9-page PDF obtained; sections on bounded observer error, i-IOSS assumptions, tube prediction and terminal conditions inspected. | Its observer and recursive-feasibility guarantees need their actual assumptions. This phase's coarse prior propagation and finite coasting do not implement or inherit them. |

The specific next question is whether measurement information can justify a useful
common action before its execution opportunity expires. Active sensing, robust safety
filters and command queues already exist. SA01 builds the operating contract and
engineering fixtures; it does not yet solve or establish novelty of this question.

## Reuse and licences

The current s-FEAST [LICENSE](https://github.com/treyra/s-FEAST/blob/master/LICENSE),
Git blob `c5302702b0f9f627636c536997fcf6f6ee1bcfd8`, limits code/data reuse to
personal and educational use and requires written permission for further use.
No permission was requested and no s-FEAST code/data is integrated or redistributed.
The cited papers inform independently written equations and design decisions only.

Runtime uses Python's standard library. Development tools are pinned to pytest 9.1.1
and Ruff 0.16.5; their project-maintainer PyPI records were checked. Both use MIT
licensing. No global environment or original scientific dependency lock is changed.
The existing KRI repository licence applies to the new, original source.

## Existing KRI components inspected

See `source-map.json` for exact source identities. Candidate certificates distinguish
common finite prefixes from recovery and assume supplied information sets; their
one-second queue interface and old geometry are not silently reused. Protective
baselines have stronger terminal and observer obligations than this fixture. The
existing adjudicator explains the conventional Picard inclusion used here, but its
higher-order code is not copied. Existing execution records supply conceptual
request/command and timing patterns, without transferring host timing or hardware
claims. Prior numerical results remain separate evidence.
