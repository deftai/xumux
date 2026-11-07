# xumux Extension: WebRTC Multichannel

**Status**: Draft | **Extension**: `webrtc-multichannel/1` | **Binding**: [webrtc](../bindings/webrtc.md) | **Core**: [0.2](../core.md)

The base WebRTC binding sends every channel over one reliable, ordered DataChannel. This extension lets individual channels have **their own DataChannel**, so they get native unreliable or unordered delivery from SCTP. That matters for things like pointer movement, where a stale packet is worse than a lost one.

## Negotiation

The client lists `webrtc-multichannel/1` in HELLO `extensions`. It only applies if the server accepts it in WELCOME. Without it, the base binding applies unchanged.

## Which channels get a DataChannel

A channel gets its own DataChannel ("dedicated") only if its opener creates one, and the opener SHOULD only do so when the requested properties are not both `reliable` and `ordered`. Channels without a dedicated DataChannel continue over the base `xumux` DataChannel. The control channel always stays on the base DataChannel.

## Labels

A dedicated DataChannel has the label `xumux/<id>`, where `<id>` is the decimal xumux channel ID (`xumux/3`), and its protocol is `xumux`.

Because the opener chooses the channel ID ([core §5.1](../core.md#51-channel-ids)), the label identifies the channel the moment the DataChannel appears, with no lookup by name.

The DataChannel's reliability options come from the channel request:

| Request | DataChannel options |
|---|---|
| `ordered` | `ordered` |
| `maxRetransmits` | `maxRetransmits` |
| `maxPacketLifeTime` | `maxPacketLifeTime` |
| `reliable: false` and neither of the above | `maxRetransmits: 0` |

The effective properties reported in CHANNEL_ACK or WELCOME are the dedicated DataChannel's actual options.

## Opening

**Channels in HELLO.** The client MAY create dedicated DataChannels for its HELLO channels before sending HELLO, in the same SDP offer. Then:

- If the server accepts the extension, it uses those DataChannels for the matching channels.
- If the server does not accept it, the server MUST ignore them (it MAY close them), and those channels run over the base DataChannel with reliable, ordered properties. The client closes any it has left after reading WELCOME.
- If the server rejects a channel, the client closes its DataChannel.

**OPEN_CHANNEL after the handshake.**

1. The opener creates `xumux/<id>`, then sends OPEN_CHANNEL on the base DataChannel.
2. The responder MUST NOT send CHANNEL_ACK until that DataChannel is open on its side. If the DataChannel has not appeared within 10 seconds, it rejects with `4010`.
3. To reject, the responder sends CHANNEL_REJECT and closes the DataChannel.

## Framing on a dedicated DataChannel

- Every frame for the channel (data and probes) MUST be sent on its dedicated DataChannel, and MUST still carry the correct Channel field so that bridges can relay it.
- A frame whose Channel field does not match the DataChannel's label MUST be discarded.
- Control frames MUST NOT be sent on a dedicated DataChannel.
- Flow control applies when the effective properties are `reliable` ([core §6](../core.md#6-flow-control)). Fragmentation is allowed only when they are both `reliable` and `ordered` ([core §7](../core.md#7-fragmentation)). A reliable but unordered DataChannel is therefore flow-controlled but never fragmented.
- Each side binds a channel to the specific DataChannel **object** it was opened with, not to its label. Frames arriving on any other DataChannel with the same label MUST be discarded.

## Closing

- The usual two-step CLOSE_CHANNEL exchange runs on the base DataChannel. When it completes, the opener closes the dedicated DataChannel.
- On this binding a channel is not fully closed, and its ID MUST NOT be reused, until its dedicated DataChannel has fired `close` on the opener's side. Frames on the old DataChannel are not ordered relative to channel 0, so this stops late frames from being attributed to a new channel with the same ID.
- These rules apply only once the extension has been accepted. Closing DataChannels that were created before a declined HELLO is not a channel event.
- If a dedicated DataChannel closes unexpectedly, the side that notices MUST send CLOSE_CHANNEL with code `1001` for that channel.
- If the base DataChannel closes, the whole connection is dead.

## Bridging

A bridge between this extension and a single-stream transport (WebSocket, TCP) moves frames between the dedicated DataChannels and the single stream unchanged. When doing so it MUST report, toward each side, the properties that side will actually get.
