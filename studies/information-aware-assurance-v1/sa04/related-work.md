# Primary sources and scope

Checked 26 September 2026. No external scientific implementation is copied.

- NASA NTRS 20240007986, *A Verification Framework for Runtime Assurance of Autonomous
  UAS*, Slagel et al. The official abstract connects monitor sample rate with time for
  protective intervention: https://ntrs.nasa.gov/citations/20240007986.
  Metadata/abstract were inspected; no PVS instance or proof was reproduced here.
- Brunke, Zhou and Schoellig, *Robust Predictive Output-Feedback Safety Filter for
  Uncertain Nonlinear Control Systems*, https://arxiv.org/abs/2212.08900.
  Current abstract and existing method notes were checked. An execution test does
  not inherit its robust-observer or recursive-feasibility hypotheses.
- Python 3.13 time documentation, https://docs.python.org/3.13/library/time.html,
  documents monotonic clocks and potentially overshooting sleep calls. Actual deadlines
  are rechecked after waits. Clock resolution is not physical clock calibration.
- Python subprocess documentation, https://docs.python.org/3.13/library/subprocess.html,
  was inspected for timeout and pipe semantics. The client uses bounded nonblocking
  I/O and explicitly terminates/reaps only children it created.
- Official pytest 9.1.1 metadata was checked at https://pypi.org/project/pytest/9.1.1/.
  The Ruff web page was unavailable once; publisher JSON metadata are checked separately
  in the command log. Existing isolated development pins are retained; runtime is stdlib.
- The current s-FEAST LICENSE was read via GitHub, blob
  c5302702b0f9f627636c536997fcf6f6ee1bcfd8, at
  https://github.com/treyra/s-FEAST/blob/master/LICENSE.
  No broader permission was obtained and no s-FEAST code/data was incorporated.

These sources motivate design and API choices; the implemented inclusion argument,
explicit trust boundaries and actual tests support this artifact. No novelty of active
sensing, runtime assurance, message binding or deadline enforcement is asserted.
