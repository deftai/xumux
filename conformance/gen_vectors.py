#!/usr/bin/env python3
"""Generate conformance/vectors.json for xumux v0.2.

Run:  python3 -I conformance/gen_vectors.py > conformance/vectors.json

JSON payloads are serialized compactly (no whitespace, keys in the order
written here). Decoders MUST accept any valid JSON; encoders are only
required to match these bytes when comparing against the vectors.
"""
import json
import struct
import sys

MORE = 0x01
PROBE = 0x02


def frame(channel, type_, flags, payload=b""):
    return struct.pack(">HBBI", channel, type_, flags, len(payload)) + payload


def js(obj):
    return json.dumps(obj, separators=(",", ":")).encode()


def hx(b):
    return " ".join(f"{x:02X}" for x in b)


valid = []
invalid = []


def ok(name, desc, data, decoded):
    valid.append({"name": name, "description": desc, "hex": hx(data), "decoded": decoded})


def bad(name, desc, data, expect, state="connected"):
    # state: "start" (before any frame), "awaiting-hello" (fresh server), or "connected" (after the handshake)
    invalid.append({"name": name, "description": desc, "state": state, "hex": hx(data), "expect": expect})


def fr(channel, type_, flags, payload_hex=None, payload_json=None):
    d = {"channel": channel, "type": type_, "flags": flags}
    if payload_json is not None:
        d["payloadJson"] = payload_json
    else:
        d["payloadHex"] = payload_hex or ""
    return d


# ── Magic ───────────────────────────────────────────────────────────────────
ok("magic", "Magic bytes 'XMUX', sent once before the first frame on stream bindings (TCP, Unix, stdio). Not a frame.",
   b"XMUX", {"magic": "XMUX"})

# ── Handshake ───────────────────────────────────────────────────────────────
h = {"version": [0, 2, 0]}
ok("hello-minimal", "Minimal HELLO.", frame(0, 0x01, 0, js(h)), fr(0, 0x01, 0, payload_json=h))

h2 = {"version": [0, 2, 0], "application": "vroom-terminal/1",
      "channels": [{"id": 1, "name": "data", "reliable": True, "ordered": True}]}
ok("hello-with-channel", "HELLO requesting one channel; the client picks odd ID 1.",
   frame(0, 0x01, 0, js(h2)), fr(0, 0x01, 0, payload_json=h2))

w = {"version": [0, 2, 0]}
ok("welcome-minimal", "Minimal WELCOME.", frame(0, 0x02, 0, js(w)), fr(0, 0x02, 0, payload_json=w))

w2 = {"version": [0, 2, 0], "channels": [{"id": 1, "reliable": True, "ordered": True}],
      "rejected": [{"id": 3, "code": 4010, "reason": "unknown channel name"}]}
ok("welcome-accept-reject", "WELCOME accepting channel 1 and rejecting channel 3.",
   frame(0, 0x02, 0, js(w2)), fr(0, 0x02, 0, payload_json=w2))

# ── Channel lifecycle ───────────────────────────────────────────────────────
o = {"id": 2, "name": "file", "reliable": True, "ordered": True}
ok("open-channel-server", "Server opens a channel; servers pick even IDs.",
   frame(0, 0x03, 0, js(o)), fr(0, 0x03, 0, payload_json=o))

a = {"id": 2, "reliable": True, "ordered": True}
ok("channel-ack", "CHANNEL_ACK reporting effective properties.",
   frame(0, 0x04, 0, js(a)), fr(0, 0x04, 0, payload_json=a))

c = {"id": 2}
ok("close-channel", "CLOSE_CHANNEL (minimal). The peer answers with its own CLOSE_CHANNEL.",
   frame(0, 0x05, 0, js(c)), fr(0, 0x05, 0, payload_json=c))

r = {"id": 5, "code": 4002}
ok("channel-reject", "CHANNEL_REJECT: channel limit reached.",
   frame(0, 0x06, 0, js(r)), fr(0, 0x06, 0, payload_json=r))

# ── Flow control ────────────────────────────────────────────────────────────
wu = struct.pack(">HI", 1, 65536)
ok("window-update", "WINDOW_UPDATE granting 65536 bytes on channel 1.",
   frame(0, 0x07, 0, wu), {**fr(0, 0x07, 0, hx(wu)), "entries": [{"channel": 1, "increment": 65536}]})

wu2 = struct.pack(">HIHI", 1, 4096, 2, 32768)
ok("window-update-batched", "WINDOW_UPDATE with two entries.",
   frame(0, 0x07, 0, wu2),
   {**fr(0, 0x07, 0, hx(wu2)), "entries": [{"channel": 1, "increment": 4096}, {"channel": 2, "increment": 32768}]})

# ── Probes ──────────────────────────────────────────────────────────────────
t = struct.pack(">I", 1000)
ok("ping-control", "PING on channel 0, token 1000.", frame(0, 0x10, PROBE, t), {**fr(0, 0x10, PROBE, hx(t)), "token": 1000})
ok("pong-control", "PONG on channel 0 echoing token 1000.", frame(0, 0x11, PROBE, t), {**fr(0, 0x11, PROBE, hx(t)), "token": 1000})
t2 = struct.pack(">I", 0xDEADBEEF)
ok("ping-channel", "PING on application channel 3, token 0xDEADBEEF.",
   frame(3, 0x10, PROBE, t2), {**fr(3, 0x10, PROBE, hx(t2)), "token": 0xDEADBEEF})

# ── Connection ──────────────────────────────────────────────────────────────
cl = {"code": 1000}
ok("close", "CLOSE (minimal).", frame(0, 0x20, 0, js(cl)), fr(0, 0x20, 0, payload_json=cl))
er = {"code": 4003, "channel": 9}
ok("error", "ERROR: frame on unknown channel 9.", frame(0, 0xF0, 0, js(er)), fr(0, 0xF0, 0, payload_json=er))

# ── Application data ────────────────────────────────────────────────────────
p = bytes.fromhex("0200012C")
ok("app-message", "Application message type 0x01 on channel 1 (x=512, y=300 as two uint16).",
   frame(1, 0x01, 0, p), fr(1, 0x01, 0, hx(p)))

msg = b"hello world"
f1 = frame(1, 0x05, MORE, msg[:5])
f2 = frame(1, 0x05, 0, msg[5:])
ok("fragmented", "'hello world' (type 0x05, channel 1) sent as two fragments: MORE on the first, cleared on the last.",
   f1 + f2,
   {"frames": [fr(1, 0x05, MORE, hx(msg[:5])), fr(1, 0x05, 0, hx(msg[5:]))], "reassembledHex": hx(msg)})

# ── Invalid inputs ──────────────────────────────────────────────────────────
bad("bad-magic", "Wrong magic on a stream binding (v0.1 'OMUX').", b"OMUX",
    {"action": "close-transport"}, state="start")
bad("reserved-flag", "Reserved flag bit 0x04 set without a negotiated extension.",
    frame(1, 0x01, 0x04, b"\x00"), {"action": "close", "code": 1002})
bad("channel-ffff", "Frame on reserved channel 0xFFFF.",
    frame(0xFFFF, 0x01, 0, b""), {"action": "close", "code": 1002})
bad("control-fragment", "MORE set on a control-channel frame.",
    frame(0, 0x01, MORE, js(h)), {"action": "close", "code": 1002}, state="awaiting-hello")
bad("probe-fragment", "MORE and PROBE both set.",
    frame(0, 0x10, MORE | PROBE, t), {"action": "close", "code": 1002})
bad("bad-json", "HELLO whose payload is not valid JSON.",
    frame(0, 0x01, 0, b"{version"), {"action": "close", "code": 4001}, state="awaiting-hello")
bad("too-large", "Header declares a 4 GiB payload (over the default maxFramePayload). Reject from the header alone, before buffering.",
    struct.pack(">HBBI", 1, 0x01, 0, 0xFFFFFFFF), {"action": "close", "code": 4005})
bad("length-mismatch", "Message binding: header says 8 bytes but only 4 follow.",
    struct.pack(">HBBI", 1, 0x01, 0, 8) + b"\x00\x00\x00\x00", {"action": "close", "code": 4001, "bindings": ["websocket", "webrtc"]})
bad("wrong-parity", "Server sends OPEN_CHANNEL with an odd (client-owned) ID.",
    frame(0, 0x03, 0, js({"id": 7, "name": "x", "reliable": True, "ordered": True})), {"action": "close", "code": 1002, "receiver": "client"})

bad("window-update-zero", "WINDOW_UPDATE with increment 0.",
    frame(0, 0x07, 0, struct.pack(">HI", 1, 0)), {"action": "close", "code": 4001})
bad("window-update-control", "WINDOW_UPDATE entry for channel 0.",
    frame(0, 0x07, 0, struct.pack(">HI", 0, 4096)), {"action": "close", "code": 1002})
bad("hello-even-id", "HELLO requesting a channel with an even (server-owned) ID.",
    frame(0, 0x01, 0, js({"version": [0, 2, 0], "channels": [{"id": 2, "name": "x", "reliable": True, "ordered": True}]})),
    {"action": "close", "code": 1002}, state="awaiting-hello")
bad("second-hello", "HELLO after the handshake has completed.",
    frame(0, 0x01, 0, js(h)), {"action": "close", "code": 1002, "receiver": "server"})
bad("limit-too-small", "HELLO declaring maxFramePayload below the 4096 minimum.",
    frame(0, 0x01, 0, js({"version": [0, 2, 0], "maxFramePayload": 1024})), {"action": "close", "code": 4001}, state="awaiting-hello")

json.dump({"xumux": "0.2.0-draft", "flags": {"MORE": MORE, "PROBE": PROBE},
           "valid": valid, "invalid": invalid}, sys.stdout, indent=2)
sys.stdout.write("\n")
