"""Scenario tests: repeat media start/stop and wake-session recovery.

Acceptance:
  1. YouTube/radio play→stop→play ≥4 times without multi-second hangs
  2. After every stop, listen() must be accepted (session not wedged)
  3. Uncached YouTube starts via yt-dlp|ffmpeg pipe (not full pre-download)
  4. Repeat query prefers a cached previously-played id
"""

from __future__ import annotations

import asyncio
import time
import unittest
from pathlib import Path
from unittest import mock

from s3_kolonka_gw.adapters.groq import GroqBackend
from s3_kolonka_gw import youtube as yt


class MediaScenarioTest(unittest.IsolatedAsyncioTestCase):
    async def test_stop_replay_four_times_keeps_listen_alive(self):
        backend = GroqBackend({"api_key": "test"})
        statuses = []

        async def on_status(state, detail="", heard="", reply="", gen=None):
            statuses.append(state)

        async def on_pcm(_data):
            return None

        await backend.start(on_pcm, on_status)

        for i in range(4):
            backend._gen = i + 1
            backend._pcm_epoch = backend._gen
            backend._busy = True
            pumping = asyncio.Event()
            stop_gate = asyncio.Event()

            async def fake_stream(_source):
                pumping.set()
                await stop_gate.wait()

            backend._stream_youtube = fake_stream

            async def turn():
                try:
                    await backend._stream_youtube("yt://round%d" % (i + 1))
                finally:
                    backend._busy = False

            task = asyncio.create_task(turn())
            await asyncio.wait_for(pumping.wait(), timeout=1.0)

            t0 = time.monotonic()
            stop_gate.set()
            await asyncio.wait_for(backend.stop_radio(), timeout=3.0)
            self.assertLess(time.monotonic() - t0, 2.5, "stop hung on round %d" % (i + 1))
            self.assertFalse(backend._busy)
            self.assertEqual(statuses[-1], "idle")

            await asyncio.wait_for(backend.listen(), timeout=1.0)
            self.assertTrue(backend._listening)

            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    async def test_prepare_prefers_cached_played_id(self):
        cache = Path("/tmp/s3-kolonka-yt-prefer-cache")
        cache.mkdir(parents=True, exist_ok=True)
        played = cache / "played.json"
        if played.exists():
            played.unlink()

        backend = GroqBackend(
            {"api_key": "test"},
            youtube_cfg={"cache_dir": str(cache)},
        )
        yt.remember_played("хрум", "cached01", backend.youtube_cfg)
        (cache / "cached01").write_bytes(b"\x00" * 8192)

        def fake_iter(query, cfg=None, search_fn=None):
            return [
                {
                    "video_id": "cached01",
                    "title": "Хрум",
                    "url": "yt://cached01",
                    "query": query,
                },
                {
                    "video_id": "other02",
                    "title": "Other",
                    "url": "yt://other02",
                    "query": query,
                },
            ]

        with mock.patch.object(yt, "iter_track_candidates", fake_iter):
            ready = await backend._prepare_youtube("хрум")
        self.assertIsNotNone(ready)
        self.assertIn("cached01", ready.get("source") or "")

    async def test_stream_youtube_pipes_when_uncached(self):
        cache = Path("/tmp/s3-kolonka-yt-pipe")
        cache.mkdir(parents=True, exist_ok=True)
        backend = GroqBackend(
            {"api_key": "test"},
            youtube_cfg={"cache_dir": str(cache)},
        )
        pcm = []

        async def on_pcm(data):
            pcm.append(data)

        await backend.start(on_pcm, lambda *a, **k: None)
        backend._gen = 1
        backend._arm_tts()

        class Out:
            def __init__(self, chunks):
                self._chunks = list(chunks)

            async def read(self, _n):
                return self._chunks.pop(0) if self._chunks else b""

            def close(self):
                return None

        class Proc:
            def __init__(self, chunks=None):
                self.pid = 515151
                self.returncode = None
                self.stdout = Out(chunks or [])
                self.kill_called = False

            def kill(self):
                self.kill_called = True
                self.returncode = -9

            async def wait(self):
                if self.returncode is None:
                    self.returncode = -9
                return self.returncode

            async def communicate(self):
                self.returncode = 0
                return (b"", b"")

        ytdlp = Proc()
        ffmpeg = Proc(chunks=[b"\x00\x00" * 640, b"\x00\x00" * 640, b""])
        calls = []

        async def fake_exec(*cmd, **kwargs):
            calls.append({"cmd": cmd, "stdin": kwargs.get("stdin")})
            if kwargs.get("stdin") is not None:
                return ffmpeg
            return ytdlp

        with mock.patch("asyncio.create_subprocess_exec", side_effect=fake_exec), mock.patch(
            "s3_kolonka_gw.youtube.cached_file", return_value=None
        ), mock.patch(
            "s3_kolonka_gw.youtube.youtube_pcm_cmds",
            return_value=(["yt-dlp", "-o", "-", "u"], ["ffmpeg", "-i", "pipe:0"]),
        ), mock.patch.object(
            backend, "_ensure_youtube_file", side_effect=AssertionError("must not pre-download")
        ):
            await asyncio.wait_for(backend._stream_youtube("yt://pipe01"), timeout=2.0)

        self.assertGreater(len(pcm), 0)
        self.assertEqual(len(calls), 2)
        self.assertIsNotNone(calls[1]["stdin"])


class FirmwareWakePolicyTest(unittest.TestCase):
    def test_wake_runs_during_media_via_afe_and_soft_aec(self):
        audio = Path("/workspace/firmware/main/app/app_audio.c").read_text(encoding="utf-8")
        self.assertIn("Soft AEC wake during media", audio)
        self.assertIn("mww_set_cutoff(on ? 220 : 247)", audio)
        # Soft-AEC owns wake while media plays; AFE must not double-feed MWW.
        self.assertIn("do not also feed AFE audio into MWW", audio)
        feed = audio.split("afe_feed_task")[1].split("afe_fetch_task")[0]
        self.assertIn("aec_cancel", feed)
        self.assertIn("maybe_wake(wake_mono", feed)

    def test_build_is_at_least_nine(self):
        build = Path("/workspace/firmware/BUILDNUM").read_text(encoding="utf-8").strip()
        self.assertGreaterEqual(int(build), 9)


if __name__ == "__main__":
    unittest.main()
