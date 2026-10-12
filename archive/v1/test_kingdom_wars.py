import random
import unittest

from kingdom_wars import (
    GameEngine,
    GameError,
    IntentKind,
    Job,
    Personality,
    ProposalKind,
    Resource,
    approve_proposal,
    assign_workers,
    build_grand_market,
    cancel_intent,
    create_proposal,
    fortify,
    generate_candidates,
    market_price,
    post_intent,
    produce_and_feed,
    recruit,
    resolve_attack,
    run_cli,
    settle_proposal,
    train,
    upgrade,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class MaximumRng(random.Random):
    def randint(self, start: int, end: int) -> int:
        return end


def make_engine(seed: int = 7) -> tuple[GameEngine, FakeClock]:
    clock = FakeClock()
    engine = GameEngine.new_game(
        "Ada",
        "Testland",
        clock=clock,
        sleeper=clock.advance,
        rng=random.Random(seed),
    )
    return engine, clock


def stock_all(engine: GameEngine, amount: int = 100) -> None:
    for kingdom in engine.state.kingdoms.values():
        for resource in Resource:
            kingdom.resources[resource] = amount


class StateAndEconomyTests(unittest.TestCase):
    def test_new_game_has_expected_four_kingdoms(self) -> None:
        engine, _ = make_engine()
        self.assertEqual(
            [kingdom.personality for kingdom in engine.state.kingdoms.values()],
            [Personality.HUMAN, Personality.BALANCED, Personality.ASSASSIN, Personality.FRIENDLY],
        )
        for kingdom in engine.state.kingdoms.values():
            self.assertEqual(kingdom.defense, 10)
            self.assertEqual(kingdom.workers, 4)
            self.assertEqual(kingdom.resources[Resource.FOOD], 8)
            self.assertEqual(kingdom.assignments, {Job.IDLE: 0, Job.FOOD: 2, Job.WOOD: 1, Job.METAL: 1})
            region = engine.state.regions[kingdom.name]
            self.assertIn(region.wood, range(4, 13))
            self.assertIn(region.metal, range(4, 13))

    def test_assignment_is_atomic_and_leaves_remainder_idle(self) -> None:
        engine, _ = make_engine()
        kingdom = engine.human
        assign_workers(kingdom, {Job.FOOD: 1, Job.WOOD: 1, Job.METAL: 0})
        self.assertEqual(kingdom.assignments[Job.IDLE], 2)
        before = kingdom.assignments.copy()
        with self.assertRaises(GameError):
            assign_workers(kingdom, {Job.FOOD: 5})
        self.assertEqual(kingdom.assignments, before)

    def test_production_obeys_capacity_and_food_upkeep(self) -> None:
        engine, _ = make_engine()
        kingdom = engine.human
        region = engine.state.regions[kingdom.name]
        region.wood = 1
        region.metal = 9
        message = produce_and_feed(kingdom, region)
        self.assertEqual(kingdom.resources, {Resource.FOOD: 10, Resource.WOOD: 1, Resource.METAL: 2})
        self.assertIn("+1 wood", message)

    def test_starvation_uses_deterministic_priority(self) -> None:
        engine, _ = make_engine()
        kingdom = engine.human
        kingdom.resources[Resource.FOOD] = 0
        kingdom.assignments = {Job.IDLE: 1, Job.FOOD: 1, Job.WOOD: 1, Job.METAL: 1}
        kingdom.warriors = {1: 2, 2: 1, 3: 1}
        produce_and_feed(kingdom, engine.state.regions[kingdom.name])
        self.assertEqual(kingdom.assignments[Job.IDLE], 0)
        self.assertEqual(kingdom.assignments[Job.WOOD], 0)
        self.assertEqual(kingdom.assignments[Job.METAL], 0)
        self.assertEqual(kingdom.warriors[1], 0)
        self.assertEqual(kingdom.warriors[2], 1)
        self.assertEqual(kingdom.warriors[3], 1)
        self.assertEqual(kingdom.assignments[Job.FOOD], 1)

    def test_fake_clock_processes_all_elapsed_epochs(self) -> None:
        engine, clock = make_engine()
        clock.advance(121)
        messages = engine.advance_time()
        self.assertEqual(engine.state.epoch, 2)
        self.assertEqual(messages.count("-- Epoch 1 --"), 1)
        self.assertEqual(messages.count("-- Epoch 2 --"), 1)

    def test_catchup_stops_after_winner(self) -> None:
        engine, clock = make_engine()
        for kingdom in engine.state.kingdoms.values():
            if not kingdom.human:
                kingdom.active = False
                engine.state.regions.pop(kingdom.name)
        clock.advance(180)
        engine.advance_time()
        self.assertEqual(engine.state.epoch, 1)
        self.assertEqual(engine.state.winner, engine.human.name)


class DevelopmentAndCombatTests(unittest.TestCase):
    def test_recruit_train_upgrade_and_fortify_costs(self) -> None:
        engine, _ = make_engine()
        kingdom = engine.human
        kingdom.resources = {resource: 100 for resource in Resource}
        recruit(kingdom, 2)
        self.assertEqual(kingdom.workers, 6)
        self.assertEqual(kingdom.resources[Resource.FOOD], 90)
        train(kingdom, 2)
        self.assertEqual((kingdom.workers, kingdom.warriors[1]), (4, 2))
        self.assertEqual(kingdom.resources[Resource.FOOD], 84)
        upgrade(kingdom, 1, 1)
        self.assertEqual(kingdom.warriors, {1: 1, 2: 1, 3: 0})
        upgrade(kingdom, 2, 1)
        self.assertEqual(kingdom.warriors, {1: 1, 2: 0, 3: 1})
        fortify(kingdom, 2)
        self.assertEqual(kingdom.defense, 20)
        self.assertEqual(kingdom.resources[Resource.WOOD], 59)
        self.assertEqual(kingdom.resources[Resource.METAL], 59)

    def test_failed_development_action_changes_nothing(self) -> None:
        engine, _ = make_engine()
        kingdom = engine.human
        before_resources = kingdom.resources.copy()
        before_workers = kingdom.workers
        with self.assertRaises(GameError):
            train(kingdom, 2)
        self.assertEqual(kingdom.resources, before_resources)
        self.assertEqual(kingdom.workers, before_workers)

    def test_combat_is_simultaneous_and_overflow_hits_defense(self) -> None:
        engine, _ = make_engine()
        attacker = engine.human
        defender = engine.state.kingdoms["Stonewatch"]
        attacker.warriors[1] = 2
        defender.warriors[1] = 1
        message = resolve_attack(engine.state, attacker.name, defender.name, MaximumRng())
        self.assertEqual(attacker.warriors[1], 1)
        self.assertEqual(defender.warriors[1], 0)
        self.assertEqual(defender.defense, 8)
        self.assertIn("dealt 4", message)

    def test_attack_is_limited_to_once_per_epoch(self) -> None:
        engine, _ = make_engine()
        engine.human.warriors[1] = 1
        resolve_attack(engine.state, engine.human.name, "Stonewatch", MaximumRng())
        with self.assertRaises(GameError):
            resolve_attack(engine.state, engine.human.name, "Nightveil", MaximumRng())

    def test_takeover_absorbs_assets_and_preserves_credit(self) -> None:
        engine, _ = make_engine()
        attacker = engine.human
        defender = engine.state.kingdoms["Stonewatch"]
        attacker.warriors[3] = 2
        defender.defense = 1
        attacker.balance = 5
        defender.balance = -5
        defender.resources[Resource.WOOD] = 9
        defender.assignments = {Job.IDLE: 2, Job.FOOD: 0, Job.WOOD: 0, Job.METAL: 0}
        resolve_attack(engine.state, attacker.name, defender.name, MaximumRng())
        self.assertFalse(defender.active)
        self.assertEqual(attacker.balance, 0)
        self.assertEqual(sum(k.balance for k in engine.state.kingdoms.values()), 0)
        self.assertEqual(attacker.resources[Resource.WOOD], 9)
        self.assertGreaterEqual(attacker.assignments[Job.IDLE], 2)
        self.assertNotIn(defender.name, engine.state.regions)


class ExchangeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine, _ = make_engine()
        stock_all(self.engine)
        self.state = self.engine.state
        self.human = self.engine.human

    def test_exact_bilateral_barter_requires_explicit_human_approval(self) -> None:
        post_intent(self.state, self.human.name, IntentKind.BARTER, Resource.WOOD, 2, Resource.FOOD, 3)
        post_intent(self.state, "Stonewatch", IntentKind.BARTER, Resource.FOOD, 3, Resource.WOOD, 2)
        candidate = generate_candidates(self.state)[0]
        self.assertEqual(candidate.kind, ProposalKind.BARTER)
        proposal = create_proposal(self.state, candidate.id)
        self.assertNotIn(self.human.name, proposal.approvals)
        wood_before = self.human.resources[Resource.WOOD]
        message = approve_proposal(self.state, self.human.name, proposal.id)
        self.assertIn("settled", message)
        self.assertEqual(self.human.resources[Resource.WOOD], wood_before - 2)
        self.assertEqual(self.human.resources[Resource.FOOD], 103)

    def test_three_kingdom_cycle_is_found_and_recorded(self) -> None:
        post_intent(self.state, self.human.name, IntentKind.BARTER, Resource.WOOD, 2, Resource.FOOD, 4)
        post_intent(self.state, "Stonewatch", IntentKind.BARTER, Resource.METAL, 2, Resource.WOOD, 2)
        post_intent(self.state, "Sunmeadow", IntentKind.BARTER, Resource.FOOD, 4, Resource.METAL, 2)
        candidates = generate_candidates(self.state)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(len(candidates[0].participants), 3)
        proposal = create_proposal(self.state, candidates[0].id)
        approve_proposal(self.state, self.human.name, proposal.id)
        for name in (self.human.name, "Stonewatch", "Sunmeadow"):
            self.assertEqual(self.state.kingdoms[name].completed_cycles, 1)

    def test_broken_cycle_produces_no_candidate(self) -> None:
        post_intent(self.state, self.human.name, IntentKind.BARTER, Resource.WOOD, 2, Resource.FOOD, 4)
        post_intent(self.state, "Stonewatch", IntentKind.BARTER, Resource.METAL, 3, Resource.WOOD, 2)
        post_intent(self.state, "Sunmeadow", IntentKind.BARTER, Resource.FOOD, 4, Resource.METAL, 2)
        self.assertEqual(generate_candidates(self.state), [])

    def test_cycles_rank_ahead_of_direct_swaps(self) -> None:
        post_intent(self.state, self.human.name, IntentKind.BARTER, Resource.WOOD, 2, Resource.FOOD, 2)
        post_intent(self.state, "Stonewatch", IntentKind.BARTER, Resource.FOOD, 2, Resource.WOOD, 2)
        post_intent(self.state, "Nightveil", IntentKind.BARTER, Resource.METAL, 2, Resource.WOOD, 2)
        post_intent(self.state, "Sunmeadow", IntentKind.BARTER, Resource.FOOD, 2, Resource.METAL, 2)
        candidates = generate_candidates(self.state)
        self.assertEqual(len(candidates[0].participants), 3)
        self.assertEqual(len(candidates[-1].participants), 2)

    def test_pending_proposal_reserves_goods_and_expires(self) -> None:
        first = post_intent(self.state, self.human.name, IntentKind.BARTER, Resource.WOOD, 100, Resource.FOOD, 3)
        post_intent(self.state, "Stonewatch", IntentKind.BARTER, Resource.FOOD, 3, Resource.WOOD, 100)
        candidate = generate_candidates(self.state)[0]
        proposal = create_proposal(self.state, candidate.id)
        with self.assertRaises(GameError):
            post_intent(self.state, self.human.name, IntentKind.SELL, Resource.WOOD, 1)
        with self.assertRaises(GameError):
            cancel_intent(self.state, self.human.name, first.id)
        spend_result = self.engine.execute("fortify")
        self.assertFalse(spend_result.ok)
        self.assertIn("unreserved", spend_result.message)
        self.engine.process_epoch()
        self.assertNotIn(proposal.id, self.state.proposals)

    def test_dynamic_credit_price_clamps_and_uses_demand_supply(self) -> None:
        post_intent(self.state, "Stonewatch", IntentKind.SELL, Resource.WOOD, 10)
        post_intent(self.state, self.human.name, IntentKind.BUY, Resource.WOOD, 10)
        self.assertEqual(market_price(self.state, Resource.WOOD), 2)
        self.state.intents.clear()
        post_intent(self.state, "Stonewatch", IntentKind.SELL, Resource.WOOD, 10)
        post_intent(self.state, self.human.name, IntentKind.BUY, Resource.WOOD, 1)
        self.assertEqual(market_price(self.state, Resource.WOOD), 1)
        self.state.intents.clear()
        post_intent(self.state, "Stonewatch", IntentKind.SELL, Resource.WOOD, 1)
        post_intent(self.state, self.human.name, IntentKind.BUY, Resource.WOOD, 10)
        self.assertEqual(market_price(self.state, Resource.WOOD), 5)

    def test_credit_settlement_locks_price_and_conserves_balances(self) -> None:
        post_intent(self.state, "Stonewatch", IntentKind.SELL, Resource.METAL, 4)
        post_intent(self.state, self.human.name, IntentKind.BUY, Resource.METAL, 4)
        candidate = generate_candidates(self.state)[0]
        self.assertEqual(candidate.unit_price, 2)
        proposal = create_proposal(self.state, candidate.id)
        # A later unmatched intent would change a fresh quote, but not this proposal.
        post_intent(self.state, "Nightveil", IntentKind.BUY, Resource.METAL, 20)
        approve_proposal(self.state, self.human.name, proposal.id)
        self.assertEqual(self.human.balance, -8)
        self.assertEqual(self.state.kingdoms["Stonewatch"].balance, 8)
        self.assertEqual(sum(k.balance for k in self.state.kingdoms.values()), 0)
        self.assertEqual(self.human.completed_credit_trades, 1)

    def test_selling_goods_can_repay_mutual_credit_debt(self) -> None:
        self.human.balance = -6
        self.state.kingdoms["Stonewatch"].balance = 6
        post_intent(self.state, self.human.name, IntentKind.SELL, Resource.WOOD, 3)
        post_intent(self.state, "Stonewatch", IntentKind.BUY, Resource.WOOD, 3)
        candidate = generate_candidates(self.state)[0]
        proposal = create_proposal(self.state, candidate.id)
        approve_proposal(self.state, self.human.name, proposal.id)
        self.assertEqual(self.human.balance, 0)
        self.assertEqual(self.state.kingdoms["Stonewatch"].balance, 0)

    def test_credit_debt_limit_is_checked_before_reservation(self) -> None:
        post_intent(self.state, "Stonewatch", IntentKind.SELL, Resource.FOOD, 2)
        post_intent(self.state, self.human.name, IntentKind.BUY, Resource.FOOD, 2)
        candidate = generate_candidates(self.state)[0]
        self.human.balance = -29
        # Balance conservation for the test ledger.
        self.state.kingdoms["Stonewatch"].balance = 29
        with self.assertRaises(GameError):
            create_proposal(self.state, candidate.id)

    def test_pending_credit_proposals_reserve_debt_capacity(self) -> None:
        post_intent(self.state, "Stonewatch", IntentKind.SELL, Resource.FOOD, 5)
        post_intent(self.state, self.human.name, IntentKind.BUY, Resource.FOOD, 5)
        first_candidate = generate_candidates(self.state)[0]
        first = create_proposal(self.state, first_candidate.id)
        self.assertEqual(first.credit_amount, 10)

        post_intent(self.state, "Sunmeadow", IntentKind.SELL, Resource.METAL, 5)
        post_intent(self.state, self.human.name, IntentKind.BUY, Resource.METAL, 5)
        second_candidate = next(
            candidate for candidate in generate_candidates(self.state) if "Sunmeadow" in candidate.participants
        )
        self.human.balance = -20
        self.state.kingdoms["Nightveil"].balance = 20
        with self.assertRaises(GameError):
            create_proposal(self.state, second_candidate.id)


class VictoryAiAndCliTests(unittest.TestCase):
    def test_grand_market_requires_every_prerequisite(self) -> None:
        engine, _ = make_engine()
        kingdom = engine.human
        kingdom.resources = {resource: 30 for resource in Resource}
        with self.assertRaises(GameError):
            build_grand_market(engine.state, kingdom.name)
        kingdom.completed_cycles = 1
        with self.assertRaises(GameError):
            build_grand_market(engine.state, kingdom.name)
        kingdom.completed_credit_trades = 1
        kingdom.balance = -1
        engine.state.kingdoms["Stonewatch"].balance = 1
        with self.assertRaises(GameError):
            build_grand_market(engine.state, kingdom.name)
        kingdom.balance = 0
        engine.state.kingdoms["Stonewatch"].balance = 0
        build_grand_market(engine.state, kingdom.name)
        self.assertEqual((engine.state.winner, engine.state.victory_type), (kingdom.name, "prosperity"))
        self.assertEqual(kingdom.resources, {resource: 0 for resource in Resource})

    def test_friendly_ai_never_attacks(self) -> None:
        engine, _ = make_engine()
        friendly = engine.state.kingdoms["Sunmeadow"]
        friendly.warriors[3] = 10
        self.assertIsNone(engine._ai_attack(friendly))

    def test_friendly_ai_offers_surplus_for_credit(self) -> None:
        engine, _ = make_engine()
        friendly = engine.state.kingdoms["Sunmeadow"]
        friendly.resources = {
            Resource.FOOD: 20,
            Resource.WOOD: 10,
            Resource.METAL: 5,
        }
        message = engine._post_ai_intent(friendly)
        intent = next(intent for intent in engine.state.intents.values() if intent.owner == friendly.name)
        self.assertIn("posted intent", message)
        self.assertEqual(intent.kind, IntentKind.SELL)
        self.assertEqual(intent.resource, Resource.FOOD)

    def test_balanced_ai_assigns_for_upkeep_and_scarcity(self) -> None:
        engine, _ = make_engine()
        balanced = engine.state.kingdoms["Stonewatch"]
        balanced.assignments[Job.IDLE] += 1
        balanced.resources[Resource.WOOD] = 1
        balanced.resources[Resource.METAL] = 20
        engine._ai_assign(balanced)
        self.assertEqual(balanced.assignments[Job.FOOD], 2)
        self.assertEqual(balanced.assignments[Job.WOOD], 2)
        self.assertEqual(balanced.assignments[Job.METAL], 1)

    def test_assassin_attacks_weakest_target(self) -> None:
        engine, _ = make_engine()
        engine.rng = MaximumRng()
        assassin = engine.state.kingdoms["Nightveil"]
        assassin.warriors[3] = 3
        engine.state.kingdoms["Stonewatch"].defense = 20
        engine.state.kingdoms["Sunmeadow"].defense = 15
        engine.human.defense = 1
        message = engine._ai_attack(assassin)
        self.assertIn(engine.human.name, message)

    def test_command_errors_do_not_raise_and_status_is_explainable(self) -> None:
        engine, _ = make_engine()
        error = engine.execute("assign food 99")
        self.assertFalse(error.ok)
        self.assertIn("Only 4 workers", error.message)
        status = engine.execute("status Testland")
        self.assertTrue(status.ok)
        self.assertIn("resources:", status.message)
        self.assertIn("warriors:", status.message)
        self.assertIn("balance=", status.message)

    def test_command_boundary_processes_live_time_first(self) -> None:
        engine, clock = make_engine()
        clock.advance(60)
        result = engine.execute("status Testland")
        self.assertEqual(engine.state.epoch, 1)
        self.assertTrue(result.message.startswith("-- Epoch 1 --"))

    def test_wait_uses_injected_sleeper(self) -> None:
        engine, clock = make_engine()
        result = engine.execute("wait")
        self.assertEqual(clock.now, 60)
        self.assertEqual(engine.state.epoch, 1)
        self.assertIn("-- Epoch 1 --", result.message)

    def test_player_elimination_ends_cli_session(self) -> None:
        engine, _ = make_engine()
        attacker = engine.state.kingdoms["Nightveil"]
        attacker.warriors[3] = 2
        engine.human.defense = 1
        resolve_attack(engine.state, attacker.name, engine.human.name, MaximumRng())
        result = engine.execute("recruit")
        self.assertTrue(result.quit)
        self.assertIn("reign is over", result.message)

    def test_seeded_engines_reproduce_regions_and_epochs(self) -> None:
        first, first_clock = make_engine(seed=42)
        second, second_clock = make_engine(seed=42)
        first_clock.advance(120)
        second_clock.advance(120)
        self.assertEqual(first.advance_time(), second.advance_time())
        self.assertEqual(first.state.regions, second.state.regions)

    def test_cli_can_start_and_quit_without_traceback(self) -> None:
        commands = iter(["Ada", "Testland", "quit"])
        output: list[str] = []
        result = run_cli(lambda _prompt: next(commands), output.append)
        self.assertEqual(result, 0)
        self.assertIn("Welcome", output[0])
        self.assertEqual(output[-1], "Farewell, Your Majesty.")


if __name__ == "__main__":
    unittest.main()
