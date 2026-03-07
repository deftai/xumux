# ~~SocketPipe Extension: WebRTC Transport~~ — DEPRECATED

> **⚠️ This document is deprecated and should not be used.**
>
> OpenMux is **transport-agnostic by design**. WebRTC DataChannel is a first-class transport binding, documented in:
>
> → **[openmux-on-webrtc.md](openmux-on-webrtc.md)**
>
> OpenMux does not need a separate "WebRTC extension" because:
>
> - The **same frame format** works over any transport (WebRTC, WebSocket, TCP, stdio, QUIC)
> - WebRTC DataChannels map **1:1 to OpenMux channels** (labeled `omux/<channel-name>`), with native per-channel reliability
> - **No signaling protocol is defined by OpenMux** — signaling (SDP/ICE exchange) is the application's responsibility, typically done via a REST API or existing WebSocket before the DataChannel connects
> - Transport fallback (WebRTC → WebSocket) is an application-level concern, not a protocol concern
>
> **Migration**: Implementations using the old SocketPipe WebRTC extension should:
>
> 1. Use the standard OpenMux frame format over DataChannels (no changes needed — it's the same 6-byte header)
> 2. Handle SDP/ICE signaling in application code (not in the OpenMux protocol layer)
> 3. Refer to [openmux-on-webrtc.md](openmux-on-webrtc.md) for the transport binding specification
