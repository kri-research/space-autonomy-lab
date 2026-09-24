# Robustness of a fixed three-state construction

## Statement and information convention

Let the nominal states, fixed pair commands, authority U=1/50 m/s2 and exact
represented n0 be those in anchors.json. For each i=0,1,2 define an exact
information box B_i(p,v) whose two position coordinates differ by at most p m
from z_i and whose two velocity coordinates differ by at most v m/s. The shifts
are independent across coordinates and across the three states. They are fixed
initial-state choices, not arbitrary moving errors. The three states remain
observationally indistinguishable until the complete schedule ends.

A model realization has one constant, common n in [n0(1-e),n0(1+e)] and one known
delay d in [0,D]. The same zero command is held for d seconds, then one command
is held for exactly one second. For pair (i,j), that command is the original
listed u_ij. There is no additive disturbance or effectiveness loss in this new
sensitivity family. There is no new sensing, acceleration switching or feedback.
This continuous d parameter is separately declared here; the frozen spacecraft
campaign's discrete age/delay schema is not extended or changed.

The positive obligation is the original closed corridor A. Since A is a subset
of S=A union H, this supplies the full positional obligation and hence separation
at least27m, outside the declared2m collision and10m keep-out spheres. The
stronger sufficient corridor proof may fail even where a union proof would pass.
Initial membership is verified separately; no initially invalid point is counted
as an admissible departing trajectory.

## Continuous response and perturbation gains

R02's unchanged Phi(t,n), Gamma(t,n) are used. Before application z(t)=Phi(t,n)z0.
After application, at elapsed tau in [0,1],

    z(d+tau)=Phi(d+tau,n)z0+Gamma(tau,n)u_ij.

Split each phase into256 complete time intervals. For a hold interval [a,b],
Phi is enclosed over t in [a,b+D] and Gamma over tau in [a,b], both over the
complete n interval. This covers every allowed d,tau jointly, even though their
correlation is discarded. The zero queue is checked over all [0,D], which
conservatively includes every shorter queue. There are no omitted event intervals.
The supporting R02 coefficient bounds cover0<=nt<=1/32 and duration<=3s; every
parameter in the present protocol is within that proved domain. Integer dyadic
arithmetic and exact rational final sums control rounding. No time samples or
floating-point sign decide a certificate.

For corridor face a_l^T position<=c_l, write R=a_l^T Phi_pos and G=a_l^T Gamma_pos.
The normals are (0,-1),(0,1),(1,1/10),(-1,1/10), with limits100,-30,0,0m.
For each pair the computation provides

    m = min_{member,face,time cell} (c_l - upper(R z_i + G u_ij)),
    Lp = max_{face,time cell} sum_{k=0,1} max(abs(lower R_k),abs(upper R_k)),
    Lv = max_{face,time cell} sum_{k=2,3} max(abs(lower R_k),abs(upper R_k)).

Queue cells omit G u. Lp is dimensionless and Lv has units seconds. Therefore

    m - Lp*p - Lv*v >= 0                                      (P)

is sufficient for every complete box member, every model/delay realization,
and the full time interval for that pair. The minimum m is a linear residual
margin in meters, not a Euclidean distance, sensor accuracy or enclosure width.
Bounding gains separately from the nominal worst row deliberately sacrifices
sharpness for an inspectable sufficient condition. All quantities are computed
from the original states and coefficients, not fitted to successful outcomes.

## Uniform obstruction

Retain the simple three nonnegative weights lambda=(1,5,5)/11 from the independent
reference. Row i uses original state i, at tau=1, with normal (0,-1), (1,1/10)
and (-1,1/10), respectively. Their bounds are100,0,0m. Each halfspace contains
the entire original nonconvex union, as established by the checked support proof.
Thus any common safe command necessarily satisfies M(n)u<=b(n,d,delta), where

    M_i = a_i^T Gamma_pos(1,n),
    b_i = c_i - a_i^T Phi_pos(d+1,n)(z_i+delta_i).

Outward intervals bound every M coefficient and the nominal-center rhs b0.
Let

    R_j=max(abs(sum lambda_i lower M_ij),abs(sum lambda_i upper M_ij)),
    Delta0=-sum lambda_i upper b0_i - U*sum_j R_j,
    beta_p=sum lambda_i sum_{k=0,1} max(abs(lower R_ik),abs(upper R_ik)),
    beta_v=sum lambda_i sum_{k=2,3} max(abs(lower R_ik),abs(upper R_ik)),
    Delta_shift=Delta0-beta_p*p-beta_v*v.                       (N)

Here R_ik in the last two lines denotes the projected STATE coefficient row,
not the preceding action-residual R_j. State coefficients have dimensionless
position and second-valued velocity gains; action coefficients/residuals have
units s2. Both Delta0 and Delta_shift are residuals in meters. This explicit SI
accounting never adds a position radius to a velocity radius without a time gain.

For any allowed n,d and shifted states, sum lambda_i b_i is at most its bounded
center value plus beta_p*p+beta_v*v. The actuator disk implies |u_j|<=U.
Consequently lambda^T(Mu-b)>=Delta_shift. A strictly positive Delta_shift
contradicts Mu<=b. The proof is uniform over independently shifted state triples,
not merely over triples containing the nominal points. The certificate uses a
new family identity; no old information hash is reassigned to shifted data.

## Proposition and two distinct consequences

Assume every initial box is contained in A and condition(P) holds for each of
the three fixed pair commands, with model/delay bounds as stated.

1. If Delta0>0, every pair of FULL nominal-centered information boxes has a
   common safe fixed command, while their full union has no common held command.
   Proof: (P) supplies each pair; the original nominal centers remain possible,
   and the residual contradiction with those centers rules out joint control.

2. If Delta_shift>0, EVERY independently shifted triple selected from those boxes
   is initially admissible and pairwise feasible under the original commands,
   but has no common held command for its complete triple.
   Proof: pairwise feasibility follows from(P) for every member. The uniform
   bound(N) excludes joint feasibility for each triple's own shifted states.

The first consequence does not imply the second. In particular an enlarged
information set can retain an obstruction solely because its nominal centers
are still possible, even when this sufficient bound cannot exclude a command
for some individual shifted triple. Failed bounds do not prove such a command
exists. Neither consequence establishes recursive recovery, operational sensor
validity, a different held-command class, or nonlinear impossibility.

## Registered search and interpretation

protocol.json fixes six parameter directions and separate14-step bisections
for the two consequences before systematic runs. Every tested value and every
noncertificate is retained. The lower radius certifies the whole componentwise
neighborhood up to that radius. A failed upper endpoint is only the next
noncertified sufficient bound, not an exact maximal physical radius. The
joint-state direction uses distinct1mm and1mm/s scales multiplied by one
dimensionless radius. Model/delay changes also affect the negative coefficient
residual; retaining a nominal residual without this change would be unsound.

The three larger predeclared stress realizations retain initial admissibility
and explicit point-time enclosures. A verified departure there refutes that
fixed pair command at that stress realization, not the smaller certified box
and not the existence of a different pair command. No new command is optimized.

## Relation to established methods

This is a concrete sufficient-margin application, not a new general robustness
theorem. Componentwise affine support and a nonnegative weighted contradiction
are standard convex/robust feasibility arguments. Jansson's2007 paper, Section8,
provides explicit verified-infeasibility context, including why approximate
floating-point certificates need rigorous error control. The present bound uses
a bounded-command residual allowance and reconstructs the specific HCW family.
It does not claim Jansson supplied this spacecraft example or these perturbation
numbers. See sources.json for the primary references inspected. The earlier
state-isolated numerical audit is unchanged and remains a different experiment.
