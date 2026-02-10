# SocketPipe Protocol Specification

**Version**: 1.0.0-draft  
**Status**: Draft  
**Date**: 2026-02-09

SocketPipe is an open protocol for transporting terminal I/O between web-based clients and backend services over WebSocket connections.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Transport](#transport)
- [Protocol](#protocol)
  - [Frame Format](#frame-format)
  - [Message Types](#message-types)
  - [Handshake](#handshake)
  - [Data Transfer](#data-transfer)
  - [Control Messages](#control-messages)
  - [Keepalive](#keepalive)
  - [Session Management](#session-management)
  - [Error Handling](#error-handling)
- [Security](#security)
- [Examples](#examples)
- [Future Extensions](#future-extensions)

---

## Overview

SocketPipe standardizes how web-based terminal clients (such as xterm.js or ghostty-wasm) communicate with backend services through proxy servers. It supports two operational modes:

- **Tunnel Mode**: Raw TCP passthrough for already-encrypted protocols (e.g., SSH)
- **PTY Mode**: Terminated connections with plaintext terminal I/O

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph LR
    subgraph "Browser"
        C[Web Terminal Client]
    end
    
    subgraph "Proxy Server"
        P[SocketPipe Proxy]
    end
    
    subgraph "Backend"
        S1[SSHd]
        S2[Other TCP Service]
    end
    
    C <-->|WebSocket| P
    P <-->|TCP/SSH| S1
    P <-->|TCP| S2
```

### Design Goals

- **Interoperability**: Any compliant client works with any compliant server
- **Efficiency**: Minimal overhead binary framing for real-time terminal interaction
- **Security**: Clear security boundaries with mode-appropriate encryption requirements
- **Simplicity**: Easy to implement in any language

### Non-Goals

- Client UI implementation
- Server-side credential storage
- Logging/audit format specification

---

## Architecture

### Operational Modes

SocketPipe supports two distinct modes, each exposed on a separate endpoint:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TB
    subgraph "Tunnel Mode (/tunnel)"
        direction LR
        TC[Client] -->|"WebSocket<br/>(ws:// or wss://)"| TP[Proxy]
        TP -->|"Raw TCP"| TS[Backend:port]
        
        note1["• Transparent TCP pipe<br/>• Client handles SSH encryption<br/>• Any TCP protocol supported"]
    end
    
    subgraph "PTY Mode (/pty)"
        direction LR
        PC[Client] -->|"WebSocket<br/>(wss:// only)"| PP[Proxy]
        PP -->|"SSH"| PS[SSHd]
        
        note2["• Proxy terminates SSH<br/>• Plaintext PTY I/O over WebSocket<br/>• Supports resize, signals, env vars"]
    end
```

### Mode Comparison

| Aspect | Tunnel Mode (`/tunnel`) | PTY Mode (`/pty`) |
| --- | --- | --- |
| Data | Encrypted SSH bytes | Plaintext terminal I/O |
| TLS | Optional | **Required** |
| Backend | Any TCP service | SSH only |
| Client responsibility | Full SSH handling | Terminal emulation only |
| Use case | SSH client in browser | Simple terminal access |

---

## Transport

### Requirements

- **WebSocket**: MUST be the primary transport
- **Binary frames**: MUST use binary WebSocket frames (opcode 0x02)
- **Byte order**: MUST use big-endian (network byte order) for multi-byte fields

### Endpoints

| Endpoint | TLS Requirement | Description |
| --- | --- | --- |
| `/tunnel` | MAY use `ws://` or `wss://` | Raw TCP tunnel |
| `/pty` | MUST use `wss://` only | Terminated SSH with PTY |

---

## Protocol

### Connection Lifecycle

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server
    participant B as Backend

    C->>S: WebSocket Connect
    S-->>C: WebSocket Accept
    
    C->>S: HANDSHAKE_REQUEST
    S->>B: TCP Connect (if tunnel) or SSH Connect (if pty)
    B-->>S: Connection Established
    S-->>C: HANDSHAKE_RESPONSE (success)
    
    loop Data Transfer
        C->>S: DATA
        S->>B: Forward
        B-->>S: Response
        S-->>C: DATA
    end
    
    alt Keepalive
        C->>S: PING
        S-->>C: PONG
    end
    
    C->>S: CLOSE
    S->>B: Disconnect
    S-->>C: CLOSE (ack)
```

### Frame Format

All messages use an 8-byte header followed by an optional payload:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|     Type      |     Flags     |           Reserved            |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         Payload Length                        |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                         Payload (variable)                  ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Offset | Field | Size | Description |
| --- | --- | --- | --- |
| 0 | Type | 1 byte | Message type identifier |
| 1 | Flags | 1 byte | Message-specific flags |
| 2 | Reserved | 2 bytes | MUST be `0x0000` |
| 4 | Payload Length | 4 bytes | Payload size in bytes |
| 8 | Payload | variable | Message-specific data |

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070'}}}%%
packet-beta
  0-7: "Type (1 byte)"
  8-15: "Flags (1 byte)"
  16-31: "Reserved (2 bytes, must be 0x0000)"
  32-63: "Payload Length (4 bytes, big-endian)"
  64-127: "Payload (variable length)"
```

### Message Types

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TD
    subgraph "Handshake (0x01-0x0F)"
        H1[0x01 HANDSHAKE_REQUEST]
        H2[0x02 HANDSHAKE_RESPONSE]
    end
    
    subgraph "Data (0x10-0x1F)"
        D1[0x10 DATA]
    end
    
    subgraph "Control (0x20-0x2F)"
        C1[0x20 RESIZE]
        C2[0x21 SIGNAL]
        C3[0x22 ENV]
        C4[0x23 FLOW_CONTROL]
    end
    
    subgraph "Keepalive (0x30-0x3F)"
        K1[0x30 PING]
        K2[0x31 PONG]
    end
    
    subgraph "Session (0x40-0x4F)"
        S1[0x40 CLOSE]
    end
    
    subgraph "Error (0xF0-0xFF)"
        E1[0xF0 ERROR]
    end
```

| Type | Name | Direction | Support | Description |
| --- | --- | --- | --- | --- |
| `0x01` | HANDSHAKE_REQUEST | C→S | MUST | Client initiates connection |
| `0x02` | HANDSHAKE_RESPONSE | S→C | MUST | Server accepts/rejects |
| `0x10` | DATA | Both | MUST | Terminal/tunnel data |
| `0x20` | RESIZE | C→S | MUST | Terminal resize (PTY only) |
| `0x21` | SIGNAL | C→S | SHOULD | Send signal (PTY only) |
| `0x22` | ENV | C→S | SHOULD | Set env var (PTY only) |
| `0x23` | FLOW_CONTROL | Both | SHOULD | XON/XOFF |
| `0x30` | PING | Both | MUST | Keepalive request |
| `0x31` | PONG | Both | MUST | Keepalive response |
| `0x40` | CLOSE | Both | MUST | Graceful close |
| `0xF0` | ERROR | S→C | MUST | Error notification |

---

### Handshake

The handshake MUST be the first exchange after WebSocket connection establishment.

#### HANDSHAKE_REQUEST (0x01)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070'}}}%%
packet-beta
  0-7: "Version Major"
  8-15: "Version Minor"
  16-31: "Target Port"
  32-47: "Ping Interval (sec)"
  48-63: "Ping Timeout (sec)"
  64-95: "Max Message Size"
  96-103: "Host Length"
  104-159: "Target Host (variable)"
  160-175: "Token Length"
  176-255: "Token (variable)"
```

| Field | Size | Description |
| --- | --- | --- |
| Version Major | 1 byte | Protocol major version (current: `1`) |
| Version Minor | 1 byte | Protocol minor version (current: `0`) |
| Target Port | 2 bytes | Backend port number |
| Ping Interval | 2 bytes | Requested ping interval (0 = default) |
| Ping Timeout | 2 bytes | Requested ping timeout (0 = default) |
| Max Message Size | 4 bytes | Requested max size (0 = default) |
| Host Length | 1 byte | Length of hostname |
| Target Host | variable | Hostname or IP (UTF-8) |
| Token Length | 2 bytes | Length of auth token |
| Token | variable | Authentication token |

**Negotiable Parameters & Defaults**:

| Parameter | Default | Description |
| --- | --- | --- |
| Ping Interval | 30 seconds | How often to send PING |
| Ping Timeout | 10 seconds | How long to wait for PONG |
| Max Message Size | 65536 bytes | Maximum DATA payload size |

#### HANDSHAKE_RESPONSE (0x02)

**Flags**:
- Bit 0: `1` = Success, `0` = Failure

**Success Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Version Major | 1 byte | Server's protocol version |
| Version Minor | 1 byte | Server's protocol version |
| Ping Interval | 2 bytes | Negotiated interval |
| Ping Timeout | 2 bytes | Negotiated timeout |
| Max Message Size | 4 bytes | Negotiated max size |

**Failure Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Error Code | 2 bytes | Error code |
| Message Length | 1 byte | Length of message |
| Message | variable | Human-readable error (UTF-8) |

#### Handshake State Machine

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#808080', 'secondaryColor': '#909090', 'tertiaryColor': '#707070', 'stateLabelColor': '#000000', 'compositeBackground': '#a0a0a0', 'lineColor': '#404040'}}}%%
stateDiagram-v2
    [*] --> CONNECTING: WebSocket Open
    CONNECTING --> HANDSHAKING: Send HANDSHAKE_REQUEST
    HANDSHAKING --> ESTABLISHED: Receive HANDSHAKE_RESPONSE (success)
    HANDSHAKING --> CLOSED: Receive HANDSHAKE_RESPONSE (failure)
    HANDSHAKING --> CLOSED: Timeout
    ESTABLISHED --> CLOSING: Send/Receive CLOSE
    ESTABLISHED --> CLOSED: Error
    CLOSING --> CLOSED: Close Complete
    CLOSED --> [*]
```

---

### Data Transfer

#### DATA (0x10)

Carries terminal I/O (PTY mode) or raw TCP bytes (tunnel mode).

**Payload**: Raw bytes to forward. No additional framing.

**Constraints**:
- MUST NOT exceed negotiated Max Message Size
- No minimum size (empty DATA is valid but not useful)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant C as Client
    participant P as Proxy
    participant B as Backend
    
    Note over C,B: Bidirectional data flow
    
    C->>P: DATA (user keystroke)
    P->>B: Forward bytes
    B-->>P: Response bytes
    P-->>C: DATA (terminal output)
    
    Note over C,B: High-throughput scenario
    B-->>P: Large output (e.g., cat file)
    P-->>C: DATA (chunk 1)
    P-->>C: DATA (chunk 2)
    P-->>C: DATA (chunk n)
```

---

### Control Messages

Control messages are used for PTY-specific functionality. They MAY be ignored in tunnel mode.

#### RESIZE (0x20) — MUST support

Notifies server of terminal dimension change.

| Field | Size | Description |
| --- | --- | --- |
| Columns | 2 bytes | Terminal width in characters |
| Rows | 2 bytes | Terminal height in characters |
| Pixel Width | 2 bytes | Terminal width in pixels (0 if unknown) |
| Pixel Height | 2 bytes | Terminal height in pixels (0 if unknown) |

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant C as Client
    participant P as Proxy
    participant PTY as PTY/Shell
    
    Note over C: User resizes browser window
    C->>P: RESIZE (cols=120, rows=40)
    P->>PTY: ioctl(TIOCSWINSZ)
    PTY-->>PTY: SIGWINCH to shell
```

#### SIGNAL (0x21) — SHOULD support

Sends a signal to the PTY process.

| Field | Size | Description |
| --- | --- | --- |
| Signal | 1 byte | Signal identifier |

| Value | Signal | Typical Use |
| --- | --- | --- |
| `0x01` | SIGINT | Ctrl+C |
| `0x02` | SIGTERM | Graceful termination |
| `0x03` | SIGHUP | Hangup |
| `0x04` | SIGKILL | Force kill |

#### ENV (0x22) — SHOULD support

Sets an environment variable. MUST be sent before the first DATA message.

| Field | Size | Description |
| --- | --- | --- |
| Name Length | 1 byte | Length of variable name |
| Name | variable | Variable name (UTF-8) |
| Value Length | 2 bytes | Length of value |
| Value | variable | Variable value (UTF-8) |

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant C as Client
    participant P as Proxy
    
    C->>P: HANDSHAKE_REQUEST
    P-->>C: HANDSHAKE_RESPONSE (success)
    C->>P: ENV (TERM=xterm-256color)
    C->>P: ENV (LANG=en_US.UTF-8)
    C->>P: DATA (first input)
    Note over C,P: ENV messages after DATA are ignored
```

#### FLOW_CONTROL (0x23) — SHOULD support

XON/XOFF flow control signaling.

**Flags**:
- Bit 0: `1` = XON (resume), `0` = XOFF (pause)

**Payload**: Empty.

---

### Keepalive

Keepalive ensures connection liveness and detects stale connections.

#### PING (0x30)

Either side MAY send PING at any time.

**Payload**: Optional opaque data (up to 125 bytes recommended).

#### PONG (0x31)

Response to PING.

**Payload**: MUST echo the PING payload exactly.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server
    
    Note over C,S: Normal keepalive
    C->>S: PING (payload: 0xDEADBEEF)
    S-->>C: PONG (payload: 0xDEADBEEF)
    
    Note over C,S: Timeout scenario
    C->>S: PING
    Note over S: Server unresponsive
    Note over C: No PONG within timeout
    C->>S: CLOSE (timeout)
```

**Requirements**:
- MUST respond to PING with PONG within negotiated timeout
- SHOULD send PING at negotiated interval when idle
- SHOULD close connection if PONG not received within timeout

---

### Session Management

#### CLOSE (0x40)

Initiates graceful connection close.

**Flags**:
- Bit 0: `1` = Client-initiated, `0` = Server-initiated

**Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Reason Code | 2 bytes | Close reason |
| Message Length | 1 byte | Length of message |
| Message | variable | Human-readable reason (UTF-8) |

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant C as Client
    participant P as Proxy
    participant B as Backend
    
    alt Client-initiated close
        C->>P: CLOSE (reason: user disconnect)
        P->>B: Close TCP/SSH
        P-->>C: CLOSE (ack)
    else Backend-initiated close
        B-->>P: Connection closed
        P-->>C: CLOSE (reason: backend closed)
    else Error close
        P-->>C: ERROR (code: 2003)
        P-->>C: CLOSE
    end
```

---

### Error Handling

#### ERROR (0xF0)

Server reports an error condition.

**Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Error Code | 2 bytes | Error code |
| Message Length | 1 byte | Length of message |
| Message | variable | Human-readable error (UTF-8) |

#### Error Codes

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TD
    subgraph "1xxx: Authentication"
        E1000[1000 AUTH_FAILED]
        E1001[1001 AUTH_EXPIRED]
        E1002[1002 AUTH_INSUFFICIENT]
    end
    
    subgraph "2xxx: Connection"
        E2000[2000 CONNECT_FAILED]
        E2001[2001 CONNECT_TIMEOUT]
        E2002[2002 CONNECT_REFUSED]
        E2003[2003 BACKEND_CLOSED]
    end
    
    subgraph "3xxx: Protocol"
        E3000[3000 PROTOCOL_ERROR]
        E3001[3001 INVALID_MESSAGE]
        E3002[3002 INVALID_STATE]
        E3003[3003 MESSAGE_TOO_LARGE]
        E3004[3004 UNSUPPORTED_VERSION]
    end
```

| Code | Name | Description |
| --- | --- | --- |
| 1000 | AUTH_FAILED | Token validation failed |
| 1001 | AUTH_EXPIRED | Token has expired |
| 1002 | AUTH_INSUFFICIENT | Token lacks required permissions |
| 2000 | CONNECT_FAILED | Failed to connect to backend |
| 2001 | CONNECT_TIMEOUT | Backend connection timed out |
| 2002 | CONNECT_REFUSED | Backend refused connection |
| 2003 | BACKEND_CLOSED | Backend closed connection |
| 3000 | PROTOCOL_ERROR | Generic protocol violation |
| 3001 | INVALID_MESSAGE | Malformed message |
| 3002 | INVALID_STATE | Message invalid in current state |
| 3003 | MESSAGE_TOO_LARGE | Message exceeds max size |
| 3004 | UNSUPPORTED_VERSION | Protocol version not supported |

---

## Security

### Authentication

- Clients MUST present a token in HANDSHAKE_REQUEST
- Servers MUST validate tokens before establishing backend connections
- Token format (JWT, opaque, etc.) is implementation-defined

### Transport Security

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TB
    subgraph "Tunnel Mode"
        T1[Client] -->|"ws:// or wss://"| T2[Proxy]
        T2 -->|"Encrypted SSH"| T3[SSHd]
        Note1["TLS optional: SSH provides encryption"]
    end
    
    subgraph "PTY Mode"
        P1[Client] -->|"wss:// REQUIRED"| P2[Proxy]
        P2 -->|"SSH (terminated)"| P3[SSHd]
        Note2["TLS required: PTY data is plaintext"]
    end
```

| Mode | Client to Proxy | Proxy to Backend | Rationale |
| --- | --- | --- | --- |
| Tunnel | TLS optional | Encrypted (SSH) | SSH provides end-to-end encryption |
| PTY | TLS **required** | SSH | Plaintext terminal data needs protection |

### Recommendations

- SHOULD use allowlists for permitted backend hosts/ports
- SHOULD implement rate limiting on connection attempts
- SHOULD log authentication failures
- MAY implement IP-based access controls

---

## Examples

### Tunnel Mode: SSH Connection

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant B as Browser (SSH Client)
    participant P as SocketPipe Proxy
    participant S as SSHd (port 22)
    
    B->>P: WebSocket Connect (ws://proxy/tunnel)
    P-->>B: WebSocket Accept
    
    B->>P: HANDSHAKE_REQUEST<br/>(host=server.local, port=22, token=xxx)
    P->>S: TCP Connect
    S-->>P: TCP Accept
    P-->>B: HANDSHAKE_RESPONSE (success)
    
    Note over B,S: SSH handshake (encrypted in DATA payloads)
    B->>P: DATA (SSH_MSG_KEXINIT)
    P->>S: Forward
    S-->>P: SSH_MSG_KEXINIT
    P-->>B: DATA
    
    Note over B,S: SSH session (all encrypted)
    B->>P: DATA (encrypted commands)
    P->>S: Forward
    S-->>P: Encrypted responses
    P-->>B: DATA
```

### PTY Mode: Terminal Session

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant B as Browser (xterm.js)
    participant P as SocketPipe Proxy
    participant S as SSHd
    
    B->>P: WebSocket Connect (wss://proxy/pty)
    P-->>B: WebSocket Accept
    
    B->>P: HANDSHAKE_REQUEST<br/>(host=server.local, port=22, token=xxx)
    P->>S: SSH Connect (credentials from token)
    S-->>P: SSH Session Ready
    P->>S: Request PTY + Shell
    S-->>P: PTY Allocated
    P-->>B: HANDSHAKE_RESPONSE (success)
    
    B->>P: ENV (TERM=xterm-256color)
    B->>P: RESIZE (cols=80, rows=24)
    P->>S: Set TERM, TIOCSWINSZ
    
    Note over B,S: Terminal session (plaintext over WebSocket)
    B->>P: DATA ("ls -la\r")
    P->>S: Write to PTY
    S-->>P: "drwxr-xr-x  2 user..."
    P-->>B: DATA
    
    Note over B,S: Window resize
    B->>P: RESIZE (cols=120, rows=40)
    P->>S: TIOCSWINSZ + SIGWINCH
```

---

## Future Extensions

The following are candidates for future specification versions:

| Extension | Description |
| --- | --- |
| Session Resume | Reconnect after network disruption with session ID |
| Session Persistence | Long-lived sessions surviving client disconnect |
| WebRTC Transport | Data channels for lower latency |
| Multiplexing | Multiple logical sessions over single connection |
| File Transfer | SCP/SFTP support |
| Port Forwarding | SSH port forwarding tunnels |

---

## References

- [RFC 6455](https://datatracker.ietf.org/doc/html/rfc6455) — The WebSocket Protocol
- [RFC 4254](https://datatracker.ietf.org/doc/html/rfc4254) — SSH Connection Protocol
- [RFC 2119](https://datatracker.ietf.org/doc/html/rfc2119) — Key words for use in RFCs

---

## License

This specification is released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).

---

## Contributing

Contributions welcome. Please open an issue or pull request.
