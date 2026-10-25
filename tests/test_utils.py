from __future__ import annotations

import unittest
from datetime import date

from wintoolbox.utils import (
    decode_console,
    fit_window_geometry,
    human_bytes,
    human_duration,
    normalize_msi_uninstall,
    parse_install_date,
    strip_ansi,
    truncate_middle,
)


class FormatTests(unittest.TestCase):
    def test_human_bytes(self) -> None:
        self.assertEqual(human_bytes(0), "0 B")
        self.assertEqual(human_bytes(1024), "1.0 KB")
        self.assertEqual(human_bytes(5 * 1024 * 1024), "5.0 MB")
        self.assertIn("GB", human_bytes(3 * 1024**3))

    def test_duration(self) -> None:
        self.assertEqual(human_duration(30), "30 秒")
        self.assertIn("小时", human_duration(7200))
        self.assertIn("天", human_duration(90000))

    def test_install_date(self) -> None:
        self.assertEqual(parse_install_date("20240501"), date(2024, 5, 1))
        self.assertEqual(parse_install_date("2024-05-01"), date(2024, 5, 1))
        self.assertIsNone(parse_install_date("not-a-date"))

    def test_truncate(self) -> None:
        self.assertEqual(truncate_middle("short", 10), "short")
        self.assertIn("…", truncate_middle("a" * 100, 20))

    def test_console_and_ansi(self) -> None:
        self.assertEqual(strip_ansi("\x1b[32mok\x1b[0m"), "ok")
        self.assertEqual(decode_console("中文".encode("utf-8")), "中文")
        self.assertEqual(decode_console("中文".encode("gb18030")), "中文")

    def test_msi_uninstall_normalization(self) -> None:
        self.assertEqual(
            normalize_msi_uninstall("MsiExec.exe /I{ABC}"),
            "MsiExec.exe /X{ABC}",
        )
        self.assertEqual(
            normalize_msi_uninstall("MsiExec.exe /X{ABC}"), "MsiExec.exe /X{ABC}"
        )


class WindowGeometryTests(unittest.TestCase):
    def _parse(self, value: str) -> tuple[int, int, int, int]:
        size, x, y = value.split("+")
        width, height = size.split("x")
        return int(width), int(height), int(x), int(y)

    def test_oversized_geometry_falls_back_and_centers(self) -> None:
        width, height, x, y = self._parse(
            fit_window_geometry("1717x1340+534+521", 2560, 1440)
        )
        self.assertEqual((width, height), (1360, 860))
        self.assertGreaterEqual(x, 10)
        self.assertGreaterEqual(y, 10)
        self.assertLessEqual(x + width, 2560)
        self.assertLessEqual(y + height, 1440)

    def test_small_screen_is_clamped(self) -> None:
        width, height, x, y = self._parse(
            fit_window_geometry("1717x1340+100+100", 1366, 768)
        )
        self.assertLessEqual(x + width, 1366)
        self.assertLessEqual(y + height, 768)

    def test_normal_geometry_is_preserved(self) -> None:
        self.assertEqual(
            fit_window_geometry("1400x900+0+0", 2560, 1440),
            "1400x900+580+252",
        )


if __name__ == "__main__":
    unittest.main()
