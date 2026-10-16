"""Metrics and stress harness for the Latent Exchange matching engine.

This maps one-to-one onto the Phase-1 measurement list in ``README.md``
("Phased prototype" -> "Phase 1: exchange clearing", step 9):

    Measure match rate, participant surplus, completion rate, time to
    match, cancellation rate, probability calibration, cold-start access,
    distributional fairness, and explanation quality.

Design notes
------------
* Zero dependencies (Python standard library only), matching the game.
* Fully deterministic under a fixed seed: same arguments -> same report.
* Uses the public engine API only (``post_intent``, ``generate_candidates``,
  ``create_proposal``, ``settle_proposal``). It drives the real matching
  engine; it never reimplements it.

Metrics that README names but the prototype has no model for yet
(probability calibration, explanation quality) are reported as N/A and
left to the risk-model phase rather than invented here.

Usage
-----
    python benchmarks/matching_benchmark.py --mode metrics --kingdoms 20 --epochs 60 --seed 42
    python benchmarks/matching_benchmark.py --mode metrics --late-join-epoch 30 --seed 7
    python benchmarks/matching_benchmark.py --mode stress --max-kingdoms 40 --seed 7
    python benchmarks/matching_benchmark.py --mode all --out report.json
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from kingdom_wars import (  # noqa: E402
    GameError,
    GameState,
    IntentKind,
    Kingdom,
    Personality,
    ProposalKind,
    Region,
    Resource,
    create_proposal,
    generate_candidates,
    post_intent,
    settle_proposal,
)

RESOURCES = list(Resource)
INTENT_KINDS = [IntentKind.BARTER, IntentKind.SELL, IntentKind.BUY]
MAX_INTENTS_PER_KINGDOM = 3
INTENT_MAX_AGE = 6
POST_PROBABILITY = 0.8


def make_world(n_kingdoms: int, seed: int) -> tuple[GameState, random.Random]:
    """Build an N-kingdom world with the same shapes the game uses.

    Kingdoms are all non-human so that ``create_proposal`` fills in every
    approval automatically and settlement is not gated on a human turn.
    """
    rng = random.Random(seed)
    kingdoms: dict[str, Kingdom] = {}
    regions: dict[str, Region] = {}
    for i in range(n_kingdoms):
        name = f"K{i}"
        kingdoms[name] = Kingdom(name, f"King {i}", Personality.BALANCED)
        regions[name] = Region(rng.randint(4, 12), rng.randint(4, 12))
    state = GameState(kingdoms=kingdoms, regions=regions, human_kingdom="K0")
    return state, rng


def top_up(state: GameState, rng: random.Random) -> None:
    """Mimic production so kingdoms have goods to offer and fund to spend."""
    for kingdom in state.kingdoms.values():
        if not kingdom.active:
            continue
        kingdom.resources[Resource.FOOD] += rng.randint(6, 16)
        kingdom.resources[Resource.WOOD] += rng.randint(2, 8)
        kingdom.resources[Resource.METAL] += rng.randint(2, 8)


def random_intent_spec(
    rng: random.Random,
) -> tuple[IntentKind, Resource, int, Resource | None, int | None]:
    """Sample one intent shape: barter, cash sale, or credit buy."""
    kind = rng.choice(INTENT_KINDS)
    resource = rng.choice(RESOURCES)
    quantity = rng.randint(1, 3)
    if kind is IntentKind.BARTER:
        want_resource = rng.choice([r for r in RESOURCES if r is not resource])
        return kind, resource, quantity, want_resource, rng.randint(1, 3)
    return kind, resource, quantity, None, None


def post_intent_for(
    state: GameState,
    kingdom: Kingdom,
    rng: random.Random,
    metrics: "Metrics",
    intent_epoch: dict[int, int],
) -> None:
    """Post one intent for a kingdom; silence on GameError is intentional."""
    kind, resource, quantity, want_resource, want_quantity = random_intent_spec(rng)
    try:
        intent = post_intent(
            state,
            kingdom.name,
            kind,
            resource,
            quantity,
            want_resource,
            want_quantity,
        )
    except GameError:
        return  # not affordable etc.; the kingdom stays quiet this epoch
    metrics.intents_posted += 1
    intent_epoch[intent.id] = state.epoch


@dataclass
class Metrics:
    """Raw event counters collected while driving the real engine."""

    epochs: int
    kingdoms: int
    intents_posted: int = 0
    candidates_found: int = 0
    proposals_created: int = 0
    proposals_settled: int = 0
    intents_settled: int = 0
    intents_expired: int = 0
    intent_ages: list[int] = field(default_factory=list)
    credit_volume: int = 0
    units_traded: int = 0
    trades: Counter[str] = field(default_factory=Counter)
    first_trade_epoch: dict[str, int] = field(default_factory=dict)
    cold_start_delays: list[int] = field(default_factory=list)

    def summary(self) -> dict:
        """Derive the README Phase-1 metrics from the raw counters."""
        settled = self.proposals_settled
        created = self.proposals_created
        posted = self.intents_posted
        ages = self.intent_ages
        trade_counts = list(self.trades.values())
        total_trades = sum(trade_counts)
        hhi = sum((c / total_trades) ** 2 for c in trade_counts) if total_trades else 0.0
        top1 = max(trade_counts) / total_trades if total_trades else 0.0
        return {
            "intents_posted": posted,
            "candidates_found": self.candidates_found,
            "proposals_created": created,
            "proposals_settled": settled,
            "completion_rate": round(settled / created, 4) if created else 0.0,
            "match_rate": round(self.intents_settled / posted, 4) if posted else 0.0,
            "mean_time_to_match_epochs": round(statistics.mean(ages), 3) if ages else 0.0,
            "median_time_to_match_epochs": statistics.median(ages) if ages else 0,
            "intents_expired_unmatched": self.intents_expired,
            "intent_expiry_rate": round(self.intents_expired / posted, 4) if posted else 0.0,
            "credit_volume": self.credit_volume,
            "units_traded": self.units_traded,
            "participants_who_traded": len(self.trades),
            "trade_concentration_hhi": round(hhi, 4),
            "top1_participant_share": round(top1, 4),
            "probability_calibration": "N/A (no risk model yet; see README risk phase)",
            "explanation_quality": "N/A (no explanation field in the prototype yet)",
        }


def _record_settle(
    state: GameState,
    proposal,
    metrics: Metrics,
    intent_epoch: dict[int, int],
) -> None:
    metrics.intents_settled += len(proposal.intent_ids)
    for intent_id in proposal.intent_ids:
        posted = intent_epoch.get(intent_id)
        if posted is not None:
            metrics.intent_ages.append(state.epoch - posted)
    if proposal.kind is ProposalKind.CREDIT:
        metrics.credit_volume += proposal.credit_amount
    for transfer in proposal.transfers:
        metrics.units_traded += transfer.quantity
        metrics.trades[transfer.provider] += 1
        metrics.trades[transfer.receiver] += 1
        metrics.first_trade_epoch.setdefault(transfer.provider, state.epoch)
        metrics.first_trade_epoch.setdefault(transfer.receiver, state.epoch)


def simulate(
    n_kingdoms: int,
    epochs: int,
    seed: int,
    *,
    late_join_epoch: int | None = None,
    join_share: float = 0.3,
) -> Metrics:
    """Run the real engine over ``epochs`` epochs and collect metrics.

    ``late_join_epoch`` activates a cohort of previously-inactive kingdoms
    part-way through, so cold-start access can be measured.
    """
    state, rng = make_world(n_kingdoms, seed)
    metrics = Metrics(epochs=epochs, kingdoms=n_kingdoms)
    intent_epoch: dict[int, int] = {}

    joiners: list[str] = []
    if late_join_epoch is not None:
        active_count = sum(1 for k in state.kingdoms.values() if k.active)
        joiners = [name for name in list(state.kingdoms)[active_count - int(n_kingdoms * join_share):]]
        for name in joiners:
            state.kingdoms[name].active = False

    for epoch in range(1, epochs + 1):
        state.epoch = epoch
        top_up(state, rng)

        if late_join_epoch is not None and epoch == late_join_epoch:
            for name in joiners:
                state.kingdoms[name].active = True

        for kingdom in state.kingdoms.values():
            if not kingdom.active:
                continue
            active_intents = sum(1 for i in state.intents.values() if i.owner == kingdom.name)
            if active_intents < MAX_INTENTS_PER_KINGDOM and rng.random() < POST_PROBABILITY:
                post_intent_for(state, kingdom, rng, metrics, intent_epoch)

        for intent_id, posted in list(intent_epoch.items()):
            if intent_id not in state.intents:
                intent_epoch.pop(intent_id)
                continue
            if state.epoch - posted >= INTENT_MAX_AGE:
                state.intents.pop(intent_id)
                intent_epoch.pop(intent_id)
                metrics.intents_expired += 1

        candidates = generate_candidates(state)
        metrics.candidates_found += len(candidates)

        for candidate in candidates:
            try:
                proposal = create_proposal(state, candidate.id)
            except GameError:
                continue
            metrics.proposals_created += 1
            try:
                settle_proposal(state, proposal.id)
                metrics.proposals_settled += 1
                _record_settle(state, proposal, metrics, intent_epoch)
            except GameError:
                state.proposals.pop(proposal.id, None)  # failed validation; treated as cancellation

    if late_join_epoch is not None:
        metrics.cold_start_delays = [
            metrics.first_trade_epoch[name] - late_join_epoch
            for name in joiners
            if name in metrics.first_trade_epoch
        ]
    else:
        metrics.cold_start_delays = []
    return metrics


def stress(max_kingdoms: int, seed: int, intents_per_kingdom: int = 2) -> list[dict]:
    """Sweep kingdom count and time ``generate_candidates``.

    The generator enumerates pairwise combinations and all 3-cycles, so
    wall time should blow up combinatorially. This quantifies the ceiling.
    """
    rows: list[dict] = []
    for n in range(5, max_kingdoms + 1, 5):
        state, rng = make_world(n, seed)
        for kingdom in state.kingdoms.values():
            kingdom.resources = {resource: 60 for resource in RESOURCES}
            for _ in range(intents_per_kingdom):
                kind, resource, quantity, want_resource, want_quantity = random_intent_spec(rng)
                try:
                    post_intent(
                        state,
                        kingdom.name,
                        kind,
                        resource,
                        quantity,
                        want_resource,
                        want_quantity,
                    )
                except GameError:
                    pass
        intent_count = len(state.intents)
        start = time.perf_counter()
        candidates = generate_candidates(state)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        rows.append(
            {
                "kingdoms": n,
                "intents": intent_count,
                "candidates": len(candidates),
                "generate_ms": round(elapsed_ms, 2),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["metrics", "stress", "all"], default="metrics")
    parser.add_argument("--kingdoms", type=int, default=20, help="kingdoms for metrics mode")
    parser.add_argument("--epochs", type=int, default=60, help="epochs for metrics mode")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--late-join-epoch",
        type=int,
        default=None,
        help="activate a late cohort at this epoch to measure cold-start access",
    )
    parser.add_argument("--max-kingdoms", type=int, default=40, help="ceiling for stress mode")
    parser.add_argument("--out", default=None, help="write the JSON report to this path")
    args = parser.parse_args(argv)

    report: dict = {"seed": args.seed, "mode": args.mode}
    if args.mode in ("metrics", "all"):
        metrics = simulate(
            args.kingdoms,
            args.epochs,
            args.seed,
            late_join_epoch=args.late_join_epoch,
        )
        report["metrics"] = metrics.summary()
        print("== Metrics ==")
        for key, value in report["metrics"].items():
            print(f"  {key}: {value}")
    if args.mode in ("stress", "all"):
        rows = stress(args.max_kingdoms, args.seed)
        report["stress"] = rows
        print("== Stress: generate_candidates wall time ==")
        print(f"  {'kingdoms':>8} {'intents':>8} {'candidates':>10} {'generate_ms':>12}")
        for row in rows:
            print(
                f"  {row['kingdoms']:>8} {row['intents']:>8} "
                f"{row['candidates']:>10} {row['generate_ms']:>12}"
            )
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Report written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
