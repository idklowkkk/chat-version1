import secrets
import hashlib

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


class CipherError(Exception):
    pass


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
