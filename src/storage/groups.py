import os
import json
import hashlib
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict


@dataclass
class Group:
    group_id: str
    name: str
    password: str
    members: List[str]


class GroupStore:

    def __init__(self, path: str):
        self._path = path
        self._groups: Dict[str, Group] = {}
        self._load()

    def _load(self):
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for gid, info in data.items():
                self._groups[gid] = Group(**info)
        except (json.JSONDecodeError, OSError, TypeError):
            pass

    def _save(self):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump({k: asdict(v) for k, v in self._groups.items()}, f, indent=2)

    @staticmethod
    def generate_group_id(name: str, password: str) -> str:
        raw = hashlib.sha256(f"{name}:{password}".encode()).hexdigest()[:16]
        return raw

    def create(self, name: str, password: str) -> Group:
        gid = self.generate_group_id(name, password)
        group = Group(group_id=gid, name=name, password=password, members=[])
        self._groups[gid] = group
        self._save()
        return group

    def add(self, group: Group) -> None:
        self._groups[group.group_id] = group
        self._save()

    def remove(self, group_id: str) -> None:
        self._groups.pop(group_id, None)
        self._save()

    def get(self, group_id: str) -> Optional[Group]:
        return self._groups.get(group_id)

    def get_all(self) -> Dict[str, Group]:
        return dict(self._groups)

    def exists(self, group_id: str) -> bool:
        return group_id in self._groups
