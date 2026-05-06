# ~~SocketPipe Extension: Multiplexing~~ — DEPRECATED

> **⚠️ This document is deprecated and should not be used.**
>
> Multiplexing is a **core feature of xumux** and no longer needs a separate extension document.
> xumux provides native channel multiplexing including:
>
> - **2-byte Channel field in every frame header** (bytes 0–1) — all messages are inherently multiplexed
> - **OPEN_CHANNEL / CHANNEL_ACK / CHANNEL_REJECT / CLOSE_CHANNEL** — dynamic channel lifecycle on the control channel (0x0000)
> - **Per-channel reliability and ordering** — declared in HELLO or OPEN_CHANNEL (`reliable`, `ordered`, `maxRetransmits`)
> - **Channel IDs 1–65534** assigned by the server during HELLO/WELCOME or dynamically via OPEN_CHANNEL
> - **Channel 0x0000 (control)** is always implicit and carries all protocol messages
>
> See the [xumux README](../README.md) and core specification for full details.
>
> **Migration**: Any implementation using the old SocketPipe multiplexing extension should switch to native xumux channels. The concepts map directly:
>
> | Old SocketPipe Multiplexing | xumux Native |
> |---|---|
> | `CHANNEL_OPEN` (0x70) | `OPEN_CHANNEL` (0x03) |
> | `CHANNEL_OPEN_ACK` (0x71) | `CHANNEL_ACK` (0x04) |
> | `CHANNEL_CLOSE` (0x72) | `CLOSE_CHANNEL` (0x05) |
> | `CHANNEL_CLOSE_ACK` (0x73) | (not needed — CLOSE_CHANNEL is unilateral) |
> | `CHANNEL_WINDOW_UPDATE` (0x74) | (not yet specified — future extension) |
> | Reserved field as Channel ID | Dedicated 2-byte Channel field (offset 0) |
