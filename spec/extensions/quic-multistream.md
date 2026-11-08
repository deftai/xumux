# xumux Extension: QUIC Multistream

**Status**: Experimental, design draft, not for implementation | **Extension**: `quic-multistream/1` | **Binding**: [quic](../bindings/quic.md) | **Core**: [0.2](../core.md)

> This is a proposal. Normative keywords mark what the draft decides. Undecided points are listed in [Open questions](#open-questions), each with a recommendation.

The base [QUIC binding](../bindings/quic.md) sends every channel over one session stream. This extension lets a channel have **its own QUIC stream**, so loss on one channel does not delay the others, or travel on **QUIC datagrams**, which makes it natively unreliable and unordered. It is the QUIC counterpart of [`webrtc-multichannel/1`](webrtc-multichannel.md), and follows it wherever QUIC allows.

## 1. Negotiation

The client lists `quic-multistream/1` in HELLO `extensions`. It applies only if WELCOME accepts it. Without it, the base binding applies unchanged.

## 2. Choosing a path

The opener chooses each channel's **path** with a `quic` field in the channel request (OPEN_CHANNEL, or the channel's entry in HELLO):

| `quic` | Path | Effective properties |
|---|---|---|
| absent | the session stream | `reliable: true, ordered: true` |
| `"stream"` | a dedicated bidirectional stream | `reliable: true, ordered: true` |
| `"datagram"` | QUIC datagrams | `reliable: false, ordered: false, maxRetransmits: 0` |

- An opener SHOULD request `"datagram"` only for channels that ask for `reliable: false`, and MUST NOT request it unless the peer supports datagrams (QUIC transport parameter `max_datagram_frame_size` > 0, or WebTransport datagrams available).
- The responder MAY place a channel on the session stream instead of the requested path. When the request had a `quic` field, its CHANNEL_ACK (or WELCOME entry) MUST include `quic` with the path actually used (`"session"`, `"stream"` or `"datagram"`), along with the effective properties. If it chose the session stream for a `"stream"` request, it need not wait for the opener's stream ([§3.2](#32-opening)), and resets that stream if it arrives.
- Channel 0 always uses the session stream.
- **Frames must arrive on their channel's path.** A receiver MUST discard a frame (data or probe) that arrives on a path other than the one its channel uses: a datagram for a channel on a stream, a frame on the session stream for a channel with a dedicated stream or on datagrams, and any datagram for channel 0.

## 3. Dedicated streams

### 3.1 Identifying the stream

QUIC streams carry no label, and WebTransport does not expose stream IDs, so the channel is identified by the stream's **first frame**:

- The opener creates a new bidirectional stream and immediately writes, as the stream's first frame, a **binding PING**: a PING ([core §8.1](../core.md#81-ping-0x10-and-pong-0x11)) whose Channel field is the channel's ID, and whose token the opener also puts in the request as `"streamToken"`: a JSON integer from 0 to 4294967295, the PING token read as a big-endian unsigned 32-bit number. The token MUST differ from the token of any earlier stream the opener created for the same ID in this connection. The responder matches a stream to a request by **ID and token**, so a delayed stream from an earlier, rejected attempt can never be bound to a later request with the same ID. Writing it makes the stream visible to the peer, and the opener chooses the ID ([core §5.1](../core.md#51-channel-ids)), so the stream identifies its channel the moment it arrives. This PING is exempt from the rule that an opener sends no probes before CHANNEL_ACK.
- A stream whose first frame is not a PING, whose PING names an ID of the wrong parity, or whose ID and token match no pending or future request (see the holding rule in [§3.2](#32-opening)), MUST be reset and ignored.
- The responder answers the binding PING with a PONG on the stream after it has sent CHANNEL_ACK. The pair is an ordinary RTT sample.

### 3.2 Opening

1. The opener creates the stream and writes the binding PING, then sends OPEN_CHANNEL (with `"quic": "stream"`) on the session stream. The two can arrive in either order.
2. To accept the channel on its dedicated stream, the responder MUST NOT send CHANNEL_ACK until the stream with the matching ID and token has arrived. If it has not arrived within 10 seconds, the responder either rejects the channel with `4010` or accepts it on the session stream (`"quic": "session"`). It MAY place the channel on the session stream at once, without waiting, for example when it is at its stream limit. A stream that arrives before its OPEN_CHANNEL is held for up to 10 seconds, then reset. The responder MAY limit how many streams it holds this way to its channel limit. A stream that arrives for a request that was already rejected or placed on the session stream is reset.
3. To reject, the responder sends CHANNEL_REJECT and resets the stream.
4. After CHANNEL_ACK, the responder sends on the stream's other direction. Frames that overtake the ACK are held by the opener, as [core §5.2](../core.md#52-opening-a-channel) already requires.

**Channels in HELLO.** The client MAY create dedicated streams for its HELLO channels right after opening the session stream. Streams can arrive in any order, so the server finds the session stream by its first frame ([quic §2](../bindings/quic.md#2-the-session-stream)) and holds streams that start with a binding PING until it has read HELLO. If the server accepts the extension, it uses them, and waits for them before WELCOME as in step 2. If it does not accept the extension, it resets them, and those channels run over the session stream.

### 3.3 Framing on a dedicated stream

- Frames are parsed from the stream as on the session stream. Every frame for the channel (data and probes) MUST be sent on its stream, and MUST still carry the correct Channel field so that bridges can relay it.
- A frame whose Channel field does not match the stream's channel MUST be discarded. Control frames MUST NOT be sent on a dedicated stream.
- Each side binds a channel to the specific stream **object** it was opened with. Frames on any other stream are never attributed to it.
- Fragmentation is allowed ([core §7](../core.md#7-fragmentation)).

### 3.4 Flow control

A dedicated stream is flow-controlled **by QUIC, not by xumux credit**:

- [Core §6](../core.md#6-flow-control) does not apply to channels on a dedicated stream. Senders do not wait for xumux credit, and a WINDOW_UPDATE entry for such a channel MUST cause CLOSE `1002`, as for an unreliable channel.
- The receiver provides the backpressure. It MUST bound what it buffers for each dedicated channel (to at least the receiver's `maxMessageSize`, so a whole message always fits), and MUST stop reading the stream while that bound is reached. QUIC stream flow control then stops the sender.
- `maxFramePayload` and `maxMessageSize` still apply.

Rationale and the alternative are in [Open question 1](#open-questions).

### 3.5 Closing

- The usual two-step CLOSE_CHANNEL exchange runs on the session stream. A side that has sent CLOSE_CHANNEL ends its direction of the dedicated stream (FIN) after its last frame. Once it has also received the peer's CLOSE_CHANNEL, it MAY stop reading (`STOP_SENDING`).
- The ID can be reused when core §5.4 says, with no extra wait. Every stream of the earlier use was bound before its CHANNEL_ACK was sent (step 2 above), and frames on an old stream are tied to that stream object, so they can never be attributed to a new channel with the same ID.
- If a dedicated stream is reset unexpectedly, the side that notices MUST send CLOSE_CHANNEL `1001` for the channel.

## 4. Datagram channels

- Each datagram carries exactly one complete frame, including its 8-byte header. The receiver MUST check that the datagram length equals 8 + Payload Length ([core §2.3](../core.md#23-frame-validation)). The Channel field identifies the channel.
- A frame MUST fit in one datagram. For a datagram channel the largest payload a sender may send is the smaller of the peer's `maxFramePayload` and the current maximum datagram size minus 8 (WebTransport: `datagrams.maxDatagramSize`). Datagram channels cannot be fragmented, so a larger message cannot be sent, and the implementation reports that to the application.
- Datagram channels are not flow-controlled, since they are unreliable ([core §6](../core.md#6-flow-control)).
- Probes on a datagram channel are sent as datagrams. A lost probe is part of the loss measurement ([core §8.1](../core.md#81-ping-0x10-and-pong-0x11)).
- Datagrams for a channel that is not open are discarded ([core §5.5](../core.md#55-frames-on-unknown-channels)). Datagrams that overtake the CHANNEL_ACK are held by the opener, as for any channel ([core §5.2](../core.md#52-opening-a-channel)).
- **ID reuse.** A datagram carries nothing but the channel ID, so a datagram delayed in the network could be attributed to a later channel with the same ID. On this extension a datagram channel is therefore not fully closed, and its ID MUST NOT be reused, until at least 2 seconds after core §5.4 would free it.

## 5. Bridging

Frames on dedicated streams and datagrams carry their full header, so a bridge can move them to a single-stream binding unchanged. Flow control is the exception. A channel on a dedicated stream has no xumux credit, while the same channel on WebSocket or TCP needs it. A bridge between the two MUST therefore be a flow-control endpoint for such channels: it grants and consumes credit on the credit-based side, and applies backpressure by reading the QUIC stream on the other. As with webrtc-multichannel, it reports toward each side the properties that side will actually get.

## Open questions

1. **xumux credit on dedicated streams.** QUIC already flow-controls each stream and the connection. The options are:
   - **(A) Keep xumux credit everywhere.** This is uniform: core §6 is unchanged, the 0.2 implementations' credit code is reused, and a bridge can forward WINDOW_UPDATE. But every channel gets two windows, the effective one is the smaller, and auto-tuning runs twice. Worse, WINDOW_UPDATE travels on the session stream, so a lost packet on the session stream stalls credit for every channel. That brings back the cross-channel head-of-line blocking that dedicated streams exist to remove.
   - **(B) QUIC flow control only (this draft).** There is one window, tuned by QUIC, with no control traffic and no shared stall point. The costs: an extension now changes the scope of core §6 (which extensions are allowed to do), a receiver must back-pressure by not reading (which the 0.2 implementations, with their single eager read loop, do not do yet), and bridges to credit-based bindings must terminate flow control (§5).
   - **(C) Per-channel choice**, negotiated in the request. That gives the most flexibility and the most to test.

   **Decided (2026-11-08): (B).** Avoiding cross-channel head-of-line blocking is the only reason to use dedicated streams, and (A) gives it back through WINDOW_UPDATE.
2. **Bidirectional stream with a binding PING, or two unidirectional streams.** If each side opened its own unidirectional stream when it first sends, the channel would be identified by an ordinary first frame with no PING exemption. But a stream of an earlier channel instance could then arrive after its ID was reused, so a channel needs a quarantine or an incarnation number. It also uses twice as many streams. *Recommendation:* a bidirectional stream with a binding PING, as drafted.
3. **Datagram ID quarantine.** A fixed 2 seconds is simple but arbitrary, and a datagram delayed longer is still misattributed. The alternatives are a per-instance tag in each datagram (which changes the frame on this path, so bridges must rewrite it), or a separate ID range for datagram channels. *Recommendation:* the quarantine, plus a SHOULD for applications to tolerate one stray message after reuse on unreliable channels, which they already must for loss and duplication.
4. **Reliable, unordered channels.** QUIC has no native reliable-unordered primitive. One stream per message would provide it, at a cost of many streams. *Recommendation:* map them to a dedicated (ordered) stream, report `ordered: true`, and revisit if an application needs it.
5. **Priorities.** QUIC and WebTransport (`sendOrder`) support stream priorities, and xumux has none. *Recommendation:* leave priorities to implementations for now, and consider a channel `priority` hint in the request later.
6. **Session resume.** Connection migration covers most of what [session-resume](session-resume.md) is for. Resuming across QUIC connections with dedicated streams would need streams re-created before replay. *Recommendation:* do not combine them in the first version. Session-resume closes channels with dedicated paths on resume, as its draft proposes.
7. **Responder override.** §2 lets the responder put a channel on the session stream instead of the requested path, and reports that in `quic`. That is the only new field in CHANNEL_ACK. *Recommendation:* keep it. It lets a server without datagram support, or one at its stream limit, still accept the channel.
