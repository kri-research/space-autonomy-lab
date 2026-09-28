"""Exact, audited transformations of the unchanged 0.1.0 runtime closure."""


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Pinned patch context changed")
    return text.replace(old, new, 1)


def apply(package):
    path = package / "_vendor/iaa/types.py"
    text = path.read_text()
    text = once(
        text,
        "from fractions import Fraction as Q",
        "from fractions import Fraction as Q\n\n"
        "from kri_assurance_eval._numeric import observation_value",
    )
    text = once(
        text,
        "        rational(self.value)\n",
        '        object.__setattr__(self, "value", observation_value(self.value))\n',
    )
    path.write_text("# Post-audit 0.1.1 adds bounded observation conversion.\n" + text)

    path = package / "_vendor/sa02/estimator.py"
    text = path.read_text()
    text = once(
        text,
        "from kri_assurance_eval._vendor.iaa.types import StateBox",
        "from kri_assurance_eval._vendor.iaa.types import ObservationPacket, StateBox",
    )
    old = """                try:
                    validate_packet(p, self.contract)
                except (ValueError, TypeError, OverflowError):
                    diagnostics["ignored_invalid"] += 1
                    continue
                if p.available_ms > now_ms or p.acquired_ms - p.timestamp_uncertainty_ms > now_ms:
                    diagnostics["ignored_future"] += 1
                    continue
"""
    new = """                # Check only the typed availability envelope before sensor content.
                try:
                    if not isinstance(p, ObservationPacket):
                        raise ValueError("Typed observation required")
                    millis(p.available_ms)
                    millis(p.acquired_ms)
                    millis(p.timestamp_uncertainty_ms)
                except (ValueError, TypeError, OverflowError):
                    diagnostics["ignored_invalid"] += 1
                    continue
                if p.available_ms > now_ms or p.acquired_ms - p.timestamp_uncertainty_ms > now_ms:
                    diagnostics["ignored_future"] += 1
                    continue
                try:
                    validate_packet(p, self.contract)
                except (ValueError, TypeError, OverflowError):
                    diagnostics["ignored_invalid"] += 1
                    continue
"""
    path.write_text(
        "# Post-audit 0.1.1 checks availability before sensor content.\n" + once(text, old, new)
    )

    path = package / "api.py"
    text = path.read_text()
    text = once(
        text,
        "from . import __version__",
        "from . import __version__\nfrom ._numeric import preflight_snapshot",
    )
    text = once(
        text,
        "    raw = wire.loads(wire.dumps(snapshot))",
        "    preflight_snapshot(snapshot)\n    raw = wire.loads(wire.dumps(snapshot))",
    )
    text = once(
        text,
        "        req = wire.loads(wire.dumps(request))",
        '        preflight_snapshot(request["initial_input"])\n'
        '        preflight_snapshot(request["current_input"])\n'
        "        req = wire.loads(wire.dumps(request))",
    )
    path.write_text(text)
    path = package / "__init__.py"
    path.write_text(once(path.read_text(), '"0.1.0"', '"0.1.1"'))
    path = package / "examples.json"
    text = path.read_text()
    if text.count('"component_version": "0.1.0"') != 10:
        raise ValueError("Unexpected example version population")
    path.write_text(text.replace('"component_version": "0.1.0"', '"component_version": "0.1.1"'))
