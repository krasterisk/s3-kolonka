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

    def test_websocket_lifecycle_waits_for_handshake(self):
        """Immediate destroy while !is_connected aborts TCP mid-handshake and
        reconnect-loops (~80 ms open→drop on the gateway)."""
        self.assertIn(".disable_auto_reconnect = false", BRAIN)
        offline = re.search(
            r"if \(!esp_websocket_client_is_connected\(s_ws\)\) \{(.*?)continue;\n\s*\}",
            BRAIN,
            re.DOTALL,
        )
        self.assertIsNotNone(offline)
        body = offline.group(1)
        self.assertIn("wait_ticks", body)
        self.assertIn("pdMS_TO_TICKS(500)", body)
        # destroy only after the stuck-offline timeout, not on every poll
        destroy_calls = re.findall(r"brain_destroy\(\)", body)
        self.assertEqual(len(destroy_calls), 1)
        self.assertIn("wait_ticks >= 24", body)
        self.assertNotIn("s_ws_dead ||", BRAIN)

    def test_listen_clears_sticky_pcm_radio(self):
        """pcm:// radio_play sets s_radio; if the stream dies without idle and
        the user re-opens listen, the mic stayed muted while UI said Слушаю."""
        audio = (FIRMWARE / "main/app/app_audio.c").read_text(encoding="utf-8")
        ui = (FIRMWARE / "main/ui/ui.c").read_text(encoding="utf-8")
        set_listen = re.search(
            r"void app_audio_set_listen\(bool on\)\s*\{(.*?)^\}",
            audio,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(set_listen)
        self.assertIn("app_audio_radio_stop()", set_listen.group(1))
        self.assertIn("live", BRAIN)
        # live/thinking/error must clear radio, not only abort PCM play
        live_block = re.search(
            r'strcmp\(st, "live"\).*?strcmp\(st, "error"\).*?\{(.*?)\} else if',
            BRAIN,
            re.DOTALL,
        )
        self.assertIsNotNone(live_block)
        self.assertIn("app_audio_radio_stop()", live_block.group(1))
        self.assertIn("ignore radio_play while listening", ui)
        self.assertIn("app_audio_is_listening()", ui)

    def test_listen_ignores_stale_end_status(self):
        """Late idle from the previous turn must not wipe a new listen.
        Protect must stay idle-only: blocking thinking/speaking left s_listen
        stuck and muted wake (maybe_wake bails while listening)."""
        self.assertIn("s_listen_protect_until", BRAIN)
        self.assertIn("s_status_gen", BRAIN)
        self.assertIn('cJSON_GetObjectItem(root, "gen")', BRAIN)
        self.assertIn("idle_protect", BRAIN)
        self.assertIn("pdMS_TO_TICKS(800)", BRAIN)
        think = re.search(
            r'if \(strcmp\(st, "thinking"\) == 0 \|\| strcmp\(st, "speaking"\).*?'
            r'\{(.*?)\n            \} else if \(strcmp\(st, "idle"\)',
            BRAIN,
            re.DOTALL,
        )
        self.assertIsNotNone(think)
        self.assertIn("!stale_gen", think.group(1))
        self.assertNotIn("idle_protect", think.group(1))
        idle = re.search(
            r'else if \(strcmp\(st, "idle"\) == 0\) \{\n'
            r'                if \(s_skip_idle\) \{(.*?)\n            \}',
            BRAIN,
            re.DOTALL,
        )
        self.assertIsNotNone(idle)
        self.assertIn("idle_protect", idle.group(1))
        set_listen = re.search(
            r"void app_brain_set_listen\(bool on\)\s*\{(.*?)^\}",
            BRAIN,
            re.DOTALL | re.MULTILINE,
        )
        self.assertIsNotNone(set_listen)
        self.assertIn("s_listen_protect_until", set_listen.group(1))
        end = re.search(
            r"if \(s_end_listen\) \{(.*?)if \(s_listen != s_listen_sent\)",
            BRAIN,
            re.DOTALL,
        )
        self.assertIsNotNone(end)
        self.assertIn("idle_protect", end.group(1))


if __name__ == "__main__":
    unittest.main()
