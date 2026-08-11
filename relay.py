import socket
import threading
import struct
import json
import os
import time

PORT = int(os.environ.get("PORT", 9999))
MAX_FRAME = 100 * 1024 * 1024
MAX_QUEUE_PER_USER = 500
MAX_QUEUE_AGE = 7 * 86400

clients = {}
clients_lock = threading.Lock()

groups = {}
groups_lock = threading.Lock()

offline_queue = {}
queue_lock = threading.Lock()


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


def queue_message(target_id, sender_id, payload):
    with queue_lock:
        if target_id not in offline_queue:
            offline_queue[target_id] = []
        queue = offline_queue[target_id]
        if len(queue) >= MAX_QUEUE_PER_USER:
            queue.pop(0)
        queue.append({"sender_id": sender_id, "payload": payload, "ts": time.time()})


def deliver_queued(client_id, sock):
    with queue_lock:
        messages = offline_queue.pop(client_id, [])
    now = time.time()
    for msg in messages:
        if now - msg["ts"] > MAX_QUEUE_AGE:
            continue
        sender_header = struct.pack(">H", len(msg["sender_id"])) + msg["sender_id"].encode()
        send_frame(sock, sender_header + msg["payload"])


def broadcast_to_group(group_id, sender_id, payload):
    with groups_lock:
        members = groups.get(group_id, set())
    sender_header = struct.pack(">H", len(sender_id)) + sender_id.encode()
    for member_id in members:
        if member_id == sender_id:
            continue
        with clients_lock:
            member_sock = clients.get(member_id)
        if member_sock:
            send_frame(member_sock, sender_header + payload)
        else:
            queue_message(member_id, sender_id, payload)


def join_group(group_id, client_id):
    with groups_lock:
        if group_id not in groups:
            groups[group_id] = set()
        groups[group_id].add(client_id)


def leave_group(group_id, client_id):
    with groups_lock:
        if group_id in groups:
            groups[group_id].discard(client_id)
            if not groups[group_id]:
                del groups[group_id]


def leave_all_groups(client_id):
    with groups_lock:
        for gid in list(groups.keys()):
            groups[gid].discard(client_id)
            if not groups[gid]:
                del groups[gid]


def purge_expired_queues():
    while True:
        time.sleep(3600)
        now = time.time()
        with queue_lock:
            for uid in list(offline_queue.keys()):
                offline_queue[uid] = [m for m in offline_queue[uid] if now - m["ts"] <= MAX_QUEUE_AGE]
                if not offline_queue[uid]:
                    del offline_queue[uid]


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
        print(f"  [+] {client_id[:8]}... connected")

        deliver_queued(client_id, sock)

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

            # Group message: target starts with "grp:"
            if target_id.startswith("grp:"):
                group_id = target_id[4:]
                join_group(group_id, client_id)
                broadcast_to_group(group_id, client_id, payload)
            # Group join command (empty payload with grp:join: prefix)
            elif target_id.startswith("grp:join:"):
                group_id = target_id[9:]
                join_group(group_id, client_id)
            else:
                # Direct message
                with clients_lock:
                    target_sock = clients.get(target_id)
                if target_sock:
                    sender_header = struct.pack(">H", len(client_id)) + client_id.encode()
                    send_frame(target_sock, sender_header + payload)
                else:
                    queue_message(target_id, client_id, payload)

    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        if client_id:
            with clients_lock:
                if clients.get(client_id) == sock:
                    del clients[client_id]
            leave_all_groups(client_id)
            print(f"  [-] {client_id[:8]}... disconnected")
        try:
            sock.close()
        except OSError:
            pass


def main():
    print()
    print("  cespo relay")
    print(f"  port {PORT}")
    print(f"  DMs + groups | offline queue: {MAX_QUEUE_PER_USER}/user, {MAX_QUEUE_AGE//86400}d")
    print()

    threading.Thread(target=purge_expired_queues, daemon=True).start()

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
