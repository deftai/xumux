# xumux on WebSocket

**Status**: Draft
**Binding ID**: `websocket`

## Overview

This binding defines how xumux operates over a single WebSocket connection. WebSocket serves as the **fallback transport** when WebRTC is unavailable, and as a viable primary transport when low-latency UDP delivery isn't required (e.g., terminal I/O, control-plane-only applications).

## Transport Requirements

- MUST use binary WebSocket frames (opcode 0x02)
- MUST use `wss://` (TLS) for any channel carrying sensitive data
- MAY use `ws://` when the channel data is already encrypted (e.g., SSH tunnel mode)
- Byte order: big-endian (network byte order) for all multi-byte fields

## Channel Multiplexing

Since WebSocket is a single bidirectional stream, **all xumux channels are multiplexed** over that one connection using the Channel byte in the frame header.

```
WebSocket Connection
├── Channel 0: control    ─┐
├── Channel 1: data        │ all interleaved in
├── Channel 2: events      │ one byte stream
└── Channel N: ...        ─┘
```

Each WebSocket binary message MUST contain exactly one complete xumux frame. Do not pack multiple frames into one WebSocket message, and do not split one frame across multiple WebSocket messages.

## Frame Format

Identical to core xumux:

```
[Channel: 1][Type: 1][Flags: 1][Reserved: 1][Length: 2][Payload: variable]
```

WebSocket framing already provides message boundaries, so the Length field is technically redundant but MUST be present for cross-transport compatibility and validation.

## Connection Lifecycle

```
Client                              Server
  │                                    │
  │── WebSocket Connect ──────────────►│
  │◄── WebSocket Accept ──────────────│
  │                                    │
  │── HELLO (ch=0, type=0x01) ────────►│
  │◄── WELCOME (ch=0, type=0x02) ─────│
  │                                    │
  │  ... application data on ch 1-N ...│
  │                                    │
  │── CLOSE (ch=0, type=0x20) ────────►│
  │◄── CLOSE (ch=0, type=0x20) ───────│
  │                                    │
  │── WebSocket Close ────────────────►│
```

## Endpoint Convention

Implementations SHOULD expose xumux WebSocket endpoints at:

```
wss://host/omux
```

Application protocols MAY define sub-paths:

```
wss://host/omux/termpipe
wss://host/omux/vroom
```

## Reliability and Ordering

WebSocket over TCP guarantees reliable, ordered delivery for **all** channels. This means:

- Channels declared as `unreliable` in the HELLO will still be delivered reliably
- Channels declared as `unordered` will still arrive in order
- This is a known limitation of the WebSocket binding vs WebRTC

Applications that depend on unreliable/unordered semantics (e.g., discarding stale mouse positions) must implement this logic at the application layer when running over WebSocket.

## Keepalive

xumux PING/PONG messages (on channel 0) operate at the application level, independent of WebSocket ping/pong frames. Implementations MAY additionally use WebSocket-level ping/pong for transport-level keepalive.

## Head-of-Line Blocking

TCP's head-of-line blocking means a lost packet delays all channels, not just the one the packet belonged to. This is the primary reason WebRTC DataChannels are preferred — SCTP provides per-stream ordering.

For latency-sensitive applications, prefer the WebRTC binding.

## Security

- `wss://` provides TLS encryption
- Authentication is carried in the HELLO message or via HTTP headers during the WebSocket upgrade
- No additional encryption layer is needed when using `wss://`
