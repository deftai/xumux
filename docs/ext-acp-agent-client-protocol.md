# xumux-ACP: Agent Client Protocol over xumux

**Version:** 1.0 (Draft)
**Status:** Proposed extension
**Published:** <https://xumux.org/acp>
**Repository:** <https://github.com/deftai/xumux>

xumux-ACP defines how the [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) runs natively over [xumux](https://github.com/deftai/xumux) — the eXtensible Universal MUltipleXer.

It keeps the **exact same JSON-RPC 2.0** messages and semantics from the official ACP specification while using xumux for transport, multiplexing, framing, and negotiation. This makes remote/cloud agents fast, reliable, and transport-agnostic (WebSocket, WebRTC, QUIC, TCP, stdio, etc.).

## Architecture Overview

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'lineColor': '#404040' }}}%%
graph TB
    ACP["ACP JSON-RPC 2.0 Messages<br/><i>initialize, session/prompt, session/update, etc.</i>"]
    XACP["xumux-ACP Binding<br/><i>Channel mapping & framing rules</i>"]
    MUX["xumux Protocol Layer<br/><i>Multiplexing, fragmentation, keep-alives</i>"]

    WS["WebSocket"]
    WR["WebRTC"]
    QC["QUIC"]
    TC["TCP"]
    ST["stdio"]

    ACP --> XACP
    XACP --> MUX
    MUX --> WS
    MUX --> WR
    MUX --> QC
    MUX --> TC
    MUX --> ST

    style ACP fill:#707070,stroke:#404040,color:#000000
    style XACP fill:#808080,stroke:#404040,color:#000000
    style MUX fill:#909090,stroke:#404040,color:#000000
    style WS fill:#a0a0a0,stroke:#404040,color:#000000
    style WR fill:#a0a0a0,stroke:#404040,color:#000000
    style QC fill:#a0a0a0,stroke:#404040,color:#000000
    style TC fill:#a0a0a0,stroke:#404040,color:#000000
    style ST fill:#a0a0a0,stroke:#404040,color:#000000
```

## Motivation

Traditional ACP transports (stdio for local, raw WebSocket for remote) have limitations:

- One connection per feature is messy
- No built-in fragmentation or multiplexing
- Inconsistent behavior across local vs remote
- Extra glue code for keepalives, auth, etc.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'lineColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040', 'noteBkgColor': '#909090' }}}%%
graph LR
    subgraph Traditional["Traditional ACP"]
        direction TB
        C1["Client"] -->|"stdio"| A1["Local Agent"]
        C2["Client"] -->|"WebSocket 1"| A2["Remote Agent"]
        C3["Client"] -->|"WebSocket 2"| A3["File Transfer"]
        C4["Client"] -->|"WebSocket 3"| A4["Streaming"]
    end

    subgraph XumuxACP["xumux-ACP"]
        direction TB
        C5["Client"] -->|"Single xumux Connection"| MX["xumux Multiplexer"]
        MX -->|"Channel 1"| B1["JSON-RPC"]
        MX -->|"Channel 2"| B2["File Transfer"]
        MX -->|"Channel 3"| B3["Streaming"]
    end

    style C1 fill:#a0a0a0,stroke:#404040,color:#000000
    style C2 fill:#a0a0a0,stroke:#404040,color:#000000
    style C3 fill:#a0a0a0,stroke:#404040,color:#000000
    style C4 fill:#a0a0a0,stroke:#404040,color:#000000
    style A1 fill:#909090,stroke:#404040,color:#000000
    style A2 fill:#909090,stroke:#404040,color:#000000
    style A3 fill:#909090,stroke:#404040,color:#000000
    style A4 fill:#909090,stroke:#404040,color:#000000
    style C5 fill:#a0a0a0,stroke:#404040,color:#000000
    style MX fill:#707070,stroke:#404040,color:#000000
    style B1 fill:#909090,stroke:#404040,color:#000000
    style B2 fill:#909090,stroke:#404040,color:#000000
    style B3 fill:#909090,stroke:#404040,color:#000000
    style Traditional fill:#c0c0c0,stroke:#404040,color:#000000
    style XumuxACP fill:#c0c0c0,stroke:#404040,color:#000000
```

xumux-ACP solves this with a single efficient connection that supports multiple logical channels while staying fully compatible with ACP's JSON-RPC layer.

Existing ACP implementations continue to work unchanged via stdio. A thin xumux wrapper can bridge them when needed.

## Core Principles

- JSON-RPC 2.0 payloads remain **unchanged** (all ACP methods, notifications, and schemas stay identical).
- xumux handles framing, multiplexing, fragmentation, keep-alives, and transport abstraction.
- Channels are pre-negotiated in the xumux HELLO for minimal latency.
- Two-layer capability model: transport-level (xumux HELLO) + application-level (ACP `initialize`).

## Negotiation

xumux-ACP uses **pre-opening channels in the HELLO** message (recommended for lowest latency).

### Recommended Channels (v1)

| Channel Name            | Reliable | Ordered | Purpose                                    | Key Metadata                               |
|-------------------------|----------|---------|--------------------------------------------|--------------------------------------------||
| `xacp-jsonrpc`          | Yes      | Yes     | All JSON-RPC 2.0 ACP messages              | `protocol`, `acpVersion`, `maxMessageSize` |
| `xacp-files` (optional) | Yes      | Yes     | Large file reads/writes and binary content | `maxChunkSize`                             |

Future channels (e.g. `xacp-stream`) can be added later.

### Negotiation Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'lineColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040', 'noteBkgColor': '#909090' }}}%%
sequenceDiagram
    participant C as Client
    participant T as Transport<br/>(WS / QUIC / TCP / ...)
    participant A as Agent

    C->>T: Connect
    T-->>C: Connection established

    C->>A: HELLO<br/>application: "xumux-acp/1.0"<br/>channels: [xacp-jsonrpc]<br/>auth: { type: "token", token: "..." }

    Note over A: Validate auth<br/>Accept channels<br/>Assign channel IDs

    A->>C: WELCOME<br/>channels: [{ name: "xacp-jsonrpc", id: 1 }]

    Note over C,A: xacp-jsonrpc channel is now open.<br/>Raw ACP JSON-RPC messages flow directly.
```

### Client HELLO Example

```json
{
  "version": [0, 1, 0],
  "application": "xumux-acp/1.0",
  "extensions": ["xacp-jsonrpc"],
  "auth": {
    "type": "token",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  },
  "channels": [
    {
      "name": "xacp-jsonrpc",
      "reliable": true,
      "ordered": true,
      "metadata": {
        "protocol": "jsonrpc-2.0",
        "acpVersion": 1,
        "maxMessageSize": 67108864
      }
    }
  ]
}
```

The agent responds with a **WELCOME** message that accepts the requested channels and assigns concrete channel IDs.

After a successful WELCOME, both sides immediately start exchanging raw ACP JSON-RPC messages on the assigned channel for `xacp-jsonrpc`. No extra envelope is used — each xumux frame carries exactly one complete JSON-RPC 2.0 object.

## Framing Rules

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'lineColor': '#404040' }}}%%
graph LR
    subgraph Frame["xumux Frame"]
        direction LR
        H["Frame Header<br/><i>channel ID, length, flags</i>"]
        P["Payload<br/><i>One complete JSON-RPC 2.0 object</i>"]
        H --> P
    end

    subgraph LargeMsg["Large Message (auto-fragmented)"]
        direction LR
        F1["Fragment 1<br/><i>FRAG_START</i>"]
        F2["Fragment 2<br/><i>FRAG_CONT</i>"]
        F3["Fragment 3<br/><i>FRAG_END</i>"]
        F1 --> F2 --> F3
    end

    style H fill:#808080,stroke:#404040,color:#000000
    style P fill:#909090,stroke:#404040,color:#000000
    style F1 fill:#808080,stroke:#404040,color:#000000
    style F2 fill:#909090,stroke:#404040,color:#000000
    style F3 fill:#a0a0a0,stroke:#404040,color:#000000
    style Frame fill:#c0c0c0,stroke:#404040,color:#000000
    style LargeMsg fill:#c0c0c0,stroke:#404040,color:#000000
```

- Messages on `xacp-jsonrpc` **MUST** be valid ACP JSON-RPC 2.0 objects (request, response, or notification).
- xumux automatically handles fragmentation for large messages.
- JSON-RPC `id` fields and error codes work exactly as in the original ACP specification.
- xumux-level channel errors and JSON-RPC errors coexist.

## Authentication and Capabilities

xumux-ACP uses a **two-layer capability model** to cleanly separate transport concerns from application logic.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'lineColor': '#404040' }}}%%
graph TB
    subgraph Transport["Transport Layer (xumux HELLO)"]
        direction TB
        TA["Token-based authentication"]
        TE["Basic extensions & limits"]
        TC["Channel pre-negotiation"]
    end

    subgraph Application["Application Layer (ACP JSON-RPC)"]
        direction TB
        AI["initialize request/response<br/><i>clientCapabilities ↔ agentCapabilities</i>"]
        AA["Optional authenticate method"]
        AC["Standard ACP capabilities<br/><i>filesystem, terminal, MCP integration,<br/>prompt modalities, etc.</i>"]
    end

    Transport --> Application

    style TA fill:#808080,stroke:#404040,color:#000000
    style TE fill:#808080,stroke:#404040,color:#000000
    style TC fill:#808080,stroke:#404040,color:#000000
    style AI fill:#909090,stroke:#404040,color:#000000
    style AA fill:#909090,stroke:#404040,color:#000000
    style AC fill:#909090,stroke:#404040,color:#000000
    style Transport fill:#c0c0c0,stroke:#404040,color:#000000
    style Application fill:#b0b0b0,stroke:#404040,color:#000000
```

This ensures full compatibility with the official ACP specification.

## Conformance Requirements

A compliant xumux-ACP implementation **MUST**:

1. Correctly implement the xumux protocol.
2. Pre-open at least the `xacp-jsonrpc` channel during HELLO/WELCOME.
3. Send and receive unmodified ACP JSON-RPC messages on that channel.
4. Respect capabilities from both transport and application layers.
5. Handle xumux keep-alives, fragmentation, and errors properly.

## Example Message Flow

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'lineColor': '#404040', 'actorBkg': '#808080', 'actorTextColor': '#000000', 'actorLineColor': '#404040', 'signalColor': '#404040', 'noteBkgColor': '#909090' }}}%%
sequenceDiagram
    participant C as Client
    participant A as Agent

    rect rgb(192, 192, 192)
        Note over C,A: Transport Layer (xumux)
        C->>A: HELLO (pre-open xacp-jsonrpc)
        A->>C: WELCOME (channel IDs assigned)
    end

    rect rgb(176, 176, 176)
        Note over C,A: Application Layer (ACP JSON-RPC)
        C->>A: initialize { clientCapabilities }
        A->>C: initialize response { agentCapabilities }
    end

    rect rgb(160, 160, 160)
        Note over C,A: Optional Authentication
        C->>A: authenticate { credentials }
        A->>C: authenticate response { success }
    end

    rect rgb(144, 144, 144)
        Note over C,A: Session Lifecycle
        C->>A: session/new
        A->>C: session/new response { sessionId }

        C->>A: session/prompt { messages }

        loop Streaming Response
            A->>C: session/update (partial)
        end

        A->>C: session/update (final)
    end

    rect rgb(128, 128, 128)
        Note over C,A: Agent-Initiated Notifications
        A->>C: tool/call notification
        A->>C: file/diff notification
        A->>C: session/update notification
    end
```

All JSON-RPC traffic uses the single multiplexed xumux channel.

## Channel Lifecycle

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'lineColor': '#404040', 'stateLabelColor': '#000000', 'compositeBackground': '#a0a0a0' }}}%%
stateDiagram-v2
    [*] --> Proposed: Client includes channel<br/>in HELLO message
    Proposed --> Accepted: Agent accepts in WELCOME
    Proposed --> Rejected: Agent rejects / omits
    Rejected --> [*]
    Accepted --> Active: Channel ID assigned
    Active --> Active: JSON-RPC messages flow
    Active --> Draining: CLOSE_CHANNEL sent
    Draining --> Closed: All in-flight messages complete
    Closed --> [*]
```

## Future Extensions

- **Additional pre-opened channels** — `xacp-files`, `xacp-stream`
- **Dynamic channel creation** — via `OPEN_CHANNEL`
- **Native binary message types** — for higher performance
- **Built-in MCP tool server multiplexing**
- **Multimodal channels** — voice, image

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'lineColor': '#404040' }}}%%
graph LR
    subgraph Today["v1 — Today"]
        CH1["xacp-jsonrpc"]
    end

    subgraph Future["v2+ — Future"]
        CH2["xacp-jsonrpc"]
        CH3["xacp-files"]
        CH4["xacp-stream"]
        CH5["xacp-mcp"]
        CH6["xacp-media"]
    end

    Today -->|"extension"| Future

    style CH1 fill:#808080,stroke:#404040,color:#000000
    style CH2 fill:#808080,stroke:#404040,color:#000000
    style CH3 fill:#909090,stroke:#404040,color:#000000
    style CH4 fill:#909090,stroke:#404040,color:#000000
    style CH5 fill:#a0a0a0,stroke:#404040,color:#000000
    style CH6 fill:#a0a0a0,stroke:#404040,color:#000000
    style Today fill:#c0c0c0,stroke:#404040,color:#000000
    style Future fill:#b0b0b0,stroke:#404040,color:#000000
```

## Relationship to Original ACP

xumux-ACP is **not** a competing protocol. It is a **transport binding** for ACP. The JSON-RPC layer stays identical.

You can still use original ACP over stdio or raw WebSocket. xumux-ACP simply provides a better wire format for modern use cases, especially remote and cloud agents.

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#909090', 'secondaryColor': '#808080', 'tertiaryColor': '#707070', 'primaryTextColor': '#000000', 'secondaryTextColor': '#000000', 'tertiaryTextColor': '#000000', 'noteTextColor': '#000000', 'lineColor': '#404040' }}}%%
graph TB
    ACP["ACP Specification<br/><i>JSON-RPC 2.0 methods & schemas</i>"]

    ACP --> B1["stdio Transport<br/><i>Local agents</i>"]
    ACP --> B2["WebSocket Transport<br/><i>Remote agents (original)</i>"]
    ACP --> B3["xumux-ACP Transport<br/><i>Remote/cloud agents (this spec)</i>"]

    B3 --> C1["WebSocket"]
    B3 --> C2["WebRTC"]
    B3 --> C3["QUIC"]
    B3 --> C4["TCP"]
    B3 --> C5["stdio"]

    style ACP fill:#707070,stroke:#404040,color:#000000
    style B1 fill:#a0a0a0,stroke:#404040,color:#000000
    style B2 fill:#a0a0a0,stroke:#404040,color:#000000
    style B3 fill:#808080,stroke:#404040,color:#000000
    style C1 fill:#b0b0b0,stroke:#404040,color:#000000
    style C2 fill:#b0b0b0,stroke:#404040,color:#000000
    style C3 fill:#b0b0b0,stroke:#404040,color:#000000
    style C4 fill:#b0b0b0,stroke:#404040,color:#000000
    style C5 fill:#b0b0b0,stroke:#404040,color:#000000
```

## References

- [Agent Client Protocol](https://agentclientprotocol.com/)
- [ACP Protocol Details & Schema](https://agentclientprotocol.com/protocol)
- [xumux Specification](https://github.com/deftai/xumux)
- [JSON-RPC 2.0](https://www.jsonrpc.org/specification)

## Contributing

This specification lives in the xumux repository under the `docs/` directory.

We welcome:

- Editor integrations (VS Code, Zed, JetBrains, etc.)
- Agent-side SDKs (Go, Python, TypeScript, Rust)
- Conformance test suite and example implementations
- Feedback and PRs
