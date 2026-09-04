import unittest

from s3_kolonka_gw.main import status_payload


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


if __name__ == "__main__":
    unittest.main()
