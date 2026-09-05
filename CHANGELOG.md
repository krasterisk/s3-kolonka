# Changelog

All notable changes are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project uses [Semantic Versioning](https://semver.org/) after 1.0.0.

## [Unreleased]

### Added

- Settings tab shows the firmware version and build number (`Прошивка 0.1.1+3`)
- Firmware build numbering via `firmware/VERSION`, `firmware/BUILDNUM`, and `app_version.h` (not `BUILD` — collides with `build/` on Windows)

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
- AFE AEC starts after the brain socket so WebSocket no longer fails with `ESP_FAIL` from a starved internal heap
- Setup portal skips AFE/MWW/brain and serves the Wi-Fi page from PSRAM so `192.168.4.1` is not an `oom` error
- Hey Jarvis uses raw mic in silence and AFE-cleaned audio during radio; the play task yields to wake; radio lowers the detect cutoff
- Radio search uses name, aliases, and genre tags; if there is no exact station it plays a close match or asks to clarify
- Radio catalog lookups no longer block the WebSocket loop; a successful name hit skips extra genre requests
- Voice can play a YouTube / YouTube Music track: the gateway searches, yt-dlp extracts audio, ffmpeg sends PCM like radio
- YouTube play starts only after a file is cached; unavailable IDs are skipped for the next search hit
- If the speaker drops mid-listen, the gateway keeps the clip and finishes the turn on reconnect
- YouTube keeps the full «или» show title, prefers episodes, and skips already played clips (другой / следующий)
- After radio stop the speaker reconnects immediately instead of sitting on retry
- Speaker WebSocket no longer parses JSON or stops I2S inside the RX callback; `esp_websocket_client` is 1.7+ (IDFGH-13387)
- `brain_task` is the only task that writes to the socket, so the client keeps its single default lock; the build fails if the separate TX lock is switched on
- Microphone PCM uses 20 ms frames and a 5 s network-write budget; its dedicated TX task no longer sleeps after every frame and throttles the 32 KB/s uplink
- Brain WebSocket keeps one client with auto-reconnect; it no longer destroys mid-handshake (that caused the open→drop reconnect loop)
- Listen clears sticky `pcm://` radio state so «Слушаю» is not muted after a failed/cancelled YouTube play
- A new listen ignores a stale idle from the previous turn (status `gen` + short idle-only protect) so the UI does not flash «Слушаю» → «Готов»
- Gateway pins the turn `gen` on status messages so a late idle cannot be re-labeled with the newer listen generation
- Listen protect no longer blocks `thinking`/`speaking` (that left listen stuck and silenced the wake word)

## [0.1.0] - 2026-09-03

### Added

- ESP-IDF firmware for Waveshare ESP32-S3-Touch-LCD-1.85C V2 BOX
- Captive Wi-Fi setup portal (`s3-kolonka` / `http://192.168.4.1`)
- WebSocket voice gateway with Groq STT/LLM and local Piper TTS
