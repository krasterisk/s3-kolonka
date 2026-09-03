from s3_kolonka_gw.adapters.base import VoiceBackend


class AipbxBackend(VoiceBackend):
    name = "aipbx"

    def __init__(self, url: str = "", assistant_id: str = "", token: str = ""):
        self.url = url
        self.assistant_id = assistant_id
        self.token = token

    async def listen(self):
        await self.status("error", "aipbx: adapter not wired yet")

    async def stop(self):
        await self.status("idle", "aipbx")

    async def send_pcm(self, data: bytes):
        return
