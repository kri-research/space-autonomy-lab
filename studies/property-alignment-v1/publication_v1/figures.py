#!/usr/bin/env python3
"""Generate figures only from fresh hash-checked historical aggregates and new diagnostic data."""

from pathlib import Path
import csv
import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Ellipse, Circle

DATA = None
OUTPUT = None
LOCAL_PDF = False


def read(name):
    with (DATA / name).open() as f:
        return list(csv.DictReader(f))


def save(fig, name):
    fig.savefig(OUTPUT / f"{name}.svg", bbox_inches="tight", metadata={"Date": None})
    fig.savefig(OUTPUT / f"{name}.png", dpi=180, bbox_inches="tight")
    if LOCAL_PDF:
        fig.savefig(
            OUTPUT / f"{name}.pdf",
            bbox_inches="tight",
            metadata={"CreationDate": None, "ModDate": None},
        )
    plt.close(fig)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    pairs = read("paired_counts.csv")
    fig = plt.figure(figsize=(7.1, 2.8))
    ax = fig.add_subplot(111)
    ax.axis("off")
    for row, x in zip(pairs, [0.14, 0.64]):
        vals = [[str(row["n00"]), str(row["n01"])], [str(row["n10"]), str(row["n11"])]]
        table = ax.table(
            cellText=vals,
            colLabels=["G = 0", "G = 1"],
            rowLabels=["R = 0", "R = 1"],
            cellLoc="center",
            bbox=[x, 0.16, 0.31, 0.59],
        )
        table.auto_set_font_size(False)
        table.set_fontsize(12)
        ax.text(x + 0.155, 0.90, row["study"], ha="center", fontsize=14)
        label = (
            "In-band historical predicate"
            if row["study"] == "E004"
            else "Closed-union historical predicate"
        )
        ax.text(x + 0.155, 0.80, label, ha="center", fontsize=9)
    ax.text(
        0.5,
        -0.03,
        "R = reference   G = monitor gate   0 = no adverse flag   1 = adverse flag",
        ha="center",
        fontsize=10,
    )
    save(fig, "figure_1_paired_tables")
    rows = read("historical_common_property.csv")
    fig = plt.figure(figsize=(7.1, 4.5))
    ax = fig.add_subplot(111)
    for i, row in enumerate(rows):
        lo, hi = float(row["minimum_episode_minimum_m"]), float(row["maximum_episode_minimum_m"])
        ax.plot([lo, hi], [i, i], marker="|", markersize=12, linewidth=2)
    ax.axvline(27, linestyle="--", label="Closed-union lower bound (27 m)")
    ax.set_yticks(
        range(8),
        [
            f"{r['study']} {r['case']}, {'R' if r['arm'] == 'primary_reference' else 'G'}"
            for r in rows
        ],
    )
    ax.invert_yaxis()
    ax.set_xlabel("Range of recorded episode-minimum separation (m)")
    ax.set_xlim(20, 28)
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    save(fig, "figure_2_common_property")
    rows = read("diagnostic_states.csv")
    fig = plt.figure(figsize=(7.1, 3.7))
    ax = fig.add_subplot(111)
    for plant, ls in [("HCW", "-"), ("nonlinear", "--")]:
        group = [r for r in rows if r["plant"] == plant]
        t = np.array([float(r["time_s"]) for r in group])
        for field, label in [
            ("union_excess_m", "closed-union excess"),
            ("old_excess_m", "in-band excess"),
        ]:
            ax.plot(
                t,
                [float(r[field]) for r in group],
                linestyle=ls,
                linewidth=1.5,
                label=f"{plant}, {label}",
            )
    ax.axhline(0, linestyle=":", linewidth=1)
    ax.set_xlabel("Time in new diagnostic (s)")
    ax.set_ylabel("Signed position excess (m)")
    ax.set_xlim(0, 300)
    ax.legend(loc="lower right", fontsize=8, ncol=2)
    fig.tight_layout()
    save(fig, "figure_3_diagnostic")
    fig = plt.figure(figsize=(7.1, 4.5))
    ax = fig.add_subplot(111)
    # Horizontal axis is along-track y, vertical axis is radial x. All patches are outlines.
    ax.add_patch(
        Polygon(
            [[-100, -10], [-100, 10], [-30, 3], [-30, -3]],
            closed=True,
            fill=False,
            linewidth=1.6,
            label="Closed approach corridor",
        )
    )
    ax.add_patch(
        Ellipse(
            (-30, 0), 6, 4, fill=False, linewidth=1.6, linestyle="--", label="Hold position ellipse"
        )
    )
    ax.add_patch(
        Circle((0, 0), 10, fill=False, linestyle=":", linewidth=1.2, label="10 m keep-out boundary")
    )
    ax.plot(
        -25,
        0,
        marker="x",
        markersize=9,
        linestyle="None",
        label="Constructed point (x, y) = (0, -25) m",
    )
    ax.annotate(
        "Sufficient exclusion boundary y = -27 m",
        xy=(-27, 6),
        xytext=(-78, 15),
        arrowprops={"arrowstyle": "->"},
        fontsize=9,
    )
    ax.plot([-27, -27], [-12, 12], linestyle=":", linewidth=1)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-108, 12)
    ax.set_ylim(-18, 18)
    ax.set_xlabel("Along-track position y (m)")
    ax.set_ylabel("Radial position x (m)")
    ax.legend(loc="lower left", fontsize=8, ncol=2)
    fig.tight_layout()
    save(fig, "figure_S1_geometry")
    print("Four figures generated from labelled source data.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--local-pdf", action="store_true")
    args = parser.parse_args()
    DATA = args.data
    OUTPUT = args.output
    LOCAL_PDF = args.local_pdf
    plt.rcParams["svg.hashsalt"] = "sal-publication-baseline-figures-v1"
    main()
