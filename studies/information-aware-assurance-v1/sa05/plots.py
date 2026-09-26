"""Deterministic plots and tables from stored outcomes; no experiment is rerun."""

import csv
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def generate(analysis, destination):
    # Dependencies may change matplotlib globals. Isolate rendering from imports.
    with plt.rc_context(rc=matplotlib.rcParamsDefault):
        _generate(analysis, destination)


def _generate(analysis, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    records = analysis["absolute"]
    columns = (
        "stratum",
        "method",
        "scheduled",
        "completed",
        "mission_completion",
        "acquired_goal",
        "requests",
        "nonzero_interventions",
        "unsafe_admissions",
        "exclusions",
        "unresolved",
        "mean_modeled_energy_mj",
        "median_potential_change_m2",
    )
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    (destination / "comparative-results.csv").write_text(buffer.getvalue())
    header = (
        "| Stratum | Schedule | Completed | Goal acquisitions | Requests | Mean modeled mJ |\n"
        "| --- | --- | ---: | ---: | ---: | ---: |\n"
    )
    for r in records:
        cost = (
            "unavailable"
            if r["mean_modeled_energy_mj"] is None
            else f"{r['mean_modeled_energy_mj']:.6f}"
        )
        header += (
            f"| {r['stratum']} | {r['method']} | {r['completed']}/{r['scheduled']} | "
            f"{r['acquired_goal']} | {r['requests']} | {cost} |\n"
        )
    (destination / "comparative-results.md").write_text(header)
    plt.rcParams["svg.hashsalt"] = "KRI-SA05-frozen-1"
    labels = [
        r["stratum"].replace("_", " ") + "\n" + r["method"].replace("_", " ") for r in records
    ]
    for field, name, ylabel in [
        ("acquired_goal", "goal-acquisition", "Numerically supported goal acquisitions"),
        ("requests", "observation-requests", "Additional observation requests"),
    ]:
        fig, ax = plt.subplots(figsize=(12, 4.8))
        ax.bar(range(len(records)), [r[field] for r in records])
        ax.set_xticks(range(len(records)), labels, rotation=55, ha="right", fontsize=8)
        ax.set_ylabel(ylabel)
        ax.set_ylim(bottom=0)
        ax.set_title("Prospective finite-manoeuvre evaluation")
        fig.tight_layout()
        fig.savefig(destination / (name + ".svg"), metadata={"Date": None})
        fig.savefig(destination / (name + ".png"), dpi=160, metadata={"Software": "KRI-SA05"})
        plt.close(fig)


def equal_rendering(generated, stored):
    """Exact vectors/tables and exact decoded PNG pixels, independent of compression.

    Original files are still separately checked against their full byte hashes.
    No pixel tolerance, resized image or removed text is accepted.
    """
    generated, stored = Path(generated), Path(stored)
    if generated.suffix != ".png":
        return generated.read_bytes() == stored.read_bytes()
    from PIL import Image

    with Image.open(generated) as a, Image.open(stored) as b:
        return (
            a.format == b.format == "PNG"
            and a.mode == b.mode == "RGBA"
            and a.size == b.size
            and a.info.get("dpi") == b.info.get("dpi")
            and a.tobytes() == b.tobytes()
        )
