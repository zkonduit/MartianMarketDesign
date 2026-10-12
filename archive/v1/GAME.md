# Kingdom Wars playable prototype

`kingdom_wars.py` applies the protocol's exchange-clearing and mutual-credit
ideas to a dependency-free terminal strategy game. You play against Balanced,
Assassin, and Friendly AI kings while gathering resources, feeding your people,
building defenses, raising warriors, and exchanging goods.

Run the game and its tests with Python 3.12 or newer:

```sh
python3 kingdom_wars.py
python3 -m unittest -v
```

One epoch passes every 60 seconds. Elapsed epochs resolve when you enter a
command, so the terminal remains readable while the game clock continues. Each
kingdom begins with four workers, eight food, ten defense, and access to wood
and metal regions whose capacity changes every epoch. Enter `help` during play
for the complete command list.

The main command groups are:

- `assign`, `recruit`, `train`, `upgrade`, and `fortify` for kingdom management;
- `intent barter`, `intent sell`, and `intent buy` for publishing structured
  offers and wants;
- `match`, `propose`, and `approve` for inspectable, explicitly authorized
  bilateral swaps, three-kingdom cycles, and mutual-credit settlements; and
- `attack` or `build market` to pursue military or Grand Market victory.

Credit prices respond to current supply and demand intents. Every credit trade
creates an equal positive provider balance and negative receiver balance, all
balances begin at zero, and the ledger total remains zero. A proposal locks its
goods and debit capacity until it settles, is rejected, or expires at the next
epoch. The Grand Market requires 30 of each resource, a completed three-party
barter, a completed credit trade, and a nonnegative credit balance.

The central idea is that exchange value is contextual. It depends not only on an
asset and its quantity, but also on timing, preferences, trust, delivery risk,
utility, and the alternatives available to each participant. Given the rise of AI agents,
it becomes feasible to represent such intents at scale.