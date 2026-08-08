# cespo Protocol Specification v2.1

## Overview

cespo is a direct messaging protocol providing end-to-end encryption between peers routed through a relay server. The relay handles message routing and offline queuing but has no access to plaintext content or encryption keys.

## Identity

Each client generates on first launch:
- Ed25519 signing keypair (32-byte private, 32-byte public)
- X25519 key agreement keypair (32-byte private, 32-byte public)

Both private keys are stored locally in `identity.key` (64 bytes: signing || agreement).

The user's **void_id** (16 alphanumeric characters) is derived from:
```
sha256(ed25519_public || x25519_public) -> map first 16 bytes to [a-z0-9]
```

## Key Agreement

When two users establish a conversation:
1. User A's X25519 private key + User B's X25519 public key -> shared_secret (ECDH)
2. Conversation key = HKDF-SHA256(shared_secret, salt=sorted(id_a + id_b), info="void-conversation-v1", length=32)

Both sides compute the same key independently. The key is static for the conversation lifetime.

## Wire Format

### Relay Registration
```
Client -> Relay: [4B frame_len][JSON: {"type":"register","id":"<void_id>"}]
Relay -> Client: "OK" (2 bytes)
```

### Message Envelope (Client -> Relay)
```
[4B frame_len][2B target_id_len][target_id_bytes][encrypted_payload]
```

### Message Delivery (Relay -> Client)
```
[4B frame_len][2B sender_id_len][sender_id_bytes][encrypted_payload]
```

### Frame Length
All frames are prefixed with a 4-byte big-endian unsigned integer indicating the payload length. Maximum frame size: 100MB.

## Message Format

### Signed Message (after decryption)
```json
{
  "payload": "<JSON string of the inner message>",
  "sig": "<base64 Ed25519 signature over payload bytes>"
}
```

### Inner Message
```json
{
  "type": "dm",
  "from": "<sender void_id>",
  "text": "<message content>",
  "nick": "<display name>",
  "pub_bundle": "<base64(ed25519_pub || x25519_pub)>",
  "seq": <integer sequence number>
}
```

## Encryption

- Algorithm: AES-256-GCM
- Nonce: 12 bytes, randomly generated per message
- Ciphertext format: nonce (12B) || ciphertext || GCM tag (16B)
- Key: 32-byte conversation key derived via HKDF

## Signature Verification

1. Receiver extracts `sig` and `payload` from outer envelope
2. Decodes base64 signature
3. Verifies Ed25519 signature against sender's stored public key
4. If verification fails: message is dropped silently
5. If sender has no stored public key (first contact): signature check is skipped, public key is stored from `pub_bundle`

## Replay Protection

Each message includes a monotonically increasing `seq` field per conversation. The receiver tracks the last seen sequence number per sender. Messages with `seq <= last_seen` are dropped.

## Offline Message Queuing

When a message's target is not connected:
1. Relay stores the encrypted envelope in an in-memory queue
2. Queue limit: 500 messages per user
3. Retention: 7 days
4. On reconnection: queued messages are delivered immediately after registration

## Certificate Pinning

The client attempts TLS connection to the relay. If `PINNED_CERT_FINGERPRINTS` is configured, the SHA-256 fingerprint of the server's DER-encoded certificate is validated against the pinned list. Connection is refused on mismatch.

## Key Derivation (for stored history)

Message history encryption key:
```
HKDF-SHA256(conversation_key, salt="void-history-v1", info=contact_id, length=32)
```

Each history entry is individually encrypted with AES-256-GCM and stored as:
```
[2B entry_length][12B nonce][ciphertext][GCM tag]
```

## Security Properties

- Confidentiality: AES-256-GCM encryption with per-conversation keys
- Authentication: Ed25519 signatures on every message
- Integrity: GCM authentication tag detects tampering
- Replay resistance: Sequence numbers reject duplicate messages
- Relay zero-knowledge: Relay only sees encrypted payloads and void_ids
- History encryption: Messages at rest encrypted with derived keys

## Known Limitations

- No forward secrecy (static conversation key)
- Relay knows connection metadata (who is online, who messages who by ID)
- Sequence numbers reset on app restart (partial replay window)
- Single relay is a single point of failure
