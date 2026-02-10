# Product Requirements Document: SocketPipe

**Generated**: 2026-02-09
**Status**: Ready for AI Interview

## Initial Input

**Project Description**: Stanardizing how web ssh clients (ghosthy-wasm, xterm.js) can talk to sshd proxies via websockets or WebRTC data channels

**I want to build SocketPipe that has the following features:**

---

# Specification Generation

Agent workflow for creating project specifications via structured interview.

Legend (from RFC2119): !=MUST, ~=SHOULD, ≉=SHOULD NOT, ⊗=MUST NOT, ?=MAY.

## Input Template

```
I want to build SocketPipe that has the following features:
1. [feature]
2. [feature]
...
N. [feature]
```

## Interview Process

- ~ Use Claude AskInterviewQuestion when available (emulate it if not available)
- ! If Input Template fields are empty: ask overview, then features, then details
- ! Ask **ONE** focused, non-trivial question per step
- ⊗ ask more than one question per step; or try to sneak-in "also" questions
- ~ Provide numbered answer options when appropriate
- ! Include "other" option for custom/unknown responses
- ! make it clear which option you feel is RECOMMENDED
- ! when you are done, append to the end of this file all questions asked and answers given.

**Question Areas:**

- ! Missing decisions (language, framework, deployment)
- ! Edge cases (errors, boundaries, failure modes)
- ! Implementation details (architecture, patterns, libraries)
- ! Requirements (performance, security, scalability)
- ! UX/constraints (users, timeline, compatibility)
- ! Tradeoffs (simplicity vs features, speed vs safety)

**Completion:**

- ! Continue until little ambiguity remains
- ! Ensure spec is comprehensive enough to implement

## Output Generation

- ! Generate as SPECIFICATION.md
- ! follow all relevant deft guidelines
- ! use RFC2119 MUST, SHOULD, MAY, SHOULD NOT, MUST NOT wording
- ! Break into phases, subphases, tasks
- ! end of each phase/subphase must implement and run testing until it passes
- ! Mark all dependencies explicitly: "Phase 2 (depends on: Phase 1)"
- ! Design for parallel work (multiple agents)
- ⊗ Write code (specification only)

## Afterwards

- ! let user know to type "implement SPECIFICATION.md" to start implementation

**Structure:**

```markdown
# Project Name

## Overview

## Requirements

## Architecture

## Implementation Plan

### Phase 1: Foundation

#### Subphase 1.1: Setup

- Task 1.1.1: (description, dependencies, acceptance criteria)

#### Subphase 1.2: Core (depends on: 1.1)

### Phase 2: Features (depends on: Phase 1)

## Testing Strategy

## Deployment
```

## Best Practices

- ! Detailed enough to implement without guesswork
- ! Clear scope boundaries (in vs out)
- ! Include rationale for major decisions
- ~ Size tasks for 1-4 hours
- ! Minimize inter-task dependencies
- ! Define clear component interfaces

## Anti-Patterns

- ⊗ Multiple questions at once
- ⊗ Assumptions without clarifying
- ⊗ Vague requirements
- ⊗ Missing dependencies
- ⊗ Sequential tasks that could be parallel

---

# Interview Questions & Answers

**Q1: Primary Language & Runtime**
A: N/A — This is a protocol specification, not a software implementation.

**Q2: Transport Priority**
A: WebSocket-first, with WebRTC data channels as a potential future extension.

**Q3: Message Framing Format**
A: Binary with simple header (type byte + length + payload).

**Q4: Authentication Model**
A: Token-based (JWT/opaque) — client presents pre-obtained token; proxy validates.

**Q5: Terminal Resize Handling**
A: Control message in-band — dedicated message type within the same WebSocket connection.

**Q6: Session Lifecycle**
A: Stateless (no reconnect) MUST be supported; session resume and full persistence are optional extensions.

**Q7: Additional Control Signals**
A: Minimal set (ping/pong, close, error) MUST be supported; full PTY control (flow control, terminal modes, env vars) SHOULD be supported.

**Q8: Error Reporting Granularity**
A: Numeric codes with categories (1xxx=auth, 2xxx=connection, 3xxx=protocol) with optional human-readable message.

**Q9: Protocol Versioning**
A: Version in handshake — client sends supported version(s); server confirms; breaking changes = major version bump.

**Q10: Transport Security**
A: Mode-dependent (see Q12).

**Q11: Proxy Model**
A: Hybrid — supports both raw SSH tunnel (dumb pipe) and terminated SSH (PTY I/O), negotiated at connection time.

**Q12: Transport Security (Revised)**
A: Mode-dependent — raw SSH tunnel mode MAY use ws://; terminated SSH mode MUST use wss://.

**Q13: Endpoint Architecture**
A: Separate endpoints — distinct paths (`/tunnel` for raw SSH, `/pty` for terminated); clear security boundaries.

**Q14: Backend Target Scope**
A: Tunnel mode supports generic TCP (any port); PTY mode is SSH-specific.

**Q15: Handshake Format**
A: First binary message — client sends handshake (version, mode, target host:port, token) as first frame; server responds accept/reject.

**Q16: Keepalive & Timeout**
A: Negotiated intervals with spec-defined defaults (30s ping, 10s timeout).

**Q17: Maximum Message Size**
A: Negotiated with spec-defined default (64KB).

**Q18: Flow Control / Backpressure**
A: No application-level flow control for v1; rely on TCP/WebSocket backpressure.

**Q19: Client Compatibility**
A: Client-agnostic spec; ghostty-wasm and xterm.js are reference use cases, not compliance targets.

**Q20: Explicit Exclusions**
A: Minimal exclusions only — client UI, server-side SSH credential storage, logging/audit formats.

**Q21: Binary Frame Header Format**
A: Extended 8-byte header — 1 byte type + 1 byte flags + 2 bytes reserved + 4 bytes payload length.

**Q22: Byte Order**
A: Big-endian (network byte order) for all multi-byte fields.

**Q23: Anything Else?**
A: Ready to generate specification.

