import json

from kri_space_autonomy.evidence import EvidenceLogger
from kri_space_autonomy.scenario import load_scenario
from kri_space_autonomy.simulation import run_episode


def test_evidence_hash_chain_detects_tampering(tmp_path):
    path = tmp_path / "evidence.jsonl"
    scenario = load_scenario("scenarios/nominal.json")
    run_episode(scenario, "protected", path)
    assert EvidenceLogger.verify_jsonl(path)

    lines = path.read_text(encoding="utf-8").splitlines()
    data = json.loads(lines[2])
    data["confidence"] = 0.123456
    lines[2] = json.dumps(data)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert not EvidenceLogger.verify_jsonl(path)
