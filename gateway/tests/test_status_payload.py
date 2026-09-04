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


if __name__ == "__main__":
    unittest.main()
