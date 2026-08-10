# CSNETWK-MP-GRP-6# MTGNP Protocol Implementation (CSNETWK MP)

## Build and Run Instructions
Run the server:
```bash
python server.py --port 4444 --verbose
```
Run the test client (after running the server):
```bash
python test_client.py
```
As of writing, server is closed with a keyboard interrupt i.e. CTRL + C
## Task / Feature Distribution

| Task / Feature | Jimlor | Naomi | Earl |
| :--- | :---: | :---: | :---: |
| **TCP Server:** connection handling, framing, dispatch | | | ✓ |
| **Game lifecycle:** LOBBY, GAME_SETUP, MULLIGAN logic | ✓ | | |
| **Turn & phase engine** (all phases/steps, transitions) | | | ✓ |
| **Priority & Stack logic**, spell/ability resolution | | | ✓ |
| **Combat system** (attackers, blockers, damage) | | ✓ | |
| **Client implementation** & state rendering | | ✓ | |
| **PDU serialisation/deserialisation** (all 25 PDU types) | ✓ | | |
| **Error handling**, PING/PONG heartbeat, disconnect logic | ✓ | | |
| **Verbose mode** (client + server PDU logging, toggle on/off) | ✓ | | |
| **Testing & interoperability** | | ✓ | |
| **README / documentation / AI disclosure** | ✓ | ✓ | ✓ |