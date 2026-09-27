"""Read-only approval of individually reviewed, hash-pinned SA05 plot images.

The original frozen scanner and its archive-only validator remain unchanged.
No extension, directory or self-reported manifest grants a general exception.
"""

from __future__ import annotations

import copy
import hashlib
import struct
from pathlib import Path
from typing import Any

REVIEWED_PNG_SHA256: dict[str, str] = dict(
    [
        (
            "studies/information-aware-assurance-v1/sa05/development_recorded/plots/goal-acquisition.png",
            "7df314563436d8303f482504825da01e30b116f030d8eeb02ed1e1dead24fc9e",
        ),
        (
            "studies/information-aware-assurance-v1/sa05/development_recorded/plots/observation-requests.png",
            "87cc69c5db94ad7096ed59b068a566071157a148089facc0c93dca66a7bd9a5a",
        ),
        (
            "studies/information-aware-assurance-v1/sa05/recorded/plots/goal-acquisition.png",
            "7df314563436d8303f482504825da01e30b116f030d8eeb02ed1e1dead24fc9e",
        ),
        (
            "studies/information-aware-assurance-v1/sa05/recorded/plots/observation-requests.png",
            "1cfe433f308e83a6ee26a17d29bf156535f85b6f355a471a154697ad5eea23d5",
        ),
    ]
)


def reviewed_pngs(root: Path) -> list[str]:
    for name, expected in REVIEWED_PNG_SHA256.items():
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing reviewed plot")
        raw = path.read_bytes()
        if not 100 <= len(raw) <= 2_000_000 or hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("Reviewed plot content mismatch")
        if raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[-12:] != b"\0\0\0\0IEND\xaeB`\x82":
            raise ValueError("Reviewed plot is not a complete PNG")
        if raw[12:16] != b"IHDR" or struct.unpack(">II", raw[16:24]) != (1920, 768):
            raise ValueError("Reviewed plot dimensions changed")
    return sorted(REVIEWED_PNG_SHA256)


def normalize_reviewed_figures(report: dict[str, Any], root: Path) -> dict[str, Any]:
    """Remove only verified, exact new image findings before old validation.

    Secret/privacy fields and the old archive finding pass through unchanged.
    Any additional image, opaque object or missing finding still fails closed.
    """
    approved = reviewed_pngs(root)
    preview = report["new_opaque_files_preview"]
    if report["new_opaque_files"] != len(preview) or len(preview) != len(set(preview)):
        raise ValueError("Incomplete or duplicated opaque findings")
    if not set(approved).issubset(preview):
        raise ValueError("Missing expected reviewed-image finding")
    result = copy.deepcopy(report)
    result["new_opaque_files_preview"] = [name for name in preview if name not in approved]
    result["new_opaque_files"] -= len(approved)
    return result
