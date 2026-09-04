import json
import unittest

from s3_kolonka_gw import radio


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

        picked = radio.resolve_station("европа плюс", cfg, search_fn=search, picker_fn=picker)
        self.assertEqual(picked["uuid"], "ok-mp3")
        self.assertTrue(picked["url"].endswith(".mp3"))

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


if __name__ == "__main__":
    unittest.main()
