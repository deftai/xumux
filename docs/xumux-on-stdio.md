# xumux on stdio

**Status**: Draft
**Binding ID**: `stdio`

## Overview

This binding defines how xumux operates over standard input/output (stdin/stdout). This enables xumux between a parent process and a child process, CLI tool piping, and integration with process supervisors.

## Transport Requirements

- stdin (fd 0) for reading, stdout (fd 1) for writing
- MUST use binary mode (no line buffering, no newline translation)
- stderr (fd 2) is NOT part of the xumux transport — reserved for diagnostics/logging

## Stream Framing

Same as TCP — stdio is a raw byte stream. Frames are parsed using the Length field:

```
1. Read 6 bytes from stdin (header)
2. Parse Channel, Type, Flags, Reserved, Payload Length
3. If EXTENDED_LENGTH flag set, read 2 more bytes for 4-byte length
4. Read exactly Payload Length bytes from stdin
5. Frame complete — repeat
```

## Channel Multiplexing

All channels are multiplexed over the single stdin/stdout pair:

```
Parent Process                    Child Process
  stdout ──────────────────────► stdin
  stdin  ◄────────────────────── stdout
```

## Connection Lifecycle

```
Parent                              Child
  │                                    │
  │── spawn child process ────────────►│
  │                                    │
  │── HELLO (ch=0) on child stdin ───►│
  │◄── WELCOME (ch=0) on child stdout │
  │                                    │
  │  ... application data ...          │
  │                                    │
  │── CLOSE (ch=0) ──────────────────►│
  │◄── CLOSE (ch=0) ─────────────────│
  │                                    │
  │  child exits                       │
```

## Use Cases

- **Process-to-process IPC**: Parent spawns child, communicates over xumux
- **CLI piping**: `producer | consumer` where both speak xumux
- **MCP-style tool integration**: Language model ↔ tool server over stdio
- **SSH tunneling**: `ssh host omux-server` — xumux frames over SSH channel

## Buffering

Implementations MUST disable or flush buffering on stdout to avoid latency:

- C: `setvbuf(stdout, NULL, _IONBF, 0)`
- Python: `sys.stdout.buffer` (not `sys.stdout`), or `PYTHONUNBUFFERED=1`
- Node.js: `process.stdout` is unbuffered for pipes by default
- Go: `os.Stdout` is unbuffered

## Keepalive

xumux PING/PONG on channel 0. Additionally, implementations SHOULD monitor the child process for unexpected exit (SIGCHLD, waitpid) and treat it as a connection close.

## EOF Handling

- stdin EOF = remote side closed. Treat as connection close.
- Implementations MUST handle partial reads (short reads are normal on pipes).

## Security

- No encryption (stdio is local IPC)
- Process isolation is provided by the OS
- For remote use, wrap in SSH: `ssh host omux-server` provides encryption + authentication
