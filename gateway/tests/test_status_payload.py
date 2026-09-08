import unittest

from s3_kolonka_gw.adapters.groq import GroqBackend
from s3_kolonka_gw.main import pop_listen_orphan, stash_listen_orphan, status_payload


class StatusPayloadTest(unittest.TestCase):
    def test_includes_heard_and_reply(self):
        msg = status_payload("speaking", "groq tts", heard="который час", reply="Сейчас семь.")
        self.assertEqual(msg["type"], "status")
        self.assertEqual(msg["state"], "speaking")
        self.assertEqual(msg["heard"], "который час")
        self.assertEqual(msg["reply"], "Сейчас семь.")

    def test_omits_empty_text(self):
        msg = status_payload("idle", "groq")
        self.assertNotIn("heard", msg)
        self.assertNotIn("reply", msg)

    def test_includes_gen_when_set(self):
        msg = status_payload("live", "groq", gen=3)
        self.assertEqual(msg["gen"], 3)
        self.assertNotIn("gen", status_payload("idle", "groq"))


class StatusGenPinTest(unittest.IsolatedAsyncioTestCase):
    async def test_status_if_pins_turn_gen_after_listen_bump(self):
        """Late idle from turn N must keep gen=N even if listen bumped _gen."""
        backend = GroqBackend({"api_key": "test"})
        payloads = []

        async def on_status(state, detail="", heard="", reply="", gen=None):
            if gen is None:
                gen = backend._gen
            payloads.append(status_payload(state, detail, heard, reply, gen=gen))

        await backend.start(lambda _d: None, on_status)
        backend._gen = 4
        # Simulate TOCTOU: listen() already bumped gen before status send.
        backend._gen = 5
        await backend.status("idle", "groq", gen=4)
        self.assertEqual(len(payloads), 1)
        self.assertEqual(payloads[0]["state"], "idle")
        self.assertEqual(payloads[0]["gen"], 4)

    async def test_status_if_skips_when_gen_mismatches(self):
        backend = GroqBackend({"api_key": "test"})
        payloads = []

        async def on_status(state, detail="", heard="", reply="", gen=None):
            payloads.append(state)

        await backend.start(lambda _d: None, on_status)
        backend._gen = 2
        ok = await backend._status_if(1, "idle", "stale")
        self.assertFalse(ok)
        self.assertEqual(payloads, [])

    async def test_status_if_forwards_pinned_gen(self):
        backend = GroqBackend({"api_key": "test"})
        payloads = []

        async def on_status(state, detail="", heard="", reply="", gen=None):
            payloads.append(gen)

        await backend.start(lambda _d: None, on_status)
        backend._gen = 7
        ok = await backend._status_if(7, "thinking", "stt")
        self.assertTrue(ok)
        self.assertEqual(payloads, [7])


class ListenOrphanTest(unittest.TestCase):
    def test_stash_ignores_short_clip(self):
        store = {}
        self.assertFalse(stash_listen_orphan(store, "1.2.3.4", b"\x00" * 100, "tap", now=10))
        self.assertEqual(store, {})

    def test_pop_returns_fresh_pcm_and_expires(self):
        store = {}
        pcm = b"\x00\x01" * 10000
        self.assertTrue(stash_listen_orphan(store, "1.2.3.4", pcm, "tap", now=10))
        self.assertIsNone(pop_listen_orphan(store, "9.9.9.9", now=11))
        got = pop_listen_orphan(store, "1.2.3.4", now=12)
        self.assertEqual(got["pcm"], pcm)
        self.assertEqual(got["mode"], "tap")
        store2 = {}
        stash_listen_orphan(store2, "1.2.3.4", pcm, "wake", now=10)
        self.assertIsNone(pop_listen_orphan(store2, "1.2.3.4", now=30))

    def test_backend_snapshot_only_while_listening(self):
        backend = GroqBackend({"api_key": "test"})
        backend._listening = True
        backend._busy = False
        backend._buf.extend(b"abc")
        self.assertEqual(backend.listen_pcm_snapshot(), b"abc")
        backend._listening = False
        self.assertEqual(backend.listen_pcm_snapshot(), b"")


class ResumeOrphanTest(unittest.IsolatedAsyncioTestCase):
    async def test_resume_orphan_returns_without_awaiting_turn(self):
        """Orphan resume used to await the full YouTube turn and wedged the
        WS handler — radio_stop never ran until the track ended."""
        import asyncio
        import time

        from s3_kolonka_gw.main import _resume_orphan

        class SlowTurn(GroqBackend):
            def __init__(self):
                super().__init__({"api_key": "test"})
                self.started = asyncio.Event()
                self.release = asyncio.Event()

            async def _finish_turn(self, pcm: bytes, turn_gen: int):
                self.started.set()
                await self.release.wait()

        backend = SlowTurn()

        async def on_pcm(_d):
            return None

        async def on_status(*_a, **_k):
            return None

        await backend.start(on_pcm, on_status)
        t0 = time.monotonic()
        await asyncio.wait_for(
            _resume_orphan(backend, {"pcm": b"\x00\x01" * 9000, "mode": "tap"}),
            timeout=1.0,
        )
        self.assertLess(time.monotonic() - t0, 0.5)
        await asyncio.wait_for(backend.started.wait(), timeout=0.5)
        self.assertFalse(backend._turn_task.done())
        backend.release.set()
        await asyncio.wait_for(backend._turn_task, timeout=0.5)


if __name__ == "__main__":
    unittest.main()
