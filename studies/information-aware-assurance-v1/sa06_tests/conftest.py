import importlib
import subprocess
import sys

import pytest

from sa06.assemble import REPO, assemble


@pytest.fixture(scope="session")
def component(tmp_path_factory):
    source = subprocess.check_output(
        ["git", "-C", str(REPO), "rev-parse", "HEAD"], text=True
    ).strip()
    assembled = assemble(tmp_path_factory.mktemp("sa06") / "source", source, development=True)
    sys.path.insert(0, str(assembled / "src"))
    module = importlib.import_module("kri_assurance_eval.api")
    yield module
    sys.path.remove(str(assembled / "src"))


@pytest.fixture
def request_data(component):
    from kri_assurance_eval.examples import examples

    return examples()[0]["request"]
