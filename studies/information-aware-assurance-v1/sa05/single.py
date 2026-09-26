"""Bounded child entry point; one declared unit-policy cell."""

import json
import sys
from pathlib import Path

from iaa.types import encode

from .experiment import run


def main():
    job = json.loads(Path(sys.argv[1]).read_text())
    row, evidence, timing = run(job["case"], job["method"])
    Path(sys.argv[2]).write_text(encode(dict(row=row, evidence=evidence, timing=timing)) + "\n")


if __name__ == "__main__":
    main()
