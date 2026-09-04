# Firmware

ESP-IDF project for the Waveshare ESP32-S3-Touch-LCD-1.85C V2 BOX.

## Configure

```bash
idf.py menuconfig
```

Under **s3-kolonka**:

- `CONFIG_KOLONKA_BRAIN_HOST` — gateway IPv4 or hostname
- `CONFIG_KOLONKA_BRAIN_PORT` — WebSocket port (default 8765)

`sdkconfig` is generated locally and is not tracked. Defaults in
`sdkconfig.defaults` use a LAN example address (`192.168.1.10`).

## Build / flash

```bash
idf.py set-target esp32s3
idf.py build
idf.py -p <PORT> flash monitor
```

## Notes

- `components/auido_borad` keeps the upstream Waveshare directory name
- LVGL demo sources under `main/LVGL_UI/` are linked for the vendor drivers;
  the UI is `main/ui/` (Home / Media / Settings)
- SoftAP SSID is `s3-kolonka`. Wi-Fi is 2.4 GHz only
- Wake is on-device Hey Jarvis (microWakeWord). Echo cancellation is ESP-SR
  AFE AEC only — WakeNet stays off. If AFE fails to start, the one-tap
  canceller in `app/aec.c` is used instead
