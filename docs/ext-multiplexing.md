# SocketPipe Extension: Multiplexing

**Status**: Draft  
**Extension ID**: `multiplexing`  
**Depends on**: Core Protocol v1.0

## Overview

Multiplexing enables multiple logical sessions over a single WebSocket connection. This reduces connection overhead, simplifies firewall traversal, and enables coordinated multi-terminal workflows.

## Use Cases

- IDE with multiple terminal panes
- Split-screen terminal applications
- Reduced connection count for better performance
- Coordinated command execution across multiple shells

## Architecture

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph LR
    subgraph "Client"
        T1[Terminal 1]
        T2[Terminal 2]
        T3[Terminal 3]
    end
    
    subgraph "Single WebSocket"
        MUX[Multiplexer]
    end
    
    subgraph "Server"
        D[Demultiplexer]
        S1[Session 1]
        S2[Session 2]
        S3[Session 3]
    end
    
    T1 --> MUX
    T2 --> MUX
    T3 --> MUX
    MUX -->|"One Connection"| D
    D --> S1
    D --> S2
    D --> S3
```

## Protocol Changes

### Capability Negotiation

**Flags** (byte 1 of header):
- Bit 3: `1` = Multiplexing supported

### Channel IDs

All messages include a channel ID when multiplexing is active:

**Extended Header** (when multiplexing enabled):

```
[Type: 1][Flags: 1][Channel ID: 2][Length: 4][Payload: variable]
```

The Reserved field becomes Channel ID:
- Channel 0: Control channel (connection-level messages)
- Channels 1-65534: Data channels
- Channel 65535: Reserved

### New Message Types

| Type | Name | Direction | Description |
| --- | --- | --- | --- |
| `0x70` | CHANNEL_OPEN | C→S | Request new channel |
| `0x71` | CHANNEL_OPEN_ACK | S→C | Channel opened successfully |
| `0x72` | CHANNEL_CLOSE | Both | Close specific channel |
| `0x73` | CHANNEL_CLOSE_ACK | Both | Acknowledge channel close |

### CHANNEL_OPEN (0x70)

Sent on Channel 0 to request a new channel.

**Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Requested Channel ID | 2 bytes | Preferred channel ID (0 = server assigns) |
| Mode | 1 byte | 0 = tunnel, 1 = pty |
| Target Port | 2 bytes | Backend port |
| Host Length | 1 byte | Length of hostname |
| Target Host | variable | Hostname or IP |

### CHANNEL_OPEN_ACK (0x71)

**Flags**:
- Bit 0: `1` = Success, `0` = Failure

**Success Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Assigned Channel ID | 2 bytes | Channel ID to use |

**Failure Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Error Code | 2 bytes | Error code |
| Message Length | 1 byte | Length of message |
| Message | variable | Error description |

### CHANNEL_CLOSE (0x72)

**Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Reason Code | 2 bytes | Close reason |

### CHANNEL_CLOSE_ACK (0x73)

**Payload**: Empty

## Connection Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server

    C->>S: HANDSHAKE_REQUEST (mux flag)
    S-->>C: HANDSHAKE_RESPONSE (mux flag)
    
    Note over C,S: Open first channel
    C->>S: CHANNEL_OPEN (ch=0→1, pty, host:22)
    S-->>C: CHANNEL_OPEN_ACK (ch=1)
    
    Note over C,S: Open second channel
    C->>S: CHANNEL_OPEN (ch=0→2, pty, host:22)
    S-->>C: CHANNEL_OPEN_ACK (ch=2)
    
    Note over C,S: Data flows on respective channels
    C->>S: DATA (ch=1, "ls\n")
    C->>S: DATA (ch=2, "pwd\n")
    S-->>C: DATA (ch=1, output)
    S-->>C: DATA (ch=2, output)
    
    Note over C,S: Control messages stay on ch=0
    C->>S: PING (ch=0)
    S-->>C: PONG (ch=0)
    
    Note over C,S: Close one channel
    C->>S: CHANNEL_CLOSE (ch=2)
    S-->>C: CHANNEL_CLOSE_ACK (ch=2)
    
    Note over C,S: Channel 1 continues
    C->>S: DATA (ch=1, "exit\n")
```

## Channel Lifecycle

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#808080', 'secondaryColor': '#909090', 'tertiaryColor': '#707070', 'stateLabelColor': '#000000', 'compositeBackground': '#a0a0a0', 'lineColor': '#404040'}}}%%
stateDiagram-v2
    [*] --> OPENING: CHANNEL_OPEN
    OPENING --> OPEN: CHANNEL_OPEN_ACK (success)
    OPENING --> CLOSED: CHANNEL_OPEN_ACK (failure)
    OPEN --> CLOSING: CHANNEL_CLOSE sent
    OPEN --> CLOSED: CHANNEL_CLOSE received
    CLOSING --> CLOSED: CHANNEL_CLOSE_ACK
    CLOSED --> [*]
```

## Message Routing

| Message Type | Channel | Notes |
| --- | --- | --- |
| HANDSHAKE_* | N/A | Before multiplexing active |
| CHANNEL_OPEN | 0 | Always control channel |
| CHANNEL_OPEN_ACK | 0 | Always control channel |
| CHANNEL_CLOSE | Target | Channel being closed |
| PING/PONG | 0 | Connection-level keepalive |
| DATA | 1-65534 | Per-channel data |
| RESIZE | 1-65534 | Per-channel (PTY mode) |
| ERROR | 0 or target | 0 for connection, target for channel |

## Flow Control

Per-channel flow control (optional):

| Type | Name | Direction | Description |
| --- | --- | --- | --- |
| `0x74` | CHANNEL_WINDOW_UPDATE | Both | Increase receive window |

**Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Window Increment | 4 bytes | Bytes to add to window |

Initial window: 64KB per channel (negotiable).

## Server Requirements

- MUST support at least 16 concurrent channels per connection
- SHOULD support at least 256 channels
- MUST handle channel-specific errors without affecting other channels
- MUST close all channels on connection close

## Client Requirements

- MUST track channel state independently
- MUST route messages to correct channel handlers
- SHOULD implement channel-level flow control for high-throughput scenarios

## Error Codes

| Code | Name | Description |
| --- | --- | --- |
| 5000 | CHANNEL_LIMIT | Maximum channels exceeded |
| 5001 | INVALID_CHANNEL | Unknown channel ID |
| 5002 | CHANNEL_REFUSED | Server refused channel (auth, policy) |
