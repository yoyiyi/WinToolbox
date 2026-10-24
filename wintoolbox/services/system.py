"""系统概览信息，使用 Win32 API，避免依赖 WMI。"""

from __future__ import annotations

import ctypes
import getpass
import os
import platform
import shutil
import socket
import sys
from ctypes import wintypes
from datetime import datetime, timedelta

from ..models import SystemInfo
from ..utils import get_logger, is_admin


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", wintypes.DWORD),
        ("dwMemoryLoad", wintypes.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def _filetime_to_int(value: wintypes.FILETIME) -> int:
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


class SystemService:
    def __init__(self) -> None:
        self._last_times: tuple[int, int, int] | None = None
        self._last_cpu_percent = 0.0

    # ------------------------------------------------------------------
    def _read_cpu_name(self) -> str:
        try:
            import winreg

            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            ) as key:
                value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
                return str(value).strip()
        except OSError:
            return platform.processor() or "未知处理器"

    def memory_snapshot(self) -> tuple[int, int, int, float]:
        """返回 (总内存, 已用, 可用, 使用率)。"""
        return self._read_memory()

    def _read_memory(self) -> tuple[int, int, int, float]:
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                total = int(status.ullTotalPhys)
                available = int(status.ullAvailPhys)
                used = max(0, total - available)
                percent = (used / total * 100.0) if total else 0.0
                return total, used, available, percent
        except (AttributeError, OSError):
            pass
        return 0, 0, 0, 0.0

    def _read_cpu_times(self) -> tuple[int, int, int] | None:
        idle = wintypes.FILETIME()
        kernel = wintypes.FILETIME()
        user = wintypes.FILETIME()
        try:
            ok = ctypes.windll.kernel32.GetSystemTimes(
                ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
            )
            if ok:
                return _filetime_to_int(idle), _filetime_to_int(kernel), _filetime_to_int(user)
        except (AttributeError, OSError):
            pass
        return None

    def _cpu_percent(self) -> float:
        current = self._read_cpu_times()
        if not current:
            return 0.0
        if self._last_times is None:
            self._last_times = current
            return 0.0
        idle_delta = current[0] - self._last_times[0]
        kernel_delta = current[1] - self._last_times[1]
        user_delta = current[2] - self._last_times[2]
        self._last_times = current
        total = kernel_delta + user_delta
        if total <= 0:
            return self._last_cpu_percent
        busy = max(0, total - idle_delta)
        self._last_cpu_percent = max(0.0, min(100.0, busy / total * 100.0))
        return self._last_cpu_percent

    def _read_disk(self) -> tuple[int, int, float]:
        drive = os.environ.get("SystemDrive", "C:") + "\\"
        try:
            usage = shutil.disk_usage(drive)
            percent = usage.used / usage.total * 100.0 if usage.total else 0.0
            return usage.total, usage.used, percent
        except OSError:
            return 0, 0, 0.0

    @staticmethod
    def _os_name(build: int) -> str:
        if build >= 22000:
            return "Windows 11"
        if build >= 10240:
            return "Windows 10"
        if build >= 9600:
            return "Windows 8.1"
        if build >= 7600:
            return "Windows 7"
        return platform.system() or "Windows"

    def collect(self) -> SystemInfo:
        try:
            version = sys.getwindowsversion()
            build = int(version.build)
            os_name = f"{self._os_name(build)} · Build {build}"
        except (AttributeError, ValueError):
            build = 0
            os_name = platform.platform(terse=True)

        total, used, _available, memory_percent = self._read_memory()
        disk_total, disk_used, disk_percent = self._read_disk()
        uptime = 0
        try:
            get_tick_count = ctypes.windll.kernel32.GetTickCount64
            get_tick_count.restype = ctypes.c_ulonglong
            uptime = int(get_tick_count() / 1000)
        except (AttributeError, OSError):
            pass

        cpu_name = self._read_cpu_name()
        if len(cpu_name) > 72:
            cpu_name = cpu_name[:71] + "…"
        try:
            username = getpass.getuser()
        except OSError:
            username = os.environ.get("USERNAME", "未知用户")

        return SystemInfo(
            os_name=os_name,
            build=str(build),
            architecture=platform.machine() or os.environ.get("PROCESSOR_ARCHITECTURE", ""),
            cpu_name=cpu_name,
            cpu_cores=os.cpu_count() or 1,
            memory_total=total,
            memory_used=used,
            memory_percent=memory_percent,
            disk_total=disk_total,
            disk_used=disk_used,
            disk_percent=disk_percent,
            uptime_seconds=uptime,
            hostname=socket.gethostname(),
            username=username,
            is_admin=is_admin(),
            python_version=platform.python_version(),
            cpu_percent=self._cpu_percent(),
        )
