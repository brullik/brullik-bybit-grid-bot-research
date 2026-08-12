# ADR-0006: Exact Execution Arithmetic

- Status: accepted
- Date: 2026-07-28

## Context

Exchange tick size, quantity step, leverage, investment, stop-loss, and grid boundaries are discrete. Binary-float rounding can change validity, expected risk, or actual payloads.

## Decision

At all execution and risk boundaries:

- parse exchange numerics without lossy float coercion;
- use Decimal or scaled integers with explicit units;
- quantize through named, tested rounding policies;
- canonicalize serialized payloads;
- compute risk again after final quantization;
- fail closed if post-rounding intended loss or constraints cannot be proven.

Analytics may use Float64 only where the contract explicitly permits it and execution semantics cannot be affected.

## Consequences

- safer and reproducible payloads;
- easier request hashing and audit;
- more explicit conversion code/tests;
- physical analytical representation can be optimized independently behind contracts.

## Rejected alternatives

- Native Python/binary floats everywhere: hidden representation and rounding errors.
- Trust exchange-side validation only: does not prove local intended-risk contract.
