# Cespo

End-to-end encrypted messaging application built with Python and CustomTkinter.

## Features

- End-to-end encrypted direct messages (X25519 + AES-256-GCM)
- Encrypted group messaging
- Voice messages
- File sharing
- Disappearing messages
- Emoji reactions
- URL link detection (clickable links open in browser)
- Unread message counters
- Right-click context menu (Copy, React, Delete)
- Block/unblock users
- Identity export
- Theme system with multiple themes
- Notification sounds
- Contact pinning
- Message search

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

## Installation (Development)

```bash
git clone <repo-url>
cd cespo
pip install -r requirements.txt
python main.py
```

## Build Instructions

### Windows (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --icon=icon.png --name=cespo --add-data "icon.png;." --add-data "guest-pfp.png;." main.py
```

The resulting executable will be in `dist/cespo.exe`.

To create a Windows installer after building, use the included `installer.iss` with [Inno Setup](https://jrsoftware.org/isinfo.php):

```bash
iscc installer.iss
```

### macOS (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --windowed --icon=icon.png --name=cespo --add-data "icon.png:." --add-data "guest-pfp.png:." main.py
```

This produces `dist/cespo.app` — a macOS application bundle you can drag to Applications.

### Linux (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --onefile --name=cespo --add-data "icon.png:." --add-data "guest-pfp.png:." main.py
```

The resulting binary will be at `dist/cespo`. Make it executable:

```bash
chmod +x dist/cespo
./dist/cespo
```

## Protocol

See [PROTOCOL.md](PROTOCOL.md) for details on the messaging protocol and encryption scheme.

## License

See [LICENSE](LICENSE).
