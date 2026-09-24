"""Build a private compact referee bundle; no invitations or manuscript disclosure."""

from pathlib import Path
import argparse
import hashlib
import json
import shutil
from .harness import ROOT


def build(output):
    output = Path(output)
    if output.exists():
        raise ValueError("Bundle already exists")
    output.mkdir()
    cart = ROOT.parent / "transfer_cart_v1"
    package = output / "transfer_cart_v1"
    package.mkdir()
    for name in ("__init__.py", "schema.py", "reference.py", "cleanroom.py"):
        shutil.copyfile(cart / name, package / name)
    data = output / "data"
    data.mkdir()
    for name in ("inputs.json", "cases.jsonl"):
        shutil.copyfile(cart / "recorded" / name, data / name)
    for name in ("REVIEW_QUESTIONS.md", "LAB_PROTOCOL.md", "physical_configuration.json"):
        shutil.copyfile(ROOT / name, output / name)
    shutil.copyfile(cart / "frozen/freeze.json", output / "cart_freeze.json")
    shutil.copyfile(
        cart / "reproduction/clean_reproduction.json", output / "expected_referee_result.json"
    )
    (output / "README.md").write_text(
        "# Numerical reviewer bundle\n\nRun with Python 3.13, standard library only:\n\n```sh\npython -m venv .venv\n.venv/bin/python -m transfer_cart_v1.cleanroom --data data --output review-result.json\n```\n\nExpected 738 matching fixed-output checks. This does not rerun policies, measure new hardware or establish independent endorsement. Write a substantive review using REVIEW_QUESTIONS.md. Full spacecraft sources remain in the pinned research repository. No manuscript or private participant details are included.\n"
    )
    manifest = {
        p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(output.rglob("*"))
        if p.is_file()
    }
    (output / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return {
        "files": len(manifest),
        "bytes": sum(p.stat().st_size for p in output.rglob("*") if p.is_file()),
        "external_review_received": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(build(args.output), indent=2))


if __name__ == "__main__":
    main()
