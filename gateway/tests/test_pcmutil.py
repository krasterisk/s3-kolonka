import struct
import unittest

from s3_kolonka_gw.pcmutil import RADIO_FRAME_BYTES, ffmpeg_radio_cmd, pcm16_realtime_s, pcm16_rms


class PcmRmsTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(pcm16_rms(b""), 0.0)

    def test_silence(self):
        self.assertEqual(pcm16_rms(b"\x00\x00" * 160), 0.0)

    def test_constant(self):
        pcm = struct.pack("<h", 1000) * 80
        self.assertAlmostEqual(pcm16_rms(pcm), 1000.0, places=3)


class FfmpegRadioCmdTest(unittest.TestCase):
    def test_decodes_http_stream_to_pcm16_16k(self):
        cmd = ffmpeg_radio_cmd("http://silverrain.hostingradio.ru/silver128.mp3")
        self.assertIn("-f", cmd)
        self.assertIn("s16le", cmd)
        self.assertIn("-ar", cmd)
        self.assertIn("16000", cmd)
        self.assertIn("-ac", cmd)
        self.assertIn("1", cmd)
        self.assertEqual(cmd[-1], "pipe:1")
        self.assertIn("http://silverrain.hostingradio.ru/silver128.mp3", cmd)
        self.assertIn("+nobuffer", cmd)
        self.assertIn("low_delay", cmd)
        self.assertIn("-vn", cmd)
        self.assertEqual(RADIO_FRAME_BYTES, 640)
        self.assertAlmostEqual(pcm16_realtime_s(640), 0.02)

    def test_rejects_non_http_url(self):
        with self.assertRaises(ValueError):
            ffmpeg_radio_cmd("file:///tmp/x.mp3")


if __name__ == "__main__":
    unittest.main()
