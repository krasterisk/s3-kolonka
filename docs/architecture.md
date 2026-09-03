# Architecture

s3-kolonka splits the product in two:

| Layer | Runs | Responsibility |
| --- | --- | --- |
| Speaker | ESP32-S3 | Display, touch, Wi-Fi, I2S, WebSocket client |
| Gateway | Linux / any Python 3.11+ host | STT, LLM, TTS, session state |

The ESP32 does not host an LLM. Music and YouTube, if added later, belong
on the gateway (or a media backend), not on the board.

## Why not XiaoZhi

XiaoZhi uses a different stack (Opus, MCP, their cloud). This tree keeps
Waveshare's board bring-up and replaces the application, UI, and protocol.

## Status

The first vertical slice (splash-only) is done. Voice I/O, Wi-Fi portal,
and the Groq + Piper path are in tree. Home Assistant and music are backlog.

Historical note: [history/2026-09-01-first-slice.md](history/2026-09-01-first-slice.md).
