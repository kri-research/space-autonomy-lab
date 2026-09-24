# Post hoc spacecraft certificate audit protocol

This freeze was created before executing any primary campaign input through the
new numerical engine. Original outcomes were already known; this is not a blinded
experiment. The recorded original source, 768 input/episode/qualification identities
and independent source inventory are bound by the audit identity below.

Audit identity: `bc472385b582d0f5d6ee9e7a3e4d5f250d316f2c6c9a4c8e31be21f838577f53`

Implementation revision: `d667ef4b58ff95863282c7d48b683c7e1e24e5ce`

From the study root, verify without numerical campaign execution:

```sh
python -m independent_hcw_audit_v1.protocol --verify independent_hcw_audit_v1/frozen/protocol.json --audit-id bc472385b582d0f5d6ee9e7a3e4d5f250d316f2c6c9a4c8e31be21f838577f53
```

A separately authorized full audit uses `python -m independent_hcw_audit_v1.runner`
with the same `--freeze` and `--audit-id`, a new `--output` outside Git checkouts,
and the explicit `--authorize-R03` flag. That flag is an execution confirmation,
not an access-control mechanism. The private project stores the exact R03 command.
Use `--resume` only for an unchanged existing audit under the frozen rules: no
completed receipt or started job is retried. Record a separate audit identity for
any code, numerical-budget or retry amendment, retaining the prior attempt.

All 1,728 saved singleton qualification commands are included in the planned
read-only verification. The original nine unresolved and three late decisions
retain no on-time certificate. Offline computations never rewrite the original
one-second policy timing or 768-case endpoint. No new candidate command, replacement
dual or protected random input is generated.

The `full_campaign_executed: false` field describes this preserved pre-audit
protocol. Future execution belongs in a separate result artifact, not an edited
freeze. The implementation source branch must be retained if repository rules
require a squash merge. No main-ancestry or independent-custody claim is implied.
