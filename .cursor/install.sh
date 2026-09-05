#!/usr/bin/env bash
# Idempotent bootstrap for the s3-kolonka gateway (the runnable component in a
# Cloud Agent). The ESP32-S3 firmware needs ESP-IDF v5.5.2 + hardware and is
# not built here; see README.md / firmware/README.md for that toolchain.
set -euo pipefail

# System packages: python venv tooling plus the audio tools the gateway shells
# out to at runtime (ffmpeg for PCM transcode, espeak-ng as a TTS fallback).
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
  python3.12-venv \
  ffmpeg \
  espeak-ng

cd "$(dirname "$0")/../gateway"

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# Provide a runnable config on first setup. Defaults to the mock backend so the
# gateway starts without any API keys; switch `backend:` / add secrets locally.
if [ ! -f config.yaml ]; then
  sed 's/^backend: groq/backend: mock/' config.example.yaml > config.yaml
fi
