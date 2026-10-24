from __future__ import annotations

import json
import unittest
from datetime import datetime

from wintoolbox.headless import build_json, build_text
from wintoolbox.models import DiskHealthReport, HardwareInfo


class HeadlessReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.info = HardwareInfo(
            hostname="HEADLESS-PC",
            cpu_name="Test CPU",
            cpu_cores=8,
            cpu_threads=16,
            memory_total=32 * 1024**3,
            display_count=0,
        )
        self.disks = DiskHealthReport()
        self.now = datetime(2026, 1, 2, 3, 4, 5)

    def test_text_report_supports_no_display(self) -> None:
        text = build_text(self.info, self.disks, self.now)
        self.assertIn("HEADLESS-PC", text)
        self.assertIn("Test CPU", text)
        self.assertIn("未检测到显示器", text)
        self.assertIn("磁盘健康", text)

    def test_json_report_contains_display_and_hardware(self) -> None:
        payload = json.loads(build_json(self.info, self.disks, self.now))
        self.assertEqual(payload["mode"], "headless")
        self.assertEqual(payload["hardware"]["hostname"], "HEADLESS-PC")
        self.assertEqual(payload["hardware"]["display_count"], 0)
        self.assertIn("display", payload)


if __name__ == "__main__":
    unittest.main()
