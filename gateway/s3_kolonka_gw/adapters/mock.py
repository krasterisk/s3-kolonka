import asyncio
import logging

from s3_kolonka_gw.adapters.base import VoiceBackend

log = logging.getLogger("gw.mock")

_MAX_BYTES = 16000 * 2 * 8
_CHUNK = 640


class MockBackend(VoiceBackend):
    name = "mock"

    def __init__(self):
        self._listening = False
        self._buf = bytearray()

    async def listen(self, mode="tap"):
        self._listening = True
        self._buf.clear()
        log.info("listen")
        await self.status("live", "mock")

    async def stop(self):
        self._listening = False
        pcm = bytes(self._buf)
        self._buf.clear()
        log.info("stop bytes=%s", len(pcm))
        await self.status("speaking", "mock echo")
        on_pcm = getattr(self, "_on_pcm", None)
        if on_pcm and pcm:
            for i in range(0, len(pcm), _CHUNK):
                await on_pcm(pcm[i : i + _CHUNK])
                await asyncio.sleep(0.018)
        await self.status("idle", "mock")

    async def send_pcm(self, data: bytes):
        if not self._listening or not data:
            return
        self._buf.extend(data)
        if len(self._buf) > _MAX_BYTES:
            del self._buf[: len(self._buf) - _MAX_BYTES]
