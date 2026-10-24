from __future__ import annotations

import unittest
from datetime import date

from wintoolbox.utils import (
    decode_console,
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


if __name__ == "__main__":
    unittest.main()
