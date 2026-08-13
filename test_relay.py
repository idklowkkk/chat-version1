import socket, struct, json

s = socket.socket()
s.settimeout(10)
s.connect(("hayabusa.proxy.rlwy.net", 38403))
msg = json.dumps({"type": "register", "id": "testping12345678"}).encode()
s.sendall(struct.pack(">I", len(msg)) + msg)
r = s.recv(16)
print(f"relay response: {r}")
s.close()
