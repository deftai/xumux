# xumux Extension: Port Forwarding

**Status**: Draft
**Extension ID**: `port-forwarding`
**Depends on**: xumux 0.1.0+

## Overview

Port Forwarding enables SSH-style local and remote TCP port forwarding over an xumux connection. Each forwarded connection gets its own xumux channel, leveraging native multiplexing.

## Use Cases

- Access remote database through an xumux connection
- Expose local development server to remote environment
- Secure tunneling of web services
- Jump host / bastion scenarios

## Architecture

Port forwarding control messages are sent on a dedicated `port-forward-ctl` channel. Each individual forwarded TCP connection is assigned its own dynamically opened channel.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'clusterBkg': '#c0c0c0', 'clusterBorder': '#606060'}}}%%
graph TB
    subgraph "xumux Connection"
        CH0["Channel 0 — Control"]
        CHC["Channel 1 — port-forward-ctl"]
        CH3["Channel 3 — forwarded conn #1"]
        CH4["Channel 4 — forwarded conn #2"]
    end
```

## Forwarding Types

### Local Forwarding (-L)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'clusterBkg': '#c0c0c0', 'clusterBorder': '#606060'}}}%%
graph LR
    LC["Local App"] -->|"localhost:8080"| OC["xumux Client"]
    OC -->|"xumux channel"| OS["xumux Server"]
    OS -->|"TCP"| DB["db.internal:5432"]
```

### Remote Forwarding (-R)

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'clusterBkg': '#c0c0c0', 'clusterBorder': '#606060'}}}%%
graph RL
    RU["Remote User"] -->|"server:9000"| OS["xumux Server"]
    OS -->|"xumux channel"| OC["xumux Client"]
    OC -->|"TCP"| DS["localhost:3000"]
```

## Channel Setup

The `port-forward-ctl` channel is opened during or after handshake:

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'actorLineColor': '#404040', 'signalColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'noteBkgColor': '#909090'}}}%%
sequenceDiagram
    participant C as Client
    participant S as Server

    C->>S: OPEN_CHANNEL {name: "port-forward-ctl", reliable: true, ordered: true}
    S->>C: CHANNEL_ACK {id: 1}
    Note over C,S: Channel 1 carries forwarding control messages
```

## Control Messages (on port-forward-ctl channel)

| Type | Name | Direction | Description |
|------|------|-----------|-------------|
| `0x01` | FORWARD_REQUEST | Both | Request a port forward |
| `0x02` | FORWARD_RESPONSE | Both | Forward request result |
| `0x03` | FORWARD_CANCEL | Both | Cancel an active forward |
| `0x04` | FORWARD_CONNECTION | Both | New connection on a forward |
| `0x05` | FORWARD_CONNECTION_ACK | Both | Accept/reject forwarded connection |

### FORWARD_REQUEST (0x01)

**Payload** (JSON):
```json
{
  "forwardId": 1,
  "direction": "local",
  "bindAddress": "localhost",
  "bindPort": 8080,
  "targetAddress": "db.internal",
  "targetPort": 5432
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `forwardId` | number | MUST | Unique forward identifier |
| `direction` | string | MUST | `"local"` (-L) or `"remote"` (-R) |
| `bindAddress` | string | MUST | Address to bind (e.g., `"localhost"`, `"0.0.0.0"`) |
| `bindPort` | number | MUST | Port to bind (0 = dynamic) |
| `targetAddress` | string | MUST | Target host |
| `targetPort` | number | MUST | Target port |

### FORWARD_RESPONSE (0x02)

**Payload** (JSON):
```json
{
  "forwardId": 1,
  "success": true,
  "actualPort": 8080
}
```

On failure:
```json
{
  "forwardId": 1,
  "success": false,
  "code": 7000,
  "reason": "Port already in use"
}
```

### FORWARD_CONNECTION (0x04)

Sent when a new TCP connection arrives on a forwarded port. The sender also opens a new xumux channel for the connection data.

**Payload** (JSON):
```json
{
  "forwardId": 1,
  "channelName": "fwd-1-conn-1",
  "sourceAddress": "127.0.0.1",
  "sourcePort": 54321
}
```

The sender simultaneously sends an `OPEN_CHANNEL` on channel 0 with name matching `channelName`. The receiver correlates them.

## Local Forward Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'actorLineColor': '#404040', 'signalColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'noteBkgColor': '#909090'}}}%%
sequenceDiagram
    participant A as Local App
    participant C as Client
    participant S as Server
    participant D as db.internal:5432

    Note over C,S: Setup: on port-forward-ctl channel
    C->>S: FORWARD_REQUEST {direction: "local", bind: 8080, target: db:5432}
    S->>C: FORWARD_RESPONSE {success: true}
    Note over C: Client listens on localhost:8080

    Note over A,D: App connects to localhost:8080
    A->>C: TCP connect localhost:8080
    Note over C,S: Client opens a new channel for this connection
    C->>S: OPEN_CHANNEL {name: "fwd-1-conn-1"} (on ch 0)
    C->>S: FORWARD_CONNECTION {forwardId: 1, channelName: "fwd-1-conn-1"} (on ctl ch)
    S->>D: TCP connect db.internal:5432
    S->>C: CHANNEL_ACK {id: 5} (on ch 0)

    Note over A,D: Data flows on channel 5
    A->>C: SQL query
    C->>S: DATA (ch=5)
    S->>D: TCP forward
    D->>S: Response
    S->>C: DATA (ch=5)
    C->>A: Response
```

## Remote Forward Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': {'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'lineColor': '#404040', 'actorLineColor': '#404040', 'signalColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'noteBkgColor': '#909090'}}}%%
sequenceDiagram
    participant D as Dev Server :3000
    participant C as Client
    participant S as Server
    participant R as Remote User

    Note over C,S: Setup: on port-forward-ctl channel
    C->>S: FORWARD_REQUEST {direction: "remote", bind: 9000, target: localhost:3000}
    S->>C: FORWARD_RESPONSE {success: true, actualPort: 9000}
    Note over S: Server listens on server:9000

    Note over R,D: Remote user connects to server:9000
    R->>S: TCP connect server:9000
    Note over C,S: Server opens a new channel for this connection
    S->>C: OPEN_CHANNEL {name: "fwd-1-conn-1"} (on ch 0)
    S->>C: FORWARD_CONNECTION {forwardId: 1, channelName: "fwd-1-conn-1"} (on ctl ch)
    C->>D: TCP connect localhost:3000
    C->>S: CHANNEL_ACK {id: 6} (on ch 0)

    Note over R,D: Data flows on channel 6
    R->>S: HTTP request
    S->>C: DATA (ch=6)
    C->>D: Forward
    D->>C: Response
    C->>S: DATA (ch=6)
    S->>R: Response
```

## Error Codes

| Code | Name | Description |
|------|------|-------------|
| 7000 | PORT_IN_USE | Requested port already bound |
| 7001 | PERMISSION_DENIED | Cannot bind to port (e.g., < 1024) |
| 7002 | FORWARD_LIMIT | Maximum forwards exceeded |
| 7003 | CONNECT_FAILED | Cannot connect to target |
| 7004 | FORWARD_DISABLED | Port forwarding not allowed by policy |
| 7005 | INVALID_ADDRESS | Invalid bind or target address |

## Security Considerations

- Remote forwards expose server ports; restrict by default
- Servers SHOULD only allow localhost binds unless explicitly configured
- Consider rate limiting new connections per forward
- Audit logging recommended for all forward requests
