"""Probe Groq TTS. Never prints the API key."""
import urllib.error
import urllib.request
from pathlib import Path

import yaml

cfg = yaml.safe_load(Path("/opt/s3-kolonka-gw/config.yaml").read_text(encoding="utf-8")) or {}
key = ((cfg.get("groq") or {}).get("api_key") or "").strip()
body = (
    b'{"model":"playai-tts","input":"Privet","voice":"Celeste-PlayAI",'
    b'"response_format":"wav","sample_rate":16000}'
)
req = urllib.request.Request(
    "https://api.groq.com/openai/v1/audio/speech",
    data=body,
    headers={
        "Authorization": "Bearer " + key,
        "User-Agent": "s3-kolonka-gw/1.0",
        "Accept": "audio/wav",
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        print("OK", resp.status, "bytes", len(data), "riff", data[:4])
except urllib.error.HTTPError as exc:
    print("HTTP", exc.code, exc.read().decode("utf-8", "replace")[:220])
except Exception as exc:
    print(type(exc).__name__, str(exc)[:200])
