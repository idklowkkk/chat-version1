import os
import json
import time
import struct
import secrets
import hashlib
from typing import List, Dict, Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend


class MessageStore:

    def __init__(self, base_dir: str, conversation_key: bytes, contact_id: str):
        os.makedirs(base_dir, exist_ok=True)
        cid_hash = hashlib.sha256(contact_id.encode()).hexdigest()[:12]
        self._path = os.path.join(base_dir, f"{cid_hash}.vault")
        self._key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=b"void-history-v1",
            info=contact_id.encode(),
            backend=default_backend(),
        ).derive(conversation_key)

    def append(self, sender_id: str, text: str) -> None:
        entry = json.dumps({
            "ts": time.time(),
            "from": sender_id,
            "text": text,
        }, separators=(",", ":")).encode()

        nonce = secrets.token_bytes(12)
        ct = AESGCM(self._key).encrypt(nonce, entry, None)
        blob = nonce + ct

        with open(self._path, "ab") as f:
            f.write(struct.pack(">H", len(blob)) + blob)

    def load(self, max_age_seconds: int = 0) -> List[Dict[str, Any]]:
        if not os.path.exists(self._path):
            return []

        messages = []
        cutoff = time.time() - max_age_seconds if max_age_seconds > 0 else 0

        with open(self._path, "rb") as f:
            data = f.read()

        offset = 0
        while offset + 2 <= len(data):
            blob_len = struct.unpack(">H", data[offset:offset + 2])[0]
            offset += 2
            if offset + blob_len > len(data):
                break
            blob = data[offset:offset + blob_len]
            offset += blob_len

            if len(blob) < 12:
                continue
            try:
                plaintext = AESGCM(self._key).decrypt(blob[:12], blob[12:], None)
                entry = json.loads(plaintext.decode())
                if cutoff == 0 or entry.get("ts", 0) > cutoff:
                    messages.append(entry)
            except Exception:
                continue

        return messages

    def clear(self) -> None:
        if os.path.exists(self._path):
            os.remove(self._path)
