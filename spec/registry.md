# xumux Registry

Every number and name assigned by the [core specification](core.md), its extensions and its profiles. To allocate a new value, open a pull request that adds a row here and links the defining document.

## Control types (channel 0, PROBE clear)

| Range / value | Use |
|---|---|
| `0x00` | Reserved |
| `0x01`–`0x07` | Core: HELLO, WELCOME, OPEN_CHANNEL, CHANNEL_ACK, CLOSE_CHANNEL, CHANNEL_REJECT, WINDOW_UPDATE |
| `0x08`–`0x1F` | Reserved for core |
| `0x20` | Core: CLOSE |
| `0x21`–`0x2F` | Reserved for core |
| `0x30`–`0x7F` | Extensions (allocated below) |
| `0x80`–`0xEF` | Reserved |
| `0xF0` | Core: ERROR |
| `0xF1`–`0xFF` | Reserved for core |

Control types `0x10` and `0x11` (PING and PONG in 0.1) are reserved and MUST NOT be reused. In 0.2, PING and PONG are probe types.

### Extension allocations

| Types | Extension | Document |
|---|---|---|
| `0x30`–`0x33` | `session-resume/1` | [extensions/session-resume.md](extensions/session-resume.md) |

## Probe types (any channel, PROBE set)

| Value | Use |
|---|---|
| `0x10` | PING |
| `0x11` | PONG |
| all others | Reserved; receivers discard |

## Flag bits

| Value | Use |
|---|---|
| `0x01` | `MORE` (core) |
| `0x02` | `PROBE` (core) |
| `0x04`–`0x80` | Reserved; usable only by a negotiated extension allocated here |

## Codes

| Range | Use |
|---|---|
| 1000–1003 | Core (aligned with RFC 6455) |
| 4000–4099 | Core (4000–4011 assigned) |
| 4100–4499 | Extensions (allocated below) |
| 4500–4599 | Profiles maintained in this repository (allocated below) |
| 4600–4999 | Applications, not registered |

| Codes | Owner |
|---|---|
| 4100–4103 | `session-resume/1` |
| 4500 | `pipe/1`: TARGET_UNREACHABLE |

## Extensions

| Name | Status | Document |
|---|---|---|
| `session-resume/1` | Design draft for 0.2, not for implementation | [extensions/session-resume.md](extensions/session-resume.md) |
| `webrtc-multichannel/1` | Draft | [extensions/webrtc-multichannel.md](extensions/webrtc-multichannel.md) |
| `quic-multistream/1` | Experimental, design draft, not for implementation | [extensions/quic-multistream.md](extensions/quic-multistream.md) |

## Bindings

| ID | Status | Document | Magic |
|---|---|---|---|
| `websocket` | Draft | [bindings/websocket.md](bindings/websocket.md) | No |
| `tcp` (incl. Unix sockets) | Draft | [bindings/tcp.md](bindings/tcp.md) | `XMUX` |
| `stdio` | Draft | [bindings/stdio.md](bindings/stdio.md) | `XMUX` |
| `webrtc` | Draft | [bindings/webrtc.md](bindings/webrtc.md) | No |
| `quic` | Experimental, design draft for 0.2, not for implementation | [bindings/quic.md](bindings/quic.md) | No |

## Profiles

| Name | Status | Document |
|---|---|---|
| `pipe/1` | Draft | [profiles/pipe.md](profiles/pipe.md) |

## Identifiers

| Identifier | Value |
|---|---|
| Magic bytes | `58 4D 55 58` ("XMUX") |
| WebSocket subprotocol | `xumux` |
| WebRTC DataChannel label (base binding) | `xumux` |
| WebRTC DataChannel protocol | `xumux` |
| QUIC ALPN / WebTransport path | `xumux` / `/xumux` |
