# Independent HCW certificate audit derivation

## Scope and exact constants

The audit checks existing certificates and qualification witnesses. It does not
run a policy, change an original one-second timing verdict, generate a protected
case, or claim independent human review. The original source was read to recover
its data contract. The supplied point-state checker was also inspected and is
preserved byte-for-byte in reference_inputs. Its three pairwise commands are
reused as development fixtures. The new numerical core uses separately written
integer dyadic intervals and all four state rows, rather than the original ODE
Taylor/Picard implementation. Original numerical modules are not imported.

The state is (x,y,vx,vy), in metres and metres per second, with radial-outward x
and prograde along-track y. The mean motion is exactly
n = 5217507778172933 / 4611686018427387904 s^-1. This is the represented binary64
value used by the original validated model. The decimal string with the same
printed digits is not substituted. The equations are

    dx/dt = vx
    dy/dt = vy
    dvx/dt = 3 n^2 x + 2 n vy + fx
    dvy/dt = -2 n vx + fy.

Each forcing is constant on a declared segment. The full frozen interval is at
most three seconds: up to one second of observation age plus one of command
delay, followed by a one-second held command. The complete known queue is used.

## Cancellation-safe fundamental and forcing maps

Define S(z)=sin(z)/z, C(z)=(1-cos(z))/z^2 and T(z)=(z-sin(z))/z^3,
continuously extended at zero to 1, 1/2 and 1/6. For z=n t, the fundamental
matrix Phi and constant-forcing map Gamma are

    Phi = [1+3 n^2 t^2 C, 0, t S,          2 n t^2 C;
           -6 n^3 t^3 T, 1, -2 n t^2 C,  t-4 n^2 t^3 T;
           3 n^2 t S,     0, 1-n^2 t^2 C, 2 n t S;
           -6 n^3 t^2 C, 0, -2 n t S,    1-4 n^2 t^2 C]

    Gamma = [t^2 C,        2 n t^3 T;
             -2 n t^3 T,  t^2(4 C-3/2);
             t S,         2 n t^2 C;
             -2 n t^2 C,  t-4 n^2 t^3 T].

These maps follow by solving the constant-coefficient equations. Equivalently,
differentiation gives Phi'=A Phi, Phi(0)=I, Gamma'=A Gamma+B and Gamma(0)=0,
where B injects the two accelerations into the two velocity equations. Uniqueness
of this linear initial-value problem establishes the response for all four
components. The n=0 limits give the exact double integrator without division by n.
Independent test code also constructs a six-dimensional augmented matrix
exponential directly from A and B using rational matrix powers and a norm-bound
tail. This test oracle is not called by the auditor.

For offset r=1,2,3, the corresponding response function is

    F_r(z) = sum_{k>=0} (-1)^k z^(2k)/(2k+r)!.

The implementation encloses terms k=0 through 9 by interval Horner evaluation.
For 0<=z<=1/32, term magnitudes decrease because the ratio is at most
(1/32)^2/((2k+r+1)(2k+r+2))<1. The next term is positive, so the remainder
lies in [0,z_max^20/(20+r)!]. This is a uniform bound over the WHOLE time
interval. It extends to the complete three-second campaign domain without
relaxing the supplied checker's unproved 0.002-argument assertion. Every operation
is outward rounded using integer arithmetic on multiples of 2^-192. Multiplication
uses floor/ceiling of all endpoint products; division uses exact rational endpoint
quotients and rejects denominators containing zero. No ordinary floating-point
transcendental result is used to decide a certificate.

## Original-box superposition and independently varying segment inputs

For an original initial box X and constant input boxes F_j on [a_j,b_j],

    z(t) = Phi(t) z(0)
           + sum_{b_j<=t} Phi(t-b_j) Gamma(b_j-a_j) f_j
           + Gamma(t-a_current) f_current.

A range query never crosses an input event. This formula propagates the original
initial uncertainty directly. Each segment forcing is independently allowed to
vary in its admitted box; sequential outer-box corners are never asserted to be
attainable origins. Interval matrix products can lose correlation, but only by
outward enlargement. The same fixed n is assumed along each trajectory; optional
interval-n development checks conservatively enlarge the coefficient ranges.

For a held command u the physical forcing is eta*u+w. The original positive
checker permits independent constant uncertainty choices every quarter second,
including during the queue. The new checker encloses every such realization.
The two forcing coordinates use interval products, conservatively forgetting
that eta is shared across axes. This enlargement cannot create a false positive.
A witness used to refute a prefix must instead name an actual original point,
an allowed scalar eta and disturbance vector on every segment, and an exact time.
The bounded witness search tries constant realization sequences, a valid subset;
its failure makes no claim of safety or exhaustive adversarial search.

## Closed union and continuous time

The corridor is -100<=y<=-30 with 10*x+y<=0 and -10*x+y<=0. The hold ellipse is
9*x^2+4*(y+30)^2<=36. They form a union, including their boundaries. Integer-scaled
inequalities avoid introducing a rounded decimal geometric tolerance. A time
interval is certified only if its entire state enclosure lies in at least one
component. Otherwise the time interval is bisected, respecting all quarter-second
events. Failure to place a union-crossing enclosure in either component remains
unresolved; it is not a contradiction. In particular, point samples, a convex
outer halfspace system and the centre of an information box cannot prove a prefix.

A negative trajectory witness is accepted only if its validated point-time
position enclosure is wholly outside BOTH components. The original point and
forcing realization must first be checked for admissibility. A positive result
must cover every complete hypothesis box and all the queue and held intervals.
Both components satisfy y<=-27, so verified union containment also implies
separation>=27 m, strictly outside the 10 m keep-out and 2 m collision spheres.
There is no additional hold, terminal, recursive-recovery or mission claim.

## Saved negative certificate reconstruction

The original enumeration is reproduced explicitly: sort and deduplicate original
box vertices, retain the first64, then iterate sorted effectiveness endpoints,
sorted componentwise disturbance corners, post-application times1/2 and1, and
six normals in this order:

    (0,-1), (0,1), (1,0), (-1,0), (1,1/10), (-1,1/10)
    limits 100, -27, 10, 10, 0, 0.

Finally append coordinate action bounds, coordinate0 then1 and sign-1 then+1.
Every nonzero saved weight retains its corresponding row. Active-obligation labels
are compared when supplied, and the information/model hashes must agree. The
saved numerical margins and coefficient enclosures are ignored.

Each positional halfspace is necessary for the full union: the corridor support
is checked at its four vertices; ellipse support satisfies
-30*b+sqrt((2*a)^2+(3*b)^2)<=limit. The implementation establishes this without a
rounded square root by checking nonnegative slack and the squared inequality.
Necessary coefficients are then independently reconstructed from the maps above,
the actual original point, an allowed constant eta and disturbance, the exact
queue, and the stated witness time. Constant uncertainty over the full interval
is an allowed member of the wider segment-varying class. Only nonzero-weight rows
need numerical reconstruction; zero weights are still enumerated and validated.

For outward coefficients M_ij in [lo_ij,hi_ij], b_i<=bbar_i, saved lambda_i>=0,
and coordinate bounds |u_j|<=U, define

    R_j=max(|sum lambda_i lo_ij|, |sum lambda_i hi_ij|)
    delta=-sum lambda_i bbar_i - U sum R_j.

All sums and products at this last stage use exact rational arithmetic. If delta>0,
then lambda^T(Mu-b)>=delta>0 for any admissible u, contradicting Mu<=b. The disk
implies the coordinate bounds, so this conservative residual budget is valid.
A nonpositive delta does not prove feasible control, false science, or individual
unrecoverability; it means this saved certificate was not independently verified.
No replacement weights, solver infeasibility or differently enumerated rows are used.

## Classifications, monotonicity and operational limits

Verified prefixes, verified HCW obstructions, numerical non-resolution, malformed
or binding-invalid evidence, unsupported assumptions, genuine prefix contradictions
and absence of an original on-time certificate remain separate. Timeouts and
interrupted audit jobs have separate execution outcomes. All original unresolved
and late cases remain in the original denominator, without gaining a new on-time
certificate from an offline calculation.

A mathematically valid positive command remains valid for a contained smaller
information set. A valid obstruction remains true for a larger exact set retaining
its attainable witnesses. Hash identities change when the information changes;
the old hash-bound certificate cannot simply be reassigned to the new set. Tests
therefore distinguish mathematical inclusion, original-certificate binding and
non-monotonic behaviour of a sufficient search. Positive rescaling of necessary
rows is tested with inverse scaling of weights.

This remains conditional numerical mathematics with a trusted Python integer/
Fraction implementation, the displayed differential equations and correctly bound
raw inputs. The source-isolated tests establish computational separation, not
independent human authorship, model validity in flight, robustness to unmodelled
forces, or a new general assurance theorem.

## Primary mathematical and arithmetic references

MIT OpenCourseWare, 16.346 Astrodynamics, Lecture 26 (Fall 2008), derives the
relative-motion equations and their fundamental solution. PDF pages 3 and 4
were inspected. Its first planar equations use radial xi and along-track eta;
its final matrix switches to along-track x and radial y and nondimensional time.
The displayed maps above use radial-first SI state order throughout and include
the corresponding coordinate permutation and time scaling, rather than copying
that final matrix without transformation.
https://ocw.mit.edu/courses/16-346-astrodynamics-fall-2008/e4f0632a9f1c98f7e9b25492e1a30eb1_lec_26.pdf

Python 3.13 Fraction documentation distinguishes the exact binary value supplied
by a float from the rational value of a decimal string. This is why the original
binary64 mean motion is captured as its integer ratio. Input records use only
bounded canonical rational strings; the reader rejects exponent notation before
constructing a Fraction. Standard-library integer/rational arithmetic and the
explicit directed-rounding rules remain trusted computation, not machine-checked
formal proofs of the interpreter.
https://docs.python.org/3.13/library/fractions.html

Both primary records were inspected on 24 September 2026. They contextualize
established mathematics and arithmetic behavior; they do not validate this
implementation or establish physical spacecraft performance.

The supplied checker is stored as `reference_inputs/independent_hcw_check.py.txt`
with its original exact byte hash. This is an immutable source-data snapshot,
not a runtime module. To repeat the original standalone reference calculation,
copy it as `independent_hcw_check.py` into a new private directory; it writes its
own output there. Dependency tests still parse this source snapshot. The added
numerical implementation is checked by the unchanged repository lint pipeline;
no historical code, test or lint rule is modified to accommodate this input.
