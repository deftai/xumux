# ~~SocketPipe Extension: Multiplexing~~ — DEPRECATED

> **⚠️ This document is deprecated and should not be used.**
>
> Multiplexing is a **core feature of OpenMux** and no longer needs a separate extension document.
> OpenMux provides native channel multiplexing including:
>
> - **Channel byte in every frame header** (byte 0) — all messages are inherently multiplexed
> - **OPEN_CHANNEL / CHANNEL_ACK / CHANNEL_REJECT / CLOSE_CHANNEL** — dynamic channel lifecycle on the control channel (0x00)
> - **Per-channel reliability and ordering** — declared in HELLO or OPEN_CHANNEL (`reliable`, `ordered`, `maxRetransmits`)
> - **Channel IDs 1–254** assigned by the server during HELLO/WELCOME or dynamically via OPEN_CHANNEL
> - **Channel 0 (control)** is always implicit and carries all protocol messages
>
> See the [OpenMux README](../README.md) and core specification for full details.
>
> **Migration**: Any implementation using the old SocketPipe multiplexing extension should switch to native OpenMux channels. The concepts map directly:
>
> | Old SocketPipe Multiplexing | OpenMux Native |
> |---|---|
> | `CHANNEL_OPEN` (0x70) | `OPEN_CHANNEL` (0x03) |
> | `CHANNEL_OPEN_ACK` (0x71) | `CHANNEL_ACK` (0x04) |
> | `CHANNEL_CLOSE` (0x72) | `CLOSE_CHANNEL` (0x05) |
> | `CHANNEL_CLOSE_ACK` (0x73) | (not needed — CLOSE_CHANNEL is unilateral) |
> | `CHANNEL_WINDOW_UPDATE` (0x74) | (not yet specified — future extension) |
> | Reserved field as Channel ID | Dedicated Channel byte (offset 0) |
