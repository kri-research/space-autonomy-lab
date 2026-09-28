import importlib
import sys

import pytest

from post_audit_v1.assemble import assemble, git


@pytest.fixture(scope="session")
def component(tmp_path_factory):
    source = git("rev-parse", "HEAD").decode().strip()
    directory = assemble(tmp_path_factory.mktemp("post-audit") / "source", source, development=True)
    sys.path.insert(0, str(directory / "src"))
    api = importlib.import_module("kri_assurance_eval.api")
    yield api
    sys.path.remove(str(directory / "src"))


@pytest.fixture
def request_data(component):
    from kri_assurance_eval.examples import examples

    return examples()[0]["request"]
