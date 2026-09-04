import asyncio
import unittest

from s3_kolonka_gw.adapters.groq import GroqBackend


class SlowTurn(GroqBackend):
    def __init__(self):
        super().__init__({"api_key": "test"})
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def _finish_turn(self, pcm: bytes):
        self.started.set()
        await self.release.wait()


class SpeakChunks(GroqBackend):
    def __init__(self):
        super().__init__({"api_key": "test"})
        self.chunks = []
        self.sent = asyncio.Event()

    async def start(self, on_pcm, on_status):
        async def capture(data):
            self.chunks.append(data)
            if len(self.chunks) == 3:
                self.sent.set()
            await on_pcm(data)

        await super().start(capture, on_status)

    async def _finish_turn(self, pcm: bytes):
        await self._speak("hello", heard="hi")

    async def _tts(self, text: str) -> bytes:
        return b"\x00" * (3200 * 20)


class TurnAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_stop_returns_before_pipeline_finishes(self):
        backend = SlowTurn()
        await backend.listen()
        await backend.send_pcm(b"\x00\x00" * 2000)

        await asyncio.wait_for(backend.stop(), timeout=0.2)
        await asyncio.wait_for(backend.started.wait(), timeout=0.2)
        self.assertTrue(backend._busy)

        backend.release.set()
        await asyncio.wait_for(backend._turn_task, timeout=0.2)
        self.assertFalse(backend._busy)

    async def test_listen_drops_stale_tts_chunks(self):
        backend = GroqBackend({"api_key": "test"})
        chunks = []

        async def on_pcm(data):
            chunks.append(data)

        async def on_status(state, detail="", heard="", reply=""):
            return None

        await backend.start(on_pcm, on_status)
        await backend.listen()
        await backend._on_pcm(b"during-listen")
        self.assertEqual(chunks, [])

        backend._arm_tts()
        await backend._on_pcm(b"fresh")
        self.assertEqual(chunks, [b"fresh"])

        await backend.listen()
        await backend._on_pcm(b"stale")
        self.assertEqual(chunks, [b"fresh"])

    async def test_listen_cancels_in_flight_speak(self):
        silent = []

        async def on_pcm(data):
            silent.append(data)

        async def on_status(state, detail="", heard="", reply=""):
            return None

        backend = SpeakChunks()
        await backend.start(on_pcm, on_status)
        await backend.listen()
        await backend.send_pcm(b"\x00\x00" * 2000)
        await backend.stop()
        await asyncio.wait_for(backend.sent.wait(), timeout=2)
        before = len(backend.chunks)
        self.assertGreaterEqual(before, 3)

        await backend.listen()
        await asyncio.sleep(0.3)
        self.assertLessEqual(len(backend.chunks), before + 1)


if __name__ == "__main__":
    unittest.main()
