"""Load byte-verified original modules with explicit dependency injection.

Only relative import statements are removed from geometry/control ASTs. Bodies are
unchanged. Configs and ideal-information snapshots belong to the new diagnostic.
"""

from __future__ import annotations
import ast
import hashlib
import json
import sys
import types
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    "e004_geometry": "bb5308c8e1785ad240577e00205bd1badbbd74af",
    "e005_geometry": "f350d166d3c85637730d005f2bd081f330d02930",
    "e004_control": "67a1d65072b3bed88f84b3377cc4f7d8f6247fbe",
    "e004_dynamics": "bb6d9370baf73ff8919337d3837614087e152560",
    "e005_dynamics": "db3050c07bdcaadd96d3f0a506e88c06c450e6ec",
}


class FilterHealth(StrEnum):
    VALID = "valid"
    DEGRADED = "degraded"
    DIVERGED = "diverged"


def config():
    return types.SimpleNamespace(
        **json.loads((ROOT / "data/configuration_extract.json").read_text())["foundation"]
    )


def checked_source(name: str) -> tuple[Path, bytes]:
    path = ROOT / "source_evidence" / f"{name}.py"
    raw = path.read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if actual != SOURCES[name]:
        raise ValueError(f"Original Git blob identity failed for {name}")
    return path, raw


def load(name: str, injected: dict | None = None):
    path, raw = checked_source(name)
    tree = ast.parse(raw, filename=str(path))
    tree.body = [
        node for node in tree.body if not (isinstance(node, ast.ImportFrom) and node.level)
    ]
    module = types.ModuleType(f"sal_original_{name}")
    module.__file__ = str(path)
    module.__dict__.update(injected or {})
    sys.modules[module.__name__] = module
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


def originals(*, expanded_cache: bool = False):
    d4, d5 = load("e004_dynamics"), load("e005_dynamics")
    if expanded_cache:
        # Pure memoization only. Identical augmented-exponential calculation.
        d4._cached_discrete = lru_cache(maxsize=32768)(d4._cached_discrete.__wrapped__)
    g4 = load("e004_geometry", {"propagate_exact": d4.propagate_exact})
    g5 = load(
        "e005_geometry",
        {"pair_to_relative": d5.pair_to_relative, "propagate_fixed": d5.propagate_fixed},
    )
    c4 = load(
        "e004_control",
        {
            "discrete_matrices": d4.discrete_matrices,
            "FilterHealth": FilterHealth,
            "HCWSegment": g4.HCWSegment,
            "evaluate_segment": g4.evaluate_segment,
        },
    )
    return d4, d5, g4, g5, c4
