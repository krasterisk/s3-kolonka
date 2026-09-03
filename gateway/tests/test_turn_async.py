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


if __name__ == "__main__":
    unittest.main()
