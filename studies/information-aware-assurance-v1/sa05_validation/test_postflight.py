from copy import deepcopy
from pathlib import Path

import pytest

from iaa.artifact import read_json
from sa05_validation.verify import validate_report

HERE = Path(__file__).resolve().parent


def report():
    return read_json(HERE / "independent-numerical-audit.json")


def test_full_stored_independent_audit_accounting():
    assert validate_report(report())["numerical_cells_matched"] == 448


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "position", "acquisition", "scope", "count", "source"]
)
def test_audit_mutations_are_not_accepted(mutation):
    changed = deepcopy(report())
    if mutation == "missing":
        changed["checks"].pop()
    elif mutation == "duplicate":
        changed["checks"][1] = changed["checks"][0]
    elif mutation == "position":
        changed["checks"][0]["max_position_error_m"] = 1e-4
    elif mutation == "acquisition":
        changed["checks"][0]["recomputed_acquired_goal"] = True
    elif mutation == "scope":
        changed["physical_validation"] = True
    elif mutation == "count":
        changed["checked_cells"] -= 1
    else:
        changed["audit_source_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        validate_report(changed)
