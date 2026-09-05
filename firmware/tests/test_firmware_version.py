import re
import unittest
from pathlib import Path


FIRMWARE = Path(__file__).resolve().parents[1]
VERSION = (FIRMWARE / "VERSION").read_text(encoding="utf-8").strip()
BUILD = (FIRMWARE / "BUILDNUM").read_text(encoding="utf-8").strip()
APP_VERSION = (FIRMWARE / "main/app/app_version.h").read_text(encoding="utf-8")
SETTINGS = (FIRMWARE / "main/ui/ui_settings.c").read_text(encoding="utf-8")
CMAKE = (FIRMWARE / "CMakeLists.txt").read_text(encoding="utf-8")


class FirmwareVersionTest(unittest.TestCase):
    def test_version_files_are_numeric(self):
        self.assertRegex(VERSION, r"^\d+\.\d+\.\d+$")
        self.assertRegex(BUILD, r"^\d+$")
        self.assertGreaterEqual(int(BUILD), 1)

    def test_header_matches_version_files(self):
        self.assertIn(f'#define KOLONKA_VERSION_STR "{VERSION}"', APP_VERSION)
        self.assertIn(f"#define KOLONKA_BUILD {BUILD}", APP_VERSION)
        self.assertIn("KOLONKA_VERSION_FULL", APP_VERSION)

    def test_cmake_reads_version_file(self):
        self.assertIn("PROJECT_VER", CMAKE)
        self.assertIn("VERSION", CMAKE)

    def test_settings_shows_firmware_version(self):
        self.assertIn('app_version.h', SETTINGS)
        self.assertIn("KOLONKA_VERSION_FULL", SETTINGS)
        self.assertIn("Прошивка ", SETTINGS)


if __name__ == "__main__":
    unittest.main()
