# s3-kolonka gateway

Python WebSocket server. The speaker is the client.

```
speaker PCM 16 kHz  →  :8765  →  adapter (groq | mock | …)
```

## Setup

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.yaml config.yaml
# set groq.api_key or GROQ_API_KEY — never commit the file
python -m s3_kolonka_gw --config config.yaml
```

Default listen address is `0.0.0.0:8765`. Ports **8123 / 1900 / 5353** are
rejected so a Home Assistant host is not stomped by accident.

## TTS

1. Piper (`piper_model` in config) — preferred for Russian
2. espeak-ng
3. Groq / Edge TTS as last resorts

`deploy/install_piper.sh` downloads `ru_RU-irina-medium` into `voices/`
(gitignored).

## YouTube audio

Songs go through the same PCM path as radio. The gateway searches YouTube
Music (`ytmusicapi`, fallback `yt-dlp ytsearch`), extracts audio with
`yt-dlp`, and `ffmpeg` emits PCM16 mono 16 kHz. The speaker only receives
`radio_play` with `url=pcm://`. Repeat plays can use `youtube.cache_dir`.

Install `yt-dlp` and `ytmusicapi` on the gateway host (already in
`requirements.txt`) and keep `yt-dlp` updated — YouTube extraction breaks
when Google changes player clients.

## Tests

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
```

## Deploy

`deploy/s3-kolonka-gw.service` is a generic systemd unit for `/opt/s3-kolonka-gw`.
Keep `config.yaml` mode `0600` and firewall port 8765.

## Protocol

See [../docs/protocol.md](../docs/protocol.md).
