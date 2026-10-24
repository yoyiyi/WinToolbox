from __future__ import annotations

import unittest

from wintoolbox.services.tools import TOOL_SPECS, ToolService


class ToolCatalogTests(unittest.TestCase):
    def test_catalog_is_complete_and_unique(self) -> None:
        keys = [spec.key for spec in TOOL_SPECS]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertGreaterEqual(len(TOOL_SPECS), 14)
        for spec in TOOL_SPECS:
            self.assertTrue(spec.name)
            self.assertTrue(spec.description)
            self.assertTrue(spec.url.startswith("https://"))
            self.assertIn(spec.category, {"必用", "进阶"})

    def test_winget_mappings_are_optional_but_stable(self) -> None:
        by_key = {spec.key: spec for spec in TOOL_SPECS}
        self.assertEqual(by_key["cpuz"].winget_id, "CPUID.CPU-Z")
        self.assertEqual(by_key["crystaldiskinfo"].winget_id, "CrystalDewWorld.CrystalDiskInfo")
        self.assertEqual(by_key["memtest64"].winget_id, "")

    def test_detect_returns_one_status_per_tool(self) -> None:
        statuses = ToolService().detect()
        self.assertEqual(len(statuses), len(TOOL_SPECS))
        self.assertEqual(
            {status.spec.key for status in statuses},
            {spec.key for spec in TOOL_SPECS},
        )


if __name__ == "__main__":
    unittest.main()
