#!/usr/bin/env python3
"""xumux behavioural conformance runner.

Plays the client side of scripted xumux exchanges against an implementation
under test (IUT) that runs as a server over stdio (the stream binding), and
checks protocol invariants on every frame the IUT sends. Standard library
only, and independent of every implementation.

    python3 -I run.py [--only NAME] [--features core,pipe] -- ADAPTER [ARGS...]

The adapter is started once per scenario as `ADAPTER [ARGS...] <config-json>`.
See README.md for the adapter contract and the scenario format.
"""

import argparse
import json
import os
import select
import struct
import subprocess
import sys
import time

MAGIC = b"XMUX"
MORE, PROBE = 0x01, 0x02
CTRL = {"HELLO": 0x01, "WELCOME": 0x02, "OPEN_CHANNEL": 0x03, "CHANNEL_ACK": 0x04,
        "CLOSE_CHANNEL": 0x05, "CHANNEL_REJECT": 0x06, "WINDOW_UPDATE": 0x07,
        "CLOSE": 0x20, "ERROR": 0xF0}
CTRL_NAME = {v: k for k, v in CTRL.items()}
PING, PONG = 0x10, 0x11
CONTROL_MAX = 65536
MAX_WINDOW = 2**31 - 1
DEFAULT_LIMITS = {"maxFramePayload": 65536, "maxMessageSize": 262144, "initialWindow": 262144}
PIPE_DATA = 0x01
WRITE_TIMEOUT = 10
STDERR_TAIL = 1 << 16


class Fail(Exception):
    """A conformance failure: the IUT did something the spec forbids, or not what it requires."""


class Unsupported(Exception):
    pass


def pattern(n, seed):
    """Deterministic, position-dependent bytes, so reordering or loss shows up."""
    return bytes(((i * 131 + seed * 17 + (i >> 8)) & 0xFF) for i in range(n))


def describe(ch, typ, flags, payload):
    if ch == 0 and not flags & PROBE:
        name = CTRL_NAME.get(typ, f"control 0x{typ:02x}")
        if typ == CTRL["WINDOW_UPDATE"]:
            return f"{name} {payload.hex()}"
        try:
            return f"{name} {payload.decode()}"
        except UnicodeDecodeError:
            return f"{name} {payload.hex()}"
    if flags & PROBE:
        return f"{'PING' if typ == PING else 'PONG' if typ == PONG else hex(typ)} ch{ch} {payload.hex()}"
    more = " MORE" if flags & MORE else ""
    return f"ch{ch} type 0x{typ:02x}{more} {len(payload)} bytes"


def subset(want, got):
    """want is a JSON subset of got."""
    if isinstance(want, dict):
        return isinstance(got, dict) and all(k in got and subset(v, got[k]) for k, v in want.items())
    if isinstance(want, list):
        return isinstance(got, list) and len(want) == len(got) and all(subset(a, b) for a, b in zip(want, got))
    return want == got


REQUIRED = {
    "WELCOME": {"version": list},
    "OPEN_CHANNEL": {"id": int, "name": str, "reliable": bool, "ordered": bool},
    "CHANNEL_ACK": {"id": int, "reliable": bool, "ordered": bool},
    "CHANNEL_REJECT": {"id": int, "code": int},
    "CLOSE_CHANNEL": {"id": int},
    "CLOSE": {"code": int},
    "ERROR": {"code": int},
}


def check_body(name, body):
    """The IUT's control payload is an object with the required fields (§3, §4)."""
    if not isinstance(body, dict):
        raise Fail(f"IUT sent a {name} whose payload is not a JSON object (§4)")
    for k, t in REQUIRED.get(name, {}).items():
        v = body.get(k)
        if not isinstance(v, t) or (t is int and isinstance(v, bool)):
            raise Fail(f"IUT sent a {name} without a valid {k!r}: {json.dumps(body)[:120]} (§4)")
    if name == "WELCOME":
        for k in ("channels", "rejected"):
            if not isinstance(body.get(k, []), list) or not all(isinstance(e, dict) and isinstance(e.get("id"), int)
                                                               for e in body.get(k, [])):
                raise Fail(f"IUT sent a WELCOME with a malformed {k!r} (§3.3)")


class Chan:
    """What the runner knows about one channel."""

    def __init__(self, cid, req):
        self.id = cid
        self.req = req
        self.state = "opening"          # opening, open, closing (we sent CLOSE_CHANNEL), peer-closing, closed
        self.pipe = (req.get("metadata") or {}).get("profile") == "pipe/1"
        self.reliable = True            # stream binding: every channel is effectively reliable and ordered
        self.credit_to_iut = 0          # what the IUT may still send us
        self.credit_from_iut = 0        # what we may still send the IUT
        self.granted_by_iut = 0         # total WINDOW_UPDATE increments from the IUT
        self.sent = bytearray()         # payload bytes we sent (DATA for pipe, all for others)
        self.received = bytearray()     # payload bytes received (all non-probe, non-control)
        self.sent_msgs = []             # messages we sent (type, payload), on non-pipe channels
        self.messages = []              # complete messages (type, payload)
        self.partial = None             # (type, bytearray) while reassembling
        self.taken = 0                  # messages already matched by expectMessage
        self.iut_eof = False            # pipe/1: the IUT has sent EOF
        self.returned = 0               # received bytes we have returned credit for (returnCreditInSteps)
        self.sent_close = False
        self.got_close = None           # the IUT's CLOSE_CHANNEL body


class Runner:
    def __init__(self, cmd, scenario, verbose):
        self.cmd = cmd
        self.sc = scenario
        self.verbose = verbose
        self.log = []
        self.buf = bytearray()
        self.got_magic = False
        self.eof = False
        self.iut_closed = None          # body of the IUT's CLOSE
        self.sent_close = False
        self.chans = {}
        self.closed = {}                # fully closed channels, kept for expectations
        self.limits = dict(DEFAULT_LIMITS)  # what we declare (bind the IUT)
        self.iut_limits = dict(DEFAULT_LIMITS)  # what the IUT declares (bind us)
        self.welcome = None
        self.ignore = set(scenario.get("ignore", []))
        self.next_seed = 1
        self.pings = set()              # (channel, token) of our PINGs not yet answered
        self.outq = bytearray()         # bytes for the IUT's stdin not yet written

    # ---------------------------------------------------------------- I/O

    def start(self):
        cfg = json.dumps(self.sc.get("config", {}))
        self.proc = subprocess.Popen(self.cmd + [cfg], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        self.out = self.proc.stdout.fileno()
        self.err = self.proc.stderr.fileno()
        self.inp = self.proc.stdin.fileno()
        for fd in (self.out, self.err, self.inp):
            os.set_blocking(fd, False)
        self.stderr = bytearray()
        self.write(MAGIC)

    def write(self, b):
        """Write to the IUT's stdin, reading its output meanwhile, so that neither side can
        block the other. An IUT that stops reading for WRITE_TIMEOUT fails the scenario."""
        self.outq += b
        deadline = time.monotonic() + WRITE_TIMEOUT
        while self.outq:
            if self.inp is None:
                self.outq.clear()  # the IUT has gone; reading will say so
                return
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise Fail(f"IUT stopped reading its input ({len(self.outq)} bytes unwritten for {WRITE_TIMEOUT}s)")
            r, w, _ = select.select([fd for fd in (self.out, self.err) if fd is not None], [self.inp], [], timeout)
            self.read_ready(r)
            if w:
                try:
                    n = os.write(self.inp, self.outq[:1 << 16])
                    del self.outq[:n]
                except BlockingIOError:
                    pass
                except (BrokenPipeError, OSError):
                    self.inp = None

    def read_ready(self, ready):
        for fd in ready:
            try:
                b = os.read(fd, 1 << 20)
            except BlockingIOError:
                continue
            if fd == self.err:
                if not b:
                    self.err = None
                self.stderr = (self.stderr + b)[-STDERR_TAIL:]
            elif not b:
                self.eof = True
                self.out = None
            else:
                self.buf += b

    def stop(self):
        try:
            self.proc.stdin.close()
        except (BrokenPipeError, ValueError, OSError):
            pass
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.drain_stderr()

    def drain_stderr(self):
        while self.err is not None:
            try:
                b = os.read(self.err, 1 << 16)
            except (BlockingIOError, OSError):
                return
            if not b:
                return
            self.stderr = (self.stderr + b)[-STDERR_TAIL:]

    def read_some(self, deadline):
        fds = [fd for fd in (self.out, self.err) if fd is not None]
        if self.out is None:
            return
        r, _, _ = select.select(fds, [], [], max(0.0, deadline - time.monotonic()))
        self.read_ready(r)

    def raw_frame(self, deadline):
        """The next frame from the IUT as (ch, type, flags, payload), or None at EOF/timeout."""
        while True:
            if not self.got_magic:
                if len(self.buf) >= 4:
                    if bytes(self.buf[:4]) != MAGIC:
                        raise Fail(f"IUT sent {bytes(self.buf[:4])!r} instead of the XMUX magic")
                    del self.buf[:4]
                    self.got_magic = True
                    continue
            elif len(self.buf) >= 8:
                ch, typ, flags, n = struct.unpack(">HBBI", self.buf[:8])
                limit = CONTROL_MAX if ch == 0 else self.limits["maxFramePayload"]
                if n > limit:
                    raise Fail(f"IUT sent a {n}-byte payload on channel {ch}, above our limit {limit} (§2.3, §3.4)")
                if len(self.buf) >= 8 + n:
                    payload = bytes(self.buf[8:8 + n])
                    del self.buf[:8 + n]
                    return ch, typ, flags, payload
            if self.eof:
                if self.buf:
                    raise Fail(f"IUT closed the transport in the middle of a frame ({len(self.buf)} bytes left)")
                return None
            if time.monotonic() >= deadline:
                return None
            self.read_some(deadline)

    def send_frame(self, ch, typ, flags, payload):
        self.trace(">>", describe(ch, typ, flags, payload))
        self.write(struct.pack(">HBBI", ch, typ, flags, len(payload)) + payload)

    def send_ctrl(self, name, body):
        payload = body if isinstance(body, (bytes, bytearray)) else json.dumps(body, separators=(",", ":")).encode()
        self.send_frame(0, CTRL[name] if isinstance(name, str) else name, 0, bytes(payload))

    def trace(self, d, s):
        line = f"{d} {s[:160]}"
        self.log.append(line)
        if self.verbose:
            print("   ", line, file=sys.stderr)

    # ---------------------------------------------------------- invariants

    def frame(self, deadline):
        """Next IUT frame after invariant checks and bookkeeping, or None."""
        f = self.raw_frame(deadline)
        if f is None:
            return None
        ch, typ, flags, payload = f
        self.trace("<<", describe(ch, typ, flags, payload))
        if self.iut_closed is not None:
            raise Fail(f"IUT sent a frame after its CLOSE (§9.1): {describe(*f)}")
        if ch == 0xFFFF:
            raise Fail("IUT used channel 0xFFFF (§2)")
        if flags & ~(MORE | PROBE):
            raise Fail(f"IUT set reserved flag bits 0x{flags:02x} (§2.1)")
        if flags & MORE and (ch == 0 or flags & PROBE):
            raise Fail("IUT set MORE on channel 0 or on a probe frame (§2.3, §7)")
        if self.welcome is None and not (ch == 0 and not flags & PROBE and typ in (CTRL["WELCOME"], CTRL["CLOSE"])):
            raise Fail(f"IUT's first frame must be WELCOME or CLOSE (§3.1), got {describe(*f)}")

        if flags & PROBE:
            if typ == PONG:
                if (ch, payload) not in self.pings:
                    raise Fail(f"IUT sent a PONG on channel {ch} that answers none of our PINGs (§8.1)")
                self.pings.discard((ch, payload))
            if typ == PING and len(payload) == 4:
                if ch == 0 or (ch in self.chans and self.chans[ch].state == "open"):
                    self.send_frame(ch, PONG, PROBE, payload)
                elif ch not in self.chans:
                    raise Fail(f"IUT sent a PING on channel {ch}, which is not open (§8.1)")
            if ch != 0:
                c = self.chans.get(ch)
                if c is None or c.state == "opening" or c.got_close is not None:
                    raise Fail(f"IUT sent a probe on channel {ch}, which is not open on its side (§8.1)")
            return f

        if ch == 0:
            self.control(typ, payload)
            return f

        c = self.chans.get(ch)
        if c is None or c.state == "opening":
            raise Fail(f"IUT sent data on channel {ch}, which it has not acknowledged (§5.2)")
        if c.got_close is not None:
            raise Fail(f"IUT sent data on channel {ch} after its CLOSE_CHANNEL (§5.4)")
        if c.reliable:
            if len(payload) > c.credit_to_iut:
                raise Fail(f"IUT sent {len(payload)} bytes on channel {ch} with only {c.credit_to_iut} "
                           f"bytes of credit (§6)")
            c.credit_to_iut -= len(payload)
        if c.state == "closing":
            return f  # discarded (§5.4); its credit still counted above
        if c.pipe and c.iut_eof and typ == PIPE_DATA:
            raise Fail(f"IUT sent pipe/1 DATA on channel {ch} after its EOF (pipe.md)")
        if c.pipe and flags & MORE:
            raise Fail(f"IUT fragmented a pipe/1 message (type 0x{typ:02x}) on channel {ch}: "
                       "DATA MUST NOT be fragmented (pipe.md)")
        if c.partial is not None:
            ptyp, pbuf = c.partial
            if typ != ptyp:
                raise Fail(f"IUT changed type mid-message on channel {ch} (§7)")
            pbuf += payload
        else:
            c.partial = (typ, bytearray(payload))
        if len(c.partial[1]) > self.limits["maxMessageSize"]:
            raise Fail(f"IUT's message on channel {ch} exceeds our maxMessageSize (§7)")
        if typ == PIPE_DATA or not c.pipe:
            c.received += payload
        if not flags & MORE:
            c.messages.append((c.partial[0], bytes(c.partial[1])))
            if c.pipe and c.partial[0] == 0x02:
                c.iut_eof = True
            c.partial = None
        return f

    def control(self, typ, payload):
        name = CTRL_NAME.get(typ)
        if name == "WINDOW_UPDATE":
            if len(payload) == 0 or len(payload) % 6:
                raise Fail(f"IUT sent a WINDOW_UPDATE of {len(payload)} bytes (§6.1)")
            for i in range(0, len(payload), 6):
                ch, inc = struct.unpack(">HI", payload[i:i + 6])
                if not 1 <= inc <= MAX_WINDOW:
                    raise Fail(f"IUT sent a WINDOW_UPDATE increment {inc} (§6.1)")
                if ch == 0:
                    raise Fail("IUT sent a WINDOW_UPDATE entry for channel 0 (§6.1)")
                c = self.chans.get(ch)
                if c is None and ch in self.closed:
                    raise Fail(f"IUT sent WINDOW_UPDATE for channel {ch} after its CLOSE_CHANNEL (§6)")
                if c is None:
                    continue
                if c.got_close is not None:
                    raise Fail(f"IUT sent WINDOW_UPDATE for channel {ch} after its CLOSE_CHANNEL (§6)")
                c.credit_from_iut += inc
                c.granted_by_iut += inc
                if c.credit_from_iut > MAX_WINDOW:
                    raise Fail(f"IUT raised our credit on channel {ch} above 2^31-1 (§6)")
            return
        if name is None:
            return  # an unknown control type: its payload need not be JSON
        try:
            body = json.loads(payload)
        except ValueError:
            raise Fail(f"IUT sent a {name} whose payload is not JSON (§4)")
        check_body(name, body)
        if name == "WELCOME":
            if self.welcome is not None:
                raise Fail("IUT sent a second WELCOME (§4.1)")
            self.welcome = body
            for k in DEFAULT_LIMITS:
                if k in body:
                    self.iut_limits[k] = body[k]
            ids = {c["id"] for c in body.get("channels", [])} | {c["id"] for c in body.get("rejected", [])}
            asked = {c["id"] for c in self.hello_channels}
            if ids != asked or len(body.get("channels", [])) + len(body.get("rejected", [])) != len(asked):
                raise Fail(f"WELCOME must list every HELLO channel exactly once (§3.3): asked {sorted(asked)}")
            reqs = {r["id"]: r for r in self.hello_channels}
            for a in body.get("channels", []):
                self.chans[a["id"]] = Chan(a["id"], reqs[a["id"]])
                self.opened(a["id"])
        elif name == "CHANNEL_ACK":
            c = self.chans.get(body.get("id"))
            if c is None or c.state != "opening":
                raise Fail(f"IUT acknowledged channel {body.get('id')}, which we are not opening (§4.1)")
            self.opened(c.id)
        elif name == "CHANNEL_REJECT":
            c = self.chans.get(body.get("id"))
            if c is None or c.state != "opening":
                raise Fail(f"IUT rejected channel {body.get('id')}, which we are not opening (§4.1)")
            del self.chans[c.id]
        elif name == "CLOSE_CHANNEL":
            c = self.chans.get(body.get("id"))
            if c is None:
                return  # closing an unknown channel is ignored by us too
            if c.got_close is not None:
                raise Fail(f"IUT sent a second CLOSE_CHANNEL for channel {c.id} (§5.4)")
            c.got_close = body
            if not c.sent_close:
                self.close_channel(c.id, None, reply=True)
            self.maybe_closed(c)
        elif name == "CLOSE":
            self.iut_closed = body
            if not self.sent_close:
                self.sent_close = True
                self.send_ctrl("CLOSE", {"code": 1000})
        elif name == "OPEN_CHANNEL":
            if body["id"] % 2 == 1 or body["id"] in (0, 0xFFFF) or body["id"] in self.chans:
                raise Fail(f"IUT opened channel {body['id']}, which is odd, reserved or in use (§5.1)")
            self.send_ctrl("CHANNEL_REJECT", {"id": body["id"], "code": 1003})
        elif name == "ERROR":
            pass  # surfaced to expectations
        elif name in ("HELLO",):
            raise Fail("IUT (a server) sent HELLO (§4.1)")

    def opened(self, cid):
        c = self.chans[cid]
        c.state = "open"
        c.credit_to_iut = self.limits["initialWindow"]
        c.credit_from_iut = self.iut_limits["initialWindow"]

    def maybe_closed(self, c):
        if c.sent_close and c.got_close is not None:
            c.state = "closed"
            self.chans.pop(c.id, None)
            self.closed[c.id] = c

    def close_channel(self, cid, code, reply=False):
        c = self.chans[cid]
        body = {"id": cid}
        if code is not None:
            body["code"] = code
        self.send_ctrl("CLOSE_CHANNEL", body)
        c.sent_close = True
        if c.got_close is None:
            c.state = "closing"
        self.maybe_closed(c)

    # --------------------------------------------------------- expectations

    def significant(self, frame):
        ch, typ, flags, payload = frame
        if flags & PROBE:
            return False  # PINGs are answered automatically; PONGs are matched where expected
        if ch == 0:
            name = CTRL_NAME.get(typ, "")
            if name == "WINDOW_UPDATE":
                return False
            return name not in self.ignore
        return False  # channel data is collected, and checked by data expectations

    def wait_for(self, what, pred, timeout):
        """Process frames until pred(frame) is true. Insignificant frames are skipped; a significant
        frame that does not satisfy pred is a failure."""
        deadline = time.monotonic() + timeout
        while True:
            f = self.frame(deadline)
            if f is None:
                if self.eof:
                    raise Fail(f"IUT closed the transport while we waited for {what}")
                raise Fail(f"timed out after {timeout}s waiting for {what}")
            if pred(f):
                return f
            if self.significant(f):
                raise Fail(f"expected {what}, got {describe(*f)}")

    def ctrl_pred(self, name, want):
        def pred(f):
            ch, typ, flags, payload = f
            if ch != 0 or flags & PROBE or typ != CTRL[name]:
                return False
            if want is None:
                return True
            try:
                return subset(want, json.loads(payload))
            except ValueError:
                return False
        return pred

    def pump_until(self, what, cond, timeout):
        """Process frames until cond() holds, failing on significant unexpected frames."""
        deadline = time.monotonic() + timeout
        while not cond():
            f = self.frame(deadline)
            if f is None:
                if self.eof:
                    raise Fail(f"IUT closed the transport while we waited for {what}")
                raise Fail(f"timed out after {timeout}s waiting for {what}")
            if self.significant(f):
                raise Fail(f"expected {what}, got {describe(*f)}")

    def quiet(self, ms):
        deadline = time.monotonic() + ms / 1000
        while True:
            f = self.frame(deadline)
            if f is None:
                if self.eof:
                    raise Fail("IUT closed the transport, but the connection should stay open")
                return
            if self.significant(f):
                raise Fail(f"expected nothing, got {describe(*f)}")

    # ---------------------------------------------------------------- steps

    def chan(self, cid):
        c = self.chans.get(cid) or self.closed.get(cid)
        if c is None:
            raise Fail(f"(scenario) channel {cid} is not open")
        return c

    def send_message(self, cid, typ, data, force=False, frame_size=None):
        """Send one message, fragmented to the IUT's maxFramePayload, waiting for credit unless forced."""
        c = self.chans.get(cid)
        limit = frame_size or self.iut_limits["maxFramePayload"]
        if c is not None and c.pipe and typ == PIPE_DATA and not force:
            # pipe/1 DATA MUST NOT be fragmented: send it as separate DATA messages, each
            # sized to the credit and the IUT's maxFramePayload (pipe.md).
            off = 0
            while off < len(data) or not data:
                self.pump_until(f"credit to send on channel {cid}", lambda: c.credit_from_iut > 0,
                                self.sc.get("timeout", 5))
                n = min(limit, c.credit_from_iut, len(data) - off)
                c.credit_from_iut -= n
                self.send_frame(cid, typ, 0, data[off:off + n])
                off += n
                if not data:
                    break
            c.sent += data
            return
        chunks = [data[i:i + limit] for i in range(0, len(data), limit)] or [b""]
        for i, chunk in enumerate(chunks):
            if c is not None and not force:
                self.pump_until(f"credit to send on channel {cid}",
                                lambda: c.credit_from_iut >= len(chunk), self.sc.get("timeout", 5))
            if c is not None:
                c.credit_from_iut -= len(chunk)
            flags = MORE if i < len(chunks) - 1 else 0
            self.send_frame(cid, typ, flags, chunk)
        if c is not None and (typ == PIPE_DATA or not c.pipe):
            c.sent += data
        if c is not None and not c.pipe:
            c.sent_msgs.append((typ, bytes(data)))

    def step(self, s):
        timeout = s.get("timeout", self.sc.get("timeout", 3))
        op, arg = next(iter(s.items())) if len(s) == 1 or "timeout" not in s else \
            next((k, v) for k, v in s.items() if k != "timeout")

        if op == "hello":
            body = {"version": [0, 2, 0], "pingInterval": 0}
            body.update(arg or {})
            for k in DEFAULT_LIMITS:
                if k in body:
                    self.limits[k] = body[k]
            self.hello_channels = body.get("channels", [])
            self.send_ctrl("HELLO", body)
            if s.get("expectWelcome", True):
                self.wait_for(f"WELCOME {json.dumps(s.get('welcome'))}",
                              self.ctrl_pred("WELCOME", s.get("welcome")), timeout)
        elif op == "helloRaw":  # a HELLO payload sent as is, with no bookkeeping
            self.hello_channels = []
            self.send_ctrl("HELLO", arg.encode() if isinstance(arg, str) else arg)
        elif op == "expectWelcome":
            f = self.wait_for("WELCOME", self.ctrl_pred("WELCOME", arg), timeout)
        elif op == "open":
            req = {"reliable": True, "ordered": True}
            req.update(arg)
            self.chans[req["id"]] = Chan(req["id"], req)
            self.closed.pop(req["id"], None)  # the ID is reused for a new channel
            self.send_ctrl("OPEN_CHANNEL", req)
            if s.get("expect", "ack") == "ack":
                self.wait_for(f"CHANNEL_ACK for {req['id']}", self.ctrl_pred("CHANNEL_ACK", {"id": req["id"]}),
                              timeout)
        elif op == "openRaw":
            self.send_ctrl("OPEN_CHANNEL", arg)
        elif op == "ctrl":  # {"ctrl": {"type": "NAME" | number, "json": {...} | "payloadHex": "..."}}
            t = arg["type"]
            payload = bytes.fromhex(arg["payloadHex"]) if "payloadHex" in arg else \
                json.dumps(arg.get("json", {}), separators=(",", ":")).encode()
            self.send_frame(0, CTRL[t] if isinstance(t, str) else t, arg.get("flags", 0), payload)
        elif op == "frame":  # {"frame": {"channel", "type", "flags", "payloadHex" | "bytes"}}
            payload = bytes.fromhex(arg.get("payloadHex", "")) if "bytes" not in arg else bytes(arg["bytes"])
            if arg.get("flags", 0) & PROBE and arg.get("type") == PING and len(payload) == 4:
                self.pings.add((arg["channel"], payload))  # a valid PING sent raw may be answered
            self.send_frame(arg["channel"], arg.get("type", 1), arg.get("flags", 0), payload)
        elif op == "send":  # {"send": {"channel", "type", "bytes", "force", "frameSize"}}
            seed = self.next_seed
            self.next_seed += 1
            self.send_message(arg["channel"], arg.get("type", 1), pattern(arg["bytes"], seed),
                              arg.get("force", False), arg.get("frameSize"))
        elif op == "sendEach":  # several messages of the same size
            for _ in range(arg["count"]):
                seed = self.next_seed
                self.next_seed += 1
                self.send_message(arg["channel"], arg.get("type", 1), pattern(arg["bytes"], seed))
        elif op == "grant":  # {"grant": {"channel", "bytes"}}
            c = self.chan(arg["channel"])
            self.send_ctrl("WINDOW_UPDATE", struct.pack(">HI", arg["channel"], arg["bytes"]))
            c.credit_to_iut += arg["bytes"]
        elif op == "grantRaw":
            self.send_ctrl("WINDOW_UPDATE", bytes.fromhex(arg))
        elif op == "returnCreditInSteps":
            # Behave like a real receiver that returns consumed bytes promptly, but in small
            # WINDOW_UPDATEs, so the IUT keeps seeing odd amounts of credit.
            c = self.chan(arg["channel"])
            while True:
                left = len(c.received) - c.returned
                c.returned = len(c.received)
                while left > 0:
                    n = min(arg["step"], left)
                    self.send_ctrl("WINDOW_UPDATE", struct.pack(">HI", c.id, n))
                    c.credit_to_iut += n
                    left -= n
                if len(c.received) >= arg["until"]:
                    break
                before = len(c.received)
                self.pump_until(f"{arg['until']} bytes on channel {c.id}",
                                lambda: len(c.received) > before, timeout)
        elif op == "expectPipeEOF":
            c = self.chan(arg["channel"])
            self.pump_until(f"EOF on pipe channel {c.id}", lambda: c.iut_eof, timeout)
        elif op == "expectEcho":  # the IUT sent back exactly what we sent on the channel
            c = self.chan(arg["channel"])
            n = arg.get("bytes", len(c.sent))
            if not c.pipe:
                # Messages, not just bytes: same types and boundaries, in order.
                k, total = 0, 0
                while k < len(c.sent_msgs) and total < n:
                    total += len(c.sent_msgs[k][1])
                    k += 1
                self.pump_until(f"{k} echoed messages on channel {c.id}", lambda: len(c.messages) >= k, timeout)
                for j in range(k):
                    if c.messages[j] != c.sent_msgs[j]:
                        got, want = c.messages[j], c.sent_msgs[j]
                        raise Fail(f"echoed message {j} on channel {c.id} is type 0x{got[0]:02x}, {len(got[1])} "
                                   f"bytes; we sent type 0x{want[0]:02x}, {len(want[1])} bytes")
                return
            self.pump_until(f"{n} echoed bytes on channel {c.id}", lambda: len(c.received) >= n, timeout)
            if bytes(c.received[:n]) != bytes(c.sent[:n]):
                i = next(i for i in range(n) if c.received[i] != c.sent[i])
                raise Fail(f"echo on channel {c.id} differs from what we sent at byte {i}")
        elif op == "expectReceived":  # exactly this many payload bytes so far, after a pause
            c = self.chan(arg["channel"])
            self.pump_until(f"{arg['bytes']} bytes on channel {c.id}",
                            lambda: len(c.received) >= arg["bytes"], timeout)
            self.quiet(arg.get("quietMs", 200))
            if len(c.received) != arg["bytes"]:
                raise Fail(f"expected exactly {arg['bytes']} bytes on channel {c.id}, got {len(c.received)}")
        elif op == "expectMessage":  # {"channel", "type", "bytes", "echoOf": index}
            c = self.chan(arg["channel"])
            want = c.taken
            self.pump_until(f"a message on channel {c.id}", lambda: len(c.messages) > want, timeout)
            typ, payload = c.messages[want]
            c.taken += 1
            if "type" in arg and typ != arg["type"]:
                raise Fail(f"expected a message of type 0x{arg['type']:02x} on channel {c.id}, got 0x{typ:02x}")
            if "bytes" in arg and len(payload) != arg["bytes"]:
                raise Fail(f"expected a {arg['bytes']}-byte message on channel {c.id}, got {len(payload)} bytes")
        elif op == "expectCtrl":  # {"expectCtrl": {"type": "NAME", "json": {...}}}
            self.wait_for(f"{arg['type']} {json.dumps(arg.get('json'))}",
                          self.ctrl_pred(arg["type"], arg.get("json")), timeout)
        elif op == "expectCloseChannel":  # the IUT closes channel id (with code)
            cid = arg["id"]
            want = {"id": cid}
            if "code" in arg:
                want["code"] = arg["code"]
            c = self.chans.get(cid) or self.closed.get(cid)
            if c is not None and c.got_close is not None:
                got = c.got_close
            else:
                f = self.wait_for(f"CLOSE_CHANNEL {json.dumps(want)}", self.ctrl_pred("CLOSE_CHANNEL", {"id": cid}),
                                  timeout)
                got = json.loads(f[3])
            if got.get("code", 1000) != arg.get("code", got.get("code", 1000)):
                raise Fail(f"expected CLOSE_CHANNEL {cid} with code {arg['code']}, got {got.get('code', 1000)}")
        elif op == "closeChannel":  # we close; the IUT must reply
            c = self.chan(arg["id"])
            self.close_channel(c.id, arg.get("code"))
            if s.get("expectReply", True):
                self.wait_for(f"the CLOSE_CHANNEL reply for {c.id}",
                              self.ctrl_pred("CLOSE_CHANNEL", {"id": c.id}), timeout)
        elif op == "expectClose":  # the IUT closes the connection (with code)
            want = {"code": arg["code"]} if "code" in arg else None
            deadline = time.monotonic() + timeout
            while self.iut_closed is None:
                f = self.frame(deadline)
                if f is None:
                    if self.eof and arg.get("orTransportClose"):
                        return
                    raise Fail(f"expected CLOSE {json.dumps(want)}" +
                               (", but the IUT closed the transport without one" if self.eof else
                                f" within {timeout}s"))
                if self.significant(f) and not self.ctrl_pred("CLOSE", None)(f):
                    raise Fail(f"expected CLOSE {json.dumps(want)}, got {describe(*f)}")
            if want and self.iut_closed.get("code") != want["code"]:
                raise Fail(f"expected CLOSE with code {want['code']}, got {self.iut_closed.get('code')}")
            self.expect_transport_end()
        elif op == "expectError":
            want = {"code": arg["code"]} if "code" in arg else {}
            if "channel" in arg:
                want["channel"] = arg["channel"]
            self.wait_for(f"ERROR {json.dumps(want)}", self.ctrl_pred("ERROR", want), timeout)
        elif op == "expectQuiet":
            self.quiet(arg)
        elif op == "ping":  # {"ping": {"channel", "token"}} and expect the PONG
            token = struct.pack(">I", arg.get("token", 1234))
            self.pings.add((arg.get("channel", 0), token))
            self.send_frame(arg.get("channel", 0), PING, PROBE, token)
            if s.get("expectPong", True):
                self.wait_for(f"PONG on channel {arg.get('channel', 0)}",
                              lambda f: f[2] & PROBE and f[1] == PONG and f[0] == arg.get("channel", 0) and
                              f[3] == token, timeout)
        elif op == "expectAlive":  # the connection still works: a PING on channel 0 is answered
            token = struct.pack(">I", 0xA11FE)
            self.pings.add((0, token))
            self.send_frame(0, PING, PROBE, token)
            self.wait_for("a PONG proving the connection is open",
                          lambda f: f[2] & PROBE and f[1] == PONG and f[0] == 0 and f[3] == token, timeout)
        elif op == "expectCredit":  # the IUT has returned at least `atLeast` bytes of credit on the channel
            c = self.chan(arg["channel"])
            self.pump_until(f"WINDOW_UPDATEs totalling {arg['atLeast']} on channel {c.id}",
                            lambda: c.granted_by_iut >= arg["atLeast"], timeout)
        elif op == "expectCreditAtMostEchoed":
            # pipe/1: credit follows writes to the local end. For an echo, the local end is
            # the echo writer, so the IUT may not return more credit than it has echoed.
            c = self.chan(arg["channel"])
            self.quiet(arg.get("quietMs", 300))
            if c.granted_by_iut > len(c.received):
                raise Fail(f"IUT returned {c.granted_by_iut} bytes of credit on pipe channel {c.id} but has "
                           f"echoed only {len(c.received)}: credit must follow writes to the local end (pipe.md)")
        elif op == "close":
            self.teardown()
        else:
            raise Fail(f"(scenario) unknown step {op}")

    def expect_transport_end(self):
        deadline = time.monotonic() + 6  # §9.1: the CLOSE sender waits up to 5 s for our reply
        while not self.eof:
            f = self.frame(deadline)
            if f is None and not self.eof:
                raise Fail("IUT did not close the transport after the CLOSE exchange (§9.1)")

    def teardown(self):
        """Close the connection normally: the IUT must answer CLOSE with CLOSE and end the transport."""
        if self.iut_closed is not None:
            self.expect_transport_end()
            return
        self.sent_close = True
        self.send_ctrl("CLOSE", {"code": 1000})
        deadline = time.monotonic() + 5
        while self.iut_closed is None:
            f = self.frame(deadline)
            if f is None:
                raise Fail("IUT did not answer our CLOSE with CLOSE (§9.1)")
        self.expect_transport_end()

    def run(self):
        self.hello_channels = []
        self.start()
        try:
            for s in self.sc["steps"]:
                self.step(s)
            if self.welcome is not None and self.iut_closed is None and not self.eof:
                self.teardown()
        finally:
            self.stop()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenarios"))
    ap.add_argument("--only", help="run scenarios whose name contains this")
    ap.add_argument("--features", default="core,pipe", help="features the IUT supports (core, pipe)")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("adapter", nargs="+")
    a = ap.parse_args()
    features = {f.strip() for f in a.features.split(",") if f.strip()}

    scenarios = []
    for fn in sorted(os.listdir(a.scenarios)):
        if fn.endswith(".json"):
            with open(os.path.join(a.scenarios, fn)) as fh:
                for sc in json.load(fh):
                    sc["_file"] = fn
                    scenarios.append(sc)
    passed = failed = skipped = 0
    for sc in scenarios:
        if a.only and a.only not in sc["name"]:
            continue
        need = set(sc.get("requires", ["core"]))
        if not need <= features:
            skipped += 1
            print(f"SKIP  {sc['name']}  (needs {', '.join(sorted(need - features))})")
            continue
        r = Runner(a.adapter, sc, a.verbose)
        try:
            r.run()
            passed += 1
            print(f"ok    {sc['name']}")
        except Fail as e:
            failed += 1
            print(f"FAIL  {sc['name']}  [{sc.get('spec', '')}]\n      {e}")
            for line in r.log[-8:]:
                print(f"        {line}")
            err = r.stderr.decode(errors="replace").strip()
            if err:
                print("      IUT stderr: " + err.splitlines()[-1][:200])
    print(f"\npassed {passed}, failed {failed}, skipped {skipped}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
