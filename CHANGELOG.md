# Changelog

All notable changes are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/) after 1.0.0.

## [Unreleased]

### Added

- Open-source repository layout (license, contributing, security, CI)
- Gateway auto-stop on trailing silence
- Speaker status line shows full `thinking` / `speaking`, then `Brain: groq`

### Changed

- Gateway host and port are Kconfig options (not a hardcoded public IP)
- Round UI is split into Home / Media / Settings instead of one crowded screen
- «Включи радио …» starts a station even if the LLM only repeats the phrase
- Gateway probes radio URLs and falls back to the next candidate instead of starting a dead stream
- Radio play uses the URL after HTTP redirects so the speaker does not start an empty 301 body
- Radio audio is decoded on the gateway and played as PCM16 on the speaker
- Speaker echo uses ESP-SR AFE AEC only (no WakeNet); Hey Jarvis still runs after AEC. Falls back to the one-tap canceller if AFE fails to start
- Factory app partition is 4M so the AFE library fits on the 16MB flash
- Home dialog text is cleared when a new listen starts, on idle, and when radio starts or stops

## [0.1.0] - 2026-09-03

### Added

- ESP-IDF firmware for Waveshare ESP32-S3-Touch-LCD-1.85C V2 BOX
- Captive Wi-Fi setup portal (`s3-kolonka` / `http://192.168.4.1`)
- WebSocket voice gateway with Groq STT/LLM and local Piper TTS
