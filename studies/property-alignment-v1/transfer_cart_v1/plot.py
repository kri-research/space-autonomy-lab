"""Render the complete data-derived transfer counts; no statistical pooling."""

from pathlib import Path
import argparse
import json
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--local-pdf", action="store_true")
    a = p.parse_args()
    data = json.loads((a.data / "summary.json").read_text())
    a.output.mkdir(parents=True, exist_ok=True)
    labels = {
        "interior": "Interior",
        "single_face": "Single face",
        "aliased_pair": "Aliased pair",
        "aliased_triple": "Aliased triple",
    }
    categories = [
        ("verified_prefix", "Verified prefix"),
        ("verified_obstruction", "Verified obstruction"),
        ("unresolved", "Unresolved"),
        ("budget_miss", "Budget miss"),
        ("contradicted_prefix", "Contradicted prefix"),
        ("unverified_prefix", "Unverified prefix"),
        ("unverified_obstruction", "Unverified obstruction"),
    ]
    fig, ax = plt.subplots(figsize=(8, 4.8))
    left = [0] * 4
    for key, label in categories:
        values = [
            data["by_stratum"][s]["methods"]["lag_aware_common_command"].get(key, 0) for s in labels
        ]
        if not sum(values):
            continue
        ax.barh(list(labels.values()), values, left=left, label=label)
        for i, (v, x) in enumerate(zip(values, left, strict=True)):
            if v >= 2:
                ax.text(x + v / 2, i, str(v), ha="center", va="center")
        left = [x + v for x, v in zip(left, values, strict=True)]
    ax.invert_yaxis()
    ax.set_xlim(0, 32)
    ax.set_xlabel("All prespecified transfer cases per group")
    ax.set_title("Lagged-cart transfer outcomes")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False)
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    plt.rcParams["svg.hashsalt"] = "sal-lag-cart-transfer-v1"
    dest = a.output / "transfer_outcomes.svg"
    fig.savefig(dest, metadata={"Date": None})
    dest.write_text("\n".join(line.rstrip() for line in dest.read_text().splitlines()) + "\n")
    if a.local_pdf:
        fig.savefig(
            a.output / "transfer_outcomes.pdf", metadata={"CreationDate": None, "ModDate": None}
        )
        fig.savefig(a.output / "transfer_outcomes.png", dpi=170)
    plt.close(fig)


if __name__ == "__main__":
    main()
