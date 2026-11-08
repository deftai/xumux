# xumux on WebSocket

**Status**: Draft | **Binding ID**: `websocket` | **Core**: [0.3](../core.md)

**Provides**: one message-pipe base path, reliable and ordered; subprotocol `xumux`, no magic.

WebSocket is the universal browser fallback and a good primary transport when UDP-style delivery is not needed (terminals, control-only applications).

## Transport

- The WebSocket subprotocol MUST be `xumux` (`Sec-WebSocket-Protocol: xumux`).
- All xumux data MUST use binary messages (opcode `0x2`). A text message MUST cause CLOSE `1002`.
- Each WebSocket message MUST contain exactly one complete xumux frame. Do not pack several frames into one message or split a frame across messages.
- The receiver MUST check that the message length equals 8 + Payload Length ([core §2.3](../core.md#23-frame-validation)).
- No magic bytes. The subprotocol identifies xumux.
- `wss://` MUST be used whenever channels carry sensitive data or HELLO carries `auth`.

## Endpoint

Servers SHOULD expose `wss://host/xumux`. Applications MAY use sub-paths, such as `wss://host/xumux/vroom`.

## Channel properties

All channels share one TCP stream, so every channel is effectively `reliable: true, ordered: true`, and that is what CHANNEL_ACK and WELCOME MUST report. All channels are therefore flow-controlled and may be fragmented. Applications that want "latest value wins" behaviour (for example pointer position) must drop stale messages themselves.

A packet lost in TCP delays every channel (head-of-line blocking). Senders SHOULD follow the scheduling guidance in [core §7](../core.md#7-fragmentation).

## Lifecycle

1. WebSocket upgrade with subprotocol `xumux`. Credentials MAY go in the upgrade request (cookies, headers) instead of HELLO `auth`.
2. HELLO / WELCOME.
3. Application data.
4. xumux CLOSE exchange, then a WebSocket close with code 1000 (or 1001 when going away). The xumux code carries the real reason.

If the WebSocket closes or fails without a completed xumux CLOSE exchange, the connection is dead (code `1001`), unless an extension such as [session-resume](../extensions/session-resume.md) keeps it.

## Keepalive

Use xumux keepalive ([core §8.2](../core.md#82-keepalive)). WebSocket ping/pong frames MAY also be used, but they are invisible to xumux.
