# Deploy notes

1. Copy this tree to the gateway host, e.g. `/opt/s3-kolonka-gw`.
2. Create a dedicated user, venv, and `config.yaml` (mode `0600`).
3. Run `install_piper.sh` if you want local Russian TTS.
4. Install `s3-kolonka-gw.service` and open port **8765** only to the speaker LAN.

Homelab-specific scripts stay in `private/` on your machine and are not
published.
