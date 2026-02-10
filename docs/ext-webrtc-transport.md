# SocketPipe Extension: WebRTC Transport

**Status**: Draft  
**Extension ID**: `webrtc-transport`  
**Depends on**: Core Protocol v1.0

## Overview

WebRTC Transport provides an alternative to WebSocket using WebRTC Data Channels. This enables lower latency through UDP transport, better NAT traversal, and potential peer-to-peer connections.

## Use Cases

- Latency-sensitive terminal applications
- Environments where WebSocket proxies add latency
- Direct browser-to-server connections bypassing HTTP infrastructure
- Potential P2P terminal sharing

## Architecture

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040'}}}%%
graph TB
    subgraph "WebSocket (Baseline)"
        C1[Client] -->|"TCP/TLS"| P1[Proxy]
        P1 -->|"TCP"| B1[Backend]
    end
    
    subgraph "WebRTC (This Extension)"
        C2[Client] -->|"DTLS/SCTP"| P2[Proxy]
        P2 -->|"TCP"| B2[Backend]
    end
```

## Protocol Changes

### Signaling

WebRTC requires a signaling channel to exchange SDP offers/answers and ICE candidates. SocketPipe uses WebSocket as the signaling channel.

### Signaling Messages

| Type | Name | Direction | Description |
| --- | --- | --- | --- |
| `0x60` | WEBRTC_OFFER | C→S | SDP offer from client |
| `0x61` | WEBRTC_ANSWER | S→C | SDP answer from server |
| `0x62` | ICE_CANDIDATE | Both | ICE candidate exchange |
| `0x63` | WEBRTC_READY | S→C | Data channel established |

### Connection Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteBkgColor': '#909090', 'noteTextColor': '#000000', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server (WebSocket)
    participant D as Server (DataChannel)

    Note over C,S: WebSocket for signaling
    C->>S: WebSocket Connect
    C->>S: HANDSHAKE_REQUEST (webrtc flag)
    S-->>C: HANDSHAKE_RESPONSE (webrtc flag)
    
    Note over C,S: WebRTC negotiation
    C->>S: WEBRTC_OFFER (SDP)
    S-->>C: WEBRTC_ANSWER (SDP)
    
    C->>S: ICE_CANDIDATE
    S-->>C: ICE_CANDIDATE
    C->>S: ICE_CANDIDATE
    
    Note over C,D: Data channel opens
    C-->>D: DataChannel connected
    S-->>C: WEBRTC_READY
    
    Note over C,D: All further traffic on DataChannel
    C->>D: DATA (via DataChannel)
    D-->>C: DATA (via DataChannel)
    
    Note over C,S: WebSocket kept for control only
```

### WEBRTC_OFFER (0x60)

**Payload**:

| Field | Size | Description |
| --- | --- | --- |
| SDP Length | 2 bytes | Length of SDP |
| SDP | variable | SDP offer string (UTF-8) |

### WEBRTC_ANSWER (0x61)

**Payload**:

| Field | Size | Description |
| --- | --- | --- |
| SDP Length | 2 bytes | Length of SDP |
| SDP | variable | SDP answer string (UTF-8) |

### ICE_CANDIDATE (0x62)

**Payload**:

| Field | Size | Description |
| --- | --- | --- |
| Candidate Length | 2 bytes | Length of candidate |
| Candidate | variable | ICE candidate string (UTF-8) |
| SDP Mid Length | 1 byte | Length of SDP mid |
| SDP Mid | variable | SDP media ID |
| SDP MLine Index | 2 bytes | SDP media line index |

### WEBRTC_READY (0x63)

**Payload**: Empty

Signals that the data channel is ready. Client SHOULD switch to DataChannel for DATA messages.

## Data Channel Configuration

| Parameter | Value | Rationale |
| --- | --- | --- |
| Label | `socketpipe` | Identification |
| Ordered | `true` | Terminal data must be ordered |
| Protocol | `socketpipe/1.0` | Protocol identification |
| Max Retransmits | (none) | Reliable delivery required |

## Message Format on DataChannel

Messages on the DataChannel use the same binary frame format as WebSocket:

```
[Type: 1][Flags: 1][Reserved: 2][Length: 4][Payload: variable]
```

## Fallback Behavior

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'primaryColor': '#808080', 'secondaryColor': '#909090', 'tertiaryColor': '#707070', 'stateLabelColor': '#000000', 'compositeBackground': '#a0a0a0', 'lineColor': '#404040'}}}%%
stateDiagram-v2
    [*] --> WS_HANDSHAKE: Connect
    WS_HANDSHAKE --> WEBRTC_NEGOTIATING: WebRTC supported
    WS_HANDSHAKE --> WS_ONLY: WebRTC not supported
    WEBRTC_NEGOTIATING --> WEBRTC_ACTIVE: DataChannel ready
    WEBRTC_NEGOTIATING --> WS_ONLY: Negotiation failed/timeout
    WEBRTC_ACTIVE --> WS_FALLBACK: DataChannel failed
    WS_ONLY --> [*]: Close
    WS_FALLBACK --> [*]: Close
    WEBRTC_ACTIVE --> [*]: Close
```

- If WebRTC negotiation fails within 10 seconds, fall back to WebSocket
- If DataChannel disconnects, fall back to WebSocket (session resume if available)
- WebSocket connection MUST remain open for control messages

## Server Requirements

- MUST support WebSocket as baseline
- MAY support WebRTC as optional transport
- MUST maintain WebSocket for signaling even when DataChannel active
- MUST handle fallback gracefully
- SHOULD support TURN relay for NAT traversal

## Client Requirements

- MUST support WebSocket as baseline
- MAY attempt WebRTC upgrade
- MUST handle fallback to WebSocket
- SHOULD implement ICE restart on connectivity issues

## Security Considerations

- DataChannel is encrypted via DTLS (mandatory in WebRTC)
- TURN credentials MUST be short-lived and scoped
- Servers SHOULD validate that DataChannel peer matches WebSocket peer
- P2P mode (future) requires additional authentication
