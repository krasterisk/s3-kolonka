from s3_kolonka_gw.adapters.base import VoiceBackend


class XiaozhiBackend(VoiceBackend):
    name = "xiaozhi"

    def __init__(self, url: str = "", token: str = ""):
        self.url = url
        self.token = token

    async def listen(self):
        await self.status("error", "xiaozhi: adapter not wired yet")

    async def stop(self):
        await self.status("idle", "xiaozhi")

    async def send_pcm(self, data: bytes):
        return
