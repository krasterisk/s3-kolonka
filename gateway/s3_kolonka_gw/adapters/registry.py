from s3_kolonka_gw.adapters.aipbx import AipbxBackend
from s3_kolonka_gw.adapters.base import VoiceBackend
from s3_kolonka_gw.adapters.gemini import GeminiBackend
from s3_kolonka_gw.adapters.groq import GroqBackend
from s3_kolonka_gw.adapters.mock import MockBackend
from s3_kolonka_gw.adapters.xiaozhi import XiaozhiBackend


def create_backend(cfg: dict) -> VoiceBackend:
    name = (cfg.get("backend") or "mock").strip().lower()
    if name == "mock":
        return MockBackend()
    if name == "groq":
        return GroqBackend(cfg.get("groq") or {})
    if name == "gemini":
        g = cfg.get("gemini") or {}
        return GeminiBackend(api_key=g.get("api_key") or "", model=g.get("model") or "")
    if name == "aipbx":
        a = cfg.get("aipbx") or {}
        return AipbxBackend(
            url=a.get("url") or "",
            assistant_id=a.get("assistant_id") or "",
            token=a.get("token") or "",
        )
    if name == "xiaozhi":
        x = cfg.get("xiaozhi") or {}
        return XiaozhiBackend(url=x.get("url") or "", token=x.get("token") or "")
    raise ValueError("unknown backend: %s" % name)
