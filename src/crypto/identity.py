import os
import hashlib
import base64
import secrets
from typing import Optional

from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives import serialization
from cryptography.exceptions import InvalidSignature


class Identity:
    """
    Local cryptographic identity.
    Generates a 16-char alphanumeric ID from the public key.
    Ed25519 for signing, X25519 for key agreement.
    """

    def __init__(self, signing_key: Ed25519PrivateKey, agreement_key: X25519PrivateKey):
        self._signing_key = signing_key
        self._agreement_key = agreement_key
        self._signing_pub = signing_key.public_key()
        self._agreement_pub = agreement_key.public_key()

        self._signing_pub_bytes = self._signing_pub.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self._agreement_pub_bytes = self._agreement_pub.public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

        raw = hashlib.sha256(self._signing_pub_bytes + self._agreement_pub_bytes).digest()
        charset = "abcdefghijklmnopqrstuvwxyz0123456789"
        self._void_id = "".join(charset[b % len(charset)] for b in raw[:16])

    @property
    def void_id(self) -> str:
        return self._void_id

    @property
    def signing_pub_bytes(self) -> bytes:
        return self._signing_pub_bytes

    @property
    def agreement_pub_bytes(self) -> bytes:
        return self._agreement_pub_bytes

    @property
    def pub_bundle_b64(self) -> str:
        bundle = self._signing_pub_bytes + self._agreement_pub_bytes
        return base64.b64encode(bundle).decode()

    def sign(self, data: bytes) -> bytes:
        return self._signing_key.sign(data)

    def compute_shared_secret(self, their_agreement_pub_bytes: bytes) -> bytes:
        their_pub = X25519PublicKey.from_public_bytes(their_agreement_pub_bytes)
        return self._agreement_key.exchange(their_pub)

    @staticmethod
    def verify_signature(signing_pub_bytes: bytes, signature: bytes, data: bytes) -> bool:
        try:
            pub = Ed25519PublicKey.from_public_bytes(signing_pub_bytes)
            pub.verify(signature, data)
            return True
        except (InvalidSignature, ValueError):
            return False

    @classmethod
    def load_or_create(cls, path: str) -> "Identity":
        if os.path.exists(path):
            with open(path, "rb") as f:
                raw = f.read()
            signing_key = Ed25519PrivateKey.from_private_bytes(raw[:32])
            agreement_key = X25519PrivateKey.from_private_bytes(raw[32:64])
            return cls(signing_key, agreement_key)

        signing_key = Ed25519PrivateKey.generate()
        agreement_key = X25519PrivateKey.generate()

        signing_raw = signing_key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
        )
        agreement_raw = agreement_key.private_bytes(
            serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
        )

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(signing_raw + agreement_raw)

        return cls(signing_key, agreement_key)
