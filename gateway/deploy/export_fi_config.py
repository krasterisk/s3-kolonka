import yaml
from pathlib import Path

src = Path("/home/cubie/s3-kolonka-gw/config.yaml")
dst = Path("/tmp/s3k-fi.yaml")
cfg = yaml.safe_load(src.read_text(encoding="utf-8")) or {}
groq = cfg.setdefault("groq", {})
groq["proxy"] = ""
dst.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print("wrote", dst.stat().st_size, "has_key", bool((groq.get("api_key") or "").strip()))
