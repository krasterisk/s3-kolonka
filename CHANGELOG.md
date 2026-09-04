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

## [0.1.0] - 2026-09-03

### Added

- ESP-IDF firmware for Waveshare ESP32-S3-Touch-LCD-1.85C V2 BOX
- Captive Wi-Fi setup portal (`s3-kolonka` / `http://192.168.4.1`)
- WebSocket voice gateway with Groq STT/LLM and local Piper TTS
