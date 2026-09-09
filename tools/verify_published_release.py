"""Read-only verification of the existing release and tag; never create or repair them."""

from __future__ import annotations

import json
import subprocess

REPOSITORY = "kri-research/space-autonomy-lab"
RELEASE_COMMIT = "f0e9e5d8c140ca3d5eea71cee97fd29f23bffe12"
RELEASE_TAG = "v0.1.0"


def validate_records(tag: object, release: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(tag, dict) or not isinstance(release, dict):
        return ["invalid_metadata_shape"]
    target = tag.get("object")
    if tag.get("ref") != f"refs/tags/{RELEASE_TAG}":
        errors.append("tag_name_mismatch")
    if not isinstance(target, dict) or target.get("type") != "commit":
        errors.append("tag_object_type_mismatch")
    elif target.get("sha") != RELEASE_COMMIT:
        errors.append("tag_target_mismatch")
    if release.get("tag_name") != RELEASE_TAG:
        errors.append("release_tag_mismatch")
    if release.get("target_commitish") != RELEASE_COMMIT:
        errors.append("release_target_mismatch")
    if release.get("draft") is not False or release.get("prerelease") is not False:
        errors.append("release_is_not_published_stable")
    return errors


def _read_record(endpoint: str) -> object:
    response = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/{endpoint}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return json.loads(response.stdout)


def main() -> int:
    try:
        tag = _read_record(f"git/ref/tags/{RELEASE_TAG}")
        release = _read_record(f"releases/tags/{RELEASE_TAG}")
        errors = validate_records(tag, release)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        errors = [f"remote_verification_failed:{type(exc).__name__}"]
    print(
        json.dumps(
            {
                "passed": not errors,
                "errors": errors,
                "release_commit": RELEASE_COMMIT,
                "read_only": True,
            },
            indent=2,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
