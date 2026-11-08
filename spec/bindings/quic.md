# xumux on QUIC and WebTransport

**Status**: Experimental, design draft, not for implementation | **Binding ID**: `quic` | **Core**: [0.3](../core.md)

**Provides** (proposed): one byte-stream base path (the session stream), reliable and ordered; ALPN `xumux`, no magic. [quic-multistream/1](../extensions/quic-multistream.md) would add one path per channel.

> This is a proposal that replaces the 0.1-era text. Normative keywords mark what the draft decides. Undecided points are listed in [Open questions](#open-questions), each with a recommendation. Implement the [websocket](websocket.md) or [webrtc](webrtc.md) binding first.

QUIC gives an encrypted (TLS 1.3), UDP-based connection that survives address changes (connection migration), with cheap independent streams and optional unreliable datagrams (RFC 9221). WebTransport exposes the same streams and datagrams to browsers over HTTP/3.

This document has two parts, following the [webrtc](webrtc.md) precedent:

- **The base binding** (this document) runs the whole xumux connection over **one** bidirectional QUIC stream. It is the TCP binding without magic bytes, with migration for free. The TypeScript [libxumux](https://github.com/deftai/libxumux) `QuicAdapter` already works this way.
- **[`quic-multistream/1`](../extensions/quic-multistream.md)**, a negotiated extension, gives individual channels their own QUIC stream (no head-of-line blocking between channels) or puts them on datagrams (natively unreliable and unordered).

## 1. Transport

| | Native QUIC | WebTransport |
|---|---|---|
| Identification | ALPN `xumux` | HTTP/3 extended CONNECT to the endpoint path (default `/xumux`). If WebTransport subprotocol negotiation is available, the protocol is `xumux`. |
| Streams | QUIC bidirectional streams | WebTransport bidirectional streams |
| Datagrams | RFC 9221 DATAGRAM frames | WebTransport datagrams |

- No magic bytes are sent. ALPN or the WebTransport endpoint identifies xumux.
- Encryption is always present. HELLO `auth` is allowed.
- Nothing in this binding depends on QUIC stream IDs, because the browser WebTransport API does not expose them.

## 2. The session stream

- The client opens a bidirectional stream and sends HELLO as the first bytes on it. This **session stream** carries channel 0 and every channel that does not have a path of its own. The client SHOULD open it before any other stream.
- The server identifies the session stream by its **first frame**: the first client-initiated bidirectional stream whose first frame is on channel 0 (HELLO, or an extension-defined first frame such as RESUME). Streams can arrive out of order, and WebTransport exposes neither stream IDs nor creation order, so arrival order and stream numbers MUST NOT be used. Until the session stream is found, the server MAY hold other client streams, bounded by count and by the HELLO timeout. Its HELLO timeout ([core §3.1](../core.md#31-rules)) runs from the QUIC or WebTransport session being established.
- A second stream whose first frame is on channel 0 MUST cause CLOSE `1002`.
- Frames are parsed from the byte stream exactly as in the [TCP binding](tcp.md#stream-framing): read 8 header bytes, apply [core §2.3](../core.md#23-frame-validation), read Payload Length bytes. Implementations MUST NOT assume that one read or one WebTransport chunk is one frame.
- Without an extension that defines them, any other stream the peer opens MUST be refused once the handshake has completed (or immediately, if it starts with anything other than a frame an extension could claim) (QUIC `STOP_SENDING` and `RESET_STREAM`, or the WebTransport equivalent), and datagrams MUST be discarded.

## 3. Channel properties

On the session stream every channel is effectively `reliable: true, ordered: true`, which CHANNEL_ACK and WELCOME MUST report. Flow control ([core §6](../core.md#6-flow-control)) and fragmentation ([core §7](../core.md#7-fragmentation)) apply exactly as on TCP. Head-of-line blocking between channels applies too, so senders SHOULD follow the scheduling guidance in core §7.

QUIC's own stream flow control also applies to the session stream. It limits the stream as a whole and does not replace xumux credit, which is what stops one channel from starving the others on a shared stream.

## 4. Lifecycle

1. QUIC handshake (or WebTransport session establishment).
2. The client opens the session stream. HELLO / WELCOME.
3. Application data.
4. The xumux CLOSE exchange on the session stream, then each side ends its send direction (FIN). The connection is then closed with QUIC application error code `0` (WebTransport: `close({closeCode: 0})`).

If the session stream is reset, or ends without a CLOSE exchange, or the QUIC connection closes, the xumux connection is dead (code `1001`).

## 5. Keepalive and migration

Use xumux keepalive ([core §8.2](../core.md#82-keepalive)). QUIC PING and idle timeout MAY also be used, but they are invisible to xumux. The QUIC idle timeout SHOULD be longer than xumux `pingInterval + pingTimeout`, so xumux is what decides the connection is dead.

Connection migration is transparent to xumux. After a migration the path is probably different, so RTT estimates from probes ([core §8.1](../core.md#81-ping-0x10-and-pong-0x11)) SHOULD be allowed to re-converge quickly. Implementations that see a migration event MAY reset their smoothing.

## 6. 0-RTT

0-RTT early data can be replayed by an attacker. HELLO is not idempotent in general: channels in HELLO can have side effects (a [`pipe/1`](../profiles/pipe.md) channel connects to a target), and `auth` might be single-use.

- A client MAY send HELLO in 0-RTT only if the HELLO opens no channels and the application has decided that replaying it is harmless.
- A server MUST NOT act on anything in 0-RTT data that is not safe to repeat. A server that cannot tell SHOULD reject 0-RTT.
- RESUME ([session-resume](../extensions/session-resume.md)) MUST NOT be sent in 0-RTT.

## 7. Endpoint

- Native QUIC: the port is chosen by the application. URI form for tools such as `xumcat`: `quic+xumux://host:port`.
- WebTransport: `https://host:port/xumux`. Applications MAY use sub-paths, such as `/xumux/vroom`. Port 443 (shared with HTTPS) or any other port.
- WebTransport requires a valid certificate. For development, browsers allow pinning with `serverCertificateHashes`.

## 8. Fallback

QUIC is often blocked (UDP filtered) and WebTransport is not available in every browser. Clients SHOULD fall back to WebRTC or WebSocket if no QUIC connection is established within 5 seconds. The application sees the same channels on any binding.

## Open questions

1. **Base binding plus extension, or one binding.** This draft splits the QUIC binding into a single-stream base and the `quic-multistream/1` extension, as WebRTC does. The single-stream mode is trivial to implement, already exists in libxumux, and bridges like TCP. The cost is that "plain QUIC" xumux still has head-of-line blocking between channels. *Recommendation:* keep the split. A server that wants multistream accepts the extension, and simple implementations stay simple.
2. **Magic bytes.** The libxumux `QuicAdapter` and the registry both say no magic on QUIC. Magic would catch a misconfigured ALPN or path, but ALPN already does that. *Recommendation:* no magic.
3. **0-RTT rules** ([§6](#6-0-rtt)). They are stricter than the 0.1 text, which called HELLO idempotent. *Recommendation:* keep them strict until an application needs 0-RTT and can say what is safe.
4. **URI scheme** `quic+xumux://` for native QUIC is a proposal for `xumcat`, by analogy with `tcp+xumux://`. *Recommendation:* adopt it in the xumcat tool, not in the spec.
