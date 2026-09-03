import struct
import unittest

from s3_kolonka_gw.pcmutil import pcm16_rms


class PcmRmsTest(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(pcm16_rms(b""), 0.0)

    def test_silence(self):
        self.assertEqual(pcm16_rms(b"\x00\x00" * 160), 0.0)

    def test_constant(self):
        pcm = struct.pack("<h", 1000) * 80
        self.assertAlmostEqual(pcm16_rms(pcm), 1000.0, places=3)


if __name__ == "__main__":
    unittest.main()
