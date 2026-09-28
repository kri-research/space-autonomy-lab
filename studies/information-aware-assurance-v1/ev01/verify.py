"""Read-only check of the pre-outreach protocol against its frozen Git sources."""

import hashlib
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WORKFLOW = REPO / ".github/workflows/external-integration.yml"


def git(*args):
    return subprocess.check_output(["git", "--no-replace-objects", "-C", str(REPO), *args])


def files():
    return sorted(
        [
            *HERE.glob("*.py"),
            *HERE.glob("*.md"),
            HERE / "protocol.json",
            *HERE.glob("tests/*.py"),
            WORKFLOW,
        ]
    )


def verify():
    freeze_path = HERE / "freeze.json"
    name = freeze_path.relative_to(REPO).as_posix()
    if freeze_path.is_symlink() or freeze_path.read_bytes() != git("show", "HEAD:" + name):
        raise ValueError("Protocol freeze differs from committed identity")
    freeze = json.loads(freeze_path.read_text())
    source = freeze["source_commit"]
    if freeze["schema"] != "kri-ev01-freeze/1" or not re.fullmatch("[0-9a-f]{40}", source):
        raise ValueError("Protocol identity")
    names = {p.relative_to(REPO).as_posix() for p in files()}
    if names != set(freeze["files"]):
        raise ValueError("Protocol file membership changed")
    for name, expected in freeze["files"].items():
        path = REPO / name
        tree = git("ls-tree", source, "--", name).decode().split()
        if path.is_symlink() or not path.is_file() or len(tree) < 3:
            raise ValueError("Missing or linked protocol source")
        if (
            path.read_bytes() != git("show", source + ":" + name)
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected["sha256"]
            or tree[:3] != [expected["mode"], "blob", expected["blob"]]
            or bool(path.stat().st_mode & 0o111) != (expected["mode"] == "100755")
        ):
            raise ValueError("Protocol Git content or mode mismatch")
    return dict(passed=True, source_commit=source, files=len(names), external_execution=False)


if __name__ == "__main__":
    print(json.dumps(verify(), sort_keys=True))
