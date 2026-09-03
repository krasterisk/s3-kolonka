# s3-kolonka

Своя прошивка для **Waveshare ESP32-S3-Touch-LCD-1.85C V2 BOX** и небольшой
голосовой шлюз по WebSocket.

Колонка — тонкий клиент: пишет и играет **PCM16 mono 16 kHz**.
STT, LLM и TTS живут на шлюзе, не на ESP32.
Это **не** форк XiaoZhi.

[Read in English](README.md)

## Что умеет

- Круглый UI 360×360: Listen, громкость, подсветка, сброс Wi-Fi
- Портал настройки (`s3-kolonka` → `http://192.168.4.1`, только 2.4 GHz)
- Авто-стоп по тишине (не нужно жать Stop)
- Адаптеры шлюза: Groq (по умолчанию), mock и заготовки под другие backend
- Локальный Piper (русский голос `irina`), запасной вариант — espeak-ng

## Сборка прошивки

Нужен **ESP-IDF v5.5.2**.

```powershell
. $HOME\esp\esp-idf\export.ps1
cd firmware
idf.py set-target esp32s3
idf.py menuconfig          # s3-kolonka → хост и порт шлюза
idf.py -p COM3 flash monitor
```

Адрес шлюза задаётся в menuconfig (`CONFIG_KOLONKA_BRAIN_HOST`).
Продакшен-хост в git не коммитим.

## Шлюз

```bash
cd gateway
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp config.example.yaml config.yaml
python -m s3_kolonka_gw
```

Протокол: [docs/protocol.md](docs/protocol.md). Лицензия — [MIT](LICENSE).
