# Fixed three-state robustness study

This additive post hoc study quantifies perturbation ranges for the existing
three-state spacecraft example with its three original pair commands held fixed.
It separates uncertain information boxes that retain the nominal obstruction
witnesses from a stronger statement about every independently shifted triple.
The latter requires a new uniform right-hand-side bound, not old hash reuse.

The unchanged R02 192-bit HCW response is the numerical dependency. Read
DERIVATION.md and protocol.json for the exact mathematical family, continuous-time
bounds, units, 14-step searches, known zero-input queue, model variation and limits.
This is a newly derived sufficient-margin calculation, not an independent human
replication, general optimization theorem, sensor specification or physical test.
Original frozen source and all R03 audit outputs remain unchanged.

Run tests separately from the existing study suites:

```sh
python -m pytest boundary_robustness_v1/tests
```

The systematic study is source-bound before execution. Its recorded-result
verification may recheck the same fixed sensitivity calculations; it never runs
an original protected campaign, changes a saved command or recomputes an online
budget verdict. All noncertified bounds and any implementation failures remain.
The generated LaTeX fragment is for R05 integration; the existing main manuscript
and supplement are not rewritten here.

## Fixed-output reproduction

From the study root with Python3.13.5:

```sh
python -m boundary_robustness_v1.study verify --output boundary_robustness_v1/recorded --freeze boundary_robustness_v1/frozen/study.json --study-id de8cb9a5d3e2c73b2a9f748e3e07cea301fb0cf8b739960b7d47fe38ad439b23 --recompute
python -m pytest boundary_robustness_v1/tests robustness_evidence_tests
```

To regenerate the table, figure and LaTeX fragment, use `python -m boundary_robustness_v1.presentation --data boundary_robustness_v1/recorded --freeze boundary_robustness_v1/frozen/study.json --study-id de8cb9a5d3e2c73b2a9f748e3e07cea301fb0cf8b739960b7d47fe38ad439b23 --output /a/new/local/output-directory` with Matplotlib installed in an isolated environment. Compile `preview.tex` there with `latexmk -pdf preview.tex`. The public figure is SVG; manuscript PDFs remain local. See RESULTS.md for the two scopes and the noncertified search brackets.

The public presentation export normalizes CSV line endings to LF and removes trailing horizontal whitespace from SVG lines. `presentation/manifest.json` records both raw and displayed hashes. The frozen generator and numerical records remain unchanged; raw local generation is retained. The public CSV values and SVG drawing tokens are unchanged by this serialization step.

The two generated mathematical LaTeX fragments are published as `presentation/derivation.tex.txt` and `presentation/sensitivity_table.tex.txt`, with unchanged bytes. Restore the indicated `.tex` names when using them locally. This preserves the repository's existing protection against accidental manuscript uploads without changing ignore rules. The local R05 materials already have the correct `.tex` names.
