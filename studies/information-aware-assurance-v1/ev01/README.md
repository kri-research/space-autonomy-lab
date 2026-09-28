# Independent software integration exercise

Protocol **KRI-EV01-1**, prepared 28 September 2026. This continues KRI Space
Autonomy through a voluntary, unpaid software exercise. No endorsement, efficacy
study or formal partnership is requested. Negative and incomplete results are
welcome. Stop after **60 minutes of active effort**, or earlier if inconvenient;
report the obstacle instead of working longer for a pass. Stop any individual
stalled command after five minutes. Keep failures and any later attempts separate.

## Component and environment

Can another team obtain the public component, understand its assumptions and
connect a controller it wrote using only documented interfaces?

The component is **kri-assurance-eval 0.1.1**, repository baseline
`0c360ecb158ad05a02a1deec50594796a0931a8d`, runtime source
`87c92508dde68b4f89b4bb1f138fd11d7081a919`. Expected built wheel SHA-256:
`925ae99decaea6b9ebbf3077e8de305cfa2edb26e7dcb4b441ef7d9a6d198cd8`.
`freeze.json` binds this protocol, runner and report template to a separate
pre-invitation source commit. Use the full protocol commit in the invitation,
not a floating branch. Nothing here replaces an earlier study or outcome.

Use Git and **CPython 3.13.5** in an isolated desktop environment. The package
allows >=3.13,<3.14, but this protocol validates only 3.13.5. macOS arm64 and
Ubuntu 24.04 x86_64 are the internally checked build environments. Record other
platforms as deviations, not validated targets. No GPU, Basilisk, real sensor,
account token, paid service or private KRI file is required. A full-history clone
retains the source branches needed by the existing build and evidence checks.

## Installation

Set EV01_REF to the full 40-character protocol commit printed in the invitation.
Use a new workspace, a POSIX shell and python3.13 on PATH. Do not run historical
campaigns or install the unrelated repository-root package.

```sh
: "${EV01_REF:?Set the exact protocol commit from the invitation}"
python3.13 --version  # must report 3.13.5 for this protocol
WORK=$(mktemp -d)
git clone https://github.com/kri-research/space-autonomy-lab.git "$WORK/repo"
git -C "$WORK/repo" checkout --detach "$EV01_REF"
STUDY="$WORK/repo/studies/information-aware-assurance-v1"
python3.13 -m venv "$WORK/build-env"
PY="$WORK/build-env/bin/python"
cd "$STUDY"
"$PY" -m ev01.verify
"$PY" -m pip install --require-hashes --only-binary=:all: -r sa06/requirements-build.lock
"$PY" -m post_audit_v1.verify
"$PY" -m post_audit_v1.assemble --output "$WORK/source"
SOURCE_DATE_EPOCH=$(cat "$WORK/source/BUILD_EPOCH") "$PY" -m build --no-isolation "$WORK/source" --outdir "$WORK/dist"
python3.13 -m venv "$WORK/consumer"
USE="$WORK/consumer/bin/python"
"$PY" -c 'import hashlib,pathlib,sys; p=next(pathlib.Path(sys.argv[1]).glob("*.whl")); assert hashlib.sha256(p.read_bytes()).hexdigest()=="925ae99decaea6b9ebbf3077e8de305cfa2edb26e7dcb4b441ef7d9a6d198cd8"' "$WORK/dist"
"$USE" -m pip install --no-deps "$WORK"/dist/*.whl
cd "$WORK"
"$USE" -I -m kri_assurance_eval.cli example
"$USE" -I "$STUDY/ev01/check.py" --output "$WORK/reference-report"
```

Record commands, exit codes and failures locally. Before installation, record
and check the wheel hash with `shasum -a 256` or Python hashlib. A mismatch is
reportable; do not edit the expected hash. Source archive timestamp/ownership bytes
are not claimed reproducible. The installed core has no third-party runtime
dependency; the separate build tools are pinned. Read the assembled INTERFACE.md
and CORRECTIONS.md before interpreting a result.

`check.py` defines seventeen reference vectors: ten embedded package examples
plus seven interface boundary cases. It saves requests, results, replay checks,
source hashes and minimal environment information in a new directory. It never
transmits data or actuates hardware. Copying check.py and protocol.json outside
the checkout is supported. Expected statuses are engineering checks, not added
scientific trials or external-validation attestations.

## Connect your own controller

Write a small `controller.py` outside the checkout defining
`propose(snapshot) -> [radial_acceleration, alongtrack_acceleration]`.
Use your own logic or an existing controller you may share. A simple rule is
enough; no training is requested. The runner passes two different supplied
observation histories and records your actions, assessments and replays.
The proposal may use `api.estimate_snapshot` and original observations. Do not
copy the supplied KRI controller and call it independent integration.
The public controller_adapter.py is orientation only; explain what you wrote.

Allowed numerical interfaces are the api functions in protocol.json and public
examples.examples. integrity.verify_installation is allowed for read-only identity
checking. Do not edit package code, import private _vendor modules as your interface,
patch checks or inject a precomputed safety set. Your own estimator may inform your
proposed action, but cannot replace observation-based assurance or turn covariance
into a deterministic bound. Keep the declared dynamics, frame and timing unchanged.

```sh
"$USE" -I "$STUDY/ev01/check.py" --controller "$WORK/controller.py" --output "$WORK/controller-report"
```

A controller is trusted local Python, not sandboxed code. Use only your own reviewed
source; do not execute received files without inspecting them. No device/network
access is needed. Explain handling of unsupported estimates and rejected proposals.
A zero proposal or unresolved/rejected action is not automatically an integration
failure. Show your output reaching the checker in both cases, including a nonzero
proposal when appropriate, without forcing acceptance. Acceptance count, mission
gain and execution speed are not integration success criteria.

## Status and evidence boundaries

This is a finite assumption-conditional planar model, using m, m/s, m/s2, radian
bearings and integer milliseconds from one epoch. Acceleration norm is at most
0.02 m/s2; application is in [700,710] ms, command end is 1200 ms and coast credit
expires at 4200 ms. supported_prefix is not recovery, mission completion, timely
physical execution or flight safety. unresolved does not prove impossibility;
uncredited_entry has no justified automatic fallback. Late/missed-window actions
receive no retroactive authority. No permission is granted to move any hardware.

Stale observations may yield prediction-only assessment from the bounded prior;
they are not silently used as fresh or automatically a universal safe fallback.
Contradictory arrived readings are unresolved. Valid and contract-invalid future
packets are rejected at the public delivered-only boundary. Direct-observer causal
ordering is separately regression-tested under post_audit_v1/tests; that private
interface is not exposed here as a public integration surface. The runner checks
A1's rejected result; the source regression suite instruments early rejection.
Those are different checks. The documented SA04 deadline failures and SA05 negative
acquisition/cost outcomes remain unchanged. The post-hoc attainability restriction
also remains; this exercise makes no comparative mission-benefit claim.

## Return and interpretation

Reply to the invitation with REPORT_TEMPLATE.md, generated reports and permitted
controller source/logs. A failure or stop-point contributes useful feedback.
Record every KRI clarification and its effect. Later assisted attempts have their
own identity and cannot replace an unaided failure. KRI may clarify text or errors;
it may not write your controller, perform your run or edit the original report
and describe that as independent work.

Independent installation requires an external participant's account of actual
installation, versions/environment and outputs. Independent integration also
requires their own interface/controller, two executed cases, documented error
handling and adequate provenance. A documentation comment, invitation, KRI adapter
run or self-hash alone is insufficient. Partial means steps/evidence are missing;
failure means an attempted step contradicted the contract or could not complete.
Report all, without forcing a pass. No general usability rate is inferred from
self-selected volunteers. Independence and permissions are assessed separately.

There is no claim of hardware validation, controller superiority, KRI-STD-001
conformance, certification or institutional endorsement. Response, independent
installation/integration and resolution remain pending until actual reports exist.
Original correspondence remains private. Reports, code, names and affiliations
are not published without explicit permission. Keep confidential data out.
Changes after an external attempt require a separate protocol/component identity.
