# Retained first correction build

These are byte-identical copies of the first correction release and records at
`eb0d1b3bce712cd2631970c3ba13689b723c832a`, generated from source
`88888f7fb29e3784681832f450b15de92484a47d` before GitHub CI validation.
The software tests and internal installation passed. The new workflow failed
YAML parsing because an inline pip command contained a colon followed by a space.
The seven existing workflows passed; that did not constitute complete CI success.

The current correction uses a new source/evidence identity after the workflow
format fix and an added regression. Runtime numerical logic, all older studies,
the post-hoc attainability calculation and its recorded output are unchanged.
This archive is not the currently recommended build and is not a second campaign.
For exact historical reproduction use the retained commit above in a separate
full-history checkout. The current verifier intentionally checks the current build.
