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
- If the responder is at a resource limit shared with other channels, such as the number of running `exec:` processes, it sends CHANNEL_REJECT `4011` (BUSY).

Responders MUST check `target` against an allow-list ([Security considerations](#security-considerations)). An unrestricted `target` turns the responder into an open proxy.

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
- A received EOF takes effect only after every earlier DATA on the channel has been written to the local end. Implementations MUST keep that write queue through the CLOSE_CHANNEL exchange, and close the local end only once it has drained.

### Implementation notes

Both rules above are easy to break with a general-purpose channel API:

- **Size DATA to the credit.** Core flow control lets a sender fragment a message to fit its remaining credit ([core §6](../core.md#6-flow-control)). DATA may not be fragmented, so a pipe sender sends at most `min(credit, maxFramePayload)` bytes in each DATA, and the rest in later DATA once credit returns. A send call that fragments when credit runs short produces fragmented DATA. Because boundaries carry no meaning, splitting the bytes costs nothing.
- **Return credit after the local write.** The bytes of a DATA are consumed when the write to the local end (socket, process stdin) has completed, not when they reach an intermediate buffer. An adapter that exposes the channel as a stream must return credit only after the copy's write returns. Returning it earlier lets a slow local end make the receiver buffer without bound, and the sender never feels backpressure.

## Mapping to sockets

| Socket event | Pipe message |
|---|---|
| bytes read | DATA |
| read returns EOF (peer sent FIN) | EOF |
| `ECONNRESET`, process exited abnormally | RESET |
| received EOF | `shutdown(SHUT_WR)` on the local socket, after earlier DATA has been written |

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

## Security considerations

`target` is chosen by the peer and MUST be treated as attacker-controlled input. A responder that connects pipes on request lends every peer that can open a channel its own network position, filesystem and privileges: hosts behind its firewall, services on its loopback interface, its Unix sockets, and through `exec:` any command it can run. Responders reachable by untrusted peers SHOULD also authenticate them ([core §3.7](../core.md#37-rejection)).

### Allow-list

A responder MUST check every `target` against an allow-list before connecting, and MUST reject targets that do not match with `4010`. The safest configuration ignores `target` and uses one configured endpoint. Listening addresses (`tcp-listen:`, `unix-listen:`) SHOULD NOT be allowed, since they let a peer open ports on the responder.

If the allow-list has wildcard patterns, the responder MUST parse the target as an [endpoint address](#endpoint-addresses) and match it field by field, never as one string:

| Field | Rule |
|---|---|
| kind | Exact. |
| host | Wildcards MUST NOT match `.`, so `tcp:api.example.*:443` does not match `api.example.attacker.net`. Names compare case-insensitively, ignoring a trailing `.`. |
| host, IP pattern | A host pattern that is an IP address or IP wildcard MUST match only IP literals, never a DNS name: `10.0.0.*` must not match `10.0.0.example`, which a resolver search path can send anywhere. Exact IPs compare by value (`::1` equals `0::1`). |
| port | A decimal number from 1 to 65535, in canonical form. |
| unix path | The target MUST be an absolute, clean path (no `.` or `..` segments, `//` or trailing `/`), or the responder refuses it. Wildcards MUST NOT match `/`. Abstract socket names (`@name`) exist only on Linux; elsewhere `@name` is a relative path and MUST be refused. |
| exec command | The arguments are chosen by the peer. `exec:` targets MUST be matched exactly against the whole command line, never with wildcards: `exec:ls *` would admit `exec:ls ; rm -rf ~` where commands run through a shell. |

An allowed DNS name does not constrain the address it resolves to. Responders that must not reach certain networks SHOULD check the resolved address as well.

### Resource limits

Each pipe holds a socket or process on the responder. Responders SHOULD bound:

| Resource | When exceeded |
|---|---|
| Concurrent connections | CLOSE `4011` instead of WELCOME |
| Channels per connection ([core §5.2](../core.md#52-opening-a-channel)) | CHANNEL_REJECT `4002` |
| Running `exec:` processes, across all connections | CHANNEL_REJECT `4011` |

## Codes

| Code | Name |
|---|---|
| 4500 | TARGET_UNREACHABLE |

Profiles maintained in this repository use codes 4500–4599 ([registry](../registry.md)). They are outside the extension range because profiles do not change the core.
