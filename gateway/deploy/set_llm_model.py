import yaml
from pathlib import Path

p = Path("/opt/s3-kolonka-gw/config.yaml")
cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
g = cfg.setdefault("groq", {})
g["llm_model"] = "openai/gpt-oss-20b"
p.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print("llm_model", g.get("llm_model"), "has_key", bool((g.get("api_key") or "").strip()))
