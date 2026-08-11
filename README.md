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
