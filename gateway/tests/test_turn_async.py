import asyncio
import shutil
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


class PrepareYoutubeTest(unittest.IsolatedAsyncioTestCase):
    async def test_prepare_skips_unavailable_then_returns_playable(self):
        import tempfile
        from pathlib import Path

        from s3_kolonka_gw import youtube as yt

        cache_dir = tempfile.mkdtemp(prefix="s3-kolonka-yt-test-")
        self.addCleanup(shutil.rmtree, cache_dir, True)
        backend = GroqBackend(
            {"api_key": "test"},
            youtube_cfg={"cache_dir": cache_dir},
        )
        first = {"source": "yt://peDON2N4CoQ", "title": "ТУТХАМОН", "video_id": "peDON2N4CoQ"}
        tried = []

        def fake_iter(query, cfg=None, search_fn=None):
            return [
                {"video_id": "peDON2N4CoQ", "title": "ТУТХАМОН", "url": "yt://peDON2N4CoQ", "query": "хрум"},
                {"video_id": "tale01", "title": "Сказочный детектив", "url": "yt://tale01", "query": "сказочный детектив"},
            ]

        async def fake_ensure(source):
            tried.append(source)
            if "peDON2N4CoQ" in source:
                raise RuntimeError("ERROR: [youtube] peDON2N4CoQ: This video is not available")
            return Path("/tmp/tale01")

        orig = yt.iter_track_candidates
        yt.iter_track_candidates = fake_iter
        backend._ensure_youtube_file = fake_ensure
        try:
            ready = await backend._prepare_youtube("хрум или сказочный детектив", first)
        finally:
            yt.iter_track_candidates = orig

        self.assertIn("yt://tale01", tried)
        self.assertEqual(ready["name"], "radio_play")
        self.assertEqual(ready["source"], "yt://tale01")
        self.assertEqual(ready["title"], "Сказочный детектив")


if __name__ == "__main__":
    unittest.main()
