import json
import unittest
import urllib.error
from io import BytesIO

from s3_kolonka_gw import radio


class _FakeResp:
    def __init__(self, body, ctype="audio/mpeg", extra=None):
        self.body = body
        self.headers = {"Content-Type": ctype}
        if extra:
            self.headers.update(extra)

    def read(self, n=-1):
        return self.body if n < 0 else self.body[:n]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeOpener:
    def __init__(self, routes=None, error=None):
        self.routes = routes or {}
        self.error = error

    def open(self, req, timeout=None):
        url = getattr(req, "full_url", "") or str(req)
        if self.error:
            raise urllib.error.HTTPError(url, self.error, "err", None, BytesIO(b""))
        for key, resp in self.routes.items():
            if key == "" or key in url:
                return resp
        raise urllib.error.URLError("no route for %s" % url)


SAMPLE = [
    {
        "stationuuid": "ok-mp3",
        "name": "Europa Plus",
        "url_resolved": "http://ep256.hostingradio.ru:8052/europaplus256.mp3",
        "codec": "MP3",
        "bitrate": 256,
        "hls": 0,
        "lastcheckok": 1,
        "countrycode": "RU",
    },
    {
        "stationuuid": "hls",
        "name": "Europa HLS",
        "url_resolved": "http://hls-01-fresh.emgsound.ru/9/playlist.m3u8",
        "codec": "AAC",
        "bitrate": 116,
        "hls": 1,
        "lastcheckok": 1,
        "countrycode": "RU",
    },
    {
        "stationuuid": "aac",
        "name": "Europa AAC",
        "url_resolved": "https://online2.gkvr.ru:8001/europa_che_64.aac",
        "codec": "AAC+",
        "bitrate": 64,
        "hls": 0,
        "lastcheckok": 1,
        "countrycode": "RU",
    },
    {
        "stationuuid": "low",
        "name": "Tiny MP3",
        "url_resolved": "http://example.com/low.mp3",
        "codec": "MP3",
        "bitrate": 48,
        "hls": 0,
        "lastcheckok": 1,
        "countrycode": "RU",
    },
    {
        "stationuuid": "unknown-br",
        "name": "Europa Plus 128",
        "url_resolved": "http://ep128.streamr.ru/",
        "codec": "MP3",
        "bitrate": 0,
        "hls": 0,
        "lastcheckok": 1,
        "countrycode": "RU",
    },
]


class RadioUriTest(unittest.TestCase):
    def test_adds_mp3_hint_when_path_has_no_extension(self):
        from s3_kolonka_gw.radio import player_uri

        self.assertEqual(
            player_uri("http://ep128server.streamr.ru:8030/ep128"),
            "http://ep128server.streamr.ru:8030/ep128#stream.mp3",
        )
        self.assertEqual(
            player_uri("http://emgregion.hostingradio.ru:8064/moscow.europaplus.mp3"),
            "http://emgregion.hostingradio.ru:8064/moscow.europaplus.mp3",
        )
        self.assertTrue(player_uri("https://host/stream?token=1").endswith("#stream.mp3"))


class RadioFilterTest(unittest.TestCase):
    def test_keeps_mp3_icecast_and_unknown_bitrate(self):
        cfg = radio.normalize_config({})
        got = radio.filter_stations(SAMPLE, cfg)
        ids = [s["uuid"] for s in got]
        self.assertEqual(ids, ["ok-mp3", "unknown-br"])
        self.assertTrue(all(s["url"].endswith(".mp3") or "streamr" in s["url"] for s in got))

    def test_rejects_hls_and_non_mp3(self):
        cfg = radio.normalize_config({"bitrate_min": 128})
        ids = {s["uuid"] for s in radio.filter_stations(SAMPLE, cfg)}
        self.assertNotIn("hls", ids)
        self.assertNotIn("aac", ids)
        self.assertNotIn("low", ids)


class RadioPickerTest(unittest.TestCase):
    def test_accepts_uuid_from_list(self):
        cands = radio.filter_stations(SAMPLE, radio.normalize_config({}))
        picked = radio.parse_picker_reply('{"uuid":"ok-mp3","title":"Европа Плюс"}', cands)
        self.assertEqual(picked["uuid"], "ok-mp3")
        self.assertEqual(picked["url"], SAMPLE[0]["url_resolved"])
        self.assertEqual(picked["title"], "Европа Плюс")

    def test_rejects_unknown_uuid_and_invented_url(self):
        cands = radio.filter_stations(SAMPLE, radio.normalize_config({}))
        self.assertIsNone(radio.parse_picker_reply('{"uuid":"nope","title":"x"}', cands))
        self.assertIsNone(
            radio.parse_picker_reply(
                '{"uuid":null,"title":"x","url":"http://evil.example/stream.mp3"}',
                cands,
            )
        )

    def test_resolve_uses_picker_not_aliases(self):
        cfg = radio.normalize_config({})

        def search(query, _cfg):
            self.assertEqual(query, "европа плюс")
            return SAMPLE

        def picker(query, cands):
            self.assertEqual(query, "европа плюс")
            return json.dumps({"uuid": cands[0]["uuid"], "title": cands[0]["name"]})

        picked = radio.resolve_station(
            "европа плюс", cfg, search_fn=search, picker_fn=picker, probe_fn=lambda u: True
        )
        self.assertEqual(picked["uuid"], "ok-mp3")
        self.assertTrue(picked["url"].endswith(".mp3"))


class RadioProbeTest(unittest.TestCase):
    def test_accepts_mpeg_sync_and_audio_type(self):
        mpeg = bytes.fromhex("fffbe04000000b00") + b"\x00" * 32
        self.assertTrue(radio.looks_like_mp3(mpeg, "audio/mpeg"))
        self.assertTrue(radio.looks_like_mp3(b"ID3" + b"\x00" * 20, "application/octet-stream"))
        self.assertFalse(radio.looks_like_mp3(b"<!DOCTYPE html>", "text/html"))
        self.assertFalse(radio.looks_like_mp3(b"", "text/html"))

    def test_probe_stream_uses_opener(self):
        mpeg = bytes.fromhex("fffbe040") + b"\x00" * 16
        cfg = radio.normalize_config({})
        self.assertTrue(
            radio.probe_stream(
                "http://ok.example/live.mp3",
                cfg,
                opener=_FakeOpener({"": _FakeResp(mpeg)}),
            )
        )

    def test_probe_rejects_http_error_and_html(self):
        cfg = radio.normalize_config({})
        self.assertFalse(
            radio.probe_stream(
                "http://dead.example/gone.mp3",
                cfg,
                opener=_FakeOpener(error=404),
            )
        )
        self.assertFalse(
            radio.probe_stream(
                "http://dead.example/page",
                cfg,
                opener=_FakeOpener({"": _FakeResp(b"<!DOCTYPE html>", "text/html")}),
            )
        )

    def test_probe_accepts_icecast_headers_without_mpeg_sync(self):
        cfg = radio.normalize_config({})
        self.assertTrue(
            radio.probe_stream(
                "http://ok.example/live",
                cfg,
                opener=_FakeOpener(
                    {
                        "": _FakeResp(
                            b"\x00" * 32,
                            "application/octet-stream",
                            extra={"icy-name": "Europa Plus", "icy-metaint": "16000"},
                        )
                    }
                ),
            )
        )

    def test_resolve_skips_dead_url_and_uses_next(self):
        cfg = radio.normalize_config({})

        def search(query, _cfg):
            return SAMPLE

        def picker(query, cands):
            return json.dumps({"uuid": "ok-mp3", "title": "dead first"})

        dead = "http://ep256.hostingradio.ru:8052/europaplus256.mp3"
        live = "http://ep128.streamr.ru/"

        def probe(url):
            return live in url

        picked = radio.resolve_station(
            "европа плюс", cfg, search_fn=search, picker_fn=picker, probe_fn=probe
        )
        self.assertIsNotNone(picked)
        self.assertEqual(picked["uuid"], "unknown-br")
        self.assertIn("streamr", picked["url"])

    def test_resolve_default_probe_skips_html_then_uses_live(self):
        cfg = radio.normalize_config({})
        mpeg = bytes.fromhex("fffbe040") + b"\x00" * 16
        opener = _FakeOpener(
            {
                "europaplus256": _FakeResp(b"<!DOCTYPE html>", "text/html"),
                "streamr": _FakeResp(mpeg, "audio/mpeg"),
            }
        )
        picked = radio.resolve_station(
            "европа плюс",
            cfg,
            search_fn=lambda q, c: SAMPLE,
            picker_fn=lambda q, c: json.dumps({"uuid": "ok-mp3", "title": "dead first"}),
            opener=opener,
        )
        self.assertIsNotNone(picked)
        self.assertEqual(picked["uuid"], "unknown-br")
        self.assertIn("streamr", picked["url"])

    def test_resolve_none_when_all_dead(self):
        cfg = radio.normalize_config({})

        def search(query, _cfg):
            return SAMPLE

        picked = radio.resolve_station(
            "европа плюс",
            cfg,
            search_fn=search,
            picker_fn=lambda q, c: json.dumps({"uuid": c[0]["uuid"], "title": "x"}),
            probe_fn=lambda u: False,
        )
        self.assertIsNone(picked)

    def test_search_url_uses_yaml_base(self):
        cfg = radio.normalize_config({"base_url": "https://nl1.api.radio-browser.info"})
        url = radio.search_url(cfg, "europa plus")
        self.assertTrue(url.startswith("https://nl1.api.radio-browser.info/json/stations/search?"))
        self.assertIn("codec=MP3", url)
        self.assertIn("hidebroken=true", url)


class RadioHeuristicTest(unittest.TestCase):
    def test_stop_radio_phrase(self):
        from s3_kolonka_gw.device_ctrl import heuristic_commands

        cmds = heuristic_commands("выключи радио", 50, 70)
        self.assertTrue(any(c.get("name") == "radio_stop" for c in cmds))

    def test_play_radio_query_from_spoken_request(self):
        from s3_kolonka_gw.device_ctrl import radio_play_query

        self.assertEqual(radio_play_query("Включи радио европа плюс"), "европа плюс")
        self.assertEqual(radio_play_query("включай радио европа плюс"), "европа плюс")
        self.assertEqual(radio_play_query("поставь радио джаз"), "джаз")
        self.assertEqual(radio_play_query("включи радио"), "")
        self.assertIsNone(radio_play_query("выключи радио"))
        self.assertIsNone(radio_play_query("включи экран"))
        self.assertIsNone(radio_play_query("какая погода"))

    def test_attach_radio_play_when_llm_only_talks(self):
        from s3_kolonka_gw.device_ctrl import attach_radio_play

        def pick(query):
            self.assertEqual(query, "европа плюс")
            return {
                "url": "http://ep256.hostingradio.ru:8052/europaplus256.mp3",
                "title": "Европа Плюс",
                "uuid": "ok-mp3",
            }

        cmds, err = attach_radio_play([], "Включи радио европа плюс", pick)
        self.assertIsNone(err)
        self.assertEqual(cmds[0]["name"], "radio_play")
        self.assertTrue(cmds[0]["url"].endswith(".mp3"))
        self.assertEqual(cmds[0]["title"], "Европа Плюс")

    def test_attach_radio_play_keeps_existing_cmd(self):
        from s3_kolonka_gw.device_ctrl import attach_radio_play

        existing = [{"name": "radio_play", "url": "http://already/", "title": "X"}]
        cmds, err = attach_radio_play(existing, "Включи радио европа плюс", lambda q: self.fail("should not pick"))
        self.assertEqual(cmds, existing)
        self.assertIsNone(err)

    def test_attach_radio_play_missing_station(self):
        from s3_kolonka_gw.device_ctrl import attach_radio_play

        cmds, err = attach_radio_play([], "включи радио ноунейм", lambda q: None)
        self.assertEqual(cmds, [])
        self.assertIn("станц", err.lower())


if __name__ == "__main__":
    unittest.main()
