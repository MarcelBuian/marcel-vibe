# Marcel Game — design notes (living document)

Started 2026-09-16. Working title: Marcel Game.

## One-line pitch
Every player is a tiny piece of information that grows into a universe. It grows
where the player's attention goes, keeps growing while they are away, and is
shaped by a seed and by the resources they happen to have. Later, universes get
coordinates, neighbours, trade, and become museums others can visit and learn from.

## Decisions so far (2026-09-18)

### Feel
- Target feeling after 5 minutes: calm + curious + proud + slightly obsessed.
- Genre: simulation. Half creature you raise, half world you explore.
- Player is a "god with small hands": can enter and change a few configurations,
  but the universe mostly runs itself.

### Attention
- Attention = mostly looking. Growth follows where the player looks.
- Some places can be entered and configured; each configuration changes how the
  simulation unfolds from then on.
- No penalty for looking away. Universe grows idle-style while offline.
- Offline growth caps after 7 days without a sync ("it's full").
- Game time is synced to real time. Location and music are NOT inputs.
- One natural daily unit: a new fragment/event per day.

### Content generation
- Procedural, rules + randomness, driven by a seed.
- Player may enter a seed or get a random one (shown to them).
- Others can join a universe only on the same seed. Seed changes: later content.
- Uniqueness comes from resources: every player starts with different resources,
  so identical seeds still unfold differently.
- Universal buy/sell markets with fees.
- Music is part of the generated content.

### Identity
- Tap-to-start anonymous account; claim later, rewarded with good resources.
- Name, avatar (AI-generated from the player's photo, player picks best), voice
  (later, for messages between players).
- A universe can never be lost. It can be reset to small; while small, others
  can use its resources until it grows enough to kick them out or charge them.
- Later: replicate someone's universe into one of yours and continue from there.

### Multiplayer (later phases)
- Coordinates: x,y,z hex 2–3 digits each; points on a sphere; travel between
  points costs time units. Neighbours can display each other and use each
  other's resources as decorations.
- First interaction: trading. Initially through NPC civilizations that broker
  and tax both sides; as players progress they can bypass brokers unless brokers
  offer better tax schemes.
- Then: borders, viewing a neighbour's universe.
- Competition exists but is fully optional; challenges cost/win multiplayer
  points. Most players will just observe.
- Universes as museums: viewable, buyable/sellable, something to learn from.

### Scale & money
- Aim: thousands of strangers. Targets: 2k (y1), 15k (y2), 100k (y3), 1M (y4).
- No monetisation for now.

### Team & tech
- Marcel + Claude build together; Marcel reviews and pushes infra upgrades.
- Marcel knows React Native, wants to learn Unity.
- 10–20 h/week.
- Agreed: web first as a PWA, one codebase, wrapped for Android/iOS.

### Taste
- Start simple; aim for beautiful (particles, light). Dark space likely.
- Sound is essential.

### Round 2 answers (2026-09-18)
- Stack: one web technology, PWA first. Research done → see "Tech recommendation".
- Seed vs coordinates: seed = what the universe looks like inside; coordinates =
  address in the shared multiverse. Address is assigned at first; advanced players
  can later choose to explore/move to other addresses.
- Simulation is deterministic: recomputable from seed + configuration history +
  real elapsed time. Seeded randomness only. This is also the anti-cheat.
- Simulation ladder: particles → stars → planets → life → random AI civilisations.
  A new player is GOD and must create the universe (creation is the first act).
- Reset to small is triggered by "no real progress" (definition TBD).
- Museums: anything that tempts people to look and learn; no fixed curriculum.
- Music: auto-generated. Player rates songs like/dislike; generation follows the
  player's taste.
- Currency: a shared one can be created later; not needed for phase 1.
- NPC trader civilisations: faceless mechanic, no characters.
- Multiplayer points = the player's stats.
- Avatar: v1 generated from the universe itself; photo-based AI avatar later.

## Parked (return later, each is its own design session)
- Resources: types, count, abstract vs thematic, regeneration vs mining vs trade.
- Configuration knobs ("god with small hands"): the full list and their effects.
- The daily fragment: what it is.
- Ideal first five minutes / first session. Marcel is thinking about it.
- Exact rule for "no real progress" → reset.

## Phase 1 slice (proposed, awaiting Marcel's yes)
Single-player universe: seed, deterministic idle growth, attention-driven
direction, ~3 resources, 2 configuration knobs, 1 daily fragment, generated
sound with like/dislike, anonymous tap-to-start account synced to a server.
No trade, no coordinates, no photo avatar. Playable on web and phone browser.

## Tech recommendation (researched 2026-09-18, awaiting Marcel's yes)
One TypeScript codebase, split into packages:

- `sim/`   Deterministic simulation core. Pure TypeScript, no DOM, no rendering.
           Runs identically in the browser (for smooth local play) and on the
           server (for sync, verification, offline catch-up). Seeded RNG only.
- `app/`   React + Vite PWA. Visuals in Three.js via React Three Fiber
           (particles, stars, planets in real 3D; WebGPU renderer where available,
           WebGL2 fallback). Audio via Tone.js (generative music, like/dislike
           steering). Installable PWA on web and phone browsers.
- `mobile/` Capacitor wrappers for Android and iOS around the same `app/` build.
           Only added when we want store presence.
- `server/` Node/TypeScript API using the same `sim/` package. Postgres.
           Phase 1: Supabase (Postgres + anonymous auth + row security) to move
           fast; can be replaced by our own Node service without touching `sim/`.

Rejected and why:
- Unity: web export is 30–50 MB+, slow first load, weak on mobile browsers,
  not a real PWA. Learn it on the side; not for this game.
- Godot: better web export than Unity (3–25 MB) but still a monolithic WASM
  blob, no code sharing with a React UI or a Node server, WebGPU not ready.
- React Native / Expo: would need react-native-web plus expo-gl for 3D;
  two rendering paths, worse web. Capacitor wraps the web build instead.
- PixiJS / Phaser: 2D only. The universe wants depth and particles in 3D.
- Babylon.js: viable alternative to Three.js (full engine, strong WebGPU).
  Three.js chosen for the React Three Fiber ecosystem and larger community.
