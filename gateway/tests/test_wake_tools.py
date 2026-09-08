import unittest

from s3_kolonka_gw.device_ctrl import apply_tool, heuristic_commands, spoken_ack
from s3_kolonka_gw.wake import match_wake


class WakeTest(unittest.TestCase):
    def test_wake_and_command(self):
        woke, rest = match_wake("Колонка, сделай тише")
        self.assertTrue(woke)
        self.assertIn("тише", rest.lower())

    def test_no_wake(self):
        woke, rest = match_wake("какая погода")
        self.assertFalse(woke)
        self.assertEqual(rest, "какая погода")

    def test_wake_only(self):
        woke, rest = match_wake("слушай")
        self.assertTrue(woke)
        self.assertEqual(rest, "")

    def test_whisper_tonko(self):
        woke, rest = match_wake("Тонко! Ты меня слышишь?")
        self.assertTrue(woke)
        self.assertIn("слышишь", rest.lower())


class VadTimeoutTest(unittest.TestCase):
    def test_silence_allows_pause_between_words(self):
        from s3_kolonka_gw.adapters import groq

        self.assertGreaterEqual(groq._SILENCE_MS, 2000)


class DeviceCtrlTest(unittest.TestCase):
    def test_quieter(self):
        cmds = heuristic_commands("сделай потише", 50, 70)
        self.assertEqual(cmds, [{"name": "volume", "value": 30}])

    def test_sleep(self):
        cmds = heuristic_commands("выключись", 50, 70)
        self.assertEqual(cmds, [{"name": "power_off"}])

    def test_tool_volume(self):
        cmds, vol, bl = apply_tool("set_volume", {"percent": 10}, 50, 70)
        self.assertEqual(vol, 10)
        self.assertEqual(bl, 70)
        self.assertEqual(cmds[0]["name"], "volume")

    def test_ack(self):
        self.assertIn("50", spoken_ack([{"name": "volume", "value": 50}]))


if __name__ == "__main__":
    unittest.main()
