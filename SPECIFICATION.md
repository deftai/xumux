# SocketPipe Protocol Specification

**Version**: 1.0.0-draft  
**Date**: 2026-02-09  
**Status**: Draft

## Overview

SocketPipe is a protocol specification for transporting terminal I/O between web-based SSH clients and backend services over WebSocket connections. It defines a standardized binary framing format, handshake procedure, and message types that enable interoperability between any compliant client and server implementation.

### Goals

- Standardize communication between web SSH UIs (e.g., xterm.js, ghostty-wasm) and backend proxies
- Support both raw TCP tunneling and terminated SSH/PTY modes
- Provide a minimal, efficient binary protocol suitable for real-time terminal interaction
- Enable secure, authenticated connections with clear security boundaries

### Non-Goals (Out of Scope)

- Client UI implementation
- Server-side SSH credential storage mechanisms
- Logging and audit format specifications
- WebRTC data channel transport (future extension)

## Requirements

### Transport

- Implementations MUST support WebSocket as the primary transport
- Implementations MUST use binary WebSocket frames (not text)
- Implementations MUST use big-endian (network byte order) for all multi-byte fields

### Endpoints

Implementations MUST expose two distinct WebSocket endpoints:

| Endpoint | Purpose | TLS Requirement |
|----------|---------|-----------------|
| `/tunnel` | Raw TCP tunnel (pass-through) | MAY use `ws://` or `wss://` |
| `/pty` | Terminated SSH with PTY I/O | MUST use `wss://` only |

**Rationale**: The `/tunnel` endpoint carries already-encrypted SSH protocol bytes, so TLS is optional. The `/pty` endpoint carries plaintext terminal data, so TLS is mandatory.

### Authentication

- Implementations MUST support token-based authentication
- Clients MUST present a token (JWT or opaque) in the handshake message
- Servers MUST validate the token before establishing the connection
- Token format and validation logic are implementation-defined

## Architecture

```
┌─────────────────┐     WebSocket      ┌─────────────────┐     TCP/SSH      ┌─────────────┐
│  Web SSH Client │◄──────────────────►│  SocketPipe      │◄────────────────►│  Backend    │
│  (xterm.js,     │   /tunnel or /pty  │  Proxy          │                  │  (SSHd,     │
│   ghostty-wasm) │                    │                 │                  │   any TCP)  │
└─────────────────┘                    └─────────────────┘                  └─────────────┘
```

### Tunnel Mode (`/tunnel`)

- Proxy acts as a transparent TCP pipe
- WebSocket payload contains raw bytes forwarded to/from the target host:port
- Client is responsible for SSH protocol handling (handshake, encryption, authentication)
- Supports any TCP service, not limited to SSH

### PTY Mode (`/pty`)

- Proxy terminates the SSH connection to the backend
- WebSocket payload contains plaintext PTY I/O (terminal data)
- Proxy manages SSH session lifecycle with the backend SSHd
- Supports terminal resize, signals, and environment variables

## Protocol

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

| Field | Size | Description |
|-------|------|-------------|
| Type | 1 byte | Message type identifier |
| Flags | 1 byte | Message-specific flags |
| Reserved | 2 bytes | Reserved for future use; MUST be 0x0000 |
| Payload Length | 4 bytes | Length of payload in bytes (big-endian) |
| Payload | variable | Message-specific data |

### Message Types

| Type | Name | Direction | Description |
|------|------|-----------|-------------|
| 0x01 | HANDSHAKE_REQUEST | C→S | Client initiates connection |
| 0x02 | HANDSHAKE_RESPONSE | S→C | Server accepts/rejects connection |
| 0x10 | DATA | Bidirectional | Terminal/tunnel data |
| 0x20 | RESIZE | C→S | Terminal resize event |
| 0x21 | SIGNAL | C→S | Send signal to PTY (optional) |
| 0x22 | ENV | C→S | Set environment variable (optional) |
| 0x23 | FLOW_CONTROL | Bidirectional | XON/XOFF flow control (optional) |
| 0x30 | PING | Bidirectional | Keepalive request |
| 0x31 | PONG | Bidirectional | Keepalive response |
| 0x40 | CLOSE | Bidirectional | Graceful close |
| 0xF0 | ERROR | S→C | Error notification |

### Handshake

#### HANDSHAKE_REQUEST (0x01)

The first message after WebSocket connection MUST be a HANDSHAKE_REQUEST from the client.

**Payload Structure**:
```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Version Major | Version Minor |         Target Port           |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Ping Interval (seconds)     |   Ping Timeout (seconds)      |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                      Max Message Size                         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Host Length  |            Target Host (variable)           ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Token Length (2 bytes)        |            Token (variable) ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

| Field | Size | Description |
|-------|------|-------------|
| Version Major | 1 byte | Protocol major version (current: 1) |
| Version Minor | 1 byte | Protocol minor version (current: 0) |
| Target Port | 2 bytes | Backend port number (big-endian) |
| Ping Interval | 2 bytes | Requested ping interval in seconds (0 = use default) |
| Ping Timeout | 2 bytes | Requested ping timeout in seconds (0 = use default) |
| Max Message Size | 4 bytes | Requested max message size in bytes (0 = use default) |
| Host Length | 1 byte | Length of Target Host string |
| Target Host | variable | Target hostname or IP (UTF-8) |
| Token Length | 2 bytes | Length of authentication token |
| Token | variable | Authentication token (opaque bytes) |

**Defaults**:
- Ping Interval: 30 seconds
- Ping Timeout: 10 seconds
- Max Message Size: 65536 bytes (64KB)

#### HANDSHAKE_RESPONSE (0x02)

Server MUST respond with HANDSHAKE_RESPONSE.

**Flags**:
- Bit 0: Success (1) / Failure (0)

**Payload Structure (Success)**:
```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Version Major | Version Minor |   Ping Interval (seconds)     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|   Ping Timeout (seconds)      |      Max Message Size       ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|      ... Max Message Size     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

**Payload Structure (Failure)**:
```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Error Code            |  Message Length |  Message  ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### Data Messages

#### DATA (0x10)

Carries terminal I/O or tunnel data.

**Payload**: Raw bytes to be forwarded.

Implementations MUST NOT send DATA messages larger than the negotiated Max Message Size.

### Control Messages

#### RESIZE (0x20)

Notifies server of terminal dimension change. Applicable to `/pty` endpoint only.

**Payload**:
```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|           Columns             |             Rows              |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Pixel Width           |          Pixel Height         |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

All fields are 2 bytes, big-endian.

#### SIGNAL (0x21) — SHOULD support

Sends a signal to the PTY process. Applicable to `/pty` endpoint only.

**Payload**:
```
+-+-+-+-+-+-+-+-+
|    Signal     |
+-+-+-+-+-+-+-+-+
```

| Value | Signal |
|-------|--------|
| 0x01 | SIGINT |
| 0x02 | SIGTERM |
| 0x03 | SIGHUP |
| 0x04 | SIGKILL |

#### ENV (0x22) — SHOULD support

Sets an environment variable before shell execution. Applicable to `/pty` endpoint only; MUST be sent before first DATA message.

**Payload**:
```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|  Name Length  |            Name (variable)                  ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
| Value Length (2 bytes)        |            Value (variable) ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

#### FLOW_CONTROL (0x23) — SHOULD support

XON/XOFF flow control signaling.

**Flags**:
- Bit 0: XON (1) / XOFF (0)

**Payload**: Empty.

### Keepalive Messages

#### PING (0x30)

Either side MAY send PING to verify connection liveness.

**Payload**: Optional opaque data (MUST be echoed in PONG).

#### PONG (0x31)

Response to PING.

**Payload**: Echo of PING payload.

**Requirements**:
- Implementations MUST respond to PING with PONG within the negotiated timeout
- If no PONG is received within the timeout, the connection SHOULD be closed
- Implementations SHOULD send PING at the negotiated interval when no other traffic

### Session Messages

#### CLOSE (0x40)

Initiates graceful connection close.

**Flags**:
- Bit 0: Initiated by client (1) / server (0)

**Payload**:
```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Reason Code           |  Message Length |  Message  ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

#### ERROR (0xF0)

Server reports an error condition.

**Payload**:
```
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|         Error Code            |  Message Length |  Message  ...
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

### Error Codes

| Range | Category |
|-------|----------|
| 1000-1999 | Authentication errors |
| 2000-2999 | Connection errors |
| 3000-3999 | Protocol errors |

| Code | Name | Description |
|------|------|-------------|
| 1000 | AUTH_FAILED | Token validation failed |
| 1001 | AUTH_EXPIRED | Token has expired |
| 1002 | AUTH_INSUFFICIENT | Token lacks required permissions |
| 2000 | CONNECT_FAILED | Failed to connect to backend |
| 2001 | CONNECT_TIMEOUT | Backend connection timed out |
| 2002 | CONNECT_REFUSED | Backend refused connection |
| 2003 | BACKEND_CLOSED | Backend closed connection |
| 3000 | PROTOCOL_ERROR | Generic protocol violation |
| 3001 | INVALID_MESSAGE | Malformed message received |
| 3002 | INVALID_STATE | Message not valid in current state |
| 3003 | MESSAGE_TOO_LARGE | Message exceeds max size |
| 3004 | UNSUPPORTED_VERSION | Protocol version not supported |

## Implementation Plan

### Phase 1: Core Protocol (Foundation)

#### Subphase 1.1: Frame Parser
- **Task 1.1.1**: Define frame header structure and constants
  - Dependencies: None
  - Acceptance: Header struct with type, flags, reserved, length fields
- **Task 1.1.2**: Implement frame serialization (write)
  - Dependencies: 1.1.1
  - Acceptance: Can serialize any message type to bytes
- **Task 1.1.3**: Implement frame deserialization (read)
  - Dependencies: 1.1.1
  - Acceptance: Can deserialize bytes to message structs
- **Task 1.1.4**: Add validation (reserved=0, length bounds)
  - Dependencies: 1.1.2, 1.1.3
  - Acceptance: Invalid frames rejected with appropriate errors
- **Task 1.1.5**: Unit tests for frame parser
  - Dependencies: 1.1.4
  - Acceptance: 100% coverage of serialization/deserialization, edge cases

#### Subphase 1.2: Message Types (depends on: 1.1)
- **Task 1.2.1**: Define all message type structs
  - Dependencies: 1.1.5
  - Acceptance: Structs for all 11 message types
- **Task 1.2.2**: Implement HANDSHAKE_REQUEST/RESPONSE
  - Dependencies: 1.2.1
  - Acceptance: Can encode/decode handshake messages
- **Task 1.2.3**: Implement DATA message
  - Dependencies: 1.2.1
  - Acceptance: Can encode/decode data messages
- **Task 1.2.4**: Implement control messages (RESIZE, SIGNAL, ENV, FLOW_CONTROL)
  - Dependencies: 1.2.1
  - Acceptance: Can encode/decode all control messages
- **Task 1.2.5**: Implement PING/PONG messages
  - Dependencies: 1.2.1
  - Acceptance: Can encode/decode keepalive messages
- **Task 1.2.6**: Implement CLOSE/ERROR messages
  - Dependencies: 1.2.1
  - Acceptance: Can encode/decode session messages
- **Task 1.2.7**: Unit tests for all message types
  - Dependencies: 1.2.2, 1.2.3, 1.2.4, 1.2.5, 1.2.6
  - Acceptance: Full coverage of all message encode/decode paths

### Phase 2: State Machine (depends on: Phase 1)

#### Subphase 2.1: Connection States
- **Task 2.1.1**: Define connection state enum
  - Dependencies: Phase 1
  - Acceptance: States: CONNECTING, HANDSHAKING, ESTABLISHED, CLOSING, CLOSED
- **Task 2.1.2**: Implement state transition logic
  - Dependencies: 2.1.1
  - Acceptance: Valid transitions enforced, invalid transitions rejected
- **Task 2.1.3**: State machine unit tests
  - Dependencies: 2.1.2
  - Acceptance: All valid/invalid transitions tested

#### Subphase 2.2: Handshake Flow (depends on: 2.1)
- **Task 2.2.1**: Implement client handshake initiator
  - Dependencies: 2.1.3
  - Acceptance: Client sends HANDSHAKE_REQUEST on connect
- **Task 2.2.2**: Implement server handshake responder
  - Dependencies: 2.1.3
  - Acceptance: Server validates and responds with HANDSHAKE_RESPONSE
- **Task 2.2.3**: Implement parameter negotiation
  - Dependencies: 2.2.1, 2.2.2
  - Acceptance: Ping interval, timeout, max size negotiated correctly
- **Task 2.2.4**: Integration tests for handshake
  - Dependencies: 2.2.3
  - Acceptance: Client-server handshake succeeds with various parameters

### Phase 3: Keepalive & Error Handling (depends on: Phase 2)

#### Subphase 3.1: Keepalive
- **Task 3.1.1**: Implement ping timer
  - Dependencies: Phase 2
  - Acceptance: PING sent at negotiated interval
- **Task 3.1.2**: Implement pong handler
  - Dependencies: 3.1.1
  - Acceptance: PONG received resets timeout
- **Task 3.1.3**: Implement timeout detection
  - Dependencies: 3.1.2
  - Acceptance: Connection closed if PONG not received within timeout
- **Task 3.1.4**: Keepalive integration tests
  - Dependencies: 3.1.3
  - Acceptance: Connections stay alive with traffic, timeout without

#### Subphase 3.2: Error Handling (depends on: 3.1)
- **Task 3.2.1**: Define error code constants
  - Dependencies: 3.1.4
  - Acceptance: All error codes from spec defined
- **Task 3.2.2**: Implement error message creation
  - Dependencies: 3.2.1
  - Acceptance: Can create ERROR messages with code and text
- **Task 3.2.3**: Implement graceful close flow
  - Dependencies: 3.2.2
  - Acceptance: CLOSE message sent, connection terminated cleanly
- **Task 3.2.4**: Error handling integration tests
  - Dependencies: 3.2.3
  - Acceptance: Errors reported correctly, connections closed gracefully

### Phase 4: Endpoint Implementation (depends on: Phase 3)

#### Subphase 4.1: Tunnel Endpoint (`/tunnel`)
- **Task 4.1.1**: Implement TCP connection to backend
  - Dependencies: Phase 3
  - Acceptance: Can connect to arbitrary host:port
- **Task 4.1.2**: Implement bidirectional data forwarding
  - Dependencies: 4.1.1
  - Acceptance: Data flows both directions without modification
- **Task 4.1.3**: Implement connection cleanup
  - Dependencies: 4.1.2
  - Acceptance: Both sides closed when either disconnects
- **Task 4.1.4**: Tunnel endpoint integration tests
  - Dependencies: 4.1.3
  - Acceptance: Can tunnel SSH, HTTP, other TCP protocols

#### Subphase 4.2: PTY Endpoint (`/pty`) (depends on: 4.1)
- **Task 4.2.1**: Implement SSH client connection
  - Dependencies: 4.1.4
  - Acceptance: Can connect to SSHd with credentials from token
- **Task 4.2.2**: Implement PTY allocation
  - Dependencies: 4.2.1
  - Acceptance: Shell session started with PTY
- **Task 4.2.3**: Implement terminal resize handling
  - Dependencies: 4.2.2
  - Acceptance: RESIZE messages update PTY dimensions
- **Task 4.2.4**: Implement signal forwarding (optional)
  - Dependencies: 4.2.3
  - Acceptance: SIGNAL messages sent to PTY process
- **Task 4.2.5**: Implement environment variable setting (optional)
  - Dependencies: 4.2.3
  - Acceptance: ENV messages set variables before shell start
- **Task 4.2.6**: PTY endpoint integration tests
  - Dependencies: 4.2.5
  - Acceptance: Full terminal session works with resize and signals

### Phase 5: Security & Validation (depends on: Phase 4)

#### Subphase 5.1: Input Validation
- **Task 5.1.1**: Implement message size limits
  - Dependencies: Phase 4
  - Acceptance: Messages exceeding max size rejected
- **Task 5.1.2**: Implement host/port validation
  - Dependencies: 5.1.1
  - Acceptance: Invalid targets rejected, allowlists supported
- **Task 5.1.3**: Implement token validation interface
  - Dependencies: 5.1.2
  - Acceptance: Pluggable token validator with JWT example
- **Task 5.1.4**: Security integration tests
  - Dependencies: 5.1.3
  - Acceptance: Invalid inputs rejected, valid inputs accepted

#### Subphase 5.2: TLS Enforcement (depends on: 5.1)
- **Task 5.2.1**: Implement TLS requirement for `/pty`
  - Dependencies: 5.1.4
  - Acceptance: Non-TLS connections to `/pty` rejected
- **Task 5.2.2**: Document TLS configuration
  - Dependencies: 5.2.1
  - Acceptance: Clear docs for certificate setup
- **Task 5.2.3**: TLS integration tests
  - Dependencies: 5.2.2
  - Acceptance: TLS enforcement verified

## Testing Strategy

### Unit Tests
- Frame parser: serialization, deserialization, validation
- Message types: all encode/decode paths
- State machine: all transitions
- Error handling: all error codes

### Integration Tests
- Handshake: success, failure, version mismatch
- Keepalive: alive, timeout, recovery
- Tunnel: connect, forward, disconnect
- PTY: session, resize, signals, env

### Conformance Tests
- Reference test vectors for all message types
- Interoperability tests between implementations

## Deployment

### Server Requirements
- WebSocket server capable of binary frames
- TCP connectivity to backend services
- TLS termination (required for `/pty`, recommended for `/tunnel`)

### Client Requirements
- WebSocket client with binary frame support
- For `/tunnel`: SSH client library (e.g., libssh, ssh2)
- For `/pty`: Terminal emulator (e.g., xterm.js, ghostty-wasm)

## Future Extensions

The following features are candidates for future specification versions:

- **Session Resume**: Reconnection with session ID for network disruption recovery
- **Session Persistence**: Long-lived sessions surviving indefinite disconnection
- **WebRTC Data Channel**: Alternative transport for lower latency
- **Multi-session Multiplexing**: Multiple logical sessions over single connection
- **File Transfer**: SCP/SFTP support
- **Port Forwarding**: SSH port forwarding tunnels

---

To start implementation, type: **"implement SPECIFICATION.md"**
