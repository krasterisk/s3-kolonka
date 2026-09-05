import re
import unittest
from pathlib import Path


FIRMWARE = Path(__file__).resolve().parents[1]
BRAIN = (FIRMWARE / "main/app/app_brain.c").read_text(encoding="utf-8")
SDKCONFIG = (FIRMWARE / "sdkconfig.defaults").read_text(encoding="utf-8")
KCONFIG = (FIRMWARE / "main/Kconfig.projbuild").read_text(encoding="utf-8")


class BrainTransportConfigTest(unittest.TestCase):
    def test_separate_tx_lock_stays_at_the_upstream_default(self):
        """It aborts the connection on the send-error path (esp-protocols#898)
        and buys nothing once brain_task is the only sender."""
        self.assertNotIn("CONFIG_ESP_WS_CLIENT_SEPARATE_TX_LOCK=y", SDKCONFIG)
        self.assertNotIn("select ESP_WS_CLIENT_SEPARATE_TX_LOCK", KCONFIG)
        self.assertIn("#if CONFIG_ESP_WS_CLIENT_SEPARATE_TX_LOCK", BRAIN)
        self.assertIn("#error", BRAIN)

    def test_pcm_frames_and_send_timeout_allow_realtime_uplink(self):
        chunk = re.search(r"#define UPLINK_CHUNK\s+(\d+)", BRAIN)
        timeout = re.search(
            r"esp_websocket_client_send_bin\(\s*"
            r"s_ws,.*?pdMS_TO_TICKS\((\d+)\)\)",
            BRAIN,
            re.DOTALL,
        )
        self.assertIsNotNone(chunk)
        self.assertIsNotNone(timeout)
        self.assertEqual(int(chunk.group(1)), 640)
        self.assertEqual(int(timeout.group(1)), 5000)
        send_uplink = re.search(
            r"static int send_uplink\(.*?^}",
            BRAIN,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(send_uplink)
        self.assertNotIn("vTaskDelay(", send_uplink.group(0))
        self.assertIn("taskYIELD();", send_uplink.group(0))

    def test_ui_does_not_write_to_websocket(self):
        radio_stop = re.search(
            r"void app_brain_radio_stop\(void\)\s*\{(.*?)\n\}",
            BRAIN,
            re.DOTALL,
        )
        self.assertIsNotNone(radio_stop)
        self.assertNotIn("send_json(", radio_stop.group(1))


if __name__ == "__main__":
    unittest.main()
