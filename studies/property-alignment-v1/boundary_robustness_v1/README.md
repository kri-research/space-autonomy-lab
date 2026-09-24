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
