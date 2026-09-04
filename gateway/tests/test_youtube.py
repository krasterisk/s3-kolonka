import unittest

from s3_kolonka_gw import youtube
from s3_kolonka_gw.device_ctrl import (
    attach_music_play,
    music_play_query,
    radio_play_query,
)


class MusicIntentTest(unittest.TestCase):
    def test_music_query_from_spoken_request(self):
        self.assertEqual(music_play_query("Включи песню Кино группа крови"), "кино группа крови")
        self.assertEqual(music_play_query("поставь трек beatles yesterday"), "beatles yesterday")
        self.assertEqual(music_play_query("включи клип группа крови"), "группа крови")
        self.assertEqual(music_play_query("включи на ютубе кино"), "кино")
        self.assertEqual(
            music_play_query("Включи с YouTube хром или сказочный детектив"),
            "хрум или сказочный детектив",
        )
        self.assertEqual(
            music_play_query("включи хром или сказочный детектив"),
            "хрум или сказочный детектив",
        )
        self.assertEqual(music_play_query("включи маяк"), "маяк")
        self.assertEqual(music_play_query("включи сказочный детектив"), "сказочный детектив")
        self.assertIsNone(music_play_query("включи радио рок-фм"))
        self.assertIsNone(music_play_query("включи радио маяк"))
        self.assertIsNone(music_play_query("выключи музыку"))
        self.assertIsNone(music_play_query("включи экран"))

    def test_radio_query_ignores_songs(self):
        self.assertIsNone(radio_play_query("включи песню кино"))
        self.assertIsNone(radio_play_query("Включи с YouTube хром или сказочный детектив"))
        self.assertIsNone(radio_play_query("включи хром или сказочный детектив"))
        self.assertIsNone(radio_play_query("включи маяк"))
        self.assertEqual(radio_play_query("включи радио рок-фм"), "рок-фм")
        self.assertEqual(radio_play_query("включи радио маяк"), "маяк")

    def test_attach_music_play(self):
        def pick(query):
            self.assertEqual(query, "кино группа крови")
            return {
                "video_id": "abc123",
                "title": "Кино — Группа крови",
                "url": "yt://abc123",
            }

        cmds, err = attach_music_play([], "включи песню кино группа крови", pick)
        self.assertIsNone(err)
        self.assertEqual(cmds[0]["name"], "radio_play")
        self.assertEqual(cmds[0]["url"], "pcm://")
        self.assertEqual(cmds[0]["source"], "yt://abc123")
        self.assertEqual(cmds[0]["title"], "Кино — Группа крови")

    def test_attach_music_missing(self):
        cmds, err = attach_music_play([], "включи песню ноунейм", lambda q: None)
        self.assertEqual(cmds, [])
        self.assertIn("наш", err.lower())


class YoutubeSearchTest(unittest.TestCase):
    def test_search_tracks_tries_videos_before_songs(self):
        seen = []

        def fake(query, limit=5, kind="songs"):
            seen.append(kind)
            if kind == "videos":
                return [{"video_id": "vid1", "title": "clip", "url": "yt://vid1"}]
            return []

        orig = youtube.search_ytmusic
        youtube.search_ytmusic = fake
        try:
            rows = youtube.search_tracks("хрум")
        finally:
            youtube.search_ytmusic = orig
        self.assertEqual(seen, ["videos"])
        self.assertEqual(rows[0]["video_id"], "vid1")

    def test_parse_ytdlp_search_lines(self):
        raw = "dQw4w9WgXcQ\tRick Astley - Never Gonna Give You Up\nxyz\tOther\n"
        got = youtube.parse_search_lines(raw)
        self.assertEqual(got[0]["video_id"], "dQw4w9WgXcQ")
        self.assertIn("Rick", got[0]["title"])
        self.assertEqual(got[0]["url"], "yt://dQw4w9WgXcQ")

    def test_хром_или_becomes_хрум_not_chrome(self):
        alts = youtube.query_alternatives("Включи хром или сказочный детектив")
        self.assertEqual(alts, ["сказочный детектив", "хрум"])
        self.assertNotIn("хром", alts)

    def test_resolve_tries_или_alternative(self):
        seen = []

        def search(query, _cfg):
            seen.append(query)
            if query == "сказочный детектив":
                return [{"video_id": "tale01", "title": "Сказочный детектив", "url": "yt://tale01"}]
            return []

        picked = youtube.resolve_track("хром или сказочный детектив", search_fn=search)
        self.assertEqual(seen, ["сказочный детектив"])
        self.assertEqual(picked["video_id"], "tale01")

    def test_resolve_uses_injected_search(self):
        def search(query, _cfg):
            self.assertEqual(query, "кино группа крови")
            return [
                {"video_id": "vid1", "title": "Кино — Группа крови", "url": "yt://vid1"},
                {"video_id": "vid2", "title": "Cover", "url": "yt://vid2"},
            ]

        picked = youtube.resolve_track("кино группа крови", search_fn=search)
        self.assertEqual(picked["video_id"], "vid1")
        self.assertEqual(picked["url"], "yt://vid1")

    def test_iter_yields_all_alternatives_and_rows(self):
        def search(query, _cfg):
            if query == "сказочный детектив":
                return [
                    {"video_id": "dead01", "title": "blocked", "url": "yt://dead01"},
                    {"video_id": "tale01", "title": "Сказочный детектив", "url": "yt://tale01"},
                ]
            if query == "хрум":
                return [{"video_id": "hrum01", "title": "Хрум", "url": "yt://hrum01"}]
            return []

        rows = list(youtube.iter_track_candidates("хром или сказочный детектив", search_fn=search))
        self.assertEqual([r["video_id"] for r in rows], ["dead01", "tale01", "hrum01"])
        self.assertEqual(rows[0]["query"], "сказочный детектив")
        self.assertEqual(rows[2]["query"], "хрум")

    def test_first_playable_skips_unavailable(self):
        cands = [
            {"video_id": "peDON2N4CoQ", "title": "ТУТХАМОН", "url": "yt://peDON2N4CoQ"},
            {"video_id": "tale01", "title": "Сказочный детектив", "url": "yt://tale01"},
        ]
        tried = []

        def download(row):
            tried.append(row["video_id"])
            if row["video_id"] == "peDON2N4CoQ":
                raise RuntimeError("ERROR: [youtube] peDON2N4CoQ: This video is not available")
            return "/cache/" + row["video_id"]

        picked = youtube.first_playable_track(cands, download)
        self.assertEqual(tried, ["peDON2N4CoQ", "tale01"])
        self.assertEqual(picked["video_id"], "tale01")
        self.assertTrue(youtube.ytdlp_error_unavailable("ERROR: [youtube] x: This video is not available"))
        self.assertIsNone(youtube.first_playable_track(cands[:1], download))

    def test_watch_url_and_pcm_cmds(self):
        self.assertEqual(youtube.watch_url("dQw4w9WgXcQ"), "https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        ytdlp, ff = youtube.youtube_pcm_cmds("yt://dQw4w9WgXcQ", ytdlp="/bin/yt-dlp", ffmpeg="/bin/ffmpeg")
        self.assertEqual(ytdlp[0], "/bin/yt-dlp")
        self.assertIn("https://www.youtube.com/watch?v=dQw4w9WgXcQ", ytdlp)
        self.assertIn("-o", ytdlp)
        self.assertIn("-", ytdlp)
        self.assertEqual(ff[0], "/bin/ffmpeg")
        self.assertIn("s16le", ff)
        self.assertIn("pipe:1", ff)

    def test_cache_path_uses_id(self):
        cfg = youtube.normalize_config({"cache_dir": "/tmp/yt-test"})
        path = youtube.cache_path("AbC-12", cfg)
        self.assertTrue(str(path).endswith("AbC-12"))
        self.assertIn("yt-test", str(path))

    def test_download_cmd_writes_file_not_stdout(self):
        dest = "/var/cache/s3-kolonka-yt/dQw4w9WgXcQ.part"
        cmd = youtube.ytdlp_download_cmd("yt://dQw4w9WgXcQ", dest, ytdlp="/bin/yt-dlp")
        self.assertEqual(cmd[0], "/bin/yt-dlp")
        self.assertIn("https://www.youtube.com/watch?v=dQw4w9WgXcQ", cmd)
        self.assertEqual(cmd[cmd.index("-o") + 1], dest)
        self.assertNotIn("-", cmd[cmd.index("-o") + 1 :])


if __name__ == "__main__":
    unittest.main()
