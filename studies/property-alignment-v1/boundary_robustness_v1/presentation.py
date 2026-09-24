"""Data-derived sensitivity table, frontier and LaTeX-ready proof for R05."""

from pathlib import Path
from fractions import Fraction as Q
from decimal import Decimal, localcontext, ROUND_FLOOR
import argparse
import csv
import hashlib
import json
from .study import verify_results


def downward(value):
    value = Q(value)
    if value == 0:
        return "0"
    with localcontext() as c:
        c.prec = 70
        x = Decimal(value.numerator) / Decimal(value.denominator)
        unit = Decimal(10) ** (x.adjusted() - 3)
        return format(x.quantize(unit, rounding=ROUND_FLOOR), "f")


def frontier(summary):
    nominal = summary["nominal"]
    pairs = nominal["pair_bounds"]
    neg = nominal["negative_details"]
    rows = [
        (Q(x["base_residual_lower_m"]), Q(x["position_gain_upper"]), Q(x["velocity_gain_upper_s"]))
        for x in pairs
    ]
    maxp = min([a / b for a, b, c in rows if b > 0] + [Q(19, 22000)])
    data = []
    for k in range(111):
        p = maxp * Q(k, 100)
        for gate in ("information_boxes", "shifted_triples"):
            constraints = list(rows)
            if gate == "shifted_triples":
                constraints.append(
                    (
                        Q(neg["center_margin_lower_m"]),
                        Q(neg["position_loss_gain"]),
                        Q(neg["velocity_loss_gain_s"]),
                    )
                )
            cap = min((a - b * p) / c for a, b, c in constraints if c > 0)
            if p > Q(19, 22000) or cap < 0:
                continue
            data.append(
                {
                    "gate": gate,
                    "position_m": str(p),
                    "velocity_boundary_mps": str(cap),
                    "strict_obstruction_boundary_excluded": gate == "shifted_triples",
                }
            )
    return data


def render(data, frozen, study_id, output):
    verify_results(data, frozen, study_id)
    output = Path(output)
    output.mkdir(exist_ok=False, parents=True)
    summary = json.loads((Path(data) / "summary.json").read_text())
    rows = []
    names = {
        "position": "Position",
        "velocity": "Velocity",
        "joint_state": "Joint state",
        "mean_motion": "Mean motion",
        "known_delay": "Known delay",
        "combined": "Combined",
    }
    for search in summary["searches"]:
        p = search["lower_parameters"]
        rows.append(
            {
                "family": search["family"],
                "criterion": search["gate"],
                **p,
                "lower_radius": search["lower_radius"],
                "noncertified_upper": search["noncertified_upper"],
                "cap_passed": search["cap_passed"],
            }
        )
    with (output / "sensitivity.csv").open("x") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    table = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\small",
        r"\caption{Sufficient perturbation bounds for the fixed original pair commands. Boxes retains the nominal centers as obstruction witnesses; Shifts certifies every shifted triple. Each row is a simultaneous componentwise bound, with $n/n_0\in[1-e,1+e]$ and a known zero queue of duration $d\in[0,D]$. Displayed nonzero values are rounded down. These are mathematical bounds, not calibrated equipment tolerances or maximal radii.}",
        r"\label{tab:boundary-robustness}",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Family & Criterion & $p$ ($\mu$m) & $v$ ($\mu$m/s) & $e$ (\%) & $D$ (ms) \\",
        r"\midrule",
    ]
    for row in rows:
        values = [
            downward(Q(row["position_m"]) * 10**6),
            downward(Q(row["velocity_mps"]) * 10**6),
            downward(Q(row["mean_motion_relative"]) * 100),
            downward(Q(row["queue_delay_s"]) * 1000),
        ]
        table.append(
            names[row["family"]]
            + " & "
            + ("Boxes" if row["criterion"] == "information_boxes" else "Shifts")
            + " & "
            + " & ".join(values)
            + r" \\"
        )
    table.extend([r"\bottomrule", r"\end{tabular}", r"\end{table}"])
    (output / "sensitivity_table.tex").write_text("\n".join(table) + "\n")
    points = frontier(summary)
    with (output / "frontier.csv").open("x") as f:
        writer = csv.DictWriter(f, fieldnames=list(points[0]))
        writer.writeheader()
        writer.writerows(points)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    for gate, label in [
        ("information_boxes", "Full information boxes"),
        ("shifted_triples", "Every shifted triple"),
    ]:
        kept = [p for p in points if p["gate"] == gate]
        ax.plot(
            [float(Q(p["position_m"]) * 10**6) for p in kept],
            [float(Q(p["velocity_boundary_mps"]) * 10**6) for p in kept],
            label=label,
        )
    ax.set_xlabel("Componentwise position bound (micrometres)")
    ax.set_ylabel("Componentwise velocity bound (micrometres/s)")
    ax.set_title("Nominal-model sufficient-bound frontiers")
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "state_robustness.svg", metadata={"Date": None})
    fig.savefig(output / "state_robustness.pdf", metadata={"CreationDate": None, "ModDate": None})
    fig.savefig(output / "state_robustness.png", dpi=180)
    plt.close(fig)
    derivation = r"""\subsection{Robustness of the fixed three-state construction}\label{sec:boundary-robustness}
Let $B_i(p,v)$ contain every initial state within $p$ metres in each position coordinate and $v$ metres per second in each velocity coordinate of the original state $z_i$. Shifts are independent across coordinates and hypotheses. Each trajectory has one constant shared mean motion $n\in[n_0(1-e),n_0(1+e)]$. A known zero command is held for $d\in[0,D]$ seconds before the original pair command is held for one second, without intervening distinguishing information. Disturbance is zero and effectiveness is one. This separate continuous-delay family does not modify the earlier discrete campaign schema.

Using the unchanged independent HCW response, after application the state is
\begin{equation}
z(d+\tau)=\Phi(d+\tau,n)(z_i+\delta_i)+\Gamma(\tau,n)u_{ij},\qquad 0\le\tau\le1.
\end{equation}
For each pair, outward coefficient bounds over 256 complete intervals per phase give a nominal corridor residual $m_{ij}$ and gains $L^p_{ij}$ and $L^v_{ij}$. The gains have units one and seconds, respectively. Thus
\begin{equation}
 m_{ij}-L^p_{ij}p-L^v_{ij}v\ge0
 \label{eq:robust-pair-margin}
\end{equation}
is sufficient for every member of both complete boxes to remain in the closed corridor, hence in the corridor--ellipse union, throughout the queue and hold. The zero queue is checked separately. All initial boxes must also satisfy the corridor inequalities.

For the three necessary union-containing halfspaces and fixed weights $\lambda=(1,5,5)/11$, reconstruct the coefficient intervals $[\underline M,\overline M]$ and center right-hand-side upper bounds $\overline b^0$. Define
\begin{align}
 R_j&=\max\left(\left|\sum_i\lambda_i\underline M_{ij}\right|,\left|\sum_i\lambda_i\overline M_{ij}\right|\right),\\
 \Delta_0&=-\sum_i\lambda_i\overline b_i^0-U\sum_jR_j,\\
 \Delta_{\rm shift}&=\Delta_0-\beta_pp-\beta_vv.
\end{align}
Here $\beta_p,\beta_v$ are the weighted absolute state-response gains. They bound the increase in the weighted right-hand side under every independently shifted triple. Coefficient dependence on the full $n,d$ intervals is included in $R_j$ and $\overline b^0$; a nominal obstruction margin is not reused without those changes. Both deltas have residual units metres, not Euclidean-distance meaning.

\paragraph{Sufficient robustness proposition.}
Assume initial box membership and Eq.~\eqref{eq:robust-pair-margin} for each original pair command. If $\Delta_0>0$, every pair of full nominal-centered boxes admits its command, while the full information union is obstructed by the still-possible nominal centers. If $\Delta_{\rm shift}>0$, every independently shifted triple in those boxes is itself pairwise feasible and jointly obstructed for this held-command class.

\paragraph{Proof.}
The pair inequalities bound the complete continuous response for all states and model parameters. For any allegedly feasible joint command, the actuator disk implies $|u_j|\le U$, while the outward coefficient and right-hand-side bounds imply $\lambda^\top(Mu-b)\ge\Delta_{\rm shift}>0$, contradicting $Mu\le b$. The center argument substitutes the nominal points and uses $\Delta_0$. Containment of centers alone does not establish the all-shifted-triples conclusion.\hfill$\square$

\input{sensitivity_table}
\begin{figure}[htbp]
\centering\includegraphics[width=.88\linewidth]{state_robustness.pdf}
\caption{Frontiers of the nominal-model sufficient inequalities in position--velocity error coordinates. Certified interiors lie below the respective frontiers; the strict obstruction boundary is excluded. These frontiers describe this sufficient calculation rather than the exact maximal feasible neighborhood. The information-box argument retains nominal witnesses; the smaller all-shifts argument bounds the perturbed witnesses themselves.}
\end{figure}

The post hoc protocol fixes six directions and 14-step bisections separately for both statements. Failed upper bounds remain noncertificates. Original pair commands and the three states are never optimized or replaced. The larger, separately specified stress examples retain admissible starting points and exhibit validated departures for their fixed commands. They do not falsify the smaller certified neighborhoods or exclude other pair commands.

This is an application of established affine-support and residual-verified infeasibility principles, not a new general theorem. Jansson, \emph{Guaranteed Accuracy for Conic Programming Problems in Vector Lattices} (2007), Section~8, provides relevant verified-infeasibility context. All results remain model-conditional; numerical residuals and these perturbation bounds are not sensor specifications, physical measurements, nonlinear safety or recursive recovery guarantees.
"""
    (output / "derivation.tex").write_text(derivation)
    (output / "preview.tex").write_text(
        r"\documentclass[11pt]{article}"
        + "\n"
        + r"\usepackage[margin=1in]{geometry}\usepackage{amsmath,amssymb,graphicx,booktabs,microtype}\begin{document}\input{derivation}\end{document}"
        + "\n"
    )
    manifest = {
        f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in output.iterdir() if f.is_file()
    }
    (output / "presentation_manifest.json").write_text(
        json.dumps(
            {
                "study_id": study_id,
                "files": manifest,
                "figure_is_data_derived": True,
                "no_original_manuscript_modified": True,
            },
            indent=2,
        )
        + "\n"
    )
    return {"outputs": len(manifest), "rows": len(rows), "frontier_points": len(points)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--study-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.data, args.freeze, args.study_id, args.output), indent=2))
