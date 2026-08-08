from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    sidebar: str
    surface: str
    input_bg: str
    border: str
    text: str
    text_dim: str
    accent: str
    accent_hover: str
    incoming: str
    danger: str
    warning: str


THEMES: Dict[str, Theme] = {
    "Midnight": Theme(
        name="Midnight",
        bg="#050508",
        sidebar="#0a0a10",
        surface="#0e0e16",
        input_bg="#14141e",
        border="#1e1e2e",
        text="#e0e0ea",
        text_dim="#4a4a5e",
        accent="#00ff9d",
        accent_hover="#00cc7d",
        incoming="#8b5cf6",
        danger="#ef4444",
        warning="#f59e0b",
    ),
    "Emerald": Theme(
        name="Emerald",
        bg="#040a08",
        sidebar="#081410",
        surface="#0c1a14",
        input_bg="#10221a",
        border="#1a3328",
        text="#d8f0e8",
        text_dim="#4a6e5c",
        accent="#34d399",
        accent_hover="#10b981",
        incoming="#60a5fa",
        danger="#f87171",
        warning="#fbbf24",
    ),
    "Crimson": Theme(
        name="Crimson",
        bg="#080404",
        sidebar="#100808",
        surface="#160c0c",
        input_bg="#1e1010",
        border="#2e1a1a",
        text="#f0dede",
        text_dim="#6e4a4a",
        accent="#f43f5e",
        accent_hover="#e11d48",
        incoming="#a78bfa",
        danger="#fbbf24",
        warning="#fb923c",
    ),
    "Violet": Theme(
        name="Violet",
        bg="#06050a",
        sidebar="#0c0a14",
        surface="#120e1c",
        input_bg="#1a1426",
        border="#2a2040",
        text="#e8e0f8",
        text_dim="#5a4a7a",
        accent="#a78bfa",
        accent_hover="#8b5cf6",
        incoming="#34d399",
        danger="#f87171",
        warning="#fbbf24",
    ),
    "Arctic": Theme(
        name="Arctic",
        bg="#080a0c",
        sidebar="#0c1014",
        surface="#101820",
        input_bg="#142028",
        border="#1e3040",
        text="#e0eef8",
        text_dim="#4a6a82",
        accent="#38bdf8",
        accent_hover="#0ea5e9",
        incoming="#c084fc",
        danger="#f87171",
        warning="#fbbf24",
    ),
}

DEFAULT_THEME = "Midnight"
