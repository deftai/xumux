# xumux on stdio

**Status**: Draft | **Binding ID**: `stdio` | **Core**: [0.3](../core.md)

**Provides**: one byte-stream base path (stdin and stdout), reliable and ordered; magic `XMUX`.

For a parent process and a child process, CLI pipelines, process supervisors, and tunnelling over SSH (`ssh host xumux-server`).

## Transport

- The process reads from stdin (fd 0) and writes to stdout (fd 1).
- Both streams MUST be in binary mode: no newline translation and no text encoding.
- stderr (fd 2) is not part of the transport and is free for logging.
- Writes to stdout MUST NOT be held in a buffer that is not flushed. Each frame (or batch of frames) must be flushed promptly. Examples: Python `sys.stdout.buffer` plus `flush()`; C `setvbuf(stdout, NULL, _IONBF, 0)`.

## Roles

By default the process that spawns the other is the **client**. Applications MAY reverse this, but both ends must agree in advance.

## Magic bytes and framing

These are identical to the [TCP binding](tcp.md#magic-bytes): `XMUX` first in each direction, then frames parsed from the byte stream, with short reads expected.

Nothing else may be written to stdout. Stray output, such as a shell profile printing a banner over SSH, shows up as a magic mismatch and the connection is closed.

## Channel properties

Every channel is effectively `reliable: true, ordered: true`.

## Close and EOF

- After the xumux CLOSE exchange, each side closes its stdout. The child then exits.
- EOF on stdin without a CLOSE means the peer has gone. Treat it as a connection close with code `1001`.
- A parent SHOULD also watch for the child exiting (SIGCHLD or `waitpid`) and treat it the same way.

## Keepalive

Use xumux keepalive ([core §8.2](../core.md#82-keepalive)). Pipes have no transport-level keepalive, and EOF or the child exiting does not detect a peer that is still running but has stopped answering.

## Security

stdio is local, so there is no encryption, and isolation comes from the operating system. For remote use, run the child over SSH, which provides encryption and authentication.
