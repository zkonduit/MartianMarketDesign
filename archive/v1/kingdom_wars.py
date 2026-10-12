"""Kingdom Wars: a dependency-free resource, combat, and exchange CLI game."""

from __future__ import annotations

import argparse
import itertools
import math
import random
import shlex
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable


class GameError(ValueError):
    """A player-visible rule violation."""


class Resource(str, Enum):
    FOOD = "food"
    WOOD = "wood"
    METAL = "metal"


class Job(str, Enum):
    IDLE = "idle"
    FOOD = "food"
    WOOD = "wood"
    METAL = "metal"


class Personality(str, Enum):
    HUMAN = "human"
    BALANCED = "balanced"
    ASSASSIN = "assassin"
    FRIENDLY = "friendly"


class IntentKind(str, Enum):
    BARTER = "barter"
    SELL = "sell"
    BUY = "buy"


class ProposalKind(str, Enum):
    BARTER = "barter"
    CREDIT = "credit"


WARRIOR_POWER = {1: 2, 2: 5, 3: 9}
TRAIN_COST = {resource: 3 for resource in Resource}
UPGRADE_COST = {
    1: {resource: 6 for resource in Resource},
    2: {resource: 9 for resource in Resource},
}


def resource_stock(food: int = 0, wood: int = 0, metal: int = 0) -> dict[Resource, int]:
    return {Resource.FOOD: food, Resource.WOOD: wood, Resource.METAL: metal}


def worker_assignments(food: int = 2, wood: int = 1, metal: int = 1, idle: int = 0) -> dict[Job, int]:
    return {Job.IDLE: idle, Job.FOOD: food, Job.WOOD: wood, Job.METAL: metal}


@dataclass
class Region:
    wood: int
    metal: int


@dataclass
class Kingdom:
    name: str
    king: str
    personality: Personality
    defense: int = 10
    resources: dict[Resource, int] = field(default_factory=lambda: resource_stock(food=8))
    assignments: dict[Job, int] = field(default_factory=worker_assignments)
    warriors: dict[int, int] = field(default_factory=lambda: {1: 0, 2: 0, 3: 0})
    balance: int = 0
    debt_limit: int = 30
    active: bool = True
    completed_cycles: int = 0
    completed_credit_trades: int = 0
    last_attack_epoch: int = -1

    @property
    def human(self) -> bool:
        return self.personality is Personality.HUMAN

    @property
    def workers(self) -> int:
        return sum(self.assignments.values())

    @property
    def warrior_count(self) -> int:
        return sum(self.warriors.values())

    @property
    def warrior_power(self) -> int:
        return sum(WARRIOR_POWER[level] * count for level, count in self.warriors.items())

    @property
    def population(self) -> int:
        return self.workers + self.warrior_count


@dataclass(frozen=True)
class Intent:
    id: int
    owner: str
    kind: IntentKind
    resource: Resource
    quantity: int
    want_resource: Resource | None = None
    want_quantity: int | None = None


@dataclass(frozen=True)
class Transfer:
    provider: str
    receiver: str
    resource: Resource
    quantity: int


@dataclass(frozen=True)
class Candidate:
    id: int
    kind: ProposalKind
    intent_ids: tuple[int, ...]
    transfers: tuple[Transfer, ...]
    participants: tuple[str, ...]
    unit_price: int = 0
    credit_amount: int = 0


@dataclass
class Proposal:
    id: int
    kind: ProposalKind
    intent_ids: tuple[int, ...]
    transfers: tuple[Transfer, ...]
    participants: tuple[str, ...]
    expires_epoch: int
    approvals: set[str] = field(default_factory=set)
    unit_price: int = 0
    credit_amount: int = 0


@dataclass
class GameState:
    kingdoms: dict[str, Kingdom]
    regions: dict[str, Region]
    human_kingdom: str
    epoch: int = 0
    intents: dict[int, Intent] = field(default_factory=dict)
    candidates: dict[int, Candidate] = field(default_factory=dict)
    proposals: dict[int, Proposal] = field(default_factory=dict)
    next_intent_id: int = 1
    next_candidate_id: int = 1
    next_proposal_id: int = 1
    winner: str | None = None
    victory_type: str | None = None


@dataclass(frozen=True)
class CommandResult:
    ok: bool
    message: str
    quit: bool = False


def _require_positive(count: int) -> None:
    if count <= 0:
        raise GameError("Quantity must be a positive integer.")


def _can_afford(kingdom: Kingdom, cost: dict[Resource, int], count: int = 1) -> bool:
    return all(kingdom.resources[resource] >= amount * count for resource, amount in cost.items())


def _spend(kingdom: Kingdom, cost: dict[Resource, int], count: int = 1) -> None:
    _require_positive(count)
    if not _can_afford(kingdom, cost, count):
        raise GameError("Insufficient resources.")
    for resource, amount in cost.items():
        kingdom.resources[resource] -= amount * count


def assign_workers(kingdom: Kingdom, requested: dict[Job, int]) -> None:
    if any(count < 0 for count in requested.values()):
        raise GameError("Worker counts cannot be negative.")
    assigned = sum(requested.get(job, 0) for job in (Job.FOOD, Job.WOOD, Job.METAL))
    if assigned > kingdom.workers:
        raise GameError(f"Only {kingdom.workers} workers are available.")
    kingdom.assignments = worker_assignments(
        food=requested.get(Job.FOOD, 0),
        wood=requested.get(Job.WOOD, 0),
        metal=requested.get(Job.METAL, 0),
        idle=kingdom.workers - assigned,
    )


def recruit(kingdom: Kingdom, count: int = 1) -> None:
    _spend(kingdom, {Resource.FOOD: 5}, count)
    kingdom.assignments[Job.IDLE] += count


def _remove_workers(kingdom: Kingdom, count: int) -> None:
    if kingdom.workers < count:
        raise GameError("Not enough workers.")
    remaining = count
    for job in (Job.IDLE, Job.WOOD, Job.METAL, Job.FOOD):
        removed = min(remaining, kingdom.assignments[job])
        kingdom.assignments[job] -= removed
        remaining -= removed
        if remaining == 0:
            return


def train(kingdom: Kingdom, count: int = 1) -> None:
    _require_positive(count)
    if kingdom.workers < count:
        raise GameError("Not enough workers.")
    if not _can_afford(kingdom, TRAIN_COST, count):
        raise GameError("Insufficient resources.")
    _remove_workers(kingdom, count)
    _spend(kingdom, TRAIN_COST, count)
    kingdom.warriors[1] += count


def upgrade(kingdom: Kingdom, from_level: int, count: int = 1) -> None:
    _require_positive(count)
    if from_level not in UPGRADE_COST:
        raise GameError("Upgrade level must be 1 or 2.")
    if kingdom.warriors[from_level] < count:
        raise GameError(f"Not enough level-{from_level} warriors.")
    if not _can_afford(kingdom, UPGRADE_COST[from_level], count):
        raise GameError("Insufficient resources.")
    _spend(kingdom, UPGRADE_COST[from_level], count)
    kingdom.warriors[from_level] -= count
    kingdom.warriors[from_level + 1] += count


def fortify(kingdom: Kingdom, count: int = 1) -> None:
    _spend(kingdom, {Resource.WOOD: 10, Resource.METAL: 10}, count)
    kingdom.defense += 5 * count


def _kill_for_starvation(kingdom: Kingdom, deaths: int) -> None:
    for job in (Job.IDLE, Job.WOOD, Job.METAL):
        killed = min(deaths, kingdom.assignments[job])
        kingdom.assignments[job] -= killed
        deaths -= killed
    for level in (1, 2, 3):
        killed = min(deaths, kingdom.warriors[level])
        kingdom.warriors[level] -= killed
        deaths -= killed
    killed = min(deaths, kingdom.assignments[Job.FOOD])
    kingdom.assignments[Job.FOOD] -= killed


def produce_and_feed(kingdom: Kingdom, region: Region) -> str:
    food = kingdom.assignments[Job.FOOD] * 3
    wood = min(region.wood, kingdom.assignments[Job.WOOD] * 2)
    metal = min(region.metal, kingdom.assignments[Job.METAL] * 2)
    kingdom.resources[Resource.FOOD] += food
    kingdom.resources[Resource.WOOD] += wood
    kingdom.resources[Resource.METAL] += metal
    upkeep = kingdom.population
    eaten = min(upkeep, kingdom.resources[Resource.FOOD])
    kingdom.resources[Resource.FOOD] -= eaten
    deaths = upkeep - eaten
    if deaths:
        _kill_for_starvation(kingdom, deaths)
    message = f"{kingdom.name}: +{food} food, +{wood} wood, +{metal} metal"
    return message + (f"; {deaths} starved" if deaths else "")


def _apply_warrior_damage(kingdom: Kingdom, damage: int) -> tuple[int, int]:
    casualties = 0
    for level in (1, 2, 3):
        power = WARRIOR_POWER[level]
        while kingdom.warriors[level] and damage >= power:
            kingdom.warriors[level] -= 1
            damage -= power
            casualties += 1
        if kingdom.warriors[level] and damage < power:
            return casualties, 0
    return casualties, damage


def resolve_attack(state: GameState, attacker_name: str, defender_name: str, rng: random.Random) -> str:
    attacker = state.kingdoms[attacker_name]
    defender = state.kingdoms[defender_name]
    if not attacker.active or not defender.active or attacker_name == defender_name:
        raise GameError("Attack requires two different active kingdoms.")
    if attacker.last_attack_epoch == state.epoch:
        raise GameError("This kingdom has already attacked in the current epoch.")
    if attacker.warrior_power == 0:
        raise GameError("At least one warrior is required to attack.")

    attack_power = attacker.warrior_power
    defense_power = defender.warrior_power
    attack_damage = rng.randint(math.ceil(attack_power / 2), attack_power)
    counter_damage = rng.randint(math.ceil(defense_power / 2), defense_power) if defense_power else 0
    attacker.last_attack_epoch = state.epoch

    defender_losses, overflow = _apply_warrior_damage(defender, attack_damage)
    attacker_losses, _ = _apply_warrior_damage(attacker, counter_damage)
    old_defense = defender.defense
    defender.defense = max(0, defender.defense - overflow)
    message = (
        f"{attacker.name} dealt {attack_damage}; {defender.name} lost {defender_losses} warriors "
        f"and {old_defense - defender.defense} defense. {attacker.name} lost {attacker_losses} warriors."
    )
    if defender.defense == 0:
        _take_over(state, attacker, defender)
        message += f" {defender.name} was conquered by {attacker.name}."
    _check_military_victory(state)
    return message


def _take_over(state: GameState, attacker: Kingdom, defender: Kingdom) -> None:
    for resource in Resource:
        attacker.resources[resource] += defender.resources[resource]
        defender.resources[resource] = 0
    attacker.assignments[Job.IDLE] += defender.workers
    defender.assignments = worker_assignments(0, 0, 0, 0)
    for level in (1, 2, 3):
        attacker.warriors[level] += defender.warriors[level]
        defender.warriors[level] = 0
    attacker.balance += defender.balance
    defender.balance = 0
    defender.active = False
    state.regions.pop(defender.name, None)
    doomed_intents = {intent_id for intent_id, intent in state.intents.items() if intent.owner == defender.name}
    for intent_id in doomed_intents:
        state.intents.pop(intent_id, None)
    for proposal_id, proposal in list(state.proposals.items()):
        if defender.name in proposal.participants or doomed_intents.intersection(proposal.intent_ids):
            state.proposals.pop(proposal_id)
    state.candidates.clear()
    _assert_credit_conservation(state)


def _check_military_victory(state: GameState) -> None:
    active = [kingdom.name for kingdom in state.kingdoms.values() if kingdom.active]
    if len(active) == 1:
        state.winner = active[0]
        state.victory_type = "military"


def _assert_credit_conservation(state: GameState) -> None:
    if sum(kingdom.balance for kingdom in state.kingdoms.values()) != 0:
        raise AssertionError("Mutual-credit balances must sum to zero.")


def post_intent(
    state: GameState,
    owner: str,
    kind: IntentKind,
    resource: Resource,
    quantity: int,
    want_resource: Resource | None = None,
    want_quantity: int | None = None,
) -> Intent:
    kingdom = state.kingdoms[owner]
    _require_positive(quantity)
    if not kingdom.active:
        raise GameError("Eliminated kingdoms cannot post intents.")
    if kind is IntentKind.BARTER:
        if want_resource is None or want_quantity is None:
            raise GameError("Barter requires a wanted resource and quantity.")
        _require_positive(want_quantity)
        if resource is want_resource:
            raise GameError("A barter must exchange different resources.")
    if kind in (IntentKind.BARTER, IntentKind.SELL) and _available_resource(state, owner, resource) < quantity:
        raise GameError("The offered goods are not available.")
    intent = Intent(
        id=state.next_intent_id,
        owner=owner,
        kind=kind,
        resource=resource,
        quantity=quantity,
        want_resource=want_resource,
        want_quantity=want_quantity,
    )
    state.next_intent_id += 1
    state.intents[intent.id] = intent
    state.candidates.clear()
    return intent


def cancel_intent(state: GameState, owner: str, intent_id: int) -> None:
    intent = state.intents.get(intent_id)
    if intent is None or intent.owner != owner:
        raise GameError("Intent not found.")
    if any(intent_id in proposal.intent_ids for proposal in state.proposals.values()):
        raise GameError("Intent is reserved by a pending proposal.")
    state.intents.pop(intent_id)
    state.candidates.clear()


def _reserved_resource(state: GameState, owner: str, resource: Resource, exclude: int | None = None) -> int:
    return sum(
        transfer.quantity
        for proposal_id, proposal in state.proposals.items()
        if proposal_id != exclude
        for transfer in proposal.transfers
        if transfer.provider == owner and transfer.resource is resource
    )


def _available_resource(state: GameState, owner: str, resource: Resource, exclude: int | None = None) -> int:
    return state.kingdoms[owner].resources[resource] - _reserved_resource(state, owner, resource, exclude)


def _can_afford_available(
    state: GameState, owner: str, cost: dict[Resource, int], count: int = 1
) -> bool:
    return all(_available_resource(state, owner, resource) >= amount * count for resource, amount in cost.items())


def _reserved_debit(state: GameState, buyer: str, exclude: int | None = None) -> int:
    return sum(
        proposal.credit_amount
        for proposal_id, proposal in state.proposals.items()
        if proposal_id != exclude
        and proposal.kind is ProposalKind.CREDIT
        and proposal.transfers[0].receiver == buyer
    )


def market_price(state: GameState, resource: Resource) -> int:
    demand = sum(
        intent.quantity
        for intent in state.intents.values()
        if intent.kind is IntentKind.BUY and intent.resource is resource and state.kingdoms[intent.owner].active
    )
    supply = sum(
        intent.quantity
        for intent in state.intents.values()
        if intent.kind is IntentKind.SELL and intent.resource is resource and state.kingdoms[intent.owner].active
    )
    price = math.ceil(2 * (demand + 1) / (supply + 1))
    return max(1, min(5, price))


def _funded(state: GameState, intent: Intent) -> bool:
    if not state.kingdoms[intent.owner].active:
        return False
    if intent.kind is IntentKind.BUY:
        return True
    return _available_resource(state, intent.owner, intent.resource) >= intent.quantity


def _barter_fits(giver: Intent, receiver: Intent) -> bool:
    return (
        giver.resource is receiver.want_resource
        and giver.quantity == receiver.want_quantity
        and giver.owner != receiver.owner
    )


def generate_candidates(state: GameState) -> list[Candidate]:
    state.candidates.clear()
    barter = sorted(
        (
            intent
            for intent in state.intents.values()
            if intent.kind is IntentKind.BARTER and _funded(state, intent)
        ),
        key=lambda intent: intent.id,
    )
    credit_sells = [
        intent for intent in state.intents.values() if intent.kind is IntentKind.SELL and _funded(state, intent)
    ]
    credit_buys = [
        intent for intent in state.intents.values() if intent.kind is IntentKind.BUY and _funded(state, intent)
    ]
    raw: list[tuple[ProposalKind, tuple[int, ...], tuple[Transfer, ...], int, int]] = []

    for first, second in itertools.combinations(barter, 2):
        if _barter_fits(first, second) and _barter_fits(second, first):
            transfers = (
                Transfer(first.owner, second.owner, first.resource, first.quantity),
                Transfer(second.owner, first.owner, second.resource, second.quantity),
            )
            raw.append((ProposalKind.BARTER, (first.id, second.id), transfers, 0, 0))

    seen_cycles: set[tuple[int, ...]] = set()
    for group in itertools.combinations(barter, 3):
        if len({intent.owner for intent in group}) != 3:
            continue
        for ordered in itertools.permutations(group):
            if all(_barter_fits(ordered[index], ordered[(index + 1) % 3]) for index in range(3)):
                ids = tuple(sorted(intent.id for intent in ordered))
                if ids in seen_cycles:
                    break
                seen_cycles.add(ids)
                transfers = tuple(
                    Transfer(intent.owner, ordered[(index + 1) % 3].owner, intent.resource, intent.quantity)
                    for index, intent in enumerate(ordered)
                )
                raw.append((ProposalKind.BARTER, ids, transfers, 0, 0))
                break

    for seller in credit_sells:
        for buyer in credit_buys:
            if (
                seller.owner != buyer.owner
                and seller.resource is buyer.resource
                and seller.quantity == buyer.quantity
            ):
                price = market_price(state, seller.resource)
                amount = seller.quantity * price
                buyer_kingdom = state.kingdoms[buyer.owner]
                projected = buyer_kingdom.balance - _reserved_debit(state, buyer.owner) - amount
                if projected < -buyer_kingdom.debt_limit:
                    continue
                transfer = Transfer(seller.owner, buyer.owner, seller.resource, seller.quantity)
                raw.append((ProposalKind.CREDIT, (seller.id, buyer.id), (transfer,), price, amount))

    raw.sort(
        key=lambda item: (
            -len({name for transfer in item[2] for name in (transfer.provider, transfer.receiver)}),
            -sum(transfer.quantity for transfer in item[2]),
            item[1],
        )
    )
    candidates: list[Candidate] = []
    for kind, intent_ids, transfers, price, amount in raw:
        participants = tuple(
            sorted({name for transfer in transfers for name in (transfer.provider, transfer.receiver)})
        )
        candidate = Candidate(
            id=state.next_candidate_id,
            kind=kind,
            intent_ids=intent_ids,
            transfers=transfers,
            participants=participants,
            unit_price=price,
            credit_amount=amount,
        )
        state.next_candidate_id += 1
        state.candidates[candidate.id] = candidate
        candidates.append(candidate)
    return candidates


def _validate_candidate(state: GameState, candidate: Candidate, exclude_proposal: int | None = None) -> None:
    if any(intent_id not in state.intents for intent_id in candidate.intent_ids):
        raise GameError("The candidate is stale.")
    if any(
        set(candidate.intent_ids).intersection(proposal.intent_ids)
        for proposal_id, proposal in state.proposals.items()
        if proposal_id != exclude_proposal
    ):
        raise GameError("One of the intents is already reserved.")
    required: dict[tuple[str, Resource], int] = {}
    for transfer in candidate.transfers:
        key = (transfer.provider, transfer.resource)
        required[key] = required.get(key, 0) + transfer.quantity
    for (provider, resource), quantity in required.items():
        if _available_resource(state, provider, resource, exclude_proposal) < quantity:
            raise GameError("A provider no longer has the promised goods.")
    if candidate.kind is ProposalKind.CREDIT:
        buyer = state.kingdoms[candidate.transfers[0].receiver]
        reserved_debit = _reserved_debit(state, buyer.name, exclude_proposal)
        if buyer.balance - reserved_debit - candidate.credit_amount < -buyer.debt_limit:
            raise GameError("The credit purchase would exceed the buyer's debt limit.")


def create_proposal(state: GameState, candidate_id: int) -> Proposal:
    candidate = state.candidates.get(candidate_id)
    if candidate is None:
        raise GameError("Candidate not found; run match again.")
    _validate_candidate(state, candidate)
    approvals = {name for name in candidate.participants if not state.kingdoms[name].human}
    proposal = Proposal(
        id=state.next_proposal_id,
        kind=candidate.kind,
        intent_ids=candidate.intent_ids,
        transfers=candidate.transfers,
        participants=candidate.participants,
        expires_epoch=state.epoch + 1,
        approvals=approvals,
        unit_price=candidate.unit_price,
        credit_amount=candidate.credit_amount,
    )
    state.next_proposal_id += 1
    state.proposals[proposal.id] = proposal
    state.candidates.clear()
    return proposal


def settle_proposal(state: GameState, proposal_id: int) -> str:
    proposal = state.proposals.get(proposal_id)
    if proposal is None:
        raise GameError("Proposal not found.")
    if set(proposal.participants) != proposal.approvals:
        raise GameError("The proposal still needs approval.")
    candidate = Candidate(
        id=0,
        kind=proposal.kind,
        intent_ids=proposal.intent_ids,
        transfers=proposal.transfers,
        participants=proposal.participants,
        unit_price=proposal.unit_price,
        credit_amount=proposal.credit_amount,
    )
    _validate_candidate(state, candidate, exclude_proposal=proposal.id)
    for transfer in proposal.transfers:
        state.kingdoms[transfer.provider].resources[transfer.resource] -= transfer.quantity
        state.kingdoms[transfer.receiver].resources[transfer.resource] += transfer.quantity
    if proposal.kind is ProposalKind.CREDIT:
        seller = state.kingdoms[proposal.transfers[0].provider]
        buyer = state.kingdoms[proposal.transfers[0].receiver]
        seller.balance += proposal.credit_amount
        buyer.balance -= proposal.credit_amount
        for participant in proposal.participants:
            state.kingdoms[participant].completed_credit_trades += 1
    elif len(proposal.participants) == 3:
        for participant in proposal.participants:
            state.kingdoms[participant].completed_cycles += 1

    used = set(proposal.intent_ids)
    for intent_id in used:
        state.intents.pop(intent_id, None)
    for other_id, other in list(state.proposals.items()):
        if used.intersection(other.intent_ids):
            state.proposals.pop(other_id)
    state.candidates.clear()
    _assert_credit_conservation(state)
    detail = ", ".join(
        f"{transfer.provider} gave {transfer.quantity} {transfer.resource.value} to {transfer.receiver}"
        for transfer in proposal.transfers
    )
    if proposal.kind is ProposalKind.CREDIT:
        detail += f" for {proposal.credit_amount} credits ({proposal.unit_price}/unit)"
    return f"Proposal {proposal.id} settled: {detail}."


def approve_proposal(state: GameState, approver: str, proposal_id: int) -> str:
    proposal = state.proposals.get(proposal_id)
    if proposal is None or approver not in proposal.participants:
        raise GameError("Proposal not found for this kingdom.")
    proposal.approvals.add(approver)
    if set(proposal.participants) == proposal.approvals:
        return settle_proposal(state, proposal_id)
    return f"Proposal {proposal_id} approved; awaiting other participants."


def reject_proposal(state: GameState, rejector: str, proposal_id: int) -> None:
    proposal = state.proposals.get(proposal_id)
    if proposal is None or rejector not in proposal.participants:
        raise GameError("Proposal not found for this kingdom.")
    state.proposals.pop(proposal_id)


def build_grand_market(state: GameState, kingdom_name: str) -> None:
    kingdom = state.kingdoms[kingdom_name]
    if kingdom.completed_cycles < 1:
        raise GameError("Complete a three-kingdom barter cycle first.")
    if kingdom.completed_credit_trades < 1:
        raise GameError("Complete a mutual-credit trade first.")
    if kingdom.balance < 0:
        raise GameError("Repay the kingdom's mutual-credit debt first.")
    if not _can_afford_available(state, kingdom_name, {resource: 30 for resource in Resource}):
        raise GameError("Insufficient unreserved resources.")
    _spend(kingdom, {resource: 30 for resource in Resource})
    state.winner = kingdom.name
    state.victory_type = "prosperity"


def _format_intent(intent: Intent) -> str:
    if intent.kind is IntentKind.BARTER:
        return (
            f"#{intent.id} {intent.owner}: give {intent.quantity} {intent.resource.value} "
            f"for {intent.want_quantity} {intent.want_resource.value}"
        )
    return f"#{intent.id} {intent.owner}: {intent.kind.value} {intent.quantity} {intent.resource.value} for credits"


def _format_candidate(candidate: Candidate) -> str:
    legs = "; ".join(
        f"{transfer.provider} -> {transfer.receiver}: {transfer.quantity} {transfer.resource.value}"
        for transfer in candidate.transfers
    )
    credit = f" at {candidate.unit_price}/unit ({candidate.credit_amount} credits)" if candidate.credit_amount else ""
    return f"#{candidate.id} {candidate.kind.value}{credit}: {legs}"


def _format_proposal(proposal: Proposal) -> str:
    legs = "; ".join(
        f"{transfer.provider} -> {transfer.receiver}: {transfer.quantity} {transfer.resource.value}"
        for transfer in proposal.transfers
    )
    return f"#{proposal.id} expires epoch {proposal.expires_epoch}: {legs}"


class GameEngine:
    """Owns time and orchestration; game-rule helpers remain independently testable."""

    def __init__(
        self,
        state: GameState,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        rng: random.Random | None = None,
        tick_seconds: float = 60.0,
    ) -> None:
        self.state = state
        self.clock = clock
        self.sleeper = sleeper
        self.rng = rng or random.Random()
        self.tick_seconds = tick_seconds
        self.last_tick_time = clock()

    @classmethod
    def new_game(
        cls,
        human_king: str = "Player",
        human_kingdom: str = "New Dawn",
        **kwargs: object,
    ) -> "GameEngine":
        rng = kwargs.get("rng") or random.Random()
        kwargs["rng"] = rng
        kingdoms = {
            human_kingdom: Kingdom(human_kingdom, human_king, Personality.HUMAN),
            "Stonewatch": Kingdom("Stonewatch", "Rowan", Personality.BALANCED),
            "Nightveil": Kingdom("Nightveil", "Nyx", Personality.ASSASSIN),
            "Sunmeadow": Kingdom("Sunmeadow", "Sol", Personality.FRIENDLY),
        }
        regions = {name: Region(rng.randint(4, 12), rng.randint(4, 12)) for name in kingdoms}
        state = GameState(kingdoms=kingdoms, regions=regions, human_kingdom=human_kingdom)
        return cls(state, **kwargs)

    @property
    def human(self) -> Kingdom:
        return self.state.kingdoms[self.state.human_kingdom]

    def advance_time(self) -> list[str]:
        now = self.clock()
        elapsed = int((now - self.last_tick_time) // self.tick_seconds)
        messages: list[str] = []
        for _ in range(max(0, elapsed)):
            if self.state.winner or not self.human.active:
                break
            self.last_tick_time += self.tick_seconds
            messages.extend(self.process_epoch())
        return messages

    def process_epoch(self) -> list[str]:
        state = self.state
        state.epoch += 1
        messages = [f"-- Epoch {state.epoch} --"]
        for proposal_id, proposal in list(state.proposals.items()):
            if proposal.expires_epoch <= state.epoch:
                state.proposals.pop(proposal_id)
                messages.append(f"Proposal {proposal_id} expired.")
        for kingdom in state.kingdoms.values():
            if kingdom.active:
                messages.append(produce_and_feed(kingdom, state.regions[kingdom.name]))
        for region in state.regions.values():
            region.wood = self.rng.randint(4, 12)
            region.metal = self.rng.randint(4, 12)
        state.candidates.clear()
        for kingdom in state.kingdoms.values():
            if kingdom.active and not kingdom.human and not state.winner and self.human.active:
                messages.extend(self.ai_take_turn(kingdom))
        if not state.winner and self.human.active:
            candidates = generate_candidates(state)
            ai_candidate = next(
                (
                    candidate
                    for candidate in candidates
                    if all(not state.kingdoms[name].human for name in candidate.participants)
                ),
                None,
            )
            if ai_candidate:
                try:
                    proposal = create_proposal(state, ai_candidate.id)
                    messages.append(settle_proposal(state, proposal.id))
                except GameError:
                    pass
        _check_military_victory(state)
        if state.winner:
            messages.append(self._winner_message())
        elif not self.human.active:
            messages.append(self._loss_message())
        return messages

    def _ai_assign(self, kingdom: Kingdom) -> None:
        farmers = min(kingdom.workers, math.ceil(kingdom.population / 3))
        remaining = kingdom.workers - farmers
        if kingdom.personality is Personality.ASSASSIN:
            metal = math.ceil(remaining / 2)
            wood = remaining - metal
        elif kingdom.resources[Resource.WOOD] <= kingdom.resources[Resource.METAL]:
            wood = math.ceil(remaining / 2)
            metal = remaining - wood
        else:
            metal = math.ceil(remaining / 2)
            wood = remaining - metal
        assign_workers(kingdom, {Job.FOOD: farmers, Job.WOOD: wood, Job.METAL: metal})

    def _try_ai_development(self, kingdom: Kingdom) -> str | None:
        if (
            kingdom.completed_cycles
            and kingdom.completed_credit_trades
            and kingdom.balance >= 0
            and _can_afford_available(self.state, kingdom.name, {resource: 30 for resource in Resource})
        ):
            build_grand_market(self.state, kingdom.name)
            return f"{kingdom.name} built the Grand Market."
        farmers = min(kingdom.workers, math.ceil(kingdom.population / 3))
        if kingdom.personality is Personality.ASSASSIN:
            if kingdom.workers > farmers and _can_afford_available(self.state, kingdom.name, TRAIN_COST):
                train(kingdom)
                return f"{kingdom.name} trained a warrior."
            if kingdom.warriors[1] and _can_afford_available(self.state, kingdom.name, UPGRADE_COST[1]):
                upgrade(kingdom, 1)
                return f"{kingdom.name} upgraded a warrior to level 2."
            if kingdom.warriors[2] and _can_afford_available(self.state, kingdom.name, UPGRADE_COST[2]):
                upgrade(kingdom, 2)
                return f"{kingdom.name} upgraded a warrior to level 3."
            if _available_resource(self.state, kingdom.name, Resource.FOOD) >= kingdom.population + 5:
                recruit(kingdom)
                return f"{kingdom.name} recruited a worker."
        else:
            if kingdom.defense < 15 and _can_afford_available(
                self.state, kingdom.name, {Resource.WOOD: 10, Resource.METAL: 10}
            ):
                fortify(kingdom)
                return f"{kingdom.name} fortified its defenses."
            if kingdom.workers < 6 and _available_resource(
                self.state, kingdom.name, Resource.FOOD
            ) >= kingdom.population + 5:
                recruit(kingdom)
                return f"{kingdom.name} recruited a worker."
            if kingdom.workers > farmers and _can_afford_available(self.state, kingdom.name, TRAIN_COST):
                train(kingdom)
                return f"{kingdom.name} trained a warrior."
            if kingdom.warriors[1] and _can_afford_available(self.state, kingdom.name, UPGRADE_COST[1]):
                upgrade(kingdom, 1)
                return f"{kingdom.name} upgraded a warrior to level 2."
        return None

    def _remove_unfunded_ai_intents(self, kingdom: Kingdom) -> None:
        reserved = {intent_id for proposal in self.state.proposals.values() for intent_id in proposal.intent_ids}
        for intent_id, intent in list(self.state.intents.items()):
            if intent.owner == kingdom.name and intent_id not in reserved and not _funded(self.state, intent):
                self.state.intents.pop(intent_id)

    def _try_close_cycle(self, kingdom: Kingdom) -> Intent | None:
        barter = [intent for intent in self.state.intents.values() if intent.kind is IntentKind.BARTER]
        human_intents = [intent for intent in barter if self.state.kingdoms[intent.owner].human]
        for human_intent in human_intents:
            for other in barter:
                if other.owner in (human_intent.owner, kingdom.name):
                    continue
                if _barter_fits(human_intent, other):
                    give_resource = human_intent.want_resource
                    give_quantity = human_intent.want_quantity
                    if (
                        give_resource is not None
                        and give_quantity is not None
                        and give_resource is not other.resource
                        and _available_resource(self.state, kingdom.name, give_resource) >= give_quantity
                    ):
                        return post_intent(
                            self.state,
                            kingdom.name,
                            IntentKind.BARTER,
                            give_resource,
                            give_quantity,
                            other.resource,
                            other.quantity,
                        )
        return None

    def _post_ai_intent(self, kingdom: Kingdom) -> str | None:
        active = [intent for intent in self.state.intents.values() if intent.owner == kingdom.name]
        if len(active) >= 2:
            return None
        if kingdom.personality is Personality.FRIENDLY and kingdom.balance >= 0:
            closed = self._try_close_cycle(kingdom)
            if closed:
                return f"{kingdom.name} posted cycle-closing intent #{closed.id}."
        stocks = sorted(Resource, key=lambda resource: (kingdom.resources[resource], resource.value))
        need, surplus = stocks[0], stocks[-1]
        available = _available_resource(self.state, kingdom.name, surplus)
        quantity = min(3, available)
        try:
            if kingdom.balance < 0 and quantity > 0:
                intent = post_intent(self.state, kingdom.name, IntentKind.SELL, surplus, quantity)
            elif kingdom.personality is Personality.ASSASSIN:
                desired = (
                    Resource.METAL
                    if kingdom.resources[Resource.METAL] <= kingdom.resources[Resource.FOOD]
                    else Resource.FOOD
                )
                intent = post_intent(self.state, kingdom.name, IntentKind.BUY, desired, 3)
            elif (
                kingdom.personality is Personality.FRIENDLY
                and kingdom.completed_credit_trades == 0
                and quantity > 0
            ):
                intent = post_intent(self.state, kingdom.name, IntentKind.SELL, surplus, quantity)
            elif quantity > 0 and surplus is not need:
                intent = post_intent(self.state, kingdom.name, IntentKind.BARTER, surplus, quantity, need, quantity)
            else:
                return None
        except GameError:
            return None
        return f"{kingdom.name} posted intent #{intent.id}."

    def _ai_attack(self, kingdom: Kingdom) -> str | None:
        if kingdom.personality is Personality.FRIENDLY or kingdom.warrior_power == 0:
            return None
        targets = sorted(
            (target for target in self.state.kingdoms.values() if target.active and target.name != kingdom.name),
            key=lambda target: (target.defense + target.warrior_power, target.name),
        )
        if not targets:
            return None
        target = targets[0]
        if kingdom.personality is Personality.ASSASSIN:
            should_attack = kingdom.warrior_power > target.warrior_power
        else:
            should_attack = math.ceil(kingdom.warrior_power / 2) >= target.warrior_power + target.defense
        if not should_attack:
            return None
        return resolve_attack(self.state, kingdom.name, target.name, self.rng)

    def ai_take_turn(self, kingdom: Kingdom) -> list[str]:
        self._ai_assign(kingdom)
        messages: list[str] = []
        development = self._try_ai_development(kingdom)
        if development:
            messages.append(development)
        if self.state.winner:
            return messages
        self._remove_unfunded_ai_intents(kingdom)
        intent_message = self._post_ai_intent(kingdom)
        if intent_message:
            messages.append(intent_message)
        attack_message = self._ai_attack(kingdom)
        if attack_message:
            messages.append(attack_message)
        return messages

    def _resolve_kingdom(self, name: str) -> Kingdom:
        exact = self.state.kingdoms.get(name)
        if exact:
            return exact
        matches = [kingdom for key, kingdom in self.state.kingdoms.items() if key.lower() == name.lower()]
        if len(matches) != 1:
            raise GameError(f"Unknown kingdom: {name}.")
        return matches[0]

    def _status(self, kingdom: Kingdom) -> str:
        resources = ", ".join(f"{resource.value}={kingdom.resources[resource]}" for resource in Resource)
        jobs = ", ".join(f"{job.value}={kingdom.assignments[job]}" for job in Job)
        warriors = ", ".join(f"L{level}={kingdom.warriors[level]}" for level in (1, 2, 3))
        region = self.state.regions.get(kingdom.name)
        availability = f"wood={region.wood}, metal={region.metal}" if region else "conquered"
        return (
            f"{kingdom.name} (King {kingdom.king}, {kingdom.personality.value})\n"
            f"  active={kingdom.active}, defense={kingdom.defense}, "
            f"balance={kingdom.balance}/{kingdom.debt_limit} debt limit\n"
            f"  resources: {resources}\n  workers: {jobs}\n"
            f"  warriors: {warriors} (power {kingdom.warrior_power})\n"
            f"  region: {availability}; cycles={kingdom.completed_cycles}, "
            f"credit trades={kingdom.completed_credit_trades}"
        )

    def _board(self) -> str:
        prices = ", ".join(f"{resource.value}={market_price(self.state, resource)}" for resource in Resource)
        intents = "\n".join(_format_intent(intent) for intent in self.state.intents.values()) or "(none)"
        proposals = "\n".join(_format_proposal(proposal) for proposal in self.state.proposals.values()) or "(none)"
        return f"Credit prices: {prices}\nIntents:\n{intents}\nPending proposals:\n{proposals}"

    def _winner_message(self) -> str:
        return f"{self.state.winner} wins by {self.state.victory_type}!"

    def _loss_message(self) -> str:
        return f"{self.human.name} has fallen. Your reign is over."

    def execute(self, command: str) -> CommandResult:
        messages = self.advance_time()
        if self.state.winner:
            return CommandResult(True, "\n".join(messages or [self._winner_message()]), True)
        if not self.human.active:
            return CommandResult(True, "\n".join(messages or [self._loss_message()]), True)
        try:
            parts = shlex.split(command)
            if not parts:
                return CommandResult(True, "\n".join(messages) if messages else "Enter 'help' for commands.")
            result = self._dispatch(parts)
            if messages:
                result = CommandResult(result.ok, "\n".join(messages + [result.message]), result.quit)
            return result
        except (GameError, ValueError) as error:
            message = f"Error: {error}"
            if messages:
                message = "\n".join(messages + [message])
            return CommandResult(False, message)

    def _dispatch(self, parts: list[str]) -> CommandResult:
        command = parts[0].lower()
        human = self.human
        if command == "help":
            return CommandResult(True, HELP_TEXT)
        if command == "quit":
            return CommandResult(True, "Farewell, Your Majesty.", True)
        if command == "status":
            if len(parts) == 1:
                return CommandResult(True, "\n".join(self._status(k) for k in self.state.kingdoms.values()))
            return CommandResult(True, self._status(self._resolve_kingdom(" ".join(parts[1:]))))
        if command == "assign":
            if len(parts) < 3 or len(parts[1:]) % 2:
                raise GameError("Usage: assign food N wood N metal N")
            requested: dict[Job, int] = {}
            for index in range(1, len(parts), 2):
                try:
                    job = Job(parts[index].lower())
                except ValueError as error:
                    raise GameError("Assignments may use food, wood, or metal.") from error
                if job is Job.IDLE or job in requested:
                    raise GameError("Assign each of food, wood, and metal at most once.")
                requested[job] = int(parts[index + 1])
            assign_workers(human, requested)
            return CommandResult(True, f"Workers reassigned; {human.assignments[Job.IDLE]} remain idle.")
        if command in {"recruit", "train", "fortify"}:
            if len(parts) > 2:
                raise GameError(f"Usage: {command} [N]")
            count = int(parts[1]) if len(parts) == 2 else 1
            costs = {
                "recruit": {Resource.FOOD: 5},
                "train": TRAIN_COST,
                "fortify": {Resource.WOOD: 10, Resource.METAL: 10},
            }
            if not _can_afford_available(self.state, human.name, costs[command], count):
                raise GameError("Insufficient unreserved resources.")
            {"recruit": recruit, "train": train, "fortify": fortify}[command](human, count)
            return CommandResult(True, f"Completed {command} x{count}.")
        if command == "upgrade":
            if len(parts) != 3:
                raise GameError("Usage: upgrade 1|2 N")
            level, count = int(parts[1]), int(parts[2])
            if level not in UPGRADE_COST:
                raise GameError("Upgrade level must be 1 or 2.")
            if not _can_afford_available(self.state, human.name, UPGRADE_COST[level], count):
                raise GameError("Insufficient unreserved resources.")
            upgrade(human, level, count)
            return CommandResult(True, f"Upgraded {count} level-{level} warriors.")
        if command == "board":
            return CommandResult(True, self._board())
        if command == "intent":
            return self._intent_command(parts)
        if command == "match":
            candidates = generate_candidates(self.state)
            return CommandResult(True, "\n".join(_format_candidate(c) for c in candidates) or "No feasible matches.")
        if command == "propose":
            if len(parts) != 2:
                raise GameError("Usage: propose CANDIDATE_ID")
            proposal = create_proposal(self.state, int(parts[1]))
            if set(proposal.participants) == proposal.approvals:
                return CommandResult(True, settle_proposal(self.state, proposal.id))
            return CommandResult(
                True,
                f"Created proposal #{proposal.id}; it expires at epoch {proposal.expires_epoch}.",
            )
        if command == "approve":
            if len(parts) != 2:
                raise GameError("Usage: approve PROPOSAL_ID")
            return CommandResult(True, approve_proposal(self.state, human.name, int(parts[1])))
        if command == "reject":
            if len(parts) != 2:
                raise GameError("Usage: reject PROPOSAL_ID")
            reject_proposal(self.state, human.name, int(parts[1]))
            return CommandResult(True, f"Rejected proposal {parts[1]}.")
        if command == "attack":
            if len(parts) < 2:
                raise GameError("Usage: attack KINGDOM")
            defender = self._resolve_kingdom(" ".join(parts[1:]))
            return CommandResult(True, resolve_attack(self.state, human.name, defender.name, self.rng))
        if command == "build" and len(parts) == 2 and parts[1].lower() == "market":
            build_grand_market(self.state, human.name)
            return CommandResult(True, self._winner_message(), True)
        if command == "wait":
            if len(parts) != 1:
                raise GameError("Usage: wait")
            remaining = max(0.0, self.tick_seconds - (self.clock() - self.last_tick_time))
            self.sleeper(remaining)
            tick_messages = self.advance_time()
            return CommandResult(True, "\n".join(tick_messages) or "No epoch elapsed.", bool(self.state.winner))
        raise GameError("Unknown command. Enter 'help' for the command list.")

    def _intent_command(self, parts: list[str]) -> CommandResult:
        if len(parts) < 3:
            raise GameError("Usage: intent barter|sell|buy|cancel ...")
        action = parts[1].lower()
        if action == "cancel" and len(parts) == 3:
            cancel_intent(self.state, self.human.name, int(parts[2]))
            return CommandResult(True, f"Cancelled intent {parts[2]}.")
        if action == "barter" and len(parts) == 7 and parts[4].lower() == "for":
            intent = post_intent(
                self.state,
                self.human.name,
                IntentKind.BARTER,
                Resource(parts[3].lower()),
                int(parts[2]),
                Resource(parts[6].lower()),
                int(parts[5]),
            )
        elif action in {"sell", "buy"} and len(parts) == 4:
            intent = post_intent(
                self.state,
                self.human.name,
                IntentKind(action),
                Resource(parts[3].lower()),
                int(parts[2]),
            )
        else:
            raise GameError(
                "Usage: intent barter N RESOURCE for N RESOURCE | "
                "intent sell|buy N RESOURCE | intent cancel ID"
            )
        return CommandResult(True, f"Posted intent #{intent.id}.")


HELP_TEXT = """Commands:
  help                              Show this help
  status [KINGDOM]                  Show exact kingdom state
  assign food N wood N metal N      Reassign workers; the remainder become idle
  recruit [N]                       Spend 5 food per worker
  train [N]                         Convert workers to level-1 warriors
  upgrade 1|2 N                     Upgrade warriors one level
  fortify [N]                       Spend 10 wood + 10 metal for 5 defense
  board                             Show prices, intents, and proposals
  intent barter N RESOURCE for N RESOURCE
  intent sell N RESOURCE            Offer goods for dynamic-price credits
  intent buy N RESOURCE             Offer credits for goods
  intent cancel ID                  Cancel an unreserved intent
  match                             Find bilateral, three-way, and credit matches
  propose CANDIDATE_ID              Lock a match until the next epoch
  approve PROPOSAL_ID               Explicitly settle a human proposal
  reject PROPOSAL_ID                Reject and release a proposal
  attack KINGDOM                    Attack with every warrior, once per epoch
  build market                      Attempt a Grand Market prosperity victory
  wait                              Wait until the next 60-second epoch
  quit                              End this session"""


def run_cli(input_fn: Callable[[str], str] = input, output_fn: Callable[[str], None] = print) -> int:
    try:
        king = input_fn("Your name [Player]: ").strip() or "Player"
        kingdom = input_fn("Your kingdom [New Dawn]: ").strip() or "New Dawn"
    except (EOFError, KeyboardInterrupt):
        output_fn("Farewell.")
        return 0
    if kingdom.lower() in {"stonewatch", "nightveil", "sunmeadow"}:
        output_fn("That kingdom name is reserved for an AI kingdom.")
        return 2
    engine = GameEngine.new_game(king, kingdom)
    output_fn(f"Welcome, King {king} of {kingdom}. One epoch is 60 seconds.\n{HELP_TEXT}")
    while True:
        try:
            command = input_fn("kingdom-wars> ")
        except (EOFError, KeyboardInterrupt):
            output_fn("\nFarewell, Your Majesty.")
            return 0
        result = engine.execute(command)
        output_fn(result.message)
        if result.quit:
            return 0


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Play Kingdom Wars in your terminal.")
    parser.parse_args(list(argv) if argv is not None else None)
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
