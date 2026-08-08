import time
import threading
from mtgnp.common.framing import send_pdu
from mtgnp.common.pdu import build_ping

class HeartbeatMonitor:
    """Manages the periodic PING messages and PONG timeout checking for the client."""
    
    def __init__(self, sock, ping_interval=30.0, timeout=10.0):
        self.sock = sock
        self.ping_interval = ping_interval
        self.timeout = timeout
        self.last_pong_time = time.time()
        self.running = False
        self.seq_num = 1 # client-maintained counter independent of priority

    def start(self):
        self.running = True
        self.last_pong_time = time.time()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self):
        self.running = False

    def receive_pong(self):
        """Called by the client's receive loop when a PONG is received."""
        self.last_pong_time = time.time()

    def _loop(self):
        while self.running:
            time.sleep(self.ping_interval)
            if not self.running:
                break
            
            # send PING
            ping_pdu = build_ping(self.seq_num, int(time.time() * 1000))
            try:
                send_pdu(self.sock, ping_pdu)
                self.seq_num += 1
            except Exception as e:
                print(f"Heartbeat send failed: {e}")
                self.running = False
                break

            # wait for timeout to check if server responded with PONG
            time.sleep(self.timeout)
            if not self.running:
                break
            
            # if the last pong was received longer ago than (interval + timeout), server is dead
            if time.time() - self.last_pong_time > (self.ping_interval + self.timeout - 1):
                print("Heartbeat timeout! No PONG received. Disconnecting from server...")
                self.sock.close()
                self.running = False
                break