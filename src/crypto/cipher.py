import secrets
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


class CipherError(Exception):
    pass


class ReplayError(Exception):
    pass


class SequenceTracker:
    """Tracks message sequence numbers to prevent replay attacks."""

    def __init__(self):
        self._counters: dict = {}  # contact_id -> last_seen_seq
        self._outgoing: dict = {}  # contact_id -> next_seq_to_send

    def next_outgoing(self, contact_id: str) -> int:
        seq = self._outgoing.get(contact_id, 0)
        self._outgoing[contact_id] = seq + 1
        return seq

    def validate_incoming(self, contact_id: str, seq: int) -> bool:
        last = self._counters.get(contact_id, -1)
        if seq <= last:
            return False
        self._counters[contact_id] = seq
        return True


def derive_conversation_key(shared_secret: bytes, our_id: str, their_id: str) -> bytes:
    sorted_ids = "".join(sorted([our_id, their_id]))
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=sorted_ids.encode(),
        info=b"void-conversation-v1",
        backend=default_backend(),
    ).derive(shared_secret)


def encrypt(key: bytes, plaintext: bytes) -> bytes:
    nonce = secrets.token_bytes(12)
    try:
        return nonce + AESGCM(key).encrypt(nonce, plaintext, None)
    except Exception as e:
        raise CipherError(f"Encryption failed: {e}") from e


def decrypt(key: bytes, data: bytes) -> bytes:
    if len(data) < 28:
        raise CipherError("Data too short")
    try:
        return AESGCM(key).decrypt(data[:12], data[12:], None)
    except Exception as e:
        raise CipherError(f"Decryption failed: {e}") from e
