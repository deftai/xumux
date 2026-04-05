# ~~SocketPipe Extension: WebRTC Transport~~ — DEPRECATED

> **⚠️ This document is deprecated and should not be used.**
>
> xumux is **transport-agnostic by design**. WebRTC DataChannel is a first-class transport binding, documented in:
>
> → **[xumux-on-webrtc.md](xumux-on-webrtc.md)**
>
> xumux does not need a separate "WebRTC extension" because:
>
> - The **same frame format** works over any transport (WebRTC, WebSocket, TCP, stdio, QUIC)
> - WebRTC DataChannels map **1:1 to xumux channels** (labeled `omux/<channel-name>`), with native per-channel reliability
> - **No signaling protocol is defined by xumux** — signaling (SDP/ICE exchange) is the application's responsibility, typically done via a REST API or existing WebSocket before the DataChannel connects
> - Transport fallback (WebRTC → WebSocket) is an application-level concern, not a protocol concern
>
> **Migration**: Implementations using the old SocketPipe WebRTC extension should:
>
> 1. Use the standard xumux frame format over DataChannels (no changes needed — it's the same 6-byte header)
> 2. Handle SDP/ICE signaling in application code (not in the xumux protocol layer)
> 3. Refer to [xumux-on-webrtc.md](xumux-on-webrtc.md) for the transport binding specification
