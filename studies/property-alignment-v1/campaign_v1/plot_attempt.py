"""Plot execution accounting only, with no candidate-performance interpretation."""

from pathlib import Path
import argparse
import csv
import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("counts", type=Path)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--pdf", action="store_true")
    args = p.parse_args()
    rows = list(csv.DictReader(args.counts.open()))
    labels = ["Interior pair", "Radial boundary", "Three-face boundary", "Timed bounded pair"]
    states = [
        ("completed_eligible", "Completed and eligible"),
        ("started_without_receipt", "Started without receipt"),
        ("not_started", "Not started"),
    ]
    fig = plt.figure(figsize=(8, 4.4))
    ax = fig.add_subplot(111)
    left = [0] * len(rows)
    for key, label in states:
        values = [int(r[key]) for r in rows]
        ax.barh(labels, values, left=left, label=label)
        for i, (base, value) in enumerate(zip(left, values, strict=True)):
            if value >= 20:
                ax.text(base + value / 2, i, str(value), ha="center", va="center")
        left = [a + b for a, b in zip(left, values, strict=True)]
    ax.invert_yaxis()
    ax.set_xlim(0, 288)
    ax.set_xlabel("Frozen qualification reserve inputs")
    ax.set_title("Qualification attempt accounting")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=1, frameon=False)
    fig.tight_layout(rect=(0, 0.11, 1, 1))
    args.output.mkdir(parents=True, exist_ok=True)
    plt.rcParams["svg.hashsalt"] = "sal-qualification-attempt-v1"
    fig.savefig(args.output / "qualification_accounting.svg", metadata={"Date": None})
    svg = args.output / "qualification_accounting.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text().splitlines()) + "\n")
    fig.savefig(args.output / "qualification_accounting.png", dpi=170)
    if args.pdf:
        fig.savefig(
            args.output / "qualification_accounting.pdf",
            metadata={"CreationDate": None, "ModDate": None},
        )
    plt.close(fig)


if __name__ == "__main__":
    main()
