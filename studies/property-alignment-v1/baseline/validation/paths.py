"""Resolve explicitly supplied, immutable historical evidence without changing it."""

from pathlib import Path
import os
import subprocess

HISTORICAL_COMMIT = "5539de5753092b09fd78351095292e7627047794"


def evidence_root() -> Path:
    value = os.environ.get("SAL_EVIDENCE_ROOT")
    if not value:
        raise RuntimeError("Set SAL_EVIDENCE_ROOT to a separate pinned evidence checkout")
    path = Path(value).expanduser().resolve(strict=True)
    command = ["git", "--no-replace-objects", "-C", str(path)]
    head = subprocess.check_output(command + ["rev-parse", "HEAD"], text=True).strip()
    status = subprocess.check_output(
        command + ["status", "--porcelain", "--untracked-files=no"], text=True
    ).strip()
    if head != HISTORICAL_COMMIT or status:
        raise RuntimeError(
            "Historical evidence must have the pinned commit and clean tracked files"
        )
    return path
