import socket
import ssl
import struct
import json
import hashlib
import threading
from typing import Optional, Callable

RELAY_HOST = "hayabusa.proxy.rlwy.net"
RELAY_PORT = 38403
MAX_FRAME = 100 * 1024 * 1024

PINNED_CERT_FINGERPRINTS = []


class RelayConnection:

    def __init__(self):
        self._sock: Optional[socket.socket] = None
        self._connected = False
        self._on_message: Optional[Callable] = None
        self._recv_thread: Optional[threading.Thread] = None

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, void_id: str, on_message: Callable) -> None:
        self._on_message = on_message
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raw_sock.settimeout(30)
        self._sock = raw_sock

        self._sock.connect((RELAY_HOST, RELAY_PORT))
        self._sock.settimeout(None)

        if PINNED_CERT_FINGERPRINTS and hasattr(self._sock, 'getpeercert'):
            der = self._sock.getpeercert(binary_form=True)
            if der:
                fp = hashlib.sha256(der).hexdigest()
                if fp not in PINNED_CERT_FINGERPRINTS:
                    self._sock.close()
                    raise ConnectionError("Certificate pinning failed")

        self._send_frame(json.dumps({"type": "register", "id": void_id}).encode())
        response = self._sock.recv(16)
        if b"OK" not in response:
            raise ConnectionError("Relay rejected registration")

        self._connected = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()

    def disconnect(self) -> None:
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def send_to(self, target_id: str, payload: bytes) -> None:
        if not self._connected:
            raise ConnectionError("Not connected")
        envelope = struct.pack(">H", len(target_id)) + target_id.encode() + payload
        self._send_frame(envelope)

    def _send_frame(self, data: bytes) -> None:
        self._sock.sendall(struct.pack(">I", len(data)) + data)

    def _recv_loop(self) -> None:
        while self._connected:
            try:
                raw_len = self._recv_exact(4)
                if not raw_len:
                    break
                length = struct.unpack(">I", raw_len)[0]
                if length > MAX_FRAME:
                    break
                payload = self._recv_exact(length)
                if not payload:
                    break
                if self._on_message:
                    self._on_message(payload)
            except (OSError, ConnectionResetError):
                break
        self._connected = False

    def _recv_exact(self, n: int) -> Optional[bytes]:
        buf = b""
        while len(buf) < n:
            try:
                chunk = self._sock.recv(min(n - len(buf), 65536))
            except (OSError, ConnectionResetError):
                return None
            if not chunk:
                return None
            buf += chunk
        return buf
