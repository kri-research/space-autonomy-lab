# Correction scope and compatibility

Dated 28 September 2026. Reviewed base
`cc93a5ce725f7a736d4837b1178b5725962ff28f`.

## A1 bounded observation input

Version 0.1.0 passed an observation string into unrestricted rational conversion
before rejecting its type. A bounded reproduction using `1e10000` constructed a
33,220-bit numerator through assess, estimate_snapshot and observation_packet.
An eventual error did not enforce the advertised preprocessing resource bound.
No unsafe command or change to a recorded scientific outcome was established.

Version 0.1.1 applies one shared scalar validator before observation conversion,
and preflights raw public snapshots before their JSON/dataclass conversion.
Plain built-in integers and finite floats retain their values and representations.
Supported strings use optional sign, 1-80 ASCII integer digits, and either a slash
plus 1-80 denominator digits or a decimal point plus 1-30 fractional digits.
Whitespace, underscores, exponent strings, booleans, NaN/Inf and unsupported scalar
types are rejected. Range must still be nonnegative and bearing in [-pi,pi].

Magnitude is at most 1e9 and the reduced numerator/denominator at most 512 bits.
The observer's narrower measurement-model domain (absolute value at most 1e6) is
unchanged and still checked separately. String length and grammar are tested
before integer/power construction; the bounded integer pair is validated before
Fraction is called. Built-in floats have a bounded short decimal representation;
their decimal pair is checked before downstream rational use. No claim is made
that every possible malicious Python object or the entire interpreter is sandboxed.

Supported string measurements normalize to exact rationals, not rounded floats.
Their packet spelling can become canonical (for example 90/2 becomes 45).
An explicitly supplied Fraction is allowed only when its bounded canonical string
fits the same grammar. Valid existing integer/float examples retain the same
numerical results. Inputs with the old component version fail the compatibility
check; construct a new request using the installed contract. The existing
assessment schema, physical model, command timing, and status vocabulary remain.
No previously issued receipt gains reusable execution authority.

## C1 causal observer ordering

The corrected installed observer first checks the typed timestamp envelope, then
ignores packets unavailable at the decision time before inspecting sensor-contract
content or identities. Ignored-future diagnostic counts may differ; present state
cells and positive-use status do not change merely because future content changes.
Basic malformed objects/timestamps and ingestion-capacity failures remain errors.
Available contract-invalid data and available same-ID conflicts retain their
previous rejection/inconsistency handling. Subsequent availability triggers normal
validation. The public delivered-only boundary continues to reject future packets.

Only the versioned build transformation changes the observer implementation.
Earlier SA02/SA04 files, scientific freezes and old SA06 source/package records
remain unchanged for reproducibility. The private installed namespace is not an
extension API or a physical control driver.

## B1 interpretation correction

A new post-hoc necessary-condition analysis excludes goal entry in time for 80 of
81 initially ineligible in-model inputs. It is separate from the prospective
experiment. No point not excluded by this conservative screen is certified
feasible. No case, denominator, primary endpoint, test, or original output is
changed and no new policy campaign is run. The current SA05 result page links to
the dated analysis; earlier source snapshots retain the original narrative.

## Provenance and retained gaps

The assembler checks original Git blobs, applies exact-context patches and binds
all changed/new runtime bytes plus correction sources. This supports content
identity, not authentication of sensor truth or a hostile interpreter. Assertions
are not used as external-input validation guards in the new scalar/parser code.

The unchanged KRI-STD-001 resource and input-validity requirements already cover
A1 and C1; its evidence-governance requirements cover B1. This is an implementation
and interpretation correction, not a standard revision or a conformance finding.
Physical, target-processor and independent external validation remain pending.
