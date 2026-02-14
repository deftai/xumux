# OpenMux

**Transport-agnostic channel multiplexing protocol**

Version: 0.1.0-draft | Status: Draft | Date: 2026-02-14

---

## What is OpenMux?

OpenMux is an open protocol for multiplexing typed, named channels over any reliable or semi-reliable transport. It provides a standard binary framing format, channel lifecycle management, and handshake procedure that works identically whether the underlying transport is a WebRTC DataChannel, a WebSocket, a TCP socket, or a Unix pipe.

Think of it as **a universal way to run multiple logical channels over a single connection** — with each channel having its own reliability and ordering guarantees.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryColor': '#4a90d9', 'secondaryColor': '#7ab648', 'tertiaryColor': '#e8a838', 'primaryTextColor': '#000', 'lineColor': '#333'}}}%%
graph TB
    subgraph "Application Layer"
        A1["VROOM<br/>(remote desktop)"]
        A2["TermPipe<br/>(terminal I/O)"]
        A3["Your Protocol<br/>(anything)"]
    end

    subgraph "OpenMux Layer"
        OM["Framing · Channels · Handshake · Keepalive"]
    end

    subgraph "Transport Layer"
        T1["WebRTC<br/>DataChannel"]
        T2["WebSocket"]
        T3["TCP"]
        T4["stdio"]
    end

    A1 --> OM
    A2 --> OM
    A3 --> OM
    OM --> T1
    OM --> T2
    OM --> T3
    OM --> T4
```

## Design Goals

- **Transport-agnostic**: Same frame format and semantics over any transport
- **Minimal overhead**: 6-byte header for the common case, extensible when needed
- **Channel-native**: First-class support for named, typed channels with independent reliability
- **Simple to implement**: Any language, any platform, in an afternoon
- **Composable**: Application protocols build on top — OpenMux doesn't define what you send, just how you multiplex it

## Non-Goals

- Defining application-level message semantics (that's your protocol's job)
- Transport negotiation (the transport is already established when OpenMux starts)
- Encryption (the transport provides this — DTLS for WebRTC, TLS for WebSocket/TCP)

---

## Core Specification

### Frame Format

All OpenMux messages use a 6-byte header followed by an optional payload:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'primaryColor': '#909090'}}}%%
packet-beta
  0-7: "Channel (1)"
  8-15: "Type (1)"
  16-23: "Flags (1)"
  24-31: "Reserved (1)"
  32-47: "Payload Length (2)"
  48-79: "Payload (variable) ..."
```

| Offset | Field | Size | Description |
|--------|-------|------|-------------|
| 0 | Channel | 1 byte | Logical channel ID (`0x00` = control channel) |
| 1 | Type | 1 byte | Message type (scoped to channel — type `0x01` on channel 0 means HELLO, type `0x01` on channel 3 means whatever the app defines) |
| 2 | Flags | 1 byte | Bitfield (see below) |
| 3 | Reserved | 1 byte | MUST be `0x00` |
| 4 | Payload Length | 2 bytes | Big-endian. Max 65,535 bytes. |
| 6 | Payload | variable | Message-specific data |

#### Flags

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'primaryColor': '#909090'}}}%%
packet-beta
  0: "EXT"
  1: "FRG"
  2: "FIN"
  3-7: "Reserved"
```

| Bit | Name | Description |
|-----|------|-------------|
| 0 | `EXTENDED_LENGTH` | Payload Length is 4 bytes instead of 2 (header becomes 8 bytes, max ~4GB) |
| 1 | `FRAGMENT` | This message is a fragment of a larger message |
| 2 | `FRAGMENT_END` | This is the last fragment |
| 3-7 | Reserved | MUST be 0 |

**Standard frame (6 bytes header):**
```
[Channel:1][Type:1][Flags:1][Rsv:1][Length:2][Payload:0-65535]
```

**Extended frame (8 bytes header, EXTENDED_LENGTH flag set):**
```
[Channel:1][Type:1][Flags:1][Rsv:1][Length:4][Payload:0-4294967295]
```

#### Fragmentation

Messages larger than the transport's MTU (or the negotiated max message size) MUST be fragmented:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'lineColor': '#333'}}}%%
sequenceDiagram
    participant S as Sender
    participant R as Receiver

    Note over S,R: 150KB message, 64KB max
    S->>R: Frame 1 [FRAGMENT] (64KB)
    S->>R: Frame 2 [FRAGMENT] (64KB)
    S->>R: Frame 3 [FRAGMENT | FRAGMENT_END] (22KB)
    Note over R: Reassemble → 150KB message
```

All fragments MUST have the same Channel, Type, and be delivered in order on that channel. The receiver reassembles until it sees `FRAGMENT_END`.

---

### Channel 0x00: Control Channel

Channel 0 is **always** the control channel. It is implicitly open — never needs OPEN_CHANNEL. It carries all OpenMux protocol messages.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'primaryColor': '#4a90d9', 'lineColor': '#333'}}}%%
graph TD
    subgraph "Control Channel (0x00) Message Types"
        subgraph "Handshake (0x01-0x02)"
            H1["0x01 HELLO"]
            H2["0x02 WELCOME"]
        end
        subgraph "Channel Management (0x03-0x06)"
            C1["0x03 OPEN_CHANNEL"]
            C2["0x04 CHANNEL_ACK"]
            C3["0x05 CLOSE_CHANNEL"]
            C4["0x06 CHANNEL_REJECT"]
        end
        subgraph "Keepalive (0x10-0x11)"
            K1["0x10 PING"]
            K2["0x11 PONG"]
        end
        subgraph "Connection (0x20)"
            X1["0x20 CLOSE"]
        end
        subgraph "Error (0xF0)"
            E1["0xF0 ERROR"]
        end
    end
```

| Type | Name | Direction | Description |
|------|------|-----------|-------------|
| `0x01` | HELLO | C→S | Client initiates connection |
| `0x02` | WELCOME | S→C | Server accepts connection |
| `0x03` | OPEN_CHANNEL | Both | Request to open a new channel |
| `0x04` | CHANNEL_ACK | Both | Channel opened successfully |
| `0x05` | CLOSE_CHANNEL | Both | Close an existing channel |
| `0x06` | CHANNEL_REJECT | Both | Refuse a channel open request |
| `0x10` | PING | Both | Keepalive request |
| `0x11` | PONG | Both | Keepalive response |
| `0x20` | CLOSE | Both | Graceful connection close |
| `0xF0` | ERROR | Both | Error notification |

---

### Connection Lifecycle

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'noteBkgColor': '#e8e8e8', 'actorBkg': '#4a90d9', 'actorTextColor': '#fff', 'signalColor': '#333'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server

    Note over C,S: Transport already established<br/>(WebRTC DC, WebSocket, TCP, etc.)

    C->>S: HELLO (version, capabilities, requested channels)
    S->>C: WELCOME (version, capabilities, assigned channel IDs)

    Note over C,S: Initial channels now open

    loop Application Data
        C->>S: [ch=1] Application message
        S->>C: [ch=1] Application message
        C->>S: [ch=2] Application message
    end

    opt Dynamic Channel
        C->>S: OPEN_CHANNEL (name, properties)
        S->>C: CHANNEL_ACK (assigned ID)
        Note over C,S: New channel now open
    end

    opt Channel Teardown
        C->>S: CLOSE_CHANNEL (channel ID)
        Note over C,S: Channel closed, ID freed
    end

    C->>S: CLOSE (reason)
    S->>C: CLOSE (ack)
    Note over C,S: Transport closed
```

---

### Message Specifications

#### HELLO (0x01) — Client → Server

The first message after transport establishment. MUST be sent by the client. Payload is JSON (UTF-8).

```json
{
  "version": [0, 1, 0],
  "application": "vroom/0.1",
  "extensions": ["fragmentation"],
  "maxMessageSize": 65535,
  "pingInterval": 30,
  "pingTimeout": 10,
  "channels": [
    {
      "name": "control",
      "reliable": true,
      "ordered": true
    },
    {
      "name": "pointer",
      "reliable": false,
      "ordered": false,
      "maxRetransmits": 0
    },
    {
      "name": "button",
      "reliable": true,
      "ordered": true
    }
  ],
  "auth": {
    "type": "token",
    "token": "eyJhbGciOi..."
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | `[major, minor, patch]` | MUST | Protocol version. Current: `[0, 1, 0]` |
| `application` | string | SHOULD | Application protocol name and version |
| `extensions` | string[] | MAY | Requested extensions |
| `maxMessageSize` | number | MAY | Max payload bytes. Default: 65535. 0 = no limit. |
| `pingInterval` | number | MAY | Keepalive interval in seconds. Default: 30. 0 = disabled. |
| `pingTimeout` | number | MAY | Seconds to wait for PONG before disconnect. Default: 10. |
| `channels` | Channel[] | SHOULD | Channels to open during handshake |
| `auth` | object | MAY | Authentication credentials |

**Channel object:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | MUST | Channel name. Must be unique per connection. |
| `reliable` | boolean | MUST | Whether delivery is guaranteed |
| `ordered` | boolean | MUST | Whether messages arrive in order |
| `maxRetransmits` | number | MAY | Max retransmission attempts (0 = fire-and-forget) |
| `maxPacketLifeTime` | number | MAY | Max milliseconds to attempt delivery |
| `metadata` | object | MAY | Application-specific channel metadata |

#### WELCOME (0x02) — Server → Client

Sent in response to HELLO. Payload is JSON (UTF-8).

```json
{
  "version": [0, 1, 0],
  "extensions": ["fragmentation"],
  "maxMessageSize": 65535,
  "pingInterval": 30,
  "pingTimeout": 10,
  "channels": [
    {"name": "control", "id": 0},
    {"name": "pointer", "id": 1},
    {"name": "button", "id": 2}
  ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | `[major, minor, patch]` | MUST | Server's protocol version |
| `extensions` | string[] | MAY | Accepted extensions (intersection of client request) |
| `maxMessageSize` | number | MAY | Negotiated max message size (min of both sides) |
| `pingInterval` | number | MAY | Negotiated ping interval |
| `pingTimeout` | number | MAY | Negotiated ping timeout |
| `channels` | AssignedChannel[] | MUST | Channels with assigned numeric IDs |

**AssignedChannel object:**

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Channel name (matches request) |
| `id` | number | Assigned channel ID (1-254). Used in frame Channel byte. |

**Channel ID 0** is always the control channel. Server assigns IDs 1-254 to application channels. ID 255 is reserved.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'lineColor': '#333'}}}%%
graph LR
    subgraph "Channel ID Space"
        C0["0x00<br/>Control<br/>(reserved)"]
        C1["0x01-0xFE<br/>Application<br/>(assigned by server)"]
        C2["0xFF<br/>Reserved"]
    end

    style C0 fill:#4a90d9,color:#fff
    style C1 fill:#7ab648,color:#fff
    style C2 fill:#999,color:#fff
```

#### OPEN_CHANNEL (0x03) — Bidirectional

Dynamically open a new channel after the handshake. Sent on channel 0. Payload is JSON (UTF-8).

```json
{
  "requestId": 1,
  "name": "file-transfer",
  "reliable": true,
  "ordered": true,
  "metadata": {
    "direction": "upload",
    "filename": "document.pdf"
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `requestId` | number | MUST | Unique request ID for correlating with ACK/REJECT |
| `name` | string | MUST | Channel name. Must be unique per connection. |
| `reliable` | boolean | MUST | Delivery guarantee |
| `ordered` | boolean | MUST | Ordering guarantee |
| `maxRetransmits` | number | MAY | Max retransmit attempts |
| `maxPacketLifeTime` | number | MAY | Max delivery time in ms |
| `metadata` | object | MAY | Application-specific metadata |

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'lineColor': '#333'}}}%%
sequenceDiagram
    participant A as Side A
    participant B as Side B

    A->>B: OPEN_CHANNEL {requestId: 1, name: "file-transfer", ...}

    alt Accepted
        B->>A: CHANNEL_ACK {requestId: 1, id: 4}
        Note over A,B: Channel 4 ("file-transfer") now open
    else Rejected
        B->>A: CHANNEL_REJECT {requestId: 1, code: 403, reason: "not authorized"}
        Note over A,B: Channel not opened
    end
```

#### CHANNEL_ACK (0x04) — Bidirectional

Confirms a channel was opened. Sent on channel 0. Payload is JSON (UTF-8).

```json
{
  "requestId": 1,
  "id": 4,
  "name": "file-transfer"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `requestId` | number | MUST | Matches the OPEN_CHANNEL requestId |
| `id` | number | MUST | Assigned channel ID (1-254) |
| `name` | string | MUST | Channel name (echoed back for clarity) |

After CHANNEL_ACK, both sides MAY immediately send messages on the new channel ID.

#### CHANNEL_REJECT (0x06) — Bidirectional

Refuses a channel open request. Sent on channel 0. Payload is JSON (UTF-8).

```json
{
  "requestId": 1,
  "code": 403,
  "reason": "Channel type not supported"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `requestId` | number | MUST | Matches the OPEN_CHANNEL requestId |
| `code` | number | MUST | Error code (see Error Codes) |
| `reason` | string | SHOULD | Human-readable reason |

#### CLOSE_CHANNEL (0x05) — Bidirectional

Close an existing channel. Sent on channel 0. Payload is JSON (UTF-8).

```json
{
  "id": 4,
  "reason": "transfer complete"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | number | MUST | Channel ID to close |
| `reason` | string | MAY | Human-readable reason |

After CLOSE_CHANNEL, the channel ID is **freed** and MAY be reused for future OPEN_CHANNEL requests. Both sides MUST stop sending on the channel immediately. Any in-flight messages on the closed channel SHOULD be discarded.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'lineColor': '#333'}}}%%
stateDiagram-v2
    [*] --> Requested: OPEN_CHANNEL sent
    Requested --> Open: CHANNEL_ACK received
    Requested --> [*]: CHANNEL_REJECT received
    Open --> Closing: CLOSE_CHANNEL sent
    Open --> Closing: CLOSE_CHANNEL received
    Closing --> [*]: Channel freed
```

#### PING (0x10) — Bidirectional

Keepalive probe. Sent on channel 0. Payload:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'primaryColor': '#909090'}}}%%
packet-beta
  0-31: "Timestamp (4 bytes, ms since epoch, big-endian)"
```

| Field | Size | Description |
|-------|------|-------------|
| Timestamp | 4 bytes | Milliseconds since connection established (big-endian, wraps at ~49 days) |

The receiver MUST respond with PONG containing the same timestamp.

#### PONG (0x11) — Bidirectional

Keepalive response. Sent on channel 0. Payload:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'primaryColor': '#909090'}}}%%
packet-beta
  0-31: "Echo Timestamp (4 bytes)"
  32-63: "Receiver Timestamp (4 bytes)"
```

| Field | Size | Description |
|-------|------|-------------|
| Echo Timestamp | 4 bytes | Copied from PING |
| Receiver Timestamp | 4 bytes | Receiver's current timestamp |

This allows both sides to compute round-trip time: `RTT = local_now - echo_timestamp`.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'lineColor': '#333'}}}%%
sequenceDiagram
    participant C as Client (t=1000ms)
    participant S as Server

    C->>S: PING [ts=1000]
    Note over S: Receives at server_t=500
    S->>C: PONG [echo=1000, server_ts=500]
    Note over C: Receives at t=1045<br/>RTT = 1045 - 1000 = 45ms
```

#### CLOSE (0x20) — Bidirectional

Graceful connection close. Sent on channel 0. Payload is JSON (UTF-8).

```json
{
  "code": 1000,
  "reason": "session ended"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | number | MUST | Close code (see Close Codes) |
| `reason` | string | MAY | Human-readable reason |

The side that receives CLOSE SHOULD respond with its own CLOSE (ack), then both sides close the transport.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'lineColor': '#333'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server

    C->>S: CLOSE {code: 1000, reason: "done"}
    Note over S: Stop sending, flush buffers
    S->>C: CLOSE {code: 1000, reason: "ack"}
    Note over C,S: Transport closed
```

#### ERROR (0xF0) — Bidirectional

Non-fatal error notification. Sent on channel 0. Payload is JSON (UTF-8).

```json
{
  "code": 4001,
  "channel": 3,
  "reason": "Invalid message type 0x99 on channel 3"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | number | MUST | Error code |
| `channel` | number | MAY | Channel the error relates to (omit for connection-level errors) |
| `reason` | string | SHOULD | Human-readable description |

Errors are informational — they do NOT close the connection or channel unless paired with a CLOSE or CLOSE_CHANNEL.

---

### Error Codes

| Code | Name | Description |
|------|------|-------------|
| 1000 | NORMAL | Normal closure |
| 1001 | GOING_AWAY | Endpoint shutting down |
| 1002 | PROTOCOL_ERROR | Protocol violation |
| 1003 | UNSUPPORTED | Unsupported message type or feature |
| 4000 | AUTH_FAILED | Authentication failed |
| 4001 | INVALID_MESSAGE | Malformed message |
| 4002 | CHANNEL_FULL | Max channels (254) reached |
| 4003 | CHANNEL_NOT_FOUND | Message on unknown channel ID |
| 4004 | RATE_LIMITED | Too many messages |
| 4005 | MESSAGE_TOO_LARGE | Payload exceeds negotiated max |
| 4100-4999 | Application-defined | Reserved for application protocols |

---

### Negotiation

Parameters are negotiated during HELLO/WELCOME:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'lineColor': '#333'}}}%%
graph TD
    subgraph "Client HELLO"
        CH1["maxMessageSize: 65535"]
        CH2["pingInterval: 30"]
        CH3["extensions: [frag, compress]"]
    end

    subgraph "Server WELCOME"
        SW1["maxMessageSize: 32768"]
        SW2["pingInterval: 30"]
        SW3["extensions: [frag]"]
    end

    subgraph "Effective Values"
        EV1["maxMessageSize: 32768<br/>(min of both)"]
        EV2["pingInterval: 30<br/>(server decides)"]
        EV3["extensions: [frag]<br/>(intersection)"]
    end

    CH1 --> EV1
    SW1 --> EV1
    CH2 --> EV2
    SW2 --> EV2
    CH3 --> EV3
    SW3 --> EV3
```

| Parameter | Negotiation Rule |
|-----------|-----------------|
| `maxMessageSize` | Minimum of both values |
| `pingInterval` | Server's value wins |
| `pingTimeout` | Server's value wins |
| `extensions` | Intersection of both sets |

---

### Transport Mapping

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000', 'lineColor': '#333'}}}%%
graph TB
    subgraph "WebRTC DataChannels"
        direction TB
        DC1["omux/control<br/>(DataChannel)"]
        DC2["omux/pointer<br/>(DataChannel)"]
        DC3["omux/button<br/>(DataChannel)"]
        Note1["1:1 mapping<br/>Each OpenMux channel = one DataChannel<br/>Native reliability per channel"]
    end

    subgraph "WebSocket / TCP / stdio"
        direction TB
        WS["Single stream"]
        MX["All channels multiplexed<br/>via Channel byte in header"]
        Note2["Channel byte is critical<br/>Receiver demuxes by Channel ID"]
    end
```

When the transport natively supports multiple channels (WebRTC DataChannels), OpenMux channels MAY map 1:1 to transport channels. Each DataChannel is labeled `omux/<channel-name>`. The Channel byte in the frame header is redundant but MUST still be present for format consistency and gateway bridging.

When the transport is a single stream (WebSocket, TCP, stdio), all channels are multiplexed over that stream using the Channel byte.

---

## Transport Bindings

| Transport | Specification | Primary/Fallback |
|-----------|---------------|-----------------|
| QUIC / WebTransport | [openmux-on-quic.md](docs/openmux-on-quic.md) | **Optimal** (when available) |
| WebRTC DataChannel | [openmux-on-webrtc.md](docs/openmux-on-webrtc.md) | **Primary** (universal browser support) |
| WebSocket | [openmux-on-websocket.md](docs/openmux-on-websocket.md) | Fallback |
| TCP | [openmux-on-tcp.md](docs/openmux-on-tcp.md) | Server-to-server |
| stdio | [openmux-on-stdio.md](docs/openmux-on-stdio.md) | Process IPC |

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
