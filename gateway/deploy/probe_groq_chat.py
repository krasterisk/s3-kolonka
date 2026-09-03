"""Probe Groq chat. Never prints the API key or full reply."""
import json
import urllib.error
import urllib.request
from pathlib import Path

import yaml

cfg = yaml.safe_load(Path("/opt/s3-kolonka-gw/config.yaml").read_text(encoding="utf-8")) or {}
g = cfg.get("groq") or {}
key = (g.get("api_key") or "").strip()
model = g.get("llm_model") or "openai/gpt-oss-20b"
print("model", model, "has_key", bool(key))
body = json.dumps(
    {
        "model": model,
        "messages": [{"role": "user", "content": "Ответь одним словом: ок"}],
        "temperature": 0.2,
        "max_tokens": 80,
    }
).encode("utf-8")
req = urllib.request.Request(
    "https://api.groq.com/openai/v1/chat/completions",
    data=body,
    headers={
        "Authorization": "Bearer " + key,
        "User-Agent": "s3-kolonka-gw/1.0",
        "Accept": "application/json",
        "Content-Type": "application/json",
    },
    method="POST",
)
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    msg = payload["choices"][0]["message"]
    content = (msg.get("content") or "").strip()
    print("OK", resp.status if False else 200, "content_len", len(content), "has_content", bool(content))
except urllib.error.HTTPError as exc:
    print("HTTP", exc.code, exc.read().decode("utf-8", "replace")[:200])
except Exception as exc:
    print(type(exc).__name__, str(exc)[:200])
