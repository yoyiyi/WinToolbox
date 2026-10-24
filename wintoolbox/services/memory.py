"""后台进程工作集整理（“内存加速”）。

注意：这里做的是回收闲置工作集，不会增加物理内存，也不会结束进程。
Windows 会在程序再次访问页面时按需换回，因此可能出现短暂卡顿。
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes

from ..models import MemoryBoostResult, ProcessInfo
from ..utils import audit, get_logger, human_bytes
from .processes import (
    PROCESS_MEMORY_COUNTERS_EX,
    PROCESS_QUERY_INFORMATION,
    PROCESS_VM_READ,
    SYSTEM_PROCESS_NAMES,
    kernel32,
    psapi,
)
from .system import SystemService
from .processes import ProcessService

LOGGER = get_logger("memory")

PROCESS_SET_QUOTA = 0x0100
MIN_WORKING_SET = 8 * 1024 * 1024

psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
psapi.EmptyWorkingSet.restype = wintypes.BOOL


def select_candidates(
    processes: list[ProcessInfo],
    include_foreground: bool = False,
    min_working_set: int = MIN_WORKING_SET,
) -> list[ProcessInfo]:
    """筛选可整理工作集的进程，按内存占用从高到低排序。"""
    candidates: list[ProcessInfo] = []
    own_pid = os.getpid()
    for process in processes:
        if process.pid <= 4 or process.pid == own_pid:
            continue
        if process.is_system or process.name.casefold() in SYSTEM_PROCESS_NAMES:
            continue
        if not include_foreground and not process.is_background:
            continue
        if process.memory_bytes < min_working_set:
            continue
        candidates.append(process)
    candidates.sort(key=lambda item: item.memory_bytes, reverse=True)
    return candidates


def _working_set_size(handle: wintypes.HANDLE) -> int:
    counters = PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
    if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return int(counters.WorkingSetSize)
    return 0


class MemoryBoostService:
    def __init__(self, system: SystemService, processes: ProcessService) -> None:
        self._system = system
        self._processes = processes

    def boost(self, include_foreground: bool = False) -> MemoryBoostResult:
        start = time.monotonic()
        before_total, _before_used, before_available, before_percent = (
            self._system.memory_snapshot()
        )
        processes = self._processes.collect(include_users=False)
        candidates = select_candidates(
            processes, include_foreground=include_foreground
        )
        skipped = max(0, len(processes) - len(candidates))
        trimmed = 0
        released = 0

        for process in candidates:
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_SET_QUOTA,
                False,
                process.pid,
            )
            if not handle:
                skipped += 1
                continue
            try:
                before_ws = _working_set_size(handle) or process.memory_bytes
                if not psapi.EmptyWorkingSet(handle):
                    skipped += 1
                    continue
                after_ws = _working_set_size(handle)
                trimmed += 1
                released += max(0, before_ws - after_ws)
            except OSError:
                skipped += 1
            finally:
                kernel32.CloseHandle(handle)

        after_total, _after_used, after_available, after_percent = (
            self._system.memory_snapshot()
        )
        result = MemoryBoostResult(
            before_total=before_total,
            before_available=before_available,
            before_percent=before_percent,
            after_total=after_total,
            after_available=after_available,
            after_percent=after_percent,
            working_set_released=released,
            trimmed=trimmed,
            skipped=skipped,
            elapsed=time.monotonic() - start,
            include_foreground=include_foreground,
        )
        audit(
            "memory_boost",
            {
                "trimmed": trimmed,
                "skipped": skipped,
                "released": released,
                "available_delta": result.available_delta,
                "include_foreground": include_foreground,
            },
        )
        LOGGER.info(
            "内存加速: trimmed=%d skipped=%d released=%s available_delta=%s",
            trimmed,
            skipped,
            human_bytes(released),
            human_bytes(result.available_delta),
        )
        return result
