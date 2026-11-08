# xumux behavioural conformance

`run.py` plays the client side of scripted exchanges against an implementation under test (IUT) acting as a server on the stdio binding. It checks the IUT's answers, and checks every frame the IUT sends against the spec. It uses only the Python standard library and shares no code with any implementation.

```sh
python3 -I conformance/behaviour/run.py [--features core,pipe] [--only TEXT] [-v] -- ADAPTER [ARGS...]
```

It exits non-zero if any scenario fails. `--features` lists what the IUT supports (`core` always; `pipe` for the pipe/1 profile), and scenarios that need anything else are skipped.

## Adapter contract

An adapter is a small program that runs the implementation as a **server** on its stdin and stdout (the [stdio binding](../../spec/bindings/stdio.md)). The runner starts it once per scenario as `ADAPTER [ARGS...] CONFIG`, where `CONFIG` is a JSON object. Each field it holds sets the matching server option, and the default applies to any field left out:

| Field | Meaning |
|---|---|
| `maxFramePayload`, `maxMessageSize`, `initialWindow` | The server's declared limits ([core §3.4](../../spec/core.md#34-limits)). |
| `maxChannels` | Cap on peer-opened channels; past it, refuse with `4002`. |
| `handshakeTimeoutMs` | HELLO timeout ([core §3.1](../../spec/core.md#31-rules)). |

The adapter must turn off its own keepalive PINGs (the runner answers them in any case). It accepts or refuses each channel the runner opens according to the channel's `name`:

| Name | Behaviour |
|---|---|
| `echo` | Send every message back with the same type and payload. |
| `sink` | Read and discard every message, so credit is returned. |
| `hold` | Accept, but never read: credit is never returned. |
| `pipe-echo` | Only with `metadata.profile` `pipe/1` (refuse with `4010` otherwise): a pipe/1 stream that writes every byte it reads back to itself, then sends EOF after the peer's EOF. Its local end is the pipe itself, with no buffer in between, so a byte counts as consumed (and its credit may be returned) only once its echo has been sent. |
| anything else | Refuse with `4010`. |

Nothing else may be written to stdout. Diagnostics go to stderr, and the runner shows the last line of stderr when a scenario fails.

Adapters exist for [libxumux-go](https://github.com/deftai/libxumux-go) (`make test/conformance XUMUX_DIR=...`) and [libxumux](https://github.com/deftai/libxumux) (`npm run test:conformance`).

## Invariants checked on every frame

Every scenario fails if the IUT:

- sends a payload above our `maxFramePayload` (65536 on channel 0), sets reserved flags, or sets `MORE` on channel 0 or on a probe;
- sends anything but WELCOME or CLOSE first, or a second WELCOME, or anything after its CLOSE;
- sends WELCOME `extensionParams` for an extension its WELCOME does not accept;
- sends more data on a channel than the credit we granted, or a WINDOW_UPDATE that is malformed, is for channel 0, or raises our credit above 2³¹−1;
- sends data or a probe on a channel it has not acknowledged or has closed, or sends WINDOW_UPDATE for a channel after its CLOSE_CHANNEL;
- changes the type mid-message, or sends a message above our `maxMessageSize`;
- on a pipe/1 channel, fragments a message, or sends DATA after its EOF;
- sends a control message that is not a JSON object or lacks a required field, or a PONG that answers none of our PINGs;
- echoes a message on a core channel with a different type or boundaries;
- stops reading its input for 10 seconds;
- fails to answer CLOSE with CLOSE, or does not close the transport after the CLOSE exchange.

The runner answers PINGs, refuses channels the IUT opens with `1003`, and replies to CLOSE_CHANNEL and CLOSE as the spec requires. It ignores WINDOW_UPDATEs and probes unless a step waits for them.

## Scenarios

`scenarios/*.json` are arrays of scenarios. Each one has a `name`, the `spec` sections it checks, optional `requires` (features), `config` (passed to the adapter), `ignore` (control types not to treat as unexpected, e.g. `"ERROR"`) and `timeout`, and a list of `steps`. A step is an object with one operation:

| Step | Effect |
|---|---|
| `hello: {...}` | Send HELLO (version 0.3, keepalive off, plus the given fields) and wait for WELCOME, which must contain `welcome` if given. With `"expectWelcome": false` it does not wait. |
| `helloRaw: "..."` | Send this HELLO payload as is. |
| `open: {...}`, `openRaw: {...}` | Send OPEN_CHANNEL and wait for its CHANNEL_ACK (`"expect": "none"` to not wait); `openRaw` sends it as is. |
| `send: {channel, bytes, type?, frameSize?, force?}` | Send one message of patterned bytes, fragmented to the IUT's `maxFramePayload` (or `frameSize`), waiting for credit unless `force`. On a pipe/1 channel, DATA is instead sent as several unfragmented DATA messages sized to the credit. |
| `sendEach: {channel, bytes, count}` | Send `count` such messages. |
| `frame: {...}`, `ctrl: {...}` | Send one raw frame, or one control message (`json` or `payloadHex`). |
| `grant`, `grantRaw` | Send a WINDOW_UPDATE (`{channel, bytes}`, or raw hex). |
| `returnCreditInSteps: {channel, step, until}` | Return credit for what arrives, `step` bytes per WINDOW_UPDATE, until `until` bytes have arrived. |
| `closeChannel: {id, code?}` | Close a channel and wait for the IUT's reply. |
| `ping: {channel, token}` | Send PING and wait for the matching PONG. |
| `close` | Close the connection; the IUT must answer CLOSE and end the transport. |
| `expectEcho`, `expectReceived`, `expectMessage` | Wait for echoed bytes (compared with what was sent), for an exact byte count, or for one complete message. |
| `expectCtrl`, `expectError`, `expectCloseChannel`, `expectClose` | Wait for a control message whose JSON contains the given fields. Any other control message arriving first is a failure. |
| `expectCredit`, `expectCreditAtMostEchoed` | Check the credit the IUT has returned. |
| `expectPipeEOF` | Wait for the IUT's pipe/1 EOF. |
| `expectAlive` | A PING on channel 0 is answered: the connection is still open. |
| `expectQuiet: ms` | No unexpected control frame arrives for `ms`. |

At the end of a scenario whose connection is still open, the runner closes it normally, so every scenario also checks the close handshake.

The suite does not include load or flood tests.
