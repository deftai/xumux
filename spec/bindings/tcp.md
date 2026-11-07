# xumux on TCP and Unix sockets

**Status**: Draft | **Binding ID**: `tcp` | **Core**: [0.2](../core.md)

For server-to-server links, local daemons and IPC. Unix domain stream sockets follow exactly the same rules.

## Transport

- A TCP stream socket, optionally under TLS, or a Unix domain stream socket (`SOCK_STREAM`).
- TLS SHOULD be used for TCP whenever channels carry sensitive data, and MUST be used if HELLO carries `auth` across a network. Unix sockets rely on file-system permissions instead.

## Magic bytes

Each side MUST send the 4 bytes `58 4D 55 58` ("XMUX") before its first frame. Each side MUST read and check the peer's 4 magic bytes before parsing any frame. On a mismatch it MUST close the transport immediately without sending anything. A peer sending `OMUX` is speaking xumux 0.1.

## Stream framing

TCP has no message boundaries, so frames are parsed from the byte stream:

1. Read 8 header bytes, which may take several reads.
2. If Payload Length exceeds the receiver's `maxFramePayload`, close with `4005` without reading further ([core §2.3](../core.md#23-frame-validation)).
3. Read exactly Payload Length bytes.
4. Repeat.

Implementations MUST handle short reads and frames split across reads, and MUST NOT assume one read returns one frame.

## Channel properties

As with WebSocket, every channel is effectively `reliable: true, ordered: true`. Head-of-line blocking applies, so follow the scheduling guidance in [core §7](../core.md#7-fragmentation).

## Endpoint

Ports are chosen by the application. URI form for tools such as `xumcat`: `tcp:host:port`, `tls:host:port`, `unix:/path/to/socket`.

## Close

After the xumux CLOSE exchange, each side shuts down its write half and closes the socket.

## Keepalive

Use xumux keepalive. `SO_KEEPALIVE` MAY also be used to detect dead peers at the transport level.
