"""Read-only integrity checks for the dated, additive evidence supplement."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import math
import re
import stat
import tarfile
from pathlib import Path, PurePosixPath
from typing import Any

SUPPLEMENT = "supplements/2026-09-09-evidence-reconciliation"
MANIFEST_SHA256 = "0b57861c9fe14ad0f21f63cbebef7197085ef0f40cc1f1aecc090043dbee6d84"
ARCHIVE_SHA256 = "3f0f71990c65159bfda70b79f24ca364bfaf12a736f2d1721844e032e9697b03"
INVENTORY_SHA256 = "0d33564bb1b979590adf9efc94f1046c158c5b4b2ddf8128bd912090fd48248e"
E002B_SHA256 = "c45a7cb29489c94460f64560b6f85e578fbbd076b9f4d325116c463dcf75b1f1"
MAX_FILE_BYTES = 8_000_000
MAX_TAR_BYTES = 32_000_000
MAX_MEMBER_BYTES = 6_000_000
MAX_TOTAL_BYTES = 15_000_000
MAX_MEMBERS = 1_100


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _constant(value: str) -> None:
    raise ValueError("nonfinite JSON constant: " + value)


def strict_json(raw: bytes) -> Any:
    value = json.loads(raw, object_pairs_hook=_unique, parse_constant=_constant)

    def finite(item: Any) -> None:
        if type(item) is float and not math.isfinite(item):
            raise ValueError("nonfinite JSON number")
        if isinstance(item, dict):
            for child in item.values():
                finite(child)
        if isinstance(item, list):
            for child in item:
                finite(child)

    finite(value)
    return value


def safe_name(name: str) -> str:
    if not isinstance(name, str) or not name:
        raise ValueError("empty or non-string path")
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or path.as_posix() != name
        or name == "."
        or ":" in name
        or chr(92) in name
        or any(ord(c) < 32 for c in name)
    ):
        raise ValueError("noncanonical relative path")
    return name


def read_regular(root: Path, relative: str, maximum: int = MAX_FILE_BYTES) -> bytes:
    safe_name(relative)
    path = root
    for part in PurePosixPath(relative).parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("symlink in inspected path")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise ValueError("invalid file type or excessive size")
    with path.open("rb") as handle:
        raw = handle.read(maximum + 1)
    if len(raw) != info.st_size or len(raw) > maximum:
        raise ValueError("file changed during read or exceeds size limit")
    return raw


def _file_entries(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("nonempty file inventory required")
    entries = {}
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("invalid inventory entry")
        name = safe_name(item["path"])
        if name in entries:
            raise ValueError("duplicate inventory path")
        if type(item["bytes"]) is not int or item["bytes"] < 0:
            raise ValueError("invalid byte count")
        if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise ValueError("invalid digest")
        entries[name] = item
    return entries


def validate_archive(raw: bytes, inventory: dict[str, Any]) -> dict[str, bytes]:
    """Validate every member in memory; never extract an archive into a filesystem."""
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError("archive exceeds compressed size bound")
    entries = _file_entries(inventory["files"])
    total = sum(e["bytes"] for e in entries.values())
    if (
        len(entries) > MAX_MEMBERS
        or inventory["member_count"] != len(entries)
        or inventory["total_member_bytes"] != total
        or total > MAX_TOTAL_BYTES
        or any(e["bytes"] > MAX_MEMBER_BYTES for e in entries.values())
    ):
        raise ValueError("inventory size or count bound violated")
    with gzip.GzipFile(fileobj=io.BytesIO(raw), mode="rb") as stream:
        expanded = stream.read(MAX_TAR_BYTES + 1)
    if len(expanded) > MAX_TAR_BYTES:
        raise ValueError("unexpected archive expansion")
    members: dict[str, bytes] = {}
    with tarfile.open(fileobj=io.BytesIO(expanded), mode="r:") as archive:
        for member in archive:
            name = safe_name(member.name)
            if name in members or name not in entries:
                raise ValueError("duplicate or unexpected archive member")
            if not member.isfile() or member.issparse() or member.pax_headers:
                raise ValueError("only ordinary regular archive members are permitted")
            expected = entries[name]
            if member.size != expected["bytes"] or member.size > MAX_MEMBER_BYTES:
                raise ValueError("archive member size mismatch")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError("unreadable member")
            with handle:
                payload = handle.read(member.size + 1)
            if len(payload) != member.size or sha256(payload) != expected["sha256"]:
                raise ValueError("archive member content mismatch")
            members[name] = payload
        if any(expanded[archive.offset :]):
            raise ValueError("unexpected data after archive end")
    if set(members) != set(entries):
        raise ValueError("missing archive member")
    return members


def read_original_members(root: Path) -> dict[str, bytes]:
    directory = root / SUPPLEMENT
    raw_inventory = read_regular(directory, "e005-inventory.json")
    raw_archive = read_regular(directory, "e005-original-records.tar.gz")
    if sha256(raw_inventory) != INVENTORY_SHA256 or sha256(raw_archive) != ARCHIVE_SHA256:
        raise ValueError("pinned archive or inventory identity mismatch")
    inventory = strict_json(raw_inventory)
    if inventory["member_count"] != 1092 or inventory["total_member_bytes"] != 13716631:
        raise ValueError("recovered dataset size changed")
    return validate_archive(raw_archive, inventory)


def verify(root: Path) -> dict[str, Any]:
    directory = root / SUPPLEMENT
    raw = read_regular(directory, "manifest.json")
    if sha256(raw) != MANIFEST_SHA256:
        raise ValueError("supplement manifest identity mismatch")
    manifest = strict_json(raw)
    entries = _file_entries(manifest["files"])
    observed = {
        p.relative_to(directory).as_posix()
        for p in directory.rglob("*")
        if p.is_file() or p.is_symlink()
    }
    if observed != set(entries) | {"manifest.json"}:
        raise ValueError("missing or extra supplemental file")
    for name, expected in entries.items():
        payload = read_regular(directory, name)
        if len(payload) != expected["bytes"] or sha256(payload) != expected["sha256"]:
            raise ValueError("supplemental file identity mismatch: " + name)
    recovered = read_regular(directory, "e002b-validation-recovered.json")
    if len(recovered) != 1372 or sha256(recovered) != E002B_SHA256:
        raise ValueError("recovered validation identity mismatch")
    members = read_original_members(root)
    return {
        "status": "VERIFIED_CONTENT_IDENTITIES",
        "supplement_files": len(entries),
        "original_e005_members": len(members),
        "original_e005_bytes": sum(len(b) for b in members.values()),
        "e002b_sha256": E002B_SHA256,
        "archive_sha256": ARCHIVE_SHA256,
        "read_only": True,
        "historical_custody_authenticated": False,
        "scientific_validity_assessed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        report = verify(args.root)
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, EOFError) as exc:
        print(json.dumps({"status": "INVALID", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
