# xumux on WebRTC DataChannels

**Status**: Draft | **Binding ID**: `webrtc` | **Core**: [0.2](../core.md)

WebRTC gives browsers low-latency, encrypted (DTLS) and NAT-traversing connections, and DataChannels can sit beside audio and video tracks on the same PeerConnection.

This base binding runs the whole xumux connection over **one** reliable, ordered DataChannel. It is the simplest binding to implement and the easiest to bridge to other transports. To give individual channels their own DataChannel with native unreliable or unordered delivery (for example pointer movement), negotiate the [`webrtc-multichannel/1`](../extensions/webrtc-multichannel.md) extension on top of it.

## Signaling

xumux does not define signaling. SDP and ICE exchange happen before xumux starts, over whatever the application uses. The signaling channel is disposable, and once the DataChannel is open nothing else needs to stay up.

### Recommended: HTTP POST

```
Client                                  Server
  │── POST /offer {sdp, candidates} ──────►│
  │◄── 200 {sdp, candidates} ──────────────│
  │     ... ICE + DTLS, DataChannel opens ...
```

- `POST /offer`: the body is `{"type":"offer","sdp":"...","candidates":[...]}` and the response is `{"type":"answer","sdp":"...","candidates":[...]}`. Bundling all candidates allows a single round trip.
- `POST /candidate`: optional trickle ICE, one `{"candidate","sdpMid","sdpMLineIndex"}` per request. The server sends its candidates by SSE or polling.

## The DataChannel

The client creates the DataChannel before creating the offer:

```js
pc.createDataChannel("xumux", { negotiated: true, id: 0, ordered: true, protocol: "xumux" })
```

- The label MUST be `xumux` and the protocol MUST be `xumux`.
- It MUST be reliable and ordered (no `maxRetransmits` or `maxPacketLifeTime`).
- `negotiated: true, id: 0` is RECOMMENDED so that both sides create the channel without waiting for an in-band open. If it is used, the server creates the same channel with the same options.
- No magic bytes are sent; the label and protocol identify xumux.

## Framing

- Each DataChannel message MUST contain exactly one complete xumux frame, sent as binary (ArrayBuffer or Blob, never a string).
- The receiver MUST check that the message length equals 8 + Payload Length.
- Peers SHOULD declare a `maxFramePayload` no larger than the SCTP maximum message size from the SDP (`a=max-message-size`) minus 8, and SHOULD use 65536 when that value is not known. Browsers differ, and 64 KiB works everywhere current.

## Channel properties

Everything travels over one reliable, ordered DataChannel, so every channel is effectively `reliable: true, ordered: true`, exactly as on WebSocket. With `webrtc-multichannel/1`, channels that have their own DataChannel take that DataChannel's properties instead.

## Lifecycle

1. Signaling (SDP and ICE).
2. DTLS completes and the `xumux` DataChannel opens.
3. HELLO / WELCOME on the DataChannel.
4. Application data.
5. xumux CLOSE exchange, then close the DataChannel. Close the PeerConnection too, unless it carries other things such as media tracks.

If the `xumux` DataChannel closes unexpectedly, the connection is dead.

## Media tracks

The PeerConnection MAY carry audio and video tracks next to the DataChannel. xumux neither uses them nor interferes with them. One SDP exchange, one ICE negotiation and one DTLS handshake cover everything.

```
PeerConnection
├── MediaTrack: video          ← application (e.g. VROOM-Graphical)
├── MediaTrack: audio
└── DataChannel: xumux         ← all xumux channels
```

## Fallback

If WebRTC fails (ICE timeout, firewall, no TURN server), implementations SHOULD fall back to the [WebSocket binding](websocket.md). The application sees the same channels either way. A RECOMMENDED timeout is 10 seconds from sending the offer to the DataChannel opening.

## Security

- DataChannels are always encrypted with DTLS.
- TURN credentials MUST be short-lived and scoped to the session.
- Servers SHOULD check that the signaling identity matches the DTLS peer, by comparing the fingerprint from SDP.
