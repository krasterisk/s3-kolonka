# s3-kolonka gateway

Runs on Cubie (`192.168.3.24`). The speaker is a WebSocket client. Home Assistant stays on **8123**; this service uses **8765**.

```
speaker PCM 16 kHz  →  :8765  →  adapter (mock | gemini | aipbx | xiaozhi)
```

## Config

Copy `config.example.yaml` → `config.yaml`. `backend: mock` echoes audio (no cloud). Switch to `gemini` after the API key is on this host.

## Protocol

Text JSON: `hello`, `listen`, `stop`, `status`.  
Binary frames: PCM16 mono 16 kHz.

## HA safety

Do not bind 8123/1900/5353. Do not touch the `home-assistant` container.
