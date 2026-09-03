import yaml
from pathlib import Path

p = Path("/opt/s3-kolonka-gw/config.yaml")
cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
g = cfg.setdefault("groq", {})
g["piper_model"] = "/opt/s3-kolonka-gw/voices/ru_RU-irina-medium.onnx"
p.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print("piper_model", g.get("piper_model"), "has_key", bool((g.get("api_key") or "").strip()))
