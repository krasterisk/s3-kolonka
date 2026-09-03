import yaml
from pathlib import Path

p = Path("/home/cubie/s3-kolonka-gw/config.yaml")
cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
cfg.setdefault(
    "groq",
    {
        "api_key": "",
        "stt_model": "whisper-large-v3-turbo",
        "llm_model": "llama-3.1-8b-instant",
        "voice": "ru-RU-SvetlanaNeural",
    },
)
p.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
print("merged")
