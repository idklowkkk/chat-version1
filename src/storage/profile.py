import os
import json
from typing import Optional


class Profile:

    def __init__(self, path: str):
        self._path = path
        self._data = self._load()

    def _load(self) -> dict:
        if not os.path.exists(self._path):
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f)

    @property
    def display_name(self) -> str:
        return self._data.get("display_name", "")

    @display_name.setter
    def display_name(self, value: str):
        self._data["display_name"] = value[:15]
        self._save()

    @property
    def setup_complete(self) -> bool:
        return self._data.get("setup_complete", False)

    @setup_complete.setter
    def setup_complete(self, value: bool):
        self._data["setup_complete"] = value
        self._save()

    @property
    def theme(self) -> str:
        return self._data.get("theme", "Midnight")

    @theme.setter
    def theme(self, value: str):
        self._data["theme"] = value
        self._save()

    @property
    def avatar_path(self) -> str:
        return self._data.get("avatar_path", "")

    @avatar_path.setter
    def avatar_path(self, value: str):
        self._data["avatar_path"] = value
        self._save()

    @property
    def auto_delete(self) -> str:
        return self._data.get("auto_delete", "off")

    @auto_delete.setter
    def auto_delete(self, value: str):
        self._data["auto_delete"] = value
        self._save()

    @property
    def notification_sound(self) -> bool:
        return self._data.get("notification_sound", True)

    @notification_sound.setter
    def notification_sound(self, value: bool):
        self._data["notification_sound"] = value
        self._save()

    @property
    def font_size(self) -> int:
        return self._data.get("font_size", 11)

    @font_size.setter
    def font_size(self, value: int):
        self._data["font_size"] = max(9, min(16, value))
        self._save()

    @property
    def read_receipts(self) -> bool:
        return self._data.get("read_receipts", False)

    @read_receipts.setter
    def read_receipts(self, value: bool):
        self._data["read_receipts"] = value
        self._save()

    @property
    def show_seen(self) -> bool:
        return self._data.get("show_seen", False)

    @show_seen.setter
    def show_seen(self, value: bool):
        self._data["show_seen"] = value
        self._save()

    @property
    def link_preview(self) -> bool:
        return self._data.get("link_preview", True)

    @link_preview.setter
    def link_preview(self, value: bool):
        self._data["link_preview"] = value
        self._save()

    @property
    def pinned_contacts(self) -> list:
        return self._data.get("pinned_contacts", [])

    @pinned_contacts.setter
    def pinned_contacts(self, value: list):
        self._data["pinned_contacts"] = value
        self._save()

    @property
    def blocked_users(self) -> list:
        return self._data.get("blocked_users", [])

    @blocked_users.setter
    def blocked_users(self, value: list):
        self._data["blocked_users"] = value
        self._save()

    def block_user(self, void_id: str):
        blocked = self.blocked_users
        if void_id not in blocked:
            blocked.append(void_id)
            self.blocked_users = blocked

    def unblock_user(self, void_id: str):
        blocked = self.blocked_users
        if void_id in blocked:
            blocked.remove(void_id)
            self.blocked_users = blocked

    def is_blocked(self, void_id: str) -> bool:
        return void_id in self.blocked_users
