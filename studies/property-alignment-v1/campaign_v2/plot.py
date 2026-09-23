"""Reproduce separate descriptive figures from audited tables. No simulations."""

from pathlib import Path
import argparse
import csv
import json
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

LABELS = {
    "interior_pair": "Interior pair",
    "radial_boundary": "Radial boundary",
    "three_face_boundary": "Three-face boundary",
    "timing_bounded_pair": "Timed bounded pair",
}
STATUS_LABELS = {
    "certified_common_prefix": "Prefix certificate",
    "proved_no_common_held_command": "Obstruction certificate",
    "unresolved": "Unresolved",
    "unresolved_budget": "Decision-budget miss",
    "execution_timeout": "Whole-case timeout",
    "execution_failure_unclassified": "Execution failure",
    "infrastructure_missing": "Missing after start",
}


def save(fig, output, name, pdf):
    fig.savefig(output / (name + ".png"), dpi=180)
    path = output / (name + ".svg")
    fig.savefig(path, metadata={"Date": None})
    path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    if pdf:
        fig.savefig(output / (name + ".pdf"), metadata={"CreationDate": None, "ModDate": None})
    plt.close(fig)


def plot(directory, output, pdf=False):
    directory, output = Path(directory), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summary = json.loads((directory / "summary.json").read_text())
    plt.rcParams["svg.hashsalt"] = "sal-replacement-campaign-v2"
    groups = summary["primary"]
    statuses = list(summary["candidate_statuses"])
    statuses = sorted(
        statuses, key=lambda s: (list(STATUS_LABELS).index(s) if s in STATUS_LABELS else 100, s)
    )
    fig, ax = plt.subplots(figsize=(8.6, 4.9))
    left = [0] * len(groups)
    for status in statuses:
        values = [g.get(status, 0) for g in groups]
        ax.barh(
            [LABELS[g["stratum"]] for g in groups],
            values,
            left=left,
            label=STATUS_LABELS.get(status, status),
        )
        for i, (a, b) in enumerate(zip(left, values, strict=True)):
            if b >= 8:
                ax.text(a + b / 2, i, str(b), ha="center", va="center")
        left = [a + b for a, b in zip(left, values, strict=True)]
    ax.invert_yaxis()
    ax.set_xlim(0, 192)
    ax.set_xlabel("Selected inputs per group")
    ax.set_title("Frozen diagnostic outcomes")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=2, frameon=False)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    save(fig, output, "candidate_outcomes", pdf)
    with (directory / "selected_case_ledger.csv").open() as f:
        rows = list(csv.DictReader(f))
    fig, ax = plt.subplots(figsize=(7.8, 4.8))
    missing = 0
    for s, label in LABELS.items():
        group = [r for r in rows if r["stratum"] == s]
        values = sorted(
            float(r["policy_wall_s"])
            for r in group
            if r["policy_wall_s"] and float(r["policy_wall_s"]) > 0
        )
        missing += len(group) - len(values)
        if values:
            ax.step(
                values,
                [(i + 1) / len(values) for i in range(len(values))],
                where="post",
                label=label + " (n=" + str(len(values)) + ")",
            )
    ax.axvline(1, linestyle=":", label="One-second policy budget")
    ax.set_xscale("log")
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("Recorded candidate policy time (seconds)")
    ax.set_ylabel("Empirical cumulative proportion of returned timings")
    ax.set_title("Candidate policy timing")
    ax.legend(loc="best", fontsize=8, frameon=False)
    fig.text(
        0.5,
        0.015,
        f"{missing} missing policy timings; their cases remain in the primary denominator.",
        ha="center",
        fontsize=8,
    )
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    save(fig, output, "policy_timing", pdf)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--pdf", action="store_true")
    a = p.parse_args()
    plot(a.data, a.output, a.pdf)


if __name__ == "__main__":
    main()
