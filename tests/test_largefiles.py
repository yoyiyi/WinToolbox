from __future__ import annotations

import os
import shutil
import threading
import unittest
import uuid
from pathlib import Path

from wintoolbox.models import LargeFile
from wintoolbox.services.largefiles import LargeFileService, is_protected_path


def sparse_file(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(size)


class LargeFileTests(unittest.TestCase):
    def setUp(self) -> None:
        # 使用普通 mkdir 继承工作区权限；受管工作区里 tempfile 的 0700 可能被拒绝。
        test_root = Path.cwd() / ".runtime"
        test_root.mkdir(exist_ok=True)
        self.root = test_root / f"wintoolbox-large-{uuid.uuid4().hex[:10]}"
        self.root.mkdir()

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def test_scan_threshold_and_skip_system_dirs(self) -> None:
        sparse_file(self.root / "tiny.bin", 1024)
        sparse_file(self.root / "movies" / "big.iso", 2 * 1024**2)
        sparse_file(self.root / "Windows" / "system.bin", 3 * 1024**2)
        service = LargeFileService()
        result = service.scan(str(self.root), 1024**2, include_system=False)
        names = {item.name for item in result.files}
        self.assertEqual(names, {"big.iso"})
        self.assertEqual(result.files[0].file_type, "镜像 · ISO")
        self.assertGreaterEqual(result.scanned_files, 1)

        result_with_system = service.scan(
            str(self.root), 1024**2, include_system=True
        )
        self.assertEqual(
            {item.name for item in result_with_system.files},
            {"big.iso", "system.bin"},
        )

    def test_scan_cancellation(self) -> None:
        sparse_file(self.root / "big.bin", 2 * 1024**2)
        cancel = threading.Event()
        cancel.set()
        result = LargeFileService().scan(
            str(self.root), 0, cancel_event=cancel
        )
        self.assertTrue(result.cancelled)
        self.assertEqual(result.files, [])

    def test_scan_result_limit(self) -> None:
        for index in range(3):
            sparse_file(self.root / f"big-{index}.bin", 2 * 1024**2)
        result = LargeFileService().scan(
            str(self.root), 1024**2, max_results=2
        )
        self.assertTrue(result.truncated)
        self.assertEqual(len(result.files), 2)

    def test_protected_paths(self) -> None:
        self.assertTrue(is_protected_path(r"C:\Windows\System32\foo.dll"))
        self.assertTrue(is_protected_path(r"C:\pagefile.sys"))
        self.assertTrue(is_protected_path(r"D:\System Volume Information\x.dat"))
        self.assertFalse(is_protected_path(r"C:\Users\example\Videos\movie.mp4"))

    def test_recycle_rejects_protected_file(self) -> None:
        item = LargeFile(
            path=r"C:\Windows\not-a-real-file.exe",
            size=123,
            protected=True,
        )
        result = LargeFileService().recycle([item])
        self.assertEqual(result.recycled, [])
        self.assertEqual(len(result.failed), 1)

    def test_list_drives(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows only")
        drives = LargeFileService().list_drives()
        self.assertTrue(drives)
        self.assertTrue(any(drive.letter.endswith(":") for drive in drives))
        self.assertTrue(any(drive.total > 0 for drive in drives))


if __name__ == "__main__":
    unittest.main()
