# Security Policy

## Supported versions

This project is pre-1.0. Fixes land on `main`.

## What to report

Please report privately:

- Remote code execution or crash-on-packet bugs in the WebSocket gateway
- Unauthenticated control of a speaker on a public port
- Credential leaks in the repository or example configs
- Ways to inject audio or commands across tenants if you run a shared gateway

The speaker is a trusted LAN client. Treat the gateway like a voice backend:
bind it to a private network or firewall port **8765**, and never commit `config.yaml`.

## How to report

Use GitHub's private vulnerability reporting on the repository
(Security → Advisories → Report a vulnerability).

Do not open a public issue for an exploitable flaw.

## Secrets

| File | Status |
| --- | --- |
| `gateway/config.yaml` | local only, gitignored |
| `gateway/config.example.yaml` | placeholders only |
| `firmware/sdkconfig` | local IDF config, gitignored |
| Piper `.onnx` voices | downloaded separately, gitignored |
