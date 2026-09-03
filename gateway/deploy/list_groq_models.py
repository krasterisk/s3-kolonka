"""List Groq model ids. Never prints the API key."""
import json
import urllib.request
from pathlib import Path

import yaml

cfg = yaml.safe_load(Path("/opt/s3-kolonka-gw/config.yaml").read_text(encoding="utf-8")) or {}
key = ((cfg.get("groq") or {}).get("api_key") or "").strip()
req = urllib.request.Request(
    "https://api.groq.com/openai/v1/models",
    headers={"Authorization": "Bearer " + key, "User-Agent": "s3-kolonka-gw/1.0"},
)
with urllib.request.urlopen(req, timeout=20) as resp:
    payload = json.loads(resp.read().decode("utf-8"))
ids = sorted(item.get("id") or "" for item in payload.get("data") or [])
for mid in ids:
    if mid:
        print(mid)
