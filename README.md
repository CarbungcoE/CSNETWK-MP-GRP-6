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

## AI Usage

Document all AI tools used for this project and how they were used. All AI-generated
code must be reviewed, tested, and understood by the group before submission/demo.

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
