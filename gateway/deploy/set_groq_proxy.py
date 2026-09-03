import yaml
from pathlib import Path

p = Path("/home/cubie/s3-kolonka-gw/config.yaml")
cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
g = cfg.setdefault("groq", {})
g["proxy"] = "http://192.168.2.37:8877"
p.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print("proxy_set", bool(g.get("proxy")), "has_key", bool((g.get("api_key") or "").strip()))
