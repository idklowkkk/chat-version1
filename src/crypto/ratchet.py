"""
Double Ratchet implementation providing forward secrecy.
Based on the Signal Protocol specification.

Each message gets a unique encryption key derived from a ratcheting chain.
Compromise of any single key reveals only that one message.
"""

import secrets
import hashlib
import struct
from typing import Tuple, Optional, Dict

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend


def _hkdf(input_key: bytes, salt: bytes, info: bytes, length: int = 32) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
        backend=default_backend(),
    ).derive(input_key)


def _kdf_rk(root_key: bytes, dh_output: bytes) -> Tuple[bytes, bytes]:
    """Root key KDF: derives new root key + chain key from DH output."""
    derived = _hkdf(dh_output, root_key, b"ratchet-root", 64)
    return derived[:32], derived[32:]


def _kdf_ck(chain_key: bytes) -> Tuple[bytes, bytes]:
    """Chain key KDF: derives next chain key + message key."""
    mk = _hkdf(chain_key, b"", b"ratchet-msg-key", 32)
    next_ck = _hkdf(chain_key, b"", b"ratchet-chain-step", 32)
    return next_ck, mk


def _generate_dh() -> Tuple[X25519PrivateKey, bytes]:
    """Generate an X25519 keypair, return (private, public_bytes)."""
    priv = X25519PrivateKey.generate()
    pub = priv.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    return priv, pub


def _dh(private: X25519PrivateKey, their_pub_bytes: bytes) -> bytes:
    """Perform X25519 Diffie-Hellman."""
    their_pub = X25519PublicKey.from_public_bytes(their_pub_bytes)
    return private.exchange(their_pub)


class RatchetSession:
    """
    Double Ratchet session for one conversation.

    Usage:
        # Initiator (Alice)
        session = RatchetSession.init_sender(shared_secret, bob_pub_bytes)

        # Responder (Bob)
        session = RatchetSession.init_receiver(shared_secret, bob_private_key)

        # Encrypt
        header, ciphertext = session.encrypt(plaintext)

        # Decrypt
        plaintext = session.decrypt(header, ciphertext)
    """

    def __init__(self):
        self._root_key: bytes = b""
        self._send_chain_key: Optional[bytes] = None
        self._recv_chain_key: Optional[bytes] = None
        self._send_ratchet_priv: Optional[X25519PrivateKey] = None
        self._send_ratchet_pub: bytes = b""
        self._recv_ratchet_pub: bytes = b""
        self._send_count: int = 0
        self._recv_count: int = 0
        self._prev_send_count: int = 0
        self._skipped: Dict[Tuple[bytes, int], bytes] = {}

    @classmethod
    def init_sender(cls, shared_secret: bytes, their_ratchet_pub: bytes) -> "RatchetSession":
        """Initialize as the conversation initiator."""
        session = cls()
        session._recv_ratchet_pub = their_ratchet_pub
        priv, pub = _generate_dh()
        session._send_ratchet_priv = priv
        session._send_ratchet_pub = pub

        dh_out = _dh(priv, their_ratchet_pub)
        session._root_key, session._send_chain_key = _kdf_rk(shared_secret, dh_out)
        session._send_count = 0
        session._recv_count = 0
        return session

    @classmethod
    def init_receiver(cls, shared_secret: bytes, our_ratchet_priv: X25519PrivateKey) -> "RatchetSession":
        """Initialize as the conversation responder."""
        session = cls()
        session._root_key = shared_secret
        session._send_ratchet_priv = our_ratchet_priv
        session._send_ratchet_pub = our_ratchet_priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        session._send_count = 0
        session._recv_count = 0
        return session

    def encrypt(self, plaintext: bytes) -> Tuple[bytes, bytes]:
        """
        Encrypt a message. Returns (header, ciphertext).
        Header contains our current ratchet public key + counters.
        """
        if self._send_chain_key is None:
            raise RuntimeError("Send chain not initialized")

        self._send_chain_key, mk = _kdf_ck(self._send_chain_key)
        nonce = secrets.token_bytes(12)
        ct = AESGCM(mk).encrypt(nonce, plaintext, None)

        header = self._send_ratchet_pub + struct.pack(">II", self._prev_send_count, self._send_count)
        self._send_count += 1

        return header, nonce + ct

    def decrypt(self, header: bytes, ciphertext: bytes) -> bytes:
        """
        Decrypt a message. Automatically performs DH ratchet step if needed.
        """
        their_pub = header[:32]
        prev_count, msg_count = struct.unpack(">II", header[32:40])

        # Check skipped messages cache
        cache_key = (their_pub, msg_count)
        if cache_key in self._skipped:
            mk = self._skipped.pop(cache_key)
            return AESGCM(mk).decrypt(ciphertext[:12], ciphertext[12:], None)

        # If they sent a new ratchet key, perform DH ratchet
        if their_pub != self._recv_ratchet_pub:
            self._skip_messages(self._recv_ratchet_pub, prev_count)
            self._dh_ratchet(their_pub)

        self._skip_messages(their_pub, msg_count)
        self._recv_chain_key, mk = _kdf_ck(self._recv_chain_key)
        self._recv_count += 1

        return AESGCM(mk).decrypt(ciphertext[:12], ciphertext[12:], None)

    def _dh_ratchet(self, their_pub: bytes):
        """Perform a DH ratchet step."""
        self._recv_ratchet_pub = their_pub
        self._prev_send_count = self._send_count
        self._send_count = 0
        self._recv_count = 0

        dh_out = _dh(self._send_ratchet_priv, their_pub)
        self._root_key, self._recv_chain_key = _kdf_rk(self._root_key, dh_out)

        priv, pub = _generate_dh()
        self._send_ratchet_priv = priv
        self._send_ratchet_pub = pub

        dh_out2 = _dh(priv, their_pub)
        self._root_key, self._send_chain_key = _kdf_rk(self._root_key, dh_out2)

    def _skip_messages(self, their_pub: bytes, until: int):
        """Skip and cache message keys for out-of-order delivery."""
        if self._recv_chain_key is None:
            return
        while self._recv_count < until:
            self._recv_chain_key, mk = _kdf_ck(self._recv_chain_key)
            self._skipped[(their_pub, self._recv_count)] = mk
            self._recv_count += 1
            if len(self._skipped) > 1000:
                oldest = next(iter(self._skipped))
                del self._skipped[oldest]

    @property
    def ratchet_pub_bytes(self) -> bytes:
        return self._send_ratchet_pub


    def serialize(self) -> dict:
        """Serialize session state for persistence."""
        priv_bytes = self._send_ratchet_priv.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
        ) if self._send_ratchet_priv else b""
        return {
            "root_key": self._root_key.hex(),
            "send_chain_key": self._send_chain_key.hex() if self._send_chain_key else "",
            "recv_chain_key": self._recv_chain_key.hex() if self._recv_chain_key else "",
            "send_ratchet_priv": priv_bytes.hex(),
            "send_ratchet_pub": self._send_ratchet_pub.hex(),
            "recv_ratchet_pub": self._recv_ratchet_pub.hex(),
            "send_count": self._send_count,
            "recv_count": self._recv_count,
            "prev_send_count": self._prev_send_count,
        }

    @classmethod
    def deserialize(cls, data: dict) -> "RatchetSession":
        """Restore session from serialized state."""
        session = cls()
        session._root_key = bytes.fromhex(data["root_key"])
        session._send_chain_key = bytes.fromhex(data["send_chain_key"]) if data["send_chain_key"] else None
        session._recv_chain_key = bytes.fromhex(data["recv_chain_key"]) if data["recv_chain_key"] else None
        priv_hex = data["send_ratchet_priv"]
        if priv_hex:
            session._send_ratchet_priv = X25519PrivateKey.from_private_bytes(bytes.fromhex(priv_hex))
        session._send_ratchet_pub = bytes.fromhex(data["send_ratchet_pub"])
        session._recv_ratchet_pub = bytes.fromhex(data["recv_ratchet_pub"])
        session._send_count = data["send_count"]
        session._recv_count = data["recv_count"]
        session._prev_send_count = data["prev_send_count"]
        return session
