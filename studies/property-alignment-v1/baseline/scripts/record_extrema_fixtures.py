"""Record forced-failure fixtures against verified originals and the additive helper."""

from pathlib import Path
from types import SimpleNamespace
import sys
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validation.loader import originals
from validation.extrema import bounded_extreme

_, _, g4, g5, _ = originals()
rows = []
for name, module in [("E004", g4), ("E005", g5)]:
    for maximize in [True, False]:
        f = (lambda t: 1 - 8 * (t - 0.5) ** 2) if maximize else (lambda t: -1 + 8 * (t - 0.5) ** 2)

        def failed(*args, **kwargs):
            return SimpleNamespace(success=False, x=0.5, fun=0.0)

        saved = module.minimize_scalar
        try:
            module.minimize_scalar = failed
            old = module._bounded_extreme(f, 1.0, maximize=maximize)
        finally:
            module.minimize_scalar = saved
        fixed = bounded_extreme(f, 1.0, maximize=maximize, optimizer=failed)
        assert old[0] == (-1.0 if maximize else 1.0)
        assert fixed.value == (1.0 if maximize else -1.0) and fixed.unresolved
        rows.append(
            {
                "source": name,
                "maximize": maximize,
                "original_returned_extreme": old[0],
                "sampled_extreme": fixed.sampled_extreme,
                "corrected_returned_extreme": fixed.value,
                "unresolved": list(fixed.unresolved),
                "historical_occurrence_established": False,
            }
        )
(ROOT / "data/extrema_fixture_results.json").write_text(json.dumps(rows, indent=2) + "\n")
print("Four forced-failure fixtures reproduced against the original helpers.")
