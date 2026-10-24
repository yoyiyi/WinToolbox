from __future__ import annotations

import os
import unittest

from wintoolbox.models import MemoryBoostResult, ProcessInfo
from wintoolbox.services.memory import MemoryBoostService, select_candidates


def proc(
    pid: int,
    name: str,
    memory: int,
    *,
    background: bool = True,
    system: bool = False,
) -> ProcessInfo:
    return ProcessInfo(
        pid=pid,
        name=name,
        memory_bytes=memory,
        is_background=background,
        is_system=system,
    )


class FakeSystem:
    def __init__(self) -> None:
        self.calls = 0

    def memory_snapshot(self):
        self.calls += 1
        if self.calls == 1:
            return 32 * 1024**3, 20 * 1024**3, 12 * 1024**3, 62.5
        return 32 * 1024**3, 19 * 1024**3, 13 * 1024**3, 59.4


class FakeProcesses:
    def collect(self, include_users: bool = True):
        return []


class MemorySelectionTests(unittest.TestCase):
    def test_filters_system_foreground_small(self) -> None:
        processes = [
            proc(100, "system.exe", 1024**3, system=True),
            proc(101, "foreground.exe", 500 * 1024**2, background=False),
            proc(102, "background.exe", 500 * 1024**2),
            proc(103, "tiny.exe", 1024),
            proc(4, "System", 1024**3),
        ]
        candidates = select_candidates(processes, include_foreground=False)
        self.assertEqual([item.pid for item in candidates], [102])

    def test_include_foreground(self) -> None:
        processes = [
            proc(101, "foreground.exe", 500 * 1024**2, background=False),
            proc(102, "background.exe", 800 * 1024**2),
        ]
        candidates = select_candidates(processes, include_foreground=True)
        self.assertEqual([item.pid for item in candidates], [102, 101])

    def test_invalid_sizes_are_skipped(self) -> None:
        candidates = select_candidates(
            [proc(os.getpid(), "self.exe", 1024**3), proc(500, "small.exe", 4)]
        )
        self.assertFalse(any(item.pid == os.getpid() for item in candidates))


class MemoryBoostServiceTests(unittest.TestCase):
    def test_empty_process_list_returns_snapshot_result(self) -> None:
        service = MemoryBoostService(FakeSystem(), FakeProcesses())
        result = service.boost()
        self.assertEqual(result.trimmed, 0)
        self.assertFalse(result.include_foreground)
        self.assertGreater(result.after_available, result.before_available)
        self.assertGreater(result.available_delta, 0)

    def test_available_delta_never_negative(self) -> None:
        result = MemoryBoostResult(before_available=100, after_available=90)
        self.assertEqual(result.available_delta, 0)


if __name__ == "__main__":
    unittest.main()
