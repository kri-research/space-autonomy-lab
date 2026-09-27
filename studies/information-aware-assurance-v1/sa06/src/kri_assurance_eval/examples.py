"""Public engineering inputs, separate from the frozen SA05 population."""

import json
from copy import deepcopy
from pathlib import Path


def examples():
    return deepcopy(json.loads(Path(__file__).with_name("examples.json").read_text()))
