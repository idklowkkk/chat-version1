import os
import json
from typing import Dict, Optional
from dataclasses import dataclass, asdict


@dataclass
class Contact:
    void_id: str
    display_name: str
    signing_pub_b64: str
    agreement_pub_b64: str


class ContactStore:

    def __init__(self, path: str):
        self._path = path
        self._contacts: Dict[str, Contact] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for vid, info in data.items():
                self._contacts[vid] = Contact(**info)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({k: asdict(v) for k, v in self._contacts.items()}, f, indent=2)

    def add(self, contact: Contact) -> None:
        self._contacts[contact.void_id] = contact
        self._save()

    def remove(self, void_id: str) -> None:
        self._contacts.pop(void_id, None)
        self._save()

    def get(self, void_id: str) -> Optional[Contact]:
        return self._contacts.get(void_id)

    def get_all(self) -> Dict[str, Contact]:
        return dict(self._contacts)

    def exists(self, void_id: str) -> bool:
        return void_id in self._contacts
