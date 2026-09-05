# Contributing

Thanks for helping with s3-kolonka.

## Ways to help

- Bug reports with hardware revision, ESP-IDF version, and logs
- Fixes that stay on the thin-client path (PCM on the speaker, intelligence on the gateway)
- Documentation that does not include real hosts, keys, or home networks

## Development setup

### Firmware

ESP-IDF **v5.5.2** (or newer 5.5.x), target `esp32s3`.

```bash
. $HOME/esp/esp-idf/export.sh   # export.ps1 on Windows
cd firmware
idf.py set-target esp32s3
idf.py menuconfig               # set gateway host/port under "s3-kolonka"
idf.py build
```

Do not commit `firmware/sdkconfig` or `firmware/build/`.

Firmware versioning: bump `firmware/BUILDNUM` (and `KOLONKA_BUILD` in
`firmware/main/app/app_version.h`) for every image you flash. Bump
`firmware/VERSION` / `KOLONKA_VERSION_*` when cutting a release entry in
`CHANGELOG.md`. The Settings tab shows `Прошивка <version>+<build>`.
Do not name the build-number file `BUILD` — on Windows it collides with
the ESP-IDF `build/` directory.

### Gateway

Python 3.11+.

```bash
cd gateway
python -m venv .venv
.venv/bin/pip install -r requirements.txt   # Scripts\pip on Windows
cp config.example.yaml config.yaml          # add keys locally, never commit
PYTHONPATH=. python -m unittest discover -s tests -v
```

## Pull requests

1. Fork and branch from `main`.
2. Keep commits focused. Conventional Commits are preferred (`fix:`, `feat:`, `docs:`, `chore:`).
3. No API keys, hostnames of production boxes, or Wi-Fi credentials.
4. If you change voice protocol or UI status strings, update `docs/protocol.md`.
5. Open a PR against `main` and fill in the template.

## Code style

- C: 4-space indent, existing ESP-IDF / Waveshare naming in drivers
- Python: 4-space indent, no new runtime dependencies without discussion
- Do not rename `firmware/components/auido_borad` — the spelling is upstream
