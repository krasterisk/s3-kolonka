# s3-kolonka

Custom firmware for the **Waveshare ESP32-S3-Touch-LCD-1.85C V2 BOX** and a
small WebSocket voice gateway.

The speaker is a thin client: it captures and plays **PCM16 mono 16 kHz**.
Speech-to-text, the LLM, and TTS run on the gateway — not on the ESP32.
This is **not** a XiaoZhi fork.

[Читать на русском](README.ru.md)

## Features

- Round 360×360 UI: Listen, volume, backlight, Wi-Fi reset
- SoftAP setup portal (`s3-kolonka` → `http://192.168.4.1`, 2.4 GHz only)
- Auto-stop on silence (no need to tap Stop)
- Gateway adapters: Groq (default), mock, and stubs for other backends
- Local Piper TTS (Russian `irina`) with espeak-ng fallback

## Architecture

```
┌──────────────────────┐     PCM16 / JSON      ┌─────────────────────┐
│  ESP32-S3 speaker    │ ───────────────────►  │  s3-kolonka-gw      │
│  firmware/           │  ws://host:8765/      │  STT → LLM → TTS    │
│  mic + speaker + UI  │ ◄───────────────────  │  gateway/           │
└──────────────────────┘     PCM16 + status    └─────────────────────┘
```

See [docs/protocol.md](docs/protocol.md) for the wire format.

## Hardware

| | |
| --- | --- |
| SoC | ESP32-S3, 16 MB flash, 8 MB octal PSRAM |
| Display | ST77916 360×360 |
| Touch | CST816 |
| Audio | ES8311 + ES7210, PA on GPIO15 |
| Wi-Fi | **2.4 GHz only** |

Official XiaoZhi images can stay on the board until you flash `firmware/`.
Flashing this project replaces that firmware.

## Firmware

Needs **ESP-IDF v5.5.2** (Waveshare V2 baseline).

```bash
# once
git clone -b v5.5.2 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf && ./install.sh esp32s3     # install.ps1 on Windows

# every build
. $HOME/esp/esp-idf/export.sh          # export.ps1 on Windows
cd firmware
idf.py set-target esp32s3
idf.py menuconfig                      # s3-kolonka → gateway host / port
idf.py -p <PORT> flash monitor
```

On Windows the serial port is usually `COM3`. After flash:

- Screen shows **s3-kolonka**, sliders VOL / BL
- If no Wi-Fi is stored, join **s3-kolonka** and open `http://192.168.4.1`
- **Reset Wi-Fi** clears credentials and reboots
- Tap Listen, speak, pause — the turn ends on silence

Set the gateway address in `idf.py menuconfig` or `firmware/sdkconfig`
(`CONFIG_KOLONKA_BRAIN_HOST`). Do not commit a production host.

## Gateway

```bash
cd gateway
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.yaml config.yaml     # add GROQ_API_KEY locally
python -m s3_kolonka_gw
```

Install [Piper](https://github.com/rhasspy/piper) and a Russian voice
(`deploy/install_piper.sh` is a starting point). `config.yaml` and `*.onnx`
are gitignored.

```bash
cd gateway && PYTHONPATH=. python -m unittest discover -s tests -v
```

A systemd unit lives in `gateway/deploy/s3-kolonka-gw.service`.
Firewall port **8765**; do not expose it to the whole internet.

## Repository layout

```
firmware/     ESP-IDF project (speaker)
gateway/      Python WebSocket brain
docs/         Protocol and notes
assets/       Logo
```

Waveshare's full vendor tree is not in git (~230 MB). Board drivers used at
runtime live under `firmware/main/` and `firmware/components/`.

## License

[MIT](LICENSE). Third-party notices are in [NOTICE](NOTICE).
Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md)
before opening issues or PRs.
