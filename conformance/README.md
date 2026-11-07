# xumux conformance vectors

`vectors.json` is generated. Do not edit it by hand; change the generator and regenerate:

```sh
python3 -I conformance/gen_vectors.py > conformance/vectors.json
```

## Format

- `valid[]`: each entry has `hex` (the exact wire bytes) and `decoded` (what a decoder must produce). Implementations should check both directions: decoding `hex` gives `decoded`, and encoding `decoded` gives `hex`. JSON payloads (`payloadJson`) are compared as values, not as bytes.
- `invalid[]`: each entry has `hex` and `expect`, the action the receiver must take (`close` with a `code`, or `close-transport`). `state` says where the connection must be when the bytes arrive: `start` (before anything is read), `awaiting-hello` (a fresh server) or `connected` (after the handshake). An entry may also restrict itself to particular `bindings` or a `receiver` role.

The vectors cover the frame layer and individual control messages. Behavioural tests (handshake order, two-step close, flow-control accounting, keepalive) are not yet included and are planned as scripted exchanges.
