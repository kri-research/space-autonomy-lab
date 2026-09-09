"""Inspect fixed historical identities using read-only Git object queries.

Exit 0: complete matches. Exit 1: known unresolved provenance. Exit 2: verification
error or unexpected drift. Never fetch, check out, repair or execute scientific code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

RELEASE_COMMIT = "f0e9e5d8c140ca3d5eea71cee97fd29f23bffe12"
MAINTENANCE_COMMIT = "e85e1d4e1af917913f00e0574ead87909d5da792"
E002_SNAPSHOT = "15879624c68b8cf93709f4c108735495e368e649"
E002B_SNAPSHOT = "2459cab197a1e759b50056bfee30416c4ced3013"
E004_SNAPSHOT = "cfb56b2a5510916e5295ae9b654b3849f4a8d7e1"
E005_SNAPSHOT = "46c6de41afa46e7e43b1c6074e59ba54dd3d99b8"
PILOT_SNAPSHOT = "cf007e1cd7e44002069a8a5812867201d349f292"
E002B_EXPECTED = "c45a7cb29489c94460f64560b6f85e578fbbd076b9f4d325116c463dcf75b1f1"
E002B_OBSERVED = "4168fa738e5023ef3d59b7b46f700e54ec4bf881e3144a63329be16b9a747a70"
MATCHED = "MATCHED HISTORICAL SNAPSHOT"
PHASE = "CURRENT-CHECKOUT DIFFERENCE EXPLAINED BY PHASE HISTORY"
GAP = "UNRESOLVED PROVENANCE GAP"
ERROR = "VERIFICATION ERROR"


@dataclass(frozen=True)
class Identity:
    manifest: str
    path: str
    snapshot: str | None
    kind: str = "source"


CATALOGUE = (
    Identity("experiments/002/freeze-manifest.json", "pyproject.toml", E002_SNAPSHOT),
    Identity(
        "experiments/002/freeze-manifest.json",
        "src/kri_space_autonomy/experiment_002/dynamics.py",
        E002_SNAPSHOT,
    ),
    Identity("experiments/002/freeze-manifest.json", "uv.lock", E002_SNAPSHOT),
    Identity("experiments/002b/freeze-manifest.json", "Makefile", E002B_SNAPSHOT),
    Identity("experiments/002b/freeze-manifest.json", "README.md", E002B_SNAPSHOT),
    Identity(
        "experiments/002b/freeze-manifest.json", "experiments/002b/validation-evidence.json", None
    ),
    Identity(
        "experiments/002b/freeze-manifest.json",
        "src/kri_space_autonomy/experiment_002/dynamics.py",
        E002_SNAPSHOT,
    ),
    Identity(
        "experiments/004-confirmatory/freeze-manifest.json",
        ".github/workflows/ci.yml",
        E004_SNAPSHOT,
    ),
    Identity("experiments/005/freeze-manifest.json", ".github/workflows/ci.yml", E005_SNAPSHOT),
    Identity(
        "experiments/005-confirmatory/freeze-manifest.json",
        ".github/workflows/ci.yml",
        E005_SNAPSHOT,
    ),
    Identity(
        "results/experiment-005-transfer-pilot-replacement/manifest.json",
        "docs/research-roadmap.md",
        PILOT_SNAPSHOT,
        "artifact",
    ),
    Identity(
        "results/experiment-005-transfer-pilot-replacement/manifest.json",
        "tests/conftest.py",
        PILOT_SNAPSHOT,
        "artifact",
    ),
)


class InspectionError(Exception):
    """An identity could not be verified; never excuse it as a phase difference."""


class GitReader:
    def __init__(self, root: Path):
        self.root = root
        self.cache: dict[tuple[str, ...], bytes] = {}
        self.commits: set[str] = set()

    def read(self, *args: str) -> bytes:
        if args not in self.cache:
            env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
            try:
                result = subprocess.run(
                    ["git", "--no-replace-objects", "-C", str(self.root), *args],
                    capture_output=True,
                    check=True,
                    timeout=30,
                    env=env,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                raise InspectionError(f"git_object_unavailable:{args[-1]}") from exc
            self.cache[args] = result.stdout
        return self.cache[args]

    def require_commit(self, commit: str) -> None:
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise InspectionError("full_immutable_commit_required")
        if commit not in self.commits:
            if self.read("cat-file", "-t", commit).strip() != b"commit":
                raise InspectionError(f"not_a_commit:{commit}")
            self.commits.add(commit)

    def blob(self, commit: str, path: str) -> bytes:
        self.require_commit(commit)
        _relative_path(path)
        spec = f"{commit}:{path}"
        if self.read("cat-file", "-t", spec).strip() != b"blob":
            raise InspectionError(f"not_a_blob:{spec}")
        return self.read("cat-file", "blob", spec)


def _relative_path(value: str) -> None:
    p = PurePosixPath(value)
    if not value or p.is_absolute() or ".." in p.parts or p.as_posix() != value or chr(92) in value:
        raise InspectionError("invalid_catalogue_path")


def _working_bytes(root: Path, relative: str) -> bytes:
    _relative_path(relative)
    path = root
    for part in PurePosixPath(relative).parts:
        path /= part
        if path.is_symlink():
            raise InspectionError(f"symlink_in_inspected_path:{relative}")
    try:
        return path.read_bytes()
    except OSError as exc:
        raise InspectionError(f"working_file_unavailable:{relative}") from exc


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _expected(manifest: bytes, item: Identity) -> str:
    try:
        data = json.loads(manifest)
        if item.kind == "source":
            value = data["source_file_hashes"][item.path]
        elif item.kind == "artifact":
            candidates = [a["sha256"] for a in data["artifacts"] if a["path"] == item.path]
            if len(candidates) != 1:
                raise ValueError("artifact identity is missing or ambiguous")
            value = candidates[0]
        else:
            raise ValueError("unsupported catalogue identity kind")
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("invalid SHA-256")
        return value
    except (ValueError, KeyError, TypeError) as exc:
        raise InspectionError(f"invalid_frozen_manifest_entry:{item.manifest}:{item.path}") from exc


def _external_record_hash(path: Path, expected: str) -> str:
    try:
        if path.is_symlink() or not path.is_file():
            raise InspectionError("external_record_must_be_a_regular_file")
        digest = _sha(path.read_bytes())
    except OSError as exc:
        raise InspectionError("external_record_unavailable") from exc
    if digest != expected:
        raise InspectionError("external_record_digest_mismatch")
    return digest


def verify(
    root: Path,
    *,
    catalogue: tuple[Identity, ...] = CATALOGUE,
    release: str = RELEASE_COMMIT,
    maintenance: str = MAINTENANCE_COMMIT,
    e002b_record: Path | None = None,
) -> dict[str, object]:
    """Verify the fixed catalogue; custom arguments support isolated test fixtures."""
    root = root.resolve()
    reader = GitReader(root)
    results: list[dict[str, object]] = []
    for item in catalogue:
        row: dict[str, object] = {
            "manifest": item.manifest,
            "path": item.path,
            "historical_commit": item.snapshot,
            "manifest_anchor_commit": release,
        }
        try:
            frozen_manifest = reader.blob(release, item.manifest)
            row["manifest_sha256"] = _sha(frozen_manifest)
            if _working_bytes(root, item.manifest) != frozen_manifest:
                raise InspectionError("frozen_manifest_modified_in_checkout")
            expected = _expected(frozen_manifest, item)
            row["expected_sha256"] = expected
            observed = _sha(_working_bytes(root, item.path))
            row["current_sha256"] = observed
            if item.snapshot is None:
                if not (
                    item.path == "experiments/002b/validation-evidence.json"
                    and expected == E002B_EXPECTED
                    and observed == E002B_OBSERVED
                ):
                    raise InspectionError("unresolved_identity_changed_requires_explicit_review")
                row.update(
                    status=GAP,
                    expected_bytes_available_in_git=False,
                    external_record_matched=False,
                    reason="No catalogued Git snapshot supplies the expected bytes.",
                )
                if e002b_record is not None:
                    record_hash = _external_record_hash(e002b_record, expected)
                    row.update(
                        external_record_matched=True,
                        external_record_sha256=record_hash,
                        reason=(
                            "Supplied archival bytes match; public Git archive remains incomplete. "
                            "Byte identity alone does not authenticate custodial history."
                        ),
                    )
            else:
                historical = _sha(reader.blob(item.snapshot, item.path))
                row["historical_sha256"] = historical
                if historical != expected:
                    raise InspectionError("designated_historical_snapshot_digest_mismatch")
                if observed == expected:
                    row.update(status=MATCHED, current_snapshot_commit=item.snapshot)
                else:
                    # Exact reviewed snapshots only; never accept arbitrary historical hashes.
                    known = [(c, _sha(reader.blob(c, item.path))) for c in (release, maintenance)]
                    matches = [c for c, digest in known if digest == observed]
                    if not matches:
                        raise InspectionError("unexpected_current_file_digest")
                    row.update(
                        status=PHASE,
                        current_snapshot_commit=matches[-1],
                        matched_historical_snapshot=True,
                    )
        except InspectionError as exc:
            row.update(status=ERROR, reason=str(exc))
        results.append(row)
    counts = Counter(str(r["status"]) for r in results)
    errors, gaps = counts[ERROR], counts[GAP]
    return {
        "schema_version": "sal-historical-snapshot-verification/1.0",
        "release_commit": release,
        "maintenance_commit": maintenance,
        "status": "VERIFICATION_ERROR"
        if errors
        else "INCOMPLETE_PROVENANCE"
        if gaps
        else "MATCHED",
        "catalogue_complete": not errors and not gaps,
        "experimental_provenance_verified": False,
        "verification_errors": errors,
        "unresolved_items": gaps,
        "matched_historical_snapshots": counts[MATCHED] + counts[PHASE],
        "phase_differences": counts[PHASE],
        "catalogued_items": len(catalogue),
        "scope": "Explicit identity catalogue only; not all manifests or experimental validity.",
        "scientific_calculations_executed": False,
        "checkout_modified": False,
        "results": results,
    }


def exit_code(report: dict[str, object]) -> int:
    return 2 if report["verification_errors"] else 1 if report["unresolved_items"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument(
        "--e002b-record",
        type=Path,
        help="Existing archival payload for exact-digest checking; not a replacement or waiver.",
    )
    args = parser.parse_args(argv)
    report = verify(args.root, e002b_record=args.e002b_record)
    print(json.dumps(report, indent=2, sort_keys=True))
    return exit_code(report)


if __name__ == "__main__":
    raise SystemExit(main())
