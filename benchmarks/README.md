# Matching benchmark

A metrics and stress harness for the Latent Exchange matching engine. It
implements the Phase-1 measurement list from the main `README.md`
("Phased prototype" -> "Phase 1: exchange clearing", step 9):

> Measure match rate, participant surplus, completion rate, time to match,
> cancellation rate, probability calibration, cold-start access,
> distributional fairness, and explanation quality.

It drives the **real engine** (`post_intent` → `generate_candidates` →
`create_proposal` → `settle_proposal`) — nothing is reimplemented — and is
zero-dependency and fully deterministic under a fixed seed.

## Run

```sh
# Phase-1 metrics over 20 kingdoms / 60 epochs
python benchmarks/matching_benchmark.py --mode metrics --kingdoms 20 --epochs 60 --seed 42

# cold-start: 30% of kingdoms stay inactive until epoch 30, then join
python benchmarks/matching_benchmark.py --mode metrics --kingdoms 20 --epochs 60 --late-join-epoch 30 --seed 7

# combinatorial blow-up of generate_candidates(), sweeping kingdom count
python benchmarks/matching_benchmark.py --mode stress --max-kingdoms 40 --seed 7

# both, written to a JSON report
python benchmarks/matching_benchmark.py --mode all --out report.json
```

Tests (run from the repo root):

```sh
python -m unittest discover tests -v
```

## Metrics

| Metric | Meaning | Where it comes from |
|---|---|---|
| `match_rate` | settled intents ÷ intents posted | `intents_settled` / `intents_posted` |
| `completion_rate` | settled proposals ÷ proposals created | `proposals_settled` / `proposals_created` |
| `mean/median_time_to_match` | epochs between an intent being posted and its settlement | per-intent `intent_epoch` bookkeeping |
| `intent_expiry_rate` | intents that aged out unmatched | `intents_expired` / `intents_posted` |
| `credit_volume` / `units_traded` | value actually moved | summed `credit_amount` / transfer quantities |
| `participants_who_traded` | distinct kingdoms that appeared in a settled proposal | trade counter |
| `trade_concentration_hhi` | Herfindahl-Hirschman index of trade concentration | share of each kingdom in all trades |
| `top1_participant_share` | share of trades captured by the single busiest kingdom | trade counter |
| `cold_start_delays` | epochs a late-joining kingdom needed before its first trade | `late-join-epoch` cohort |

## Metrics deliberately left as N/A

`probability_calibration` and `explanation_quality` are named in the README's
Phase-1 list, but the prototype has no probability model (`s_{pq}` / `π`) and
no per-proposal explanation field yet. Inventing either here would duplicate
the risk-model phase, so the harness reports them as `N/A` rather than
fabricating numbers.

## Why the stress sweep matters

`generate_candidates` enumerates every pairwise combination and every 3-cycle,
so its cost is polynomial in the intent count. The `stress` mode times a single
call while sweeping kingdom count, exposing the scaling ceiling before any
solver work is attempted — the empirical motivation for a bounded candidate
generator or a Rust core.
