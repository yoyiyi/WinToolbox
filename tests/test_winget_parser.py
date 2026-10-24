from __future__ import annotations

import unittest

from wintoolbox.services.winget import parse_upgrade_table


SAMPLE = """\
Name                              Id                          Version      Available    Source
----------------------------------------------------------------------------------------------
Mozilla Firefox                   Mozilla.Firefox             128.0        130.0        winget
7-Zip 24.09                       7zip.7zip                   24.09        24.10        winget
Microsoft Teams                   Microsoft.Teams             1.0          2.0          msstore
Some Tool With Spaces             Vendor.SomeTool             2.1          2.2          winget

4 upgrades available.
"""


class WingetParserTests(unittest.TestCase):
    def test_parses_standard_table(self) -> None:
        updates = parse_upgrade_table(SAMPLE)
        self.assertEqual(len(updates), 4)
        self.assertEqual(updates[0].name, "Mozilla Firefox")
        self.assertEqual(updates[0].package_id, "Mozilla.Firefox")
        self.assertEqual(updates[0].current_version, "128.0")
        self.assertEqual(updates[0].available_version, "130.0")
        self.assertEqual(updates[2].source, "msstore")
        self.assertEqual(updates[3].name, "Some Tool With Spaces")

    def test_handles_localized_header(self) -> None:
        output = """\
名称                          ID                          版本         可用         源
------------------------------------------------------------------------------------------
Google Chrome                 Google.Chrome               120.0        121.0        winget

1 upgrades available.
"""
        updates = parse_upgrade_table(output)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].package_id, "Google.Chrome")

    def test_handles_cjk_display_width(self) -> None:
        # 中文表头按显示宽度排版，不能按字符下标切片；长名称可能只有一个空格分隔 ID。
        output = """\
名称                    ID                     版本          可用                 源

----------------------------------------------------------------------------------------

Microsoft Edge          Microsoft.Edge         155.0.4283.62 156.0.4314.42        winget

Microsoft Teams         Microsoft.Teams        1.0.0.1       26225.1806.5074.1452 winget

Rockstar Games Launcher RockstarGames.Launcher 1.0.90.1977   1.0.109.3031         winget

3 升级可用。
"""
        updates = parse_upgrade_table(output)
        self.assertEqual(len(updates), 3)
        self.assertEqual(updates[0].name, "Microsoft Edge")
        self.assertEqual(updates[0].current_version, "155.0.4283.62")
        self.assertEqual(updates[0].available_version, "156.0.4314.42")
        self.assertEqual(updates[2].name, "Rockstar Games Launcher")
        self.assertEqual(updates[2].package_id, "RockstarGames.Launcher")

    def test_handles_unaligned_row(self) -> None:
        output = """\
Name                              Id                          Version      Available    Source
----------------------------------------------------------------------------------------------
Microsoft Teams              Microsoft.Teams           1.0          2.0          msstore

1 upgrades available.
"""
        updates = parse_upgrade_table(output)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].package_id, "Microsoft.Teams")

    def test_no_updates(self) -> None:
        self.assertEqual(parse_upgrade_table("No installed package found matching input criteria."), [])
        self.assertEqual(parse_upgrade_table(""), [])

    def test_does_not_return_header_or_summary(self) -> None:
        output = """\
Name Id Version Available Source
--------------------------------
"""
        self.assertEqual(parse_upgrade_table(output), [])


if __name__ == "__main__":
    unittest.main()
