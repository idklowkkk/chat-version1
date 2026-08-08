import urllib.request
import json
import threading
from typing import Optional, Callable

REPO = "idklowkkk/chat-version1"
CURRENT_VERSION = "2.1.0"
RELEASES_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
SOURCE_URL = f"https://github.com/{REPO}"


def check_for_update(callback: Callable[[Optional[str], Optional[str]], None]) -> None:
    def task():
        try:
            req = urllib.request.Request(RELEASES_URL, headers={"User-Agent": "cespo-updater"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            tag = data.get("tag_name", "").lstrip("v")
            if tag and tag != CURRENT_VERSION:
                download_url = ""
                for asset in data.get("assets", []):
                    if asset["name"].endswith(".exe"):
                        download_url = asset["browser_download_url"]
                        break
                callback(tag, download_url)
            else:
                callback(None, None)
        except Exception:
            callback(None, None)

    threading.Thread(target=task, daemon=True).start()
