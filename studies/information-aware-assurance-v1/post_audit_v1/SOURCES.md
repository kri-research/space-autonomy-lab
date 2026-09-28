# Source and design references

Checked 28 September 2026. Source identities in the build inventory identify the
actual reused versions; these links are explanatory primary references.

- Python 3.13 fractions documentation: https://docs.python.org/3.13/library/fractions.html
  String constructors accept decimal/exponent forms, and float and string inputs
  do not generally represent the same rational. The patch validates its own
  deliberately narrower grammar and preserves existing finite-float semantics.
- Python 3.13 json documentation: https://docs.python.org/3.13/library/json.html
  Default JSON decoding accepts nonfinite values; the inherited strict loader
  remains active. A wire-size cap alone does not bound a later expanded number.
- Inherited component source: `50003cb0511265afbe7c2f368d9fb19100ee4d44`.
- Reviewed main: `cc93a5ce725f7a736d4837b1178b5725962ff28f`.
- SA05 source: `9d921566a919ee81cc4fb2b5391069b545667ff2`.

The original repository Apache-2.0 licence and pinned build tools are retained.
No restricted active-sensing code, reviewer identity, private review archive or
new physical validation is added to the runtime distribution. The correction
uses a separately written implementation of the supplied post-hoc argument.
