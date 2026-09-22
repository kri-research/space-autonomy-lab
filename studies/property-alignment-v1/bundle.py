"""Hash-checked exchange of baseline results; no manuscript or private state is read."""

from pathlib import Path, PurePosixPath
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parent
BASE = ROOT / "baseline"
AUDIT = [
    "equality.csv",
    "frequencies.csv",
    "initial_membership_counts.csv",
    "initial_states.csv",
    "pair_tables.csv",
    "paired_engagement.csv",
    "paired_engagement_counts.csv",
    "summary.csv",
    "verification.json",
    "witnesses.csv",
]
GROUPS = {
    "audit": ["historical_common_property.csv", "historical_engagement.csv", "paired_counts.csv"]
    + ["historical_audit/" + name for name in AUDIT],
    "diagnostics": [
        "diagnostic_commands.csv",
        "diagnostic_states.csv",
        "diagnostic_results.json",
        "independent_relative_trace.csv",
        "integration_comparison.csv",
        "statistical_design_check.json",
        "extrema_fixture_results.json",
    ],
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def regular(base: Path, relative: str) -> Path:
    name = PurePosixPath(relative)
    if name.is_absolute() or ".." in name.parts or name.as_posix() != relative:
        raise ValueError("Noncanonical artifact path")
    path = base
    for part in name.parts:
        path /= part
        if path.is_symlink():
            raise ValueError("Symlink in artifact path")
    if not path.is_file():
        raise ValueError("Required artifact is absent: " + relative)
    return path


def source_inventory() -> dict[str, str]:
    paths = [p for p in BASE.rglob("*.py") if "__pycache__" not in p.parts]
    paths += list((BASE / "evidence/prior_aggregates").glob("*.csv"))
    paths += [
        BASE / "data" / n
        for n in (
            "configuration_extract.json",
            "diagnostic_protocol.json",
            "diagnostic_protocol.sha256",
        )
    ]
    paths += [ROOT / n for n in ("run.py", "bundle.py", "pyproject.toml")]
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(paths)}


def verified_group(group: str) -> tuple[dict, dict[str, bytes]]:
    if group not in GROUPS:
        raise ValueError("Unknown output group")
    receipt = json.loads(regular(BASE / "logs", group + "-receipt.json").read_text())
    if receipt["status"] != "passed" or receipt["source_sha256"] != source_inventory():
        raise ValueError("Missing successful execution or changed source")
    if set(receipt["output_sha256"]) != set(GROUPS[group]):
        raise ValueError("Incomplete or additional artifact membership")
    payloads = {n: regular(BASE / "data", n).read_bytes() for n in GROUPS[group]}
    if any(digest(raw) != receipt["output_sha256"][n] for n, raw in payloads.items()):
        raise ValueError("Artifact hash differs from its execution receipt")
    return receipt, payloads


def export_group(group: str, destination: Path) -> dict:
    receipt, payloads = verified_group(group)
    raw_destination = destination.expanduser()
    if any(p.is_symlink() for p in [raw_destination, *raw_destination.parents]):
        raise ValueError("Symlink in export root")
    destination = raw_destination.resolve()
    historical = os.environ.get("SAL_EVIDENCE_ROOT")
    if historical and destination.is_relative_to(Path(historical).expanduser().resolve()):
        raise ValueError("Exports cannot alter historical evidence")
    repository = ROOT.parents[1]
    if destination.is_relative_to(repository):
        raise ValueError("Exports must be outside the research repository")
    targets = {}
    for name in payloads:
        target = destination / name
        if any(p.is_symlink() for p in [target, *target.parents]):
            raise ValueError("Symlink in export destination")
        if target.exists() and not target.is_file():
            raise ValueError("Non-file export destination")
        targets[name] = target
    for name, target in targets.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".pending-" + str(os.getpid()))
        with temporary.open("xb") as handle:
            handle.write(payloads[name])
        os.replace(temporary, target)
    return receipt
