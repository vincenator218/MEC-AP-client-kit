# Mirror's Edge Catalyst

## What does randomization do to this game?

You play the open world of Glass City from a save where the story is already finished. Your
abilities (Coil, Shift, stamina tiers, combat moves, Focus, ...), five traversal moves
(Springboard, Climb Up, Ledge Hang, Wallrun, MAG Rope) and the replay-menu unlocks for side
missions and opportunities are shuffled into the multiworld.

## What is the goal?

Collect the required number of **Data Shards**. That unlocks the **final activity** (chosen
in your options) in the replay menu. Finish it while you hold the shards.

## What counts as a check?

By default: side missions, the 40 opportunities, and GridLeaks in bundles (every 5 leaks in a
district sends one check). Countdown deliveries, security hubs, grid nodes, billboards,
electronic parts, surveillance recordings, documents and secret bags can be turned on.

## When do items take effect?

- Traversal moves: immediately.
- Abilities: at your next death or checkpoint restart.
- Side mission and opportunity unlocks: in the replay menu after the next load.

## Is the logic complete?

No. Which activities need which moves is still being collected, so the logic does not yet
know what anything requires. Until it does, consider `traversal_items: start_with`.
