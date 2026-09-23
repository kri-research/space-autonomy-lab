"""Write-once execution records and source-bound protocol verification."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import platform
from baseline.validation.paths import evidence_root

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_json(path, value):
    with Path(path).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write(chr(10))


def source_hashes():
    files = set()
    for folder in ("causal", "adjudication", "specification"):
        files.update((ROOT / folder).glob("*.py"))
    files.update(
        [
            ROOT / "specification/property_contract.json",
            ROOT / "adjudication/input_commands.json",
            PACKAGE / "protocol.json",
        ]
    )
    return {str(p.relative_to(ROOT)): sha(p) for p in sorted(files)}


def historical_sources():
    root = evidence_root()
    names = [
        *root.glob("src/kri_space_autonomy/experiment_004/*.py"),
        *root.glob("src/kri_space_autonomy/experiment_005/*.py"),
        root / "experiments/004/config.json",
        root / "experiments/005/config.json",
    ]
    return {str(p.relative_to(root)): sha(p) for p in sorted(names)}


def seal():
    value = {
        "schema": "sal-causal-seal/1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "protocol_sha256": sha(PACKAGE / "protocol.json"),
        "source_sha256": source_hashes(),
        "historical_source_sha256": historical_sources(),
        "registration_scope": "prospective local developmental protocol and public commit; not external preregistration",
    }
    save_json(PACKAGE / "seal.json", value)
    return value


def verify_seal():
    value = json.loads((PACKAGE / "seal.json").read_text())
    if (
        value["source_sha256"] != source_hashes()
        or value["historical_source_sha256"] != historical_sources()
    ):
        raise ValueError("Scientific source changed after sealing")
    if value["protocol_sha256"] != sha(PACKAGE / "protocol.json"):
        raise ValueError("Protocol changed")
    return value


def new_output(value):
    path = Path(value).expanduser().absolute()
    if any(p.is_symlink() for p in [path, *path.parents]):
        raise ValueError("Symlink output prohibited")
    path = path.resolve()
    if any(path.is_relative_to(p) for p in [ROOT.parents[1], evidence_root()]):
        raise ValueError("Execution output must be outside both repositories")
    path.mkdir(parents=True, exist_ok=False)
    return path


def manifest(directory):
    directory = Path(directory)
    files = {
        str(p.relative_to(directory)): sha(p)
        for p in sorted(directory.rglob("*"))
        if p.is_file() and p.name != "manifest.json"
    }
    save_json(directory / "manifest.json", files)
    return files


def environment():
    import numpy
    import scipy

    return {
        "python": platform.python_version(),
        "numpy": numpy.__version__,
        "scipy": scipy.__version__,
        "system": platform.system(),
        "architecture": platform.machine(),
        "blas_threads": os.environ.get("OPENBLAS_NUM_THREADS", "unspecified"),
    }
