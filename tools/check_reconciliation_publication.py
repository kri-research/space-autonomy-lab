"""Check the frozen publication policy plus the exact approved expanded archive."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from verify_evidence_supplement import (
    ARCHIVE_SHA256,
    SUPPLEMENT,
    read_original_members,
    read_regular,
    strict_json,
    verify,
)

ARCHIVE_PATH = SUPPLEMENT + "/e005-original-records.tar.gz"


def validate_frozen_report(report: dict[str, Any]) -> None:
    """Only the identified archive may fail the old new-opaque-file rule."""
    inner = report["provenance_privacy_scan"]
    if not (
        report["passed"] is False
        and report["new_opaque_files"] == 1
        and report["new_opaque_files_preview"] == [ARCHIVE_PATH]
        and report["secret_matches"] == 0
        and report["secret_matches_preview"] == []
        and inner["passed"] is True
        and inner["matches"] == 0
        and inner["matches_preview"] == []
        and inner["opaque_files"] == 1
        and inner["opaque_files_preview"] == [ARCHIVE_PATH]
    ):
        raise ValueError("unexpected frozen publication finding")


def scan_text(raw: bytes) -> None:
    text = raw.decode("utf-8")
    private_terms = (
        "/" + "Users/",
        "/" + "home/",
        "file:" + "///",
        "chat" + "gpt",
        "co" + "dex",
        "cl" + "aude",
        "k-" + "dense",
        "ka" + "dy",
    )
    if any(term.casefold() in text.casefold() for term in private_terms):
        raise ValueError("private path or internal context in public payload")
    patterns = (
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"gh[pousr]_[A-Za-z0-9]{20,}",
        r"AKIA[0-9A-Z]{16}",
        r"(?i)(?:api[_-]?key|password|access_token)\s*[=:]\s*[\"'][A-Za-z0-9_/-]{16,}",
    )
    if any(re.search(pattern, text) for pattern in patterns):
        raise ValueError("credential-shaped content in public payload")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        verify(root)
        command = [
            sys.executable,
            "-m",
            "kri_space_autonomy.experiment_005_confirmatory.workflow",
            "release-scan",
        ]
        completed = subprocess.run(command, cwd=root, capture_output=True, timeout=180)
        if completed.returncode != 1:
            raise ValueError("unexpected frozen scanner exit status")
        report = strict_json(completed.stdout)
        validate_frozen_report(report)
        members = read_original_members(root)
        for raw in members.values():
            scan_text(raw)
        supplemental = 0
        for path in (root / SUPPLEMENT).rglob("*"):
            if path.is_file() and path.name != "e005-original-records.tar.gz":
                scan_text(read_regular(root, path.relative_to(root).as_posix()))
                supplemental += 1
        print(
            json.dumps(
                {
                    "status": "PASSED_EXPANDED_PUBLICATION_CHECK",
                    "frozen_scanner_passed": False,
                    "sole_opaque_exception": ARCHIVE_PATH,
                    "exception_sha256": ARCHIVE_SHA256,
                    "expanded_members_scanned": len(members),
                    "supplemental_text_files_scanned": supplemental,
                    "frozen_scanner_source_unchanged": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "INVALID", "error_type": type(exc).__name__}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
