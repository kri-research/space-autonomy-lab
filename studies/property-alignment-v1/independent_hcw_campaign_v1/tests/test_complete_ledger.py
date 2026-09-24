"""Complete recorded-campaign and receipt mutation tests, no policy execution."""

from copy import deepcopy
from functools import lru_cache
import pytest
from independent_hcw_campaign_v1.artifact import verify, ROOT
from independent_hcw_campaign_v1.population import load_original
from independent_hcw_campaign_v1.report import summarize
from independent_hcw_audit_v1.schema import strict_json


@lru_cache(maxsize=1)
def inputs():
    _, records, _, population = load_original()
    archive = [
        strict_json(x) for x in (ROOT / "recorded/audit_records.jsonl").read_text().splitlines()
    ]
    receipts = {
        x["path"].split("/")[-1][:-5]: strict_json(x["raw_utf8"])
        for x in archive
        if x["path"].startswith("receipts/")
    }
    return records, [receipts[r["key"]] for r in records], population


def test_recorded_proof_transcripts_and_results_rebuild():
    answer = verify()
    assert answer["passed"] and answer["selected"] == 768 and answer["discrepancies"] == 0
    assert answer["independent_statuses"] == {
        "verified_prefix": 725,
        "verified_obstruction": 31,
        "no_on_time_certificate": 12,
    }
    assert answer["qualification_outcomes"] == {"verified_prefix": 1728}


def test_exact_case_and_witness_coverage():
    records, receipts, pop = inputs()
    rows, issues, summary = summarize(records, receipts, pop)
    assert len(rows) == len({r["key"] for r in rows}) == 768 and not issues
    assert (
        summary["qualification_witnesses_checked"]
        == summary["qualification_witnesses_expected"]
        == 1728
    )
    assert summary["original_statuses"] == {
        "certified_common_prefix": 725,
        "proved_no_common_held_command": 31,
        "unresolved": 9,
        "unresolved_budget": 3,
    }
    assert summary["new_probability_interval"] is None
    assert sum(r["original_candidate"]["status"] == "unresolved_budget" for r in rows) == 3


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate_source",
        "duplicate_receipt",
        "swap",
        "wrong_hash",
        "qualification_missing",
        "qualification_swap",
        "original_time",
    ],
)
def test_full_ledger_rejects_changes(mutation):
    original, original_receipts, pop = inputs()
    records = list(original)
    receipts = list(original_receipts)
    if mutation == "missing":
        records.pop()
    if mutation == "duplicate_source":
        records[1] = records[0]
    if mutation == "duplicate_receipt":
        receipts[1] = receipts[0]
    if mutation == "swap":
        receipts[0], receipts[1] = receipts[1], receipts[0]
    if mutation in ("wrong_hash", "qualification_missing", "qualification_swap"):
        receipts[0] = deepcopy(receipts[0])
        if mutation == "wrong_hash":
            receipts[0]["binding"]["job_sha256"] = "0" * 64
        if mutation == "qualification_missing":
            receipts[0]["result"]["qualification_witnesses"].pop()
        if mutation == "qualification_swap":
            receipts[0]["result"]["qualification_witnesses"].reverse()
    if mutation == "original_time":
        records[0] = deepcopy(records[0])
        records[0]["episode"]["candidate"]["wall_s"] = 0
    with pytest.raises(ValueError):
        summarize(records, receipts, pop)


def test_all_reserve_records_are_structurally_accounted():
    _, _, pop = inputs()
    assert pop["reserve"] == pop["qualification_records"] == 1152
    assert pop["selection_rule_reconstructed"] is True
    assert pop["unselected_qualification_proofs_independently_rechecked"] is False
    assert len(pop["retired_before_reserve"]) == 2
