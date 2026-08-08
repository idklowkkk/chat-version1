import socket
import threading
import struct
import json
import os
import sys

PORT = int(os.environ.get("PORT", 9999))
MAX_FRAME = 100 * 1024 * 1024

clients = {}
clients_lock = threading.Lock()


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(n - len(buf), 65536))
        if not chunk:
            return None
        buf += chunk
    return buf


def recv_frame(sock):
    raw_len = recv_exact(sock, 4)
    if not raw_len:
        return None
    length = struct.unpack(">I", raw_len)[0]
    if length > MAX_FRAME:
        return None
    return recv_exact(sock, length)


def send_frame(sock, data):
    try:
        sock.sendall(struct.pack(">I", len(data)) + data)
    except (BrokenPipeError, OSError):
        pass


def handle_client(sock, addr):
    client_id = None
    try:
        first_frame = recv_frame(sock)
        if not first_frame:
            sock.close()
            return

        try:
            reg = json.loads(first_frame.decode())
            if reg.get("type") == "register":
                client_id = reg.get("id", "")
        except (json.JSONDecodeError, UnicodeDecodeError):
            sock.close()
            return

        if not client_id:
            sock.close()
            return

        with clients_lock:
            clients[client_id] = sock

        sock.sendall(b"OK")
        print(f"  [+] {client_id[:8]}... connected from {addr[0]}")

        while True:
            frame = recv_frame(sock)
            if not frame:
                break

            if len(frame) < 2:
                continue

            target_id_len = struct.unpack(">H", frame[:2])[0]
            if len(frame) < 2 + target_id_len:
                continue

            target_id = frame[2:2 + target_id_len].decode()
            payload = frame[2 + target_id_len:]

            with clients_lock:
                target_sock = clients.get(target_id)

            if target_sock:
                sender_header = struct.pack(">H", len(client_id)) + client_id.encode()
                send_frame(target_sock, sender_header + payload)

    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        if client_id:
            with clients_lock:
                if clients.get(client_id) == sock:
                    del clients[client_id]
            print(f"  [-] {client_id[:8]}... disconnected")
        try:
            sock.close()
        except OSError:
            pass


def main():
    print()
    print("  ══════════════════════════════")
    print("  void relay")
    print("  ══════════════════════════════")
    print(f"  listening on port {PORT}")
    print()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(100)

    while True:
        try:
            client, addr = server.accept()
            threading.Thread(target=handle_client, args=(client, addr), daemon=True).start()
        except KeyboardInterrupt:
            print("\n  shutting down.")
            server.close()
            break


if __name__ == "__main__":
    main()
