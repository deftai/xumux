# xumux on TCP

**Status**: Draft
**Binding ID**: `tcp`

## Overview

This binding defines how xumux operates over a raw TCP connection. TCP is suitable for server-to-server communication, local daemon IPC, and environments where WebSocket/WebRTC overhead is unnecessary.

## Transport Requirements

- MUST use a TCP stream socket
- SHOULD use TLS for any channel carrying sensitive data
- Byte order: big-endian (network byte order) for all multi-byte fields

## Stream Framing

Unlike WebSocket (which provides message boundaries) and WebRTC DataChannels (which provide message boundaries via SCTP), TCP is a raw byte stream. xumux frames must be parsed from the stream using the Length field.

### Reading Frames

```
1. Read 6 bytes (header)
2. Parse Channel, Type, Flags, Reserved, Payload Length
3. If EXTENDED_LENGTH flag set, read 2 more bytes for 4-byte length
4. Read exactly Payload Length bytes
5. Frame complete — repeat
```

The Length field is **critical** in the TCP binding (unlike WebSocket/WebRTC where it's redundant). Implementations MUST NOT assume message boundaries.

## Channel Multiplexing

Same as WebSocket — all channels are multiplexed over the single TCP stream using the Channel byte:

```
TCP Connection
├── Channel 0: control    ─┐
├── Channel 1: data        │ interleaved byte stream
├── Channel N: ...        ─┘
```

## Connection Lifecycle

```
Client                              Server
  │                                    │
  │── TCP Connect ────────────────────►│
  │◄── TCP Accept ────────────────────│
  │                                    │
  │── [TLS Handshake if applicable] ──►│
  │                                    │
  │── HELLO (ch=0) ──────────────────►│
  │◄── WELCOME (ch=0) ───────────────│
  │                                    │
  │  ... application data ...          │
  │                                    │
  │── CLOSE (ch=0) ──────────────────►│
  │◄── CLOSE (ch=0) ─────────────────│
  │                                    │
  │── TCP FIN ────────────────────────►│
```

## Endpoint Convention

TCP servers SHOULD listen on a well-known port. Application protocols define their default ports:

| Application | Default Port |
|-------------|-------------|
| TermPipe | 2222 |
| (others) | Application-defined |

## Reliability and Ordering

Same as WebSocket — TCP guarantees reliable, ordered delivery for all channels. Head-of-line blocking applies.

## Keepalive

xumux PING/PONG on channel 0. Implementations MAY additionally use TCP keepalive (`SO_KEEPALIVE`) for transport-level dead connection detection.

## Security

- TLS provides encryption when needed
- Implementations SHOULD support both plaintext and TLS on the same port via STARTTLS or separate ports
- Authentication is carried in the HELLO message
