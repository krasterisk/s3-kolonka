import logging

from s3_kolonka_gw.adapters.base import VoiceBackend

log = logging.getLogger("gw.gemini")


class GeminiBackend(VoiceBackend):
    """Gemini Live — implemented after API key is on the gateway."""

    name = "gemini"

    def __init__(self, api_key: str = "", model: str = ""):
        self.api_key = (api_key or "").strip()
        self.model = model or "gemini-live-2.5-flash-native-audio"

    async def listen(self, mode="tap"):
        if not self.api_key:
            log.warning("no api_key")
            await self.status("error", "gemini: no api_key")
            return
        await self.status("error", "gemini: adapter not wired yet")

    async def stop(self):
        await self.status("idle", "gemini")

    async def send_pcm(self, data: bytes):
        return
