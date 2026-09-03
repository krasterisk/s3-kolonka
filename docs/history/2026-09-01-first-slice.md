# First firmware slice (2026-09-01)

Board: Waveshare ESP32-S3-Touch-LCD-1.85C V2 BOX

Write our own ESP-IDF app. Display, touch, EXIO, and codec init come from
the official Waveshare example. XiaoZhi is not forked.

Goal of that slice: after `idf.py flash`, the round screen shows `s3-kolonka`,
touch works, and the vendor Onboard/Music demo is gone.

Out of scope then: wake word, LLM, Home Assistant, YouTube, custom server.

Those pieces are documented as they landed — see [../architecture.md](../architecture.md).
