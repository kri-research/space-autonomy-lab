"""Write-once source binding for the bounded development protocol."""

from pathlib import Path
import hashlib
import json

PACKAGE = Path(__file__).resolve().parent


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def inventory():
    names = (
        "__init__.py",
        "barrier.py",
        "binding.py",
        "certificates.py",
        "common.py",
        "predictive.py",
        "run.py",
        "solver.py",
        "protocol.json",
        "requirements.txt",
    )
    files = [PACKAGE / n for n in names]
    return {p.name: digest(p) for p in sorted(files)}


def verify_seal():
    path = PACKAGE / "seal.json"
    record = json.loads(path.read_text())
    if record["source_sha256"] != inventory():
        raise ValueError("Development source or protocol changed after sealing")
    study = PACKAGE.parent
    for name, expected in record.get("dependency_sha256", {}).items():
        if digest(study / name) != expected:
            raise ValueError("Bound dependency changed: " + name)
    return record


if __name__ == "__main__":
    print(json.dumps(verify_seal(), indent=2))
