# xumux Profile: Pipe

**Status**: Draft | **Profile**: `pipe/1` | **Core**: [0.2](../core.md)

A `pipe/1` channel carries one bidirectional byte stream, with half-close, between two endpoints. It is the building block for port forwarding, for `xumcat`, and for attaching a process's stdin/stdout to a channel.

## Opening

The channel request MUST set `reliable: true` and `ordered: true`, and MUST declare the profile in metadata:

```json
{
  "id": 3,
  "name": "ssh",
  "reliable": true,
  "ordered": true,
  "metadata": { "profile": "pipe/1", "target": "tcp:localhost:22" }
}
```

| Metadata | Type | Req. | Description |
|---|---|---|---|
| `profile` | string | MUST | `"pipe/1"` |
| `target` | string | MAY | Endpoint the responder should connect the pipe to, using the [endpoint address](#endpoint-addresses) syntax. If absent, the responder's own configuration decides. |

Before acknowledging, the responder connects the pipe to its end, for example by opening a TCP connection to `target`:

- If that succeeds, it sends CHANNEL_ACK.
- If the target is not allowed, it sends CHANNEL_REJECT `4010`.
- If the target cannot be reached, it sends CHANNEL_REJECT `4500` (TARGET_UNREACHABLE).

Responders MUST check `target` against an allow-list. An unrestricted `target` turns the responder into an open proxy.

## Messages

| Type | Name | Payload | Meaning |
|---|---|---|---|
| `0x01` | DATA | bytes | The next bytes of the stream. MUST NOT be fragmented. Send at most the peer's `maxFramePayload` per message. |
| `0x02` | EOF | empty | The sender will send no more DATA (half-close, like TCP FIN). |
| `0x03` | RESET | JSON `{code, reason?}` | The sender's end failed (connection refused, reset, process died). |

Other types MUST cause CLOSE_CHANNEL `1002`.

- Message boundaries carry no meaning. Receivers treat DATA as a continuous stream, and bridges may split or combine DATA messages freely. For the same reason DATA never needs fragmenting, which keeps the receiver's buffering down to single frames.
- After sending EOF, a side MUST NOT send DATA, but it keeps receiving.
- Once a side has both sent and received EOF, or has sent or received RESET, it closes the channel with CLOSE_CHANNEL (`1000` after EOFs, `1001` after RESET).
- Flow control ([core §6](../core.md#6-flow-control)) gives a pipe the same backpressure as the socket it represents. Implementations MUST only return credit as the bytes are actually written to their end.

## Mapping to sockets

| Socket event | Pipe message |
|---|---|
| bytes read | DATA |
| read returns EOF (peer sent FIN) | EOF |
| `ECONNRESET`, process exited abnormally | RESET |
| received EOF | `shutdown(SHUT_WR)` on the local socket |

## Endpoint addresses

`pipe/1` targets and `xumcat` share one address syntax, modelled on socat:

| Address | Meaning |
|---|---|
| `tcp:host:port` | TCP connect |
| `tcp-listen:port` | TCP listen |
| `tls:host:port` | TLS connect |
| `unix:/path` | Unix-socket connect |
| `unix-listen:/path` | Unix-socket listen |
| `stdio` | Current process's stdin/stdout |
| `exec:command args…` | Spawn a process and use its stdin/stdout |

xumux connections themselves are addressed by URL (`ws://`, `wss://`, `tcp+xumux://`, `stdio+xumux:`, …). That syntax is defined by the `xumcat` tool, not by this profile.

## Codes

| Code | Name |
|---|---|
| 4500 | TARGET_UNREACHABLE |

Profiles maintained in this repository use codes 4500–4599 ([registry](../registry.md)). They are outside the extension range because profiles do not change the core.
