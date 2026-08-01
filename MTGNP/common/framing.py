import struct
import json

MAX_PDU_SIZE = 65535

def send_pdu(sock, payload_dict: dict):
    """Encodes a JSON payload and prefixes it with a 4-byte big-endian length."""
    raw_json = json.dumps(payload_dict).encode('utf-8')
    if len(raw_json) > MAX_PDU_SIZE:
        raise ValueError("PDU exceeds maximum allowed length of 65535 bytes.")
    
    length_prefix = struct.pack("!I", len(raw_json)) # 4-byte big-endian
    sock.sendall(length_prefix + raw_json)

def recv_pdu(sock) -> dict:
    """Reads exactly 4-byte length prefix then reads the corresponding JSON byte stream."""
    header = _read_exact(sock, 4)
    if not header:
        return None
    length = struct.unpack("!I", header)[0] # 4-byte big-endian
    
    if length > MAX_PDU_SIZE:
        raise ValueError("Incoming PDU exceeds size limit.")
        
    payload_bytes = _read_exact(sock, length)
    return json.loads(payload_bytes.decode('utf-8'))

def _read_exact(sock, num_bytes: int) -> bytes:
    """Helper method to read exactly `num_bytes` from the TCP socket."""
    buf = bytearray()
    while len(buf) < num_bytes:
        chunk = sock.recv(num_bytes - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)