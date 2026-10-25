from __future__ import annotations

import unittest

from wintoolbox.services.startup import approval_blob


class StartupApprovalTests(unittest.TestCase):
    def test_enabled_blob(self) -> None:
        data = approval_blob(True)
        self.assertEqual(len(data), 12)
        self.assertEqual(data[0], 2)
        self.assertEqual(data[1:], b"\x00" * 11)

    def test_disabled_blob_has_timestamp(self) -> None:
        data = approval_blob(False)
        self.assertEqual(len(data), 12)
        self.assertEqual(data[0], 3)
        self.assertNotEqual(data[4:], b"\x00" * 8)


if __name__ == "__main__":
    unittest.main()
