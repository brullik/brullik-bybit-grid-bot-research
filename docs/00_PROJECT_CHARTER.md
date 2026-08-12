# Project Charter

**Project:** brullik-bybit-grid-bot-research  
**Version:** 0.1.0  
**Date:** 2026-07-28  
**Owner / product authority:** brullik  
**Operating model:** owner-led, documentation-first, evidence-gated

## Mission

Design and later implement a reproducible research-to-live platform for Bybit linear USDT perpetual markets. The platform will discover and validate horizontal consolidation opportunities for a native Futures Grid Bot, promote only evidence-backed parameter sets, and operate live under strict risk, reconciliation, and emergency controls.

## Final outcome

The project is complete only when the owner can:

1. maintain a versioned market-history platform sized for 700 instruments and a ten-year 1m horizon;
2. reproduce any research result from immutable dataset and configuration versions;
3. build and independently verify a strategy release;
4. start the live application alone on a separate machine or environment;
5. run live without access to the full historical corpus or research optimizer;
6. recover live state after process, network, or host failure without guessing exchange state;
7. prove every create/close/risk decision through an append-only audit trail;
8. stop all new entries and safely reconcile or close active bots through an emergency workflow.

## Project authority

The owner/PM controls:

- final goal;
- scope and non-goals;
- risk policy;
- acceptance criteria and quality gates;
- promotion and live permissions;
- architecture decisions that change safety or component boundaries.

Implementation agents and contributors may propose changes but may not unilaterally weaken these controls.

## Constraints

- Public GitHub repository; no secrets, private account exports, or market datasets in Git.
- History, research, release, and live must be separately runnable.
- Live must not require the multi-billion-row historical store.
- Capacity envelope: 700 instruments × 10 years × 1m.
- Data before instrument launch must not be invented.
- Correctness and auditability take precedence over maximum throughput; performance is then optimized within those constraints.
- Exact arithmetic is mandatory at order/grid payload boundaries.
- No autonomous live launch before explicit readiness approval.

## Initial economic and strategy assumptions

These assumptions are controlled inputs, not guaranteed outcomes:

- initial equity hypothesis: 500 USDT;
- maximum planned loss per grid: 5 USDT;
- Bybit linear USDT perpetuals;
- horizontal range/consolidation strategy;
- native Futures Grid Bot;
- Neutral + Geometric mode;
- trailing disabled in V1;
- one active grid per symbol;
- manual approval for initial real executions;
- emergency stop blocks all new entries until explicit resume.

## Definition of project success

Success is not “a script places a grid” or “a backtest is profitable.” Success requires data integrity, research reproducibility, honest validation, deployment isolation, safe execution, recovery, and owner-approved live operation. Detailed criteria are in `01_FINAL_GOAL_AND_SUCCESS_CRITERIA.md`.
