#!/bin/bash
set -e
GW=/home/cubie/s3-kolonka-gw
cd "$GW"

if ! command -v ffmpeg >/dev/null; then
  echo "FFMPEG_MISSING"
else
  echo "FFMPEG_OK"
fi

"$GW/.venv/bin/python" - <<'PY'
import yaml
c = yaml.safe_load(open("/home/cubie/s3-kolonka-gw/config.yaml"))
g = c.get("groq") or {}
print("backend", c.get("backend"))
print("has_key", bool((g.get("api_key") or "").strip()))
print("has_proxy", bool((g.get("proxy") or "").strip()))
PY

# stop listeners on 8765 without printing secrets
pids=$(ss -lntp 2>/dev/null | awk '/:8765/ {print}' | sed -n 's/.*pid=\([0-9]*\).*/\1/p')
if [ -n "$pids" ]; then
  kill $pids 2>/dev/null || true
  sleep 1
fi
pkill -f "/home/cubie/s3-kolonka-gw/.venv/bin/python -m s3_kolonka_gw" 2>/dev/null || true
sleep 1

nohup "$GW/.venv/bin/python" -m s3_kolonka_gw >> "$GW/gw.log" 2>&1 &
sleep 2
ss -lnt | grep 8765 || echo "PORT_DOWN"
tail -n 6 "$GW/gw.log"
docker ps --filter name=home-assistant --format '{{.Names}} {{.Status}}' || true
