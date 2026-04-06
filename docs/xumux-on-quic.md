# xumux on QUIC / WebTransport

**Status**: Draft
**Binding ID**: `quic`

## Overview

This binding defines how xumux operates over QUIC streams, accessed via the **WebTransport** API in browsers or native QUIC libraries server-side. QUIC is the **optimal transport** for xumux — it provides UDP-based delivery, native multiplexed streams with independent flow control, built-in TLS 1.3 encryption, 0-RTT connection resumption, and no head-of-line blocking across streams.

WebTransport is the browser API that exposes QUIC streams and datagrams to JavaScript. This binding covers both native QUIC (server-to-server, CLI) and WebTransport (browser clients).

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TB
    subgraph "Browser Client"
        WT["WebTransport API"]
    end

    subgraph "Native Client"
        NQ["QUIC library<br/>(quinn, quiche, etc.)"]
    end

    subgraph "Server"
        S["QUIC endpoint"]
    end

    WT -->|"QUIC (UDP)"| S
    NQ -->|"QUIC (UDP)"| S
```

## Why QUIC?

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph LR
    subgraph "WebRTC DataChannel"
        W1["ICE negotiation ⏱️"]
        W2["STUN/TURN required"]
        W3["DTLS + SCTP"]
        W4["Complex setup"]
    end

    subgraph "QUIC / WebTransport"
        Q1["Direct connect 🚀"]
        Q2["No STUN/TURN"]
        Q3["TLS 1.3 built-in"]
        Q4["0-RTT resumption"]
    end
```

| Feature | WebRTC DC | QUIC/WebTransport | TCP/WebSocket |
|---------|-----------|-------------------|---------------|
| Transport | UDP (via SCTP) | UDP (native) | TCP |
| Encryption | DTLS | TLS 1.3 | TLS 1.2/1.3 |
| Setup latency | High (ICE+DTLS+SCTP) | 1-RTT (0-RTT on resume) | 1-RTT (TCP) + 1-RTT (TLS) |
| Stream multiplexing | Per-DataChannel | Per-stream (native) | None (single stream) |
| Head-of-line blocking | No (per-DC) | No (per-stream) | **Yes** (all channels) |
| NAT traversal | ICE/STUN/TURN | Direct (HTTP/3 ports) | Direct |
| Unreliable delivery | maxRetransmits=0 | Datagrams | Not possible |
| Connection migration | No | **Yes** (IP change survives) | No |
| 0-RTT resumption | No | **Yes** | No (TLS 1.3 partial) |
| Browser support | Universal | Chrome, Edge (Safari/Firefox WIP) | Universal |

## Architecture

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TB
    subgraph "QUIC Connection"
        direction TB

        subgraph "Bidirectional Streams (reliable, ordered)"
            S0["Stream 0: omux/control"]
            S1["Stream 1: omux/button"]
            S2["Stream 2: (dynamic channels)"]
        end

        subgraph "Datagrams (unreliable, unordered)"
            D1["omux/pointer events"]
        end
    end

    C["Client"] <--> S0
    C <--> S1
    C <--> S2
    C <-.-> D1
```

### Channel Mapping

QUIC provides two primitives that map perfectly to xumux:

| xumux Channel Property | QUIC Primitive | Mapping |
|--------------------------|---------------|---------|
| Reliable + Ordered | **Bidirectional Stream** | 1:1 — each channel gets its own QUIC stream |
| Unreliable + Unordered | **Datagram** | Channel byte in header disambiguates |

This is cleaner than WebRTC DataChannels because QUIC streams are lightweight (just a stream ID, no negotiation) and can be created/destroyed instantly.

### Stream Creation Rules

**Who opens which streams:**

1. The **client** opens the first bidirectional stream (stream 0) and sends HELLO on it. This is always the control channel.
2. After processing HELLO, the **server** opens bidirectional streams for each accepted reliable channel and includes `streamId` in WELCOME.
3. For dynamic channels (OPEN_CHANNEL after handshake), the **requesting side** opens the new QUIC stream, then sends OPEN_CHANNEL on the control stream. CHANNEL_ACK confirms with the `streamId`.

**Stream identification:** Before WELCOME is processed, the receiver cannot know which stream corresponds to which channel. Therefore:
- Stream 0 is **always** the control channel (by convention, like WebRTC's negotiated DataChannel ID 0).
- All other streams MUST include the correct Channel byte in the xumux frame header. The receiver uses the Channel byte to identify the channel, cross-referencing with the `streamId` mappings from WELCOME.
- If a frame arrives on an unknown stream with an unknown Channel byte, the receiver MUST send ERROR (code 4003, CHANNEL_NOT_FOUND) on the control stream.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TD
    subgraph "xumux Channel Types"
        R["Reliable + Ordered<br/>(control, button, data)"]
        U["Unreliable + Unordered<br/>(pointer, sensor data)"]
    end

    subgraph "QUIC Primitives"
        BS["Bidirectional Stream<br/>per-stream flow control<br/>per-stream ordering<br/>lightweight creation"]
        DG["Datagram<br/>fire-and-forget<br/>no ordering<br/>size-limited"]
    end

    R --> BS
    U --> DG
```

## Connection Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'actorLineColor': '#404040', 'signalColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'noteBkgColor': '#909090'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server

    Note over C,S: 1. QUIC handshake (1-RTT, or 0-RTT on resume)
    C->>S: QUIC ClientHello + TLS 1.3
    S->>C: QUIC ServerHello + TLS 1.3
    Note over C,S: Connection established, encrypted

    Note over C,S: 2. Open control stream
    C->>S: Open bidirectional stream 0
    C->>S: [stream 0] HELLO {version, channels, ...}
    S->>C: [stream 0] WELCOME {channels: [{name: "control", id: 0, streamId: 0}, ...]}

    Note over C,S: 3. Server opens additional streams per channel
    S->>C: Open bidirectional stream 2 → omux/button (id: 2)

    Note over C,S: 4. Application data flows
    C->>S: [stream 0] Control messages (JSON)
    C->>S: [stream 2] Button events (binary)
    C-->>S: [datagram] Pointer events (binary)

    Note over C,S: 5. Dynamic channel
    C->>S: [stream 0] OPEN_CHANNEL {name: "file-xfer"}
    S->>C: [stream 0] CHANNEL_ACK {id: 4, streamId: 4}
    Note over C,S: Stream 4 now carries file-xfer data

    Note over C,S: 6. Close
    C->>S: [stream 0] CLOSE
    S->>C: [stream 0] CLOSE
    Note over C,S: QUIC connection closed
```

### 0-RTT Connection Resumption

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'actorLineColor': '#404040', 'signalColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'noteBkgColor': '#909090'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server

    Note over C,S: First connection (1-RTT)
    C->>S: ClientHello
    S->>C: ServerHello + session ticket
    Note over C: Stores session ticket

    Note over C,S: Reconnection (0-RTT) ⚡
    C->>S: ClientHello + early data + HELLO
    Note over S: Validates ticket, processes HELLO immediately
    S->>C: ServerHello + WELCOME
    Note over C,S: Data flowing with ZERO round trips of setup latency
```

0-RTT is particularly valuable for VROOM-Graphical — reconnecting after a network glitch resumes the interactive session instantly.

**Security note**: 0-RTT data is replayable. xumux HELLO is idempotent, so this is safe. Application protocols MUST NOT send non-idempotent data in 0-RTT.

## WebTransport API Mapping

For browser clients using the WebTransport API:

```javascript
// Connect
const transport = new WebTransport("https://agent.example.com:4433/vroom");
await transport.ready;

// Control channel → bidirectional stream
const controlStream = await transport.createBidirectionalStream();
const controlWriter = controlStream.writable.getWriter();
const controlReader = controlStream.readable.getReader();

// Send HELLO on control stream
controlWriter.write(encodexumuxFrame(0, 0x01, helloPayload));

// Button channel → another bidirectional stream
const buttonStream = await transport.createBidirectionalStream();
const buttonWriter = buttonStream.writable.getWriter();

// Pointer channel → datagrams (unreliable)
const datagramWriter = transport.datagrams.writable.getWriter();
const datagramReader = transport.datagrams.readable.getReader();

// Send mouse move via datagram
datagramWriter.write(encodexumuxFrame(1, 0x01, mousePayload));

// Send key press via reliable stream
buttonWriter.write(encodexumuxFrame(2, 0x12, keyPayload));
```

### WebTransport ↔ xumux Mapping

| WebTransport Concept | xumux Concept |
|---------------------|-----------------|
| `createBidirectionalStream()` | Open reliable+ordered channel |
| `datagrams.writable` | Send on unreliable+unordered channel |
| `datagrams.readable` | Receive unreliable+unordered messages |
| Stream close | CLOSE_CHANNEL |
| `transport.close()` | CLOSE |
| Session ticket / 0-RTT | Reconnection (no xumux equivalent needed) |

## Frame Format

### On Streams (reliable channels)

Same as core xumux. Since QUIC streams are byte streams (like TCP), frames must be parsed using the Length field:

```
[Channel: 1][Type: 1][Flags: 1][Reserved: 1][Length: 2][Payload: variable]
```

Each QUIC stream carries one xumux channel. The Channel byte is redundant (the stream identity determines the channel) but MUST be present for cross-transport compatibility.

**Stream framing note**: Unlike WebSocket/DataChannel (which provide message boundaries), QUIC streams are byte streams. Implementations MUST parse frames by reading the 6-byte header, then reading exactly `Length` bytes of payload — identical to the TCP binding.

However, WebTransport's `readable`/`writable` streams in browsers operate on `Uint8Array` chunks, not raw bytes. Implementations SHOULD write one complete xumux frame per `write()` call and handle partial reads on the receive side.

### On Datagrams (unreliable channels)

QUIC datagrams are self-contained — each datagram is one complete message. The frame format is the same, but:

- Length field is redundant (datagram size is known) — MUST still be present
- EXTENDED_LENGTH MUST NOT be used (datagrams have a max size, typically ~1200 bytes)
- FRAGMENT flags MUST NOT be used (datagrams cannot be reassembled reliably)

```
One QUIC datagram = one xumux frame = one pointer/sensor event
```

Datagram max size depends on the QUIC path MTU. The server advertises `max_datagram_frame_size` during handshake. xumux pointer events are 10 bytes total (6 header + 4 payload), well within any MTU.

## Channel-to-Stream Assignment

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TD
    subgraph "WELCOME Response"
        W["channels: [<br/>  {name: 'control', id: 0, streamId: 0},<br/>  {name: 'pointer', id: 1, transport: 'datagram'},<br/>  {name: 'button', id: 2, streamId: 2}<br/>]"]
    end

    subgraph "QUIC Primitives"
        S0["Stream 0 → control"]
        S2["Stream 2 → button"]
        DG["Datagrams → pointer<br/>(Channel byte = 1)"]
    end

    W --> S0
    W --> S2
    W --> DG
```

The WELCOME message in the QUIC binding adds two optional fields to each channel assignment:

| Field | Type | Description |
|-------|------|-------------|
| `streamId` | number | QUIC stream ID for this channel (reliable channels) |
| `transport` | `"stream"` \| `"datagram"` | Which QUIC primitive. Default: `"stream"` |

Channels with `"transport": "datagram"` share the datagram pipe and are disambiguated by the Channel byte in the xumux header.

## Dynamic Channels

Creating a new channel is simpler on QUIC than any other transport:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'actorLineColor': '#404040', 'signalColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'noteBkgColor': '#909090'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server

    C->>S: [stream 0] OPEN_CHANNEL {requestId: 1, name: "screen-share", reliable: true}
    Note over S: Opens new QUIC bidirectional stream
    S->>C: [stream 0] CHANNEL_ACK {requestId: 1, id: 5, streamId: 6}
    Note over C,S: Stream 6 now carries "screen-share"<br/>Instantly available, no negotiation

    Note over C,S: Later...
    C->>S: [stream 0] CLOSE_CHANNEL {id: 5}
    Note over S: Closes QUIC stream 6
    Note over C,S: Stream freed, channel ID freed
```

QUIC streams are cheap — creating one is just sending a frame with a new stream ID. No round-trip negotiation at the transport level. The OPEN_CHANNEL/CHANNEL_ACK round-trip is purely at the xumux level for both sides to agree on the channel semantics.

## Connection Migration

QUIC supports connection migration — if the client's IP address changes (e.g., switching from WiFi to cellular), the QUIC connection survives. This is transparent to xumux.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'actorLineColor': '#404040', 'signalColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'noteBkgColor': '#909090'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server

    Note over C: IP: 192.168.1.50
    C->>S: [pointer] MOUSE_MOVE x=100 y=200
    C->>S: [button] KEY_DOWN key="a"

    Note over C: WiFi → Cellular<br/>IP: 10.0.0.42
    Note over C,S: QUIC connection migrates automatically<br/>No reconnection, no re-handshake

    C->>S: [pointer] MOUSE_MOVE x=150 y=250
    Note over S: Same connection, new path
```

This is impossible with WebRTC DataChannels (requires ICE restart) and TCP/WebSocket (requires full reconnection + re-handshake).

## Endpoint Convention

WebTransport URLs use HTTPS:

```
https://host:port/omux
https://host:port/vroom
```

Default port: **4433** (common WebTransport convention) or **443** (shared with HTTPS).

WebTransport requires a valid TLS certificate (self-signed certificates can be allowed via `serverCertificateHashes` in the browser API).

## Server Requirements

- MUST support HTTP/3 (QUIC)
- MUST support WebTransport protocol negotiation
- MUST support bidirectional streams
- SHOULD support datagrams (for unreliable channels)
- If datagrams are not supported, unreliable channels fall back to streams (with a warning that ordering/reliability semantics change)
- MUST advertise supported xumux channels in WELCOME with stream/datagram assignments

## Client Requirements

- Browser clients MUST use the WebTransport API
- Native clients MAY use any QUIC library (quinn/Rust, quiche/C, aioquic/Python)
- Clients MUST handle datagram unavailability gracefully (fall back to streams)
- Clients SHOULD implement 0-RTT for fast reconnection

## Fallback Chain

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TD
    A{QUIC/WebTransport<br/>available?}
    A -->|Yes| Q["✅ QUIC<br/>Best performance"]
    A -->|No| B{WebRTC<br/>available?}
    B -->|Yes| W["✅ WebRTC DataChannels<br/>Universal browser support"]
    B -->|No| C["✅ WebSocket<br/>Works everywhere"]

    style Q fill:#909090,color:#000000
    style W fill:#808080,color:#000000
    style C fill:#707070,color:#000000
```

Recommended client behavior:
1. Try QUIC/WebTransport first (fastest setup, best performance)
2. Fall back to WebRTC DataChannels (universal browser support, NAT traversal)
3. Fall back to WebSocket (works through any proxy/firewall)

Timeout per attempt: **5 seconds** before trying next option.

## Security

- TLS 1.3 is mandatory in QUIC (encryption is not optional)
- Certificate validation follows standard HTTPS rules
- 0-RTT data is replayable — only idempotent messages (HELLO) should be sent in 0-RTT
- QUIC has built-in amplification attack mitigation (address validation)
- No additional encryption layer is needed

## Comparison: QUIC vs WebRTC for VROOM-Graphical

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph LR
    subgraph "WebRTC (today)"
        direction TB
        R1["1. HTTP POST /offer"]
        R2["2. SDP exchange"]
        R3["3. ICE gathering"]
        R4["4. STUN/TURN"]
        R5["5. DTLS handshake"]
        R6["6. SCTP association"]
        R7["7. DataChannel open"]
        R8["8. xumux HELLO"]
        R1 --> R2 --> R3 --> R4 --> R5 --> R6 --> R7 --> R8
    end

    subgraph "QUIC (future)"
        direction TB
        Q1["1. QUIC ClientHello"]
        Q2["2. TLS 1.3 done"]
        Q3["3. Stream 0 open"]
        Q4["4. xumux HELLO"]
        Q1 --> Q2 --> Q3 --> Q4
    end
```

| Metric | WebRTC | QUIC |
|--------|--------|------|
| Setup round-trips | 3-5 | 1 (0 on resume) |
| Infrastructure needed | STUN + TURN servers | Just a server with a port |
| Connection migration | ICE restart (seconds) | Transparent (zero) |
| Stream creation cost | DataChannel negotiation | Just a new stream ID |
| Max concurrent streams | ~65535 DataChannels | ~2^62 streams |
| Datagram support | maxRetransmits=0 (hack) | Native QUIC datagrams |

**Bottom line**: QUIC is strictly superior. WebRTC remains the pragmatic choice today for browser reach. The xumux abstraction means applications don't need to change when migrating between them.
