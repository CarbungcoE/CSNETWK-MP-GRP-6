import threading
import time
from typing import Callable, Optional

from mtgnp.common.pdu import build_ping


class HeartbeatMonitor:
    """Send periodic PINGs and require a matching PONG within the timeout."""

    def __init__(
        self,
        sock,
        ping_interval: float = 30.0,
        timeout: float = 10.0,
        send_callback: Optional[Callable[[dict], None]] = None,
        verbose: bool = False,
        max_missed_heartbeats: int = 2,
    ):
        self.sock = sock
        self.ping_interval = float(ping_interval)
        self.timeout = float(timeout)
        self.send_callback = send_callback
        self.verbose = verbose
        self.max_missed_heartbeats = max(1, int(max_missed_heartbeats))
        self._missed_heartbeats = 0

        self.running = False
        self.seq_num = 1
        self._thread = None
        self._wake = threading.Event()
        self._pong_event = threading.Event()
        self._state_lock = threading.Lock()
        self._pending_seq: Optional[int] = None
        self._pending_sent_at: Optional[float] = None

    def start(self):
        if self.running:
            return
        self.running = True
        self._wake.clear()
        self._missed_heartbeats = 0
        self._thread = threading.Thread(
            target=self._loop,
            name="mtgnp-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        self.running = False
        self._wake.set()
        self._pong_event.set()

    def receive_pong(self, seq_num: int):
        """Record a PONG only when it matches the currently outstanding PING."""
        with self._state_lock:
            if self._pending_seq != seq_num:
                if self.verbose:
                    print(
                        f"[heartbeat] Ignoring unexpected PONG seq={seq_num}; "
                        f"waiting for {self._pending_seq}."
                    )
                return False
            self._pending_seq = None
            self._pending_sent_at = None
            self._pong_event.set()
            return True

    def _sleep_until_next_ping(self):
        # Wake immediately on stop; otherwise wait the configured interval.
        return not self._wake.wait(self.ping_interval)

    def _loop(self):
        # The monitor is started only after the client has received the
        # server's initial GAME_STATE_UPDATE.  Begin with a clean interval
        # so heartbeat traffic cannot race the handshake.
        while self.running:
            if not self._sleep_until_next_ping():
                break
            if not self.running:
                break

            seq = self.seq_num
            ping = build_ping(seq, int(time.time() * 1000))
            with self._state_lock:
                self._pending_seq = seq
                self._pending_sent_at = time.monotonic()
                self._pong_event.clear()

            try:
                if self.send_callback is not None:
                    self.send_callback(ping)
                else:
                    # Kept for backwards compatibility with direct use of this class.
                    from mtgnp.common.framing import send_pdu
                    send_pdu(self.sock, ping)
                if self.verbose:
                    print(f"[heartbeat] PING seq={seq}")
                self.seq_num += 1
            except Exception as exc:
                print(f"Heartbeat send failed: {exc}")
                self.running = False
                break

            # Wait specifically for the matching PONG, rather than comparing
            # against a global last-pong timestamp.
            if not self._pong_event.wait(self.timeout):
                with self._state_lock:
                    still_pending = self._pending_seq == seq
                    sent_at = self._pending_sent_at
                if not self.running:
                    break
                if still_pending:
                    elapsed = (
                        time.monotonic() - sent_at
                        if sent_at is not None
                        else self.timeout
                    )
                    self._missed_heartbeats += 1
                    if self._missed_heartbeats < self.max_missed_heartbeats:
                        print(
                            "Heartbeat warning: no matching PONG received "
                            f"for seq={seq} within {elapsed:.1f}s "
                            f"({self._missed_heartbeats}/{self.max_missed_heartbeats} missed). "
                            "Keeping the connection alive and retrying."
                        )
                        with self._state_lock:
                            self._pending_seq = None
                            self._pending_sent_at = None
                        continue

                    print(
                        "Heartbeat timeout: no matching PONG received "
                        f"for {self.max_missed_heartbeats} consecutive heartbeat(s). "
                        "Disconnecting from server..."
                    )
                    self.running = False
                    try:
                        self.sock.shutdown(2)
                    except OSError:
                        pass
                    try:
                        self.sock.close()
                    except OSError:
                        pass
                    break
            else:
                self._missed_heartbeats = 0

            with self._state_lock:
                self._pending_seq = None
                self._pending_sent_at = None
