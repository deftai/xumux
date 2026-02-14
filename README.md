# OpenMux

**Transport-agnostic channel multiplexing protocol**

Version: 0.1.0-draft | Status: Draft | Date: 2026-02-14

---

## What is OpenMux?

OpenMux is an open protocol for multiplexing typed, named channels over any reliable or semi-reliable transport. It provides a standard binary framing format, channel lifecycle management, and handshake procedure that works identically whether the underlying transport is a WebRTC DataChannel, a WebSocket, a TCP socket, or a Unix pipe.

Think of it as **a universal way to run multiple logical channels over a single connection** — with each channel having its own reliability and ordering guarantees.

## Design Goals

- **Transport-agnostic**: Same frame format and semantics over any transport
- **Minimal overhead**: 6-byte header for the common case, extensible when needed
- **Channel-native**: First-class support for named, typed channels with independent reliability
- **Simple to implement**: Any language, any platform, in an afternoon
- **Composable**: Application protocols (terminal I/O, remote desktop, file transfer) build on top

## Non-Goals

- Defining application-level message semantics (that's your protocol's job)
- Transport negotiation (the transport is already established when OpenMux starts)
- Encryption (the transport provides this — DTLS for WebRTC, TLS for WebSocket/TCP)

## Architecture

```
┌─────────────────────────────────────────────┐
│         Application Protocol                │
│   (VROOM, TermPipe, your-protocol-here)     │
├─────────────────────────────────────────────┤
│              OpenMux                        │
│   framing · channels · handshake · keepalive│
├─────────────────────────────────────────────┤
│           Transport Backend                 │
│   WebRTC DC │ WebSocket │ TCP │ stdio │ ... │
└─────────────────────────────────────────────┘
```

## Core Specification

### Frame Format

All OpenMux messages use a 6-byte header followed by an optional payload:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Channel    |     Type      |     Flags     |   Reserved    |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|        Payload Length         |       Payload (variable)    ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| 0 | Channel | 1 byte | Logical channel ID (0x00 = control) |
| 1 | Type | 1 byte | Message type within channel |
| 2 | Flags | 1 byte | Message-specific flags |
| 3 | Reserved | 1 byte | MUST be 0x00 |
| 4 | Payload Length | 2 bytes | Payload size in bytes (big-endian, max 65535) |
| 6 | Payload | variable | Message-specific data |

**Why 2-byte length?** Most real-time messages (input events, terminal data, control) are well under 64KB. For bulk transfers, use chunking at the application layer or the EXTENDED_LENGTH flag.

**Flags (bit 0)**: `EXTENDED_LENGTH` — if set, Payload Length field is 4 bytes instead of 2 (shifts payload start to offset 8). This allows messages up to 4GB for bulk data channels.

### Channel 0x00: Control (Reserved)

Channel 0 is always the control channel. It carries OpenMux protocol messages:

| Type | Name | Direction | Description |
|------|------|-----------|-------------|
| `0x01` | HELLO | C→S | Client hello with version + capabilities |
| `0x02` | WELCOME | S→C | Server hello response |
| `0x03` | OPEN_CHANNEL | Both | Request to open a named channel |
| `0x04` | CHANNEL_ACK | Both | Channel open confirmed |
| `0x05` | CLOSE_CHANNEL | Both | Close a channel |
| `0x10` | PING | Both | Keepalive request |
| `0x11` | PONG | Both | Keepalive response |
| `0x20` | CLOSE | Both | Graceful connection close |
| `0xF0` | ERROR | Both | Error notification |

### Handshake

```
Client                              Server
  │                                    │
  │──── HELLO (version, caps) ────────►│
  │                                    │
  │◄─── WELCOME (version, caps) ──────│
  │                                    │
  │──── OPEN_CHANNEL ("data") ────────►│
  │◄─── CHANNEL_ACK (ch=1) ───────────│
  │                                    │
  │──── OPEN_CHANNEL ("events") ──────►│
  │◄─── CHANNEL_ACK (ch=2) ───────────│
  │                                    │
  │  ... application data flows ...    │
```

#### HELLO (0x01)

```json
{
  "version": [0, 1, 0],
  "extensions": [],
  "application": "vroom/0.1",
  "channels": [
    {"name": "control", "reliable": true, "ordered": true},
    {"name": "pointer", "reliable": false, "ordered": false},
    {"name": "button", "reliable": true, "ordered": true}
  ]
}
```

The HELLO payload is JSON (UTF-8). This is the only JSON message in the core protocol — everything after handshake is binary.

#### WELCOME (0x02)

```json
{
  "version": [0, 1, 0],
  "extensions": [],
  "channels": [
    {"name": "control", "id": 1},
    {"name": "pointer", "id": 2},
    {"name": "button", "id": 3}
  ]
}
```

Server assigns numeric channel IDs. Channel 0 remains the control channel.

### Channel Lifecycle

Channels can be opened during handshake (via HELLO/WELCOME) or dynamically at any time via OPEN_CHANNEL/CHANNEL_ACK on the control channel.

### Transport Mapping

When the transport natively supports multiple channels (like WebRTC DataChannels), OpenMux channels MAY map 1:1 to transport channels. In this case, the Channel byte in the frame header is redundant but MUST still be present for format consistency.

When the transport is a single stream (WebSocket, TCP, stdio), all channels are multiplexed over that stream using the Channel byte.

### Keepalive

Either side MAY send PING on channel 0. The other side MUST respond with PONG. If no PONG is received within the negotiated timeout, the connection SHOULD be considered dead.

---

## Transport Bindings

| Transport | Specification |
|-----------|---------------|
| WebRTC DataChannel | [openmux-on-webrtc.md](docs/openmux-on-webrtc.md) |
| WebSocket | [openmux-on-websocket.md](docs/openmux-on-websocket.md) |
| TCP | [docs/openmux-on-tcp.md](docs/openmux-on-tcp.md) |
| stdio | [docs/openmux-on-stdio.md](docs/openmux-on-stdio.md) |

## Application Protocols

OpenMux is a multiplexing layer. Application protocols define what flows over the channels:

| Protocol | Description | Repository |
|----------|-------------|------------|
| **VROOM** | Virtual Remoting Over OpenMux — WebRTC video/audio + interactive browser control for AI agents | [github.com/visionik/vroom](https://github.com/visionik/vroom) |
| **TermPipe** | Terminal I/O transport (tunnel + PTY modes) — successor to SocketPipe | (this repo, `docs/app-termpipe.md`) |

## Prior Art

OpenMux evolved from [SocketPipe](https://github.com/visionik/socketpipe), originally designed for terminal I/O over WebSocket. The core framing and protocol concepts were generalized into a transport-agnostic multiplexing layer.

Related projects studied during design:
- **n.eko** — JSON over WebSocket for remote desktop control
- **Selkies-GStreamer** — CSV over WebRTC DataChannel for remote desktop
- **JetKVM** — Binary over WebRTC DataChannel for hardware KVM

## License

MIT
