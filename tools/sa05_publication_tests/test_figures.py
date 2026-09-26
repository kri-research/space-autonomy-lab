import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_reconciliation_publication as old
import check_sa05_figure_publication as figures

ROOT = Path(__file__).resolve().parents[2]


def report():
    archive = old.ARCHIVE_PATH
    approved = sorted(figures.REVIEWED_PNG_SHA256)
    return dict(
        passed=False,
        new_opaque_files=1 + len(approved),
        new_opaque_files_preview=approved + [archive],
        secret_matches=0,
        secret_matches_preview=[],
        provenance_privacy_scan=dict(
            passed=True,
            matches=0,
            matches_preview=[],
            opaque_files=1,
            opaque_files_preview=[archive],
        ),
    )


def test_reviewed_plots_and_unchanged_frozen_validator():
    value = report()
    with pytest.raises(ValueError):
        old.validate_frozen_report(value)
    old.validate_frozen_report(figures.normalize_reviewed_figures(value, ROOT))
    assert value["new_opaque_files"] > 1


@pytest.mark.parametrize("field", ["unexpected", "secret", "inner", "count", "duplicate"])
def test_no_other_finding_is_waived(field):
    value = report()
    if field == "unexpected":
        value["new_opaque_files"] += 1
        value["new_opaque_files_preview"].append("unreviewed.png")
    elif field == "secret":
        value["secret_matches"] = 1
    elif field == "inner":
        value["provenance_privacy_scan"]["matches"] = 1
    elif field == "count":
        value["new_opaque_files"] += 1
    else:
        value["new_opaque_files"] += 1
        value["new_opaque_files_preview"].append(value["new_opaque_files_preview"][0])
    with pytest.raises(ValueError):
        old.validate_frozen_report(figures.normalize_reviewed_figures(value, ROOT))


@pytest.mark.parametrize("change", ["missing", "changed", "symlink"])
def test_reviewed_bytes_cannot_be_substituted(tmp_path, change):
    for name in figures.REVIEWED_PNG_SHA256:
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, p)
    name = next(iter(figures.REVIEWED_PNG_SHA256))
    p = tmp_path / name
    if change == "missing":
        p.unlink()
    elif change == "changed":
        p.write_bytes(p.read_bytes() + b"extra")
    else:
        p.unlink()
        p.symlink_to(ROOT / name)
    with pytest.raises(ValueError):
        figures.normalize_reviewed_figures(report(), tmp_path)
