# Experiment 004 replacement confirmatory execution

The original Experiment 004 partition-44 confirmatory invocation was invalidated by an external execution timeout before inference. Its concise audit record is retained under `experiments/004-invalid-partition-44/`; partition 44 must never be reused.

The replacement protocol keeps the scientific design unchanged and reserves fresh partition 45. Its execution engine uses deterministic process-based parallelism with atomic paired-block checkpoint shards and canonical final assembly. On the validation host, an outcome-blind CPU benchmark was fastest at 8 workers, and re-execution of two fixed pilot blocks was byte-identical between serial and two-process execution.

The replacement partition is intentionally unmaterialized at design freeze. After the freeze is merged, the execution workflow must verify the exact freeze/readiness identities before seed materialization. The real campaign must be launched without a finite outer shell timeout.
