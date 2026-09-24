"""Public reproduction-record integrity, separate from frozen scientific methods."""

import json
import shutil
import pytest
from publication_v1.verify_recorded import verify, ROOT


def test_public_figure_and_result_bindings_are_reproducible():
    assert verify()["figures"] == 7


def test_corrupt_recorded_result_is_not_silently_accepted(tmp_path):
    dest = tmp_path / "copy"
    shutil.copytree(ROOT / "recorded", dest)
    p = dest / "verification.json"
    x = json.loads(p.read_text())
    x["checks"]["physical_trials"] = 1
    p.write_text(json.dumps(x))
    with pytest.raises(ValueError):
        verify(dest)


def test_svg_normalization_preserves_drawing_tokens():
    from publication_v1.prepare_figures import normalize

    assert normalize(b'<path d="M 0 0  \nL 1 2 \n"/>\n') == b'<path d="M 0 0\nL 1 2\n"/>\n'


def test_svg_normalization_is_idempotent():
    from publication_v1.prepare_figures import normalize

    for path in (ROOT / "recorded/figures").glob("*.svg"):
        raw = normalize(path.read_bytes())
        assert normalize(raw) == raw
