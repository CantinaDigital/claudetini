# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

Claudetini is currently in alpha. Security patches will be applied to the latest release only.

## Scope

Claudetini is a **local-only desktop application**. It does not run a public-facing server, accept inbound network connections, or transmit data to external services.

Key security properties:

- **Read-only access to `~/.claude/`** — Claudetini reads Claude Code session logs, memory files, and todos but never modifies them.
- **Local sidecar** — The Python FastAPI backend binds to `127.0.0.1:9876` and is not exposed to the network.
- **No telemetry** — No analytics, crash reporting, or phone-home behavior.
- **No credential storage** — Claudetini does not store API keys, tokens, or passwords. Bootstrap operations run through your local Claude Code installation.

## Reporting a Vulnerability

If you discover a security issue, please report it responsibly:

1. **Do not open a public issue.** Security vulnerabilities should be reported privately.
2. **Email:** Send a report to the maintainers via GitHub's [private vulnerability reporting](https://github.com/cantina-digital/claudetini/security/advisories/new).
3. **Include:** A description of the vulnerability, steps to reproduce, and the potential impact.

We aim to acknowledge reports within **72 hours** and provide a fix or mitigation within **14 days** for confirmed issues.

## What Counts as a Vulnerability

- Path traversal that reads files outside the intended project directory
- The secrets scanner missing a common credential pattern
- The sidecar accepting connections from non-localhost sources
- Sensitive data (real API keys, tokens) committed to the repository
- Cross-site scripting (XSS) via crafted project data rendered in the UI

## What Does Not Count

- Issues requiring local machine access (Claudetini is a local desktop app)
- Denial-of-service against the local sidecar
- Bugs in upstream dependencies (report those to the respective projects)
