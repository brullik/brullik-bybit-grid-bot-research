# M2 canonical publication preordered fast-path benchmark

## Purpose

Measure ADR-0086 against its immediate `main` parent on one existing receipt-verified Landing
child. The benchmark repeats no Bybit request, writes no canonical dataset, and publishes no
private path, dataset, symbol, instrument, time bound, market value, or table fingerprint.

## Fixed workload and command

- baseline checkout: merge `663cbed25589aa6dae42b904ee42b0c80aaaf19f`;
- candidate checkout: the immutable ADR-0086 implementation commit;
- input: the same completed 160,043-row trade-candle Landing child in both checkouts;
- operation: `load_verified_completed_history_publication_batch(<job-root>)`;
- sequence: baseline warm-up, candidate warm-up, candidate measured, baseline measured;
- clock: `time.perf_counter_ns()` immediately around the production loader call;
- interpreter/dependencies: the same Python executable and environment for all four processes;
- cache disclosure: warm/uncontrolled; and
- correctness: compare completed-manifest binding, canonical-admission payload, partition path,
  Arrow schema including metadata, row count, and SHA-256 of the complete Arrow IPC stream.

The exact invocation pattern is:

```powershell
& <python> <private-harness> `
  --baseline-root <clean-baseline-worktree> `
  --candidate-root <clean-candidate-worktree> `
  --job-root <receipt-verified-landing-child> `
  --order baseline,candidate,candidate,baseline
```

`<private-harness>` sets `PYTHONPATH` to the selected checkout's root plus the repository package
and application source roots, starts a fresh interpreter for each sample, measures only the
production loader call, compares private fingerprints in memory, and emits only aggregate timing,
row count, environment, and equality facts. The private harness and source identity remain outside
Git because command-line paths and the table fingerprint are deliberately non-public.

## Preliminary result

On Windows/AMD64 with Python 3.14, PyArrow 25.0.1, 12 logical CPUs, and 16 GiB RAM, the measured
baseline took 9,480,584,000 ns and the candidate took 7,672,455,000 ns. Candidate/baseline speed
was 1.236x and elapsed time fell approximately 19.1%. All correctness comparisons were equal and
canonical admission excluded zero rows.

This preliminary comparison motivated the implementation but is not a Gate 2 threshold. A
post-merge repetition must bind the candidate to its merge SHA before it is promoted to sanitized
receipt-bound performance evidence. The result does not measure campaign orchestration, Parquet
writing, catalog registration, research selection, or live execution.
