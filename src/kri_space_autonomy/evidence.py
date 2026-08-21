from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .types import GateDecision, Observation, PolicyDecision, SpacecraftState


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False)


@dataclass(frozen=True)
class EvidenceRecord:
    scenario_id: str
    step: int
    telemetry: dict[str, Any]
    autonomy_observation: dict[str, Any]
    proposed_action: dict[str, Any]
    executed_action: dict[str, Any]
    inference_output: float
    confidence: float
    model_hash: str
    active_safety_constraints: tuple[str, ...]
    override_reason: str | None
    fault_event: str | None
    previous_hash: str
    record_hash: str


class EvidenceLogger:
    """Produces a hash-chained event log approximating KRI-STD-001 §5.2 evidence fields."""

    def __init__(self, scenario_id: str):
        self.scenario_id = scenario_id
        self.records: list[EvidenceRecord] = []
        self._previous_hash = "GENESIS"

    def append(
        self,
        state: SpacecraftState,
        autonomy_observation: Observation,
        policy_decision: PolicyDecision,
        gate_decision: GateDecision,
        executed_acceleration_mps2: float,
        fault_event: str | None = None,
    ) -> EvidenceRecord:
        body: dict[str, Any] = {
            "scenario_id": self.scenario_id,
            "step": state.step,
            "telemetry": state.to_dict(),
            "autonomy_observation": autonomy_observation.to_dict(),
            "proposed_action": gate_decision.proposed.to_dict(),
            "executed_action": {"acceleration_mps2": executed_acceleration_mps2},
            "inference_output": policy_decision.raw_output,
            "confidence": policy_decision.confidence,
            "model_hash": policy_decision.model_hash,
            "active_safety_constraints": gate_decision.active_constraints,
            "override_reason": gate_decision.reason,
            "fault_event": fault_event,
            "previous_hash": self._previous_hash,
        }
        record_hash = hashlib.sha256(_canonical_json(body).encode("utf-8")).hexdigest()
        record = EvidenceRecord(**body, record_hash=record_hash)
        self.records.append(record)
        self._previous_hash = record_hash
        return record

    def write_jsonl(self, path: str | Path) -> None:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as handle:
            for record in self.records:
                handle.write(_canonical_json(asdict(record)) + "\n")

    @staticmethod
    def verify_jsonl(path: str | Path) -> bool:
        previous_hash = "GENESIS"
        with Path(path).open("r", encoding="utf-8") as handle:
            for line in handle:
                data = json.loads(line)
                record_hash = data.pop("record_hash")
                if data["previous_hash"] != previous_hash:
                    return False
                calculated = hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest()
                if calculated != record_hash:
                    return False
                previous_hash = record_hash
        return True
