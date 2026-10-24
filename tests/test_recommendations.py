from __future__ import annotations

import unittest
from datetime import date, timedelta

from wintoolbox.models import AppRecord
from wintoolbox.services.apps import classify_app, recommend_apps


def app(
    name: str,
    publisher: str = "Example",
    category_hint: str = "",
    days_old: int | None = None,
    size_kb: int = 100 * 1024,
    uninstall: str = "uninstall.exe",
) -> AppRecord:
    record = AppRecord(
        name=name,
        publisher=publisher,
        size_kb=size_kb,
        uninstall_string=uninstall,
    )
    if days_old is not None:
        record.install_date = date.today() - timedelta(days=days_old)
    return record


class ClassificationTests(unittest.TestCase):
    def test_name_beats_publisher(self) -> None:
        self.assertEqual(classify_app("YouTube", "Google\\Chrome"), "媒体")
        self.assertEqual(classify_app("Google Chrome", "Google LLC"), "浏览器")

    def test_runtime_and_security(self) -> None:
        self.assertEqual(classify_app("Microsoft Visual C++ 2015 Redistributable"), "运行库/驱动")
        self.assertEqual(classify_app("火绒安全软件"), "安全")


class RecommendationTests(unittest.TestCase):
    def test_protected_runtime_is_not_recommended(self) -> None:
        records = recommend_apps(
            [app("Microsoft Visual C++ 2015 Redistributable (x64)", "Microsoft Corporation")]
        )
        self.assertTrue(records[0].protected)
        self.assertEqual(records[0].advice, "建议保留")
        self.assertEqual(records[0].score, 0)

    def test_known_bloat_is_recommended(self) -> None:
        records = recommend_apps([app("Driver Booster 11", "IObit")])
        self.assertEqual(records[0].advice, "可考虑卸载")
        self.assertGreaterEqual(records[0].score, 45)

    def test_windows_upgrade_tool_is_recommended(self) -> None:
        records = recommend_apps(
            [app("Windows 11 安装助手", "Microsoft Corporation", size_kb=5000)]
        )
        self.assertEqual(records[0].advice, "可考虑卸载")
        self.assertIn("一次", records[0].reasons[0])

    def test_duplicate_browsers_are_flagged(self) -> None:
        records = recommend_apps(
            [
                app("Chrome"),
                app("Firefox"),
                app("Edge"),
                app("Opera"),
            ]
        )
        for record in records:
            self.assertIn("同类", " ".join(record.reasons))
            self.assertEqual(record.advice, "按需保留")

    def test_missing_uninstall_entry_is_cannot_uninstall(self) -> None:
        records = recommend_apps([app("Orphan Tool", uninstall="")])
        self.assertFalse(records[0].can_uninstall)
        self.assertEqual(records[0].advice, "无法卸载")

    def test_old_large_app_gets_age_signal(self) -> None:
        records = recommend_apps([app("Old Utility", days_old=365 * 4, size_kb=80 * 1024)])
        self.assertGreater(records[0].score, 0)
        self.assertIn("安装已超过", " ".join(records[0].reasons))


if __name__ == "__main__":
    unittest.main()
