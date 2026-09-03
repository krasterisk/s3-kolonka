# s3-kolonka

Своя прошивка умной колонки на **Waveshare ESP32-S3-Touch-LCD-1.85C V2 BOX**.

Это не XiaoZhi. Драйверы экрана, тача и аудио взяты из официального примера Waveshare. Приложение, UI и дальше протокол с сервером — наши.

Официальный XiaoZhi можно оставить на плате, пока эта прошивка не соберётся. Заливка `firmware/` затрёт его.

## Этапы

1. **Сейчас** — экран + LVGL + своя заставка (этот репозиторий).
2. Потом — динамик / микрофоны (ES8311 + ES7210).
3. Потом — свой сервер: STT → Ollama → TTS.
4. Потом — Home Assistant.
5. Потом — музыка / YouTube.

## Железо

- ESP32-S3, 16 MB flash, 8 MB Octal PSRAM
- Круглый ST77916 360×360, тач CST816
- V2: ES8311 (динамик), ES7210 (два мика), усилитель NS4150B

## Сборка

Нужен **ESP-IDF ≥ 5.5.1** (Waveshare для V2). На этой машине его ещё нет — ставим отдельно, не внутрь репозитория.

```powershell
# один раз, в PowerShell
mkdir $HOME\esp -Force
git clone -b v5.5.2 --recursive https://github.com/espressif/esp-idf.git $HOME\esp\esp-idf
cd $HOME\esp\esp-idf
.\install.ps1 esp32s3
```

Каждый раз перед сборкой:

```powershell
. $HOME\esp\esp-idf\export.ps1
cd C:\Users\Professional\Projects\s3-kolonka\firmware
idf.py set-target esp32s3
idf.py build
idf.py -p COMx flash monitor
```

После прошивки:
- на экране **s3-kolonka**, слайдеры VOL / BL
- при старте колонка пикает
- тап по экрану — режим прослушивания (дуга = уровень микрофона)
- если Wi-Fi ещё не задан, появится сеть **s3-kolonka** → http://192.168.4.1 (только 2.4 GHz)
- **Reset Wi-Fi** стирает сеть и перезагружает плату

## Структура

- `firmware/` — ESP-IDF проект
- `firmware/main/ui/` — наш интерфейс
- `vendor/waveshare-1.85c/` — официальные примеры (справочник)
