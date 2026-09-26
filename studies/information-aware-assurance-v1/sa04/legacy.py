"""Reuse the original bounded JSON and timing interface without changing it."""

import importlib.util
from pathlib import Path

PATH = (
    Path(__file__).resolve().parents[2]
    / "property-alignment-v1/execution_validation_v1/protocol.py"
)
spec = importlib.util.spec_from_file_location("kri_preserved_execution_protocol", PATH)
protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(protocol)
