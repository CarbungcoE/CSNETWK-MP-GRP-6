# CSNETWK-MP-GRP-6 — MTGNP Protocol Implementation

## Overview

This project implements a two-player networked card game using the MTGNP protocol.

The server is the authoritative source of game state. Clients connect over TCP,
send MTGNP protocol data units (PDUs), and receive authoritative state/events.

## Requirements

- Python 3.10+ recommended
- Run commands from the repository root
- No third-party packages are required by the core project

## Setup

Extract/clone the repository and open a terminal in its root:

```bash
cd CSNETWK-MP-GRP-6
```

## Start the Server

Default configuration:

```bash
python server.py --host 0.0.0.0 --port 4444
```

For verbose PDU logging:

```bash
python server.py --host 0.0.0.0 --port 4444 --verbose
```

The server listens on TCP port `4444` by default. Stop it with `Ctrl+C`.

## Start the Real Player Client

`test_client.py` is a regression/sanity test client. It is NOT the normal player
client.

For an actual interactive player, start Player 1:

```bash
python client.py --host 127.0.0.1 --port 4444 --id player_1 --verbose
```

Start Player 2 in a second terminal:

```bash
python client.py --host 127.0.0.1 --port 4444 --id player_2 --verbose
```

Each player must use a different player ID.

The interactive client supports commands such as:

```text
pass
land
cast
attack
block
mulligan
concede
```

If the top-level entry-point wrapper is unavailable in a particular checkout, the
interactive client can be launched directly as a module:

```bash
python -m mtgnp.client.socket_client --host 127.0.0.1 --port 4444 --id player_1 --verbose
```

and:

```bash
python -m mtgnp.client.socket_client --host 127.0.0.1 --port 4444 --id player_2 --verbose
```

## Running Across Two Computers

On the server computer:

```bash
python server.py --host 0.0.0.0 --port 4444 --verbose
```

On each client computer, replace `SERVER_IP` with the server computer's LAN IP:

```bash
python client.py --host SERVER_IP --port 4444 --id player_1 --verbose
```

```bash
python client.py --host SERVER_IP --port 4444 --id player_2 --verbose
```

Ensure TCP port `4444` is allowed through the server computer's firewall.

## Normal Program Flow

```text
server.py
  ↓
socket_server.py
  ↓
PLAYER_READY
  ↓
dispatcher.py
  ↓
game_session.py
  ↓
lifecycle / turn / priority / stack / combat
  ↓
authoritative GameState
  ↓
PDU response/state update
  ↓
socket_server.py
  ↓
client.py → mtgnp/client/socket_client.py
  ↓
client engine / board display
```

The normal game progression is:

```text
LOBBY
  ↓
GAME_SETUP
  ↓
MULLIGAN
  ↓
UNTAP → UPKEEP → DRAW → PRECOMBAT_MAIN
  ↓
priority and player actions
  ↓
later phases / next turns
```

### Client entry point

The top-level `client.py` is the real interactive client entry point and delegates to
`mtgnp.client.socket_client`. Run it with the commands shown above. The wrapper is
intentionally kept thin so there is only one implementation of the interactive client.

## Verbose Mode

Use `--verbose` on both the server and real clients during development and demos.

Verbose mode prints formatted PDU traffic with clearly labelled client/server
directions, making protocol sequencing and state transitions visible.

## Card Data

The authoritative fixed MTGNP card list is:

```text
mtgnp_master_card_list - Master Card List.csv
```

`mtgnp/game/card_catalog.py` loads and indexes this card data.

`card_catalog.json` is also included as a repository card-data resource.

## Testing

The test programs are separate from the real interactive client.

Basic protocol/session sanity:

```bash
python test_client.py
```

Land-play flow:

```bash
python test_client_land.py
```

Spell/stack flow:

```bash
python test_client_spell.py
```

Combat:

```bash
python test_combat_system.py
```

Turn engine:

```bash
python test_turn_engine.py
```

Session restart/recovery:

```bash
python test_session_restart.py
```

Use `client.py` for an actual player session; use the `test_*.py` programs for
automated/regression verification.

## Major Components

### `mtgnp/common`

- `framing.py` — length-prefixed TCP transport
- `pdu.py` — MTGNP PDU construction/validation
- `logger.py` — verbose PDU logging

### `mtgnp/server`

- `socket_server.py` — TCP connection/network layer
- `dispatcher.py` — PDU validation and routing
- `game_server.py` — active session management
- `game_session.py` — authoritative match controller

### `mtgnp/game`

- `game_state.py` — authoritative state
- `player.py` — player state
- `lifecycle.py` — lobby/setup/mulligan
- `turn.py` — turn/phase engine
- `priority.py` — priority ownership and sequencing
- `stack.py` — spell/ability stack
- `combat.py` — combat rules
- `card_catalog.py` — master card lookup/validation

### `mtgnp/client`

- `socket_client.py` — real interactive player client
- `engine.py` — client-side state/display
- `heartbeat.py` — PING/PONG keep-alive

## Task / Feature Distribution

| Task / Feature | Jimlor | Naomi | Earl |
| :--- | :---: | :---: | :---: |
| **TCP Server:** connection handling, framing, dispatch | | | ✓ |
| **Game lifecycle:** LOBBY, GAME_SETUP, MULLIGAN logic | ✓ | | |
| **Turn & phase engine** (all phases/steps, transitions) | | | ✓ |
| **Priority & Stack logic**, spell/ability resolution | | | ✓ |
| **Combat system** (attackers, blockers, damage) | | ✓ | |
| **Client implementation** & state rendering | | ✓ | |
| **PDU serialisation/deserialisation** | ✓ | | |
| **Error handling**, PING/PONG heartbeat, disconnect logic | ✓ | | |
| **Verbose mode** (client + server PDU logging, toggle on/off) | ✓ | | |
| **Testing & interoperability** | | ✓ | |
| **README / documentation / AI disclosure** | ✓ | ✓ | ✓ |

### AI Usage

ChatGPT (OpenAI) was used during the development of this project as an AI-assisted programming and documentation tool. It was used to assist with debugging, reviewing code for RFC compliance, identifying potential implementation issues, suggesting test cases, explaining networking and game-flow concepts, and generating/editing documentation such as the README and program-flow documentation.

All AI-assisted code and suggestions were reviewed, integrated, and tested by the group. The group remains responsible for the final implementation and its correctness.

AI tool used: OpenAI ChatGPT, GPT-5.6 Luna, accessed August 2026.


## Known Mulligan Limitation

MTGNP intentionally permits a player to mulligan repeatedly with no protocol-imposed maximum.
Each mulligan redraws a seven-card hand. However, the RFC also requires a player who keeps
after `N` mulligans to submit exactly `N` cards to put on the bottom of the library.

This creates a protocol-defined edge case once `N` exceeds the number of cards in the current hand
(which is normally seven): the player cannot legally keep because there are not enough cards to
satisfy the exact-`N` requirement. The implementation does **not** invent a mulligan limit or
change the RFC rule. Instead, the client avoids presenting an impossible bottom-card prompt and
tells the player that they must mulligan again if they want to continue. The server continues to
reject an impossible keep with `ILLEGAL_ACTION`.

This is a known MTGNP protocol limitation/edge case, not a TCP or client/server synchronization error.

## Client Prompt / Output Isolation

The real interactive client may receive game-state updates, priority changes, stack events,
and other server messages while the local player is answering a multi-step prompt. These
background updates are intentionally not printed over the active prompt. The client updates
its internal state silently and displays the resulting state after the local interaction is
completed.

This prevents one player's actions from overwriting or interleaving with another player's
active input prompt in the terminal. It is a client-side presentation/UX behavior and does not
change the authoritative server state or the MTGNP protocol messages.

## Interactive Heartbeat Behavior

The client heartbeat runs independently of stdin and game prompts, so waiting at a local
interactive prompt (for example, `Keep this hand? (y/n):`) does not pause PING/PONG processing.
The client tolerates a transient missed heartbeat and only disconnects after two consecutive
heartbeat timeouts. This prevents a single scheduling or transport delay from terminating an
otherwise healthy two-player session.

The generic `Command:` prompt is printed only when the client is not inside a protocol
sub-flow. Mulligan, targeting, combat, and other multi-step interactions provide their own
prompts so stale or duplicate command prompts do not appear underneath them.

## Protocol Reference

The protocol specification is included in:

```text
CSNETWK_MP_MTGNP.txt
```

It defines TCP framing, PDU structures, sequencing, synchronization, priority,
stack, combat, heartbeat, and error handling.

## Troubleshooting

### Connection refused

Check that:

1. The server is running.
2. The client host is correct.
3. The client port matches the server port.
4. TCP port `4444` is not blocked by a firewall.

### Game does not start

Run exactly two real clients with different IDs:

```bash
python client.py --host 127.0.0.1 --port 4444 --id player_1 --verbose
python client.py --host 127.0.0.1 --port 4444 --id player_2 --verbose
```

### Need to inspect protocol traffic

Use `--verbose` on both sides.

## Interactive Client Prompt/Transport Behavior

The interactive client keeps TCP receive/heartbeat processing independent from stdin prompts. While a multi-step local interaction is active, unsolicited remote state updates are deferred so they do not overwrite the prompt. After submitting a mulligan/action that requires a server response, the client temporarily suppresses the generic `Command:` prompt until the authoritative response arrives. This prevents duplicate prompts and prevents input entered during a server transition from being interpreted as an unrelated command.

The verified test suite includes two-client runtime checks for heartbeat traffic, prompt/output isolation, mulligan sequencing, priority synchronization, land play, spell resolution, and session restart.

## RFC 1.0 Compliance Notes

The implementation now includes focused regression coverage for the normative MTGNP 1.0 rules in `CSNETWK_MP_MTGNP.txt`, including:

- strict 4-byte big-endian framing and PDU size limits;
- per-PDU integer sequence validation and server-owned sequence numbers for server responses/errors;
- independent mulligan, priority, phase-action, trigger-choice, and cleanup action tokens;
- first-strike damage followed by state-based actions and a priority window before regular combat damage;
- repeated state-based-action checks and Active Player / Non-Active Player handling for simultaneous life-zero;
- personalized visible state including exile and RFC-shaped stack objects;
- trigger controller ownership and exact trigger-order validation;
- summoning-sickness restrictions on tap abilities;
- atomic validation of mana payments before committing payment state.

The project test suite contains `test_rfc_compliance.py` for these requirements. The live two-client integration tests also exercise the transport, mulligan, priority synchronization, land play, spell casting/resolution, heartbeat, and client prompt-isolation paths.

### Protocol extension note

`session_id` is retained as an implementation/session-routing extension used by the existing client/server architecture. It is optional on incoming `PLAYER_READY` PDUs; when omitted, the server uses the default session. It is not part of the normative MTGNP action-token semantics.

## Current Limitations

The following limitations are still present in the current implementation. This section is
intended to be the authoritative list of known limitations for the current submission and
should be read together with `CSNETWK_MP_MTGNP.txt`.

### 1. The rules engine is intentionally limited to the fixed MTGNP card set

The project is **not a general-purpose Magic: The Gathering rules engine**. It implements the
fixed pre-defined card set supplied with this project (`mtgnp_master_card_list - Master Card List.csv`).
Deck construction, arbitrary user-supplied cards, arbitrary card text, and general-purpose card
parsing are not supported.

The server resolves card behavior with a simplified effect engine and a number of explicit card
and effect handlers. The catalog can therefore contain cards whose complete printed/simplified
behavior is not yet represented by the engine.

### 2. Several card mechanics are only partially implemented or simplified

The following catalog mechanics should be considered incomplete or simplified rather than
full MTG implementations:

- **Kicker:** Kicker costs are present in card data, but there is no complete optional kicker
  payment/choice flow for all kicker cards.
- **Madness:** No complete discard-to-exile/madness replacement and optional alternate-cast flow.
- **Suspend:** The suspend/timing/counter system is not fully implemented.
- **Prowess:** Basic temporary +1/+1 behavior exists for noncreature spells, but it is not a
  general continuous/trigger rules implementation.
- **Protection:** Protection is represented in limited form, but the full four-part protection
  rules (damage, targeting, blocking, enchant/equip restrictions) are not enforced.
- **Hexproof:** The permanent data records hexproof, but target validation does not implement the
  complete controller-based hexproof restriction.
- **Regeneration:** A regeneration action is represented, but a complete regeneration shield,
  replacement, and destruction-prevention system is not implemented.
- **Trample:** The combat engine does not currently assign excess blocker damage to the defending
  player/planeswalker.
- **Double strike:** First-strike damage is implemented with a separate priority window, but the
  normal-damage portion required for a double-striking creature is not fully represented.
- **Vigilance:** The simplified turn/combat model does not model all vigilance interactions as a
  separate continuous ability system.
- **Defender/Flying:** Basic attack/block restrictions are implemented, but these are not part of
  a general keyword engine.

### 3. Choice-heavy card effects are simplified

Some cards require player choices that are currently resolved automatically or only partially:

- **Ponder:** The client/server flow exposes the top cards, but does not provide the complete
  reorder-or-shuffle choice sequence defined by the card text.
- **Mana Leak:** The target spell's controller does not receive a real `pay {3}` vs. decline choice;
  the current implementation resolves the payment automatically when enough resources are
  available.
- **Path to Exile:** The optional basic-land search is simplified rather than exposed as a full
  optional player choice.
- **Healing Salve:** The two-mode "gain 3 life" vs. "prevent the next 3 damage" choice is not
  implemented as a complete modal choice flow.
- **Mother of Runes:** The color-choice portion of protection is not represented as a complete
  player-selected color choice.
- **Vines of Vastwood / Goblin Bushwhacker:** Their optional kicker choices are not implemented
  as complete per-cast choices.

### 4. Trigger handling is still catalog-specific

The trigger framework now handles controller ownership, simultaneous ordering, and trigger-choice
plumbing required by the RFC, but trigger detection is not yet a general rules engine. The current
implementation explicitly recognizes only the trigger behaviors needed by the implemented catalog,
including examples such as:

- Goblin Guide attack trigger
- Gray Merchant enter-the-battlefield trigger
- Gravedigger enter-the-battlefield trigger
- Phantasmal Bear target/sacrifice behavior

Adding a new triggered card generally requires adding server-side trigger/effect logic; the server
does not derive arbitrary triggers from card text automatically.

### 5. Continuous effects are simplified

Effects that last "until end of turn" are represented with temporary fields and cleared during turn
cleanup, but there is no full layer-based continuous-effect system. In particular, interactions
between multiple static/temporary effects, type changes, color changes, characteristic-defining
effects, and dependency/layer ordering are outside the current implementation.

### 6. Damage-prevention and prevention-related effects are incomplete

The project has state fields for damage prevention and effects such as Skullcrack/Healing Salve are
represented in simplified form, but the complete MTG replacement/prevention system is not present.
Damage prevention shields, prevention effects with multiple sources, and "damage can't be prevented"
interactions should therefore not be considered fully rules-complete.

### 7. Some card text is implemented by simplified pattern matching

The resolver commonly selects behavior by matching phrases in `Simplified Effect`. This is useful
for the fixed catalog but means that semantically equivalent or more complicated card text cannot
necessarily be handled without a dedicated implementation. It is not intended to be a general
card-text interpreter.

### 8. Combat is not a complete Magic combat rules engine

The core attacker/blocker declarations, flying restrictions, first-strike damage step, damage
ordering, combat damage, and state-based cleanup are implemented. Remaining limitations include:

- no full trample damage assignment;
- no complete double-strike two-damage-step behavior;
- no planeswalkers or planeswalker combat/damage rules;
- no advanced combat keyword interactions such as deathtouch/lifelink;
- no general replacement/prevention system for combat damage;
- combat legality is based on the simplified permanent fields rather than a complete MTG rules
  layer system.

### 9. State-based actions cover the MTGNP requirements but not all Magic rules

The server now repeatedly checks the state-based actions required by the MTGNP specification,
including lethal creatures and life totals. It does not attempt to implement every state-based
action from full Magic rules, such as all interactions involving tokens, planeswalkers, auras,
legendary permanents, counters, and other mechanics not represented by the fixed MTGNP ruleset.

### 10. The protocol compliance tests are focused, not exhaustive

`test_rfc_compliance.py` and the live two-client tests cover the RFC areas that were specifically
implemented and regression-tested. They are not a formal proof that every possible malformed PDU,
network failure, race, or RFC edge case has been exhaustively tested.

The implementation should therefore be described as **RFC-focused and substantially compliant for
the implemented MTGNP feature set**, rather than as a formally verified implementation of every
possible RFC input/state combination.

### 11. `session_id` remains an implementation extension

`session_id` is retained for the existing server/session architecture. It is optional on
`PLAYER_READY` and is not part of the normative MTGNP action-token semantics. A peer implementing
only the base RFC and not this project extension should omit it.

### 12. The server is an in-memory two-player service

The current server is designed for the project requirement of two players and keeps active game
state in process memory. It does not provide a persistent database, durable match storage,
server clustering, or multi-process shared-session state.

A process restart therefore does not preserve an unfinished match.

### 13. Authentication and authorization are intentionally minimal

Player IDs are used to associate connections with players, but there is no authentication system,
account system, password/token system, or encrypted transport layer. The project assumes a trusted
or controlled network for the assignment environment.

### 14. The interactive client is a terminal client, not a graphical UI

The real player client is command-line based. Prompt isolation and heartbeat behavior have been
hardened, but terminal redraw, input editing, and display behavior remain subject to normal console
limitations. Server state updates are intentionally deferred while a multi-step local prompt is
active so they do not overwrite the user's input.

### 15. Mulligan has an RFC-defined edge case for repeated mulligans

MTGNP permits repeated mulligans without imposing a protocol maximum, while a keep after `N`
mulligans requires exactly `N` cards to be put on the bottom. Once `N` exceeds the number of cards
available in the hand, the player cannot legally satisfy that keep requirement. The implementation
does not invent a protocol mulligan limit; it instead requires another mulligan and rejects an
impossible keep with `ILLEGAL_ACTION`.

### 16. No general deck validation/import system exists

The project uses the supplied fixed card list and generated/test decks. There is no user-facing
deck-list import format, deck legality checker, sideboard system, card-count validator for arbitrary
constructed decks, or card availability database.

### 17. Hidden information is limited to the implemented visible-state model

The server correctly avoids sending an opponent's hand contents, but the implementation is not a
complete information-security/privacy system. The verbose development mode intentionally exposes
protocol traffic and server-side diagnostics, so verbose logs should not be treated as suitable for
an untrusted production environment.

### 18. Network reliability is handled for the assignment, not as a production service

TCP framing, PING/PONG heartbeat, duplicate-player detection, disconnect handling, and limited
reconnection behavior are implemented. There is no durable message queue, distributed failover,
TLS, NAT traversal, load balancing, or production-grade session recovery.

### What is *not* considered a current limitation

The following issues were previously observed and have been fixed in the current version:

- stale priority/mulligan action tokens caused by unrelated client updates;
- one client's active prompt being overwritten by another client's state update;
- the client remaining stuck in the mulligan waiting state after keeping a hand;
- pressing Enter at the mana-payment prompt failing to select the card's required/default colors;
- first-strike damage skipping the required post-damage priority window;
- single-pass state-based-action checking;
- incorrect Active Player / Non-Active Player handling for simultaneous life-zero;
- missing exile in personalized visible state;
- non-RFC-shaped visible stack serialization;
- duplicate/missing trigger IDs being accepted during trigger ordering;
- summoning-sickness checks for tap abilities;
- partial mana/payment state being mutated before validation failure;
- missing required PDU fields and invalid `seq_num` types on the covered dispatcher paths.

These are retained here only to make it clear that they are historical fixes, not known current
limitations.
