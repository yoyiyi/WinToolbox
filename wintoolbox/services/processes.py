"""使用 Toolhelp / Win32 API 枚举进程，不依赖 psutil 或 WMI。"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
from datetime import datetime, timedelta

from ..models import ProcessInfo
from ..utils import get_logger, human_bytes

LOGGER = get_logger("processes")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

TH32CS_SNAPPROCESS = 0x00000002
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_VM_READ = 0x0010
PROCESS_TERMINATE = 0x0001
TOKEN_QUERY = 0x0008
MAX_PATH = 32767

SYSTEM_PROCESS_NAMES = {
    "system",
    "registry",
    "memory compression",
    "secure system",
    "smss.exe",
    "csrss.exe",
    "wininit.exe",
    "winlogon.exe",
    "services.exe",
    "lsass.exe",
    "svchost.exe",
    "fontdrvhost.exe",
    "dwm.exe",
    "sihost.exe",
    "wudfhost.exe",
    "spoolsv.exe",
    "audiodg.exe",
    "conhost.exe",
    "dllhost.exe",
}


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]


class TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", SID_AND_ATTRIBUTES)]


kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE,
    wintypes.DWORD,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.GetProcessTimes.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
    ctypes.POINTER(wintypes.FILETIME),
]
kernel32.GetProcessTimes.restype = wintypes.BOOL
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL

psapi.GetProcessMemoryInfo.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
    wintypes.DWORD,
]
psapi.GetProcessMemoryInfo.restype = wintypes.BOOL

user32.EnumWindows.argtypes = [ctypes.c_void_p, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD

advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
advapi32.OpenProcessToken.restype = wintypes.BOOL
advapi32.GetTokenInformation.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
]
advapi32.GetTokenInformation.restype = wintypes.BOOL
advapi32.LookupAccountSidW.argtypes = [
    wintypes.LPCWSTR,
    ctypes.c_void_p,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(ctypes.c_int),
]
advapi32.LookupAccountSidW.restype = wintypes.BOOL


def _filetime_value(value: wintypes.FILETIME) -> int:
    return (value.dwHighDateTime << 32) | value.dwLowDateTime


def _filetime_datetime(value: wintypes.FILETIME) -> datetime | None:
    ticks = _filetime_value(value)
    if not ticks:
        return None
    try:
        return datetime(1601, 1, 1) + timedelta(microseconds=ticks // 10)
    except (OverflowError, ValueError):
        return None


def _window_titles() -> dict[int, str]:
    titles: dict[int, str] = {}

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd: int, _lparam: int) -> bool:
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            title = buffer.value.strip()
            if pid.value and title:
                titles.setdefault(int(pid.value), title[:160])
        except Exception:
            LOGGER.exception("读取窗口标题失败")
        return True

    user32.EnumWindows(callback, 0)
    return titles


def _token_username(handle: wintypes.HANDLE) -> str:
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(handle, TOKEN_QUERY, ctypes.byref(token)):
        return ""
    try:
        needed = wintypes.DWORD(0)
        advapi32.GetTokenInformation(token, 1, None, 0, ctypes.byref(needed))
        if needed.value <= 0:
            return ""
        buffer = ctypes.create_string_buffer(needed.value)
        if not advapi32.GetTokenInformation(
            token, 1, buffer, needed.value, ctypes.byref(needed)
        ):
            return ""
        token_user = ctypes.cast(buffer, ctypes.POINTER(TOKEN_USER)).contents
        if not token_user.User.Sid:
            return ""
        name = ctypes.create_unicode_buffer(256)
        domain = ctypes.create_unicode_buffer(256)
        name_size = wintypes.DWORD(256)
        domain_size = wintypes.DWORD(256)
        use = ctypes.c_int(0)
        if advapi32.LookupAccountSidW(
            None,
            token_user.User.Sid,
            name,
            ctypes.byref(name_size),
            domain,
            ctypes.byref(domain_size),
            ctypes.byref(use),
        ):
            return f"{domain.value}\\{name.value}" if domain.value else name.value
    finally:
        kernel32.CloseHandle(token)
    return ""


def _read_handle_info(
    handle: wintypes.HANDLE, include_user: bool
) -> tuple[str, int, int, datetime | None, str]:
    """返回 (路径, 内存, CPU 100ns, 创建时间, 用户名)。"""
    path = ""
    if handle:
        buffer = ctypes.create_unicode_buffer(MAX_PATH)
        size = wintypes.DWORD(MAX_PATH)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            path = buffer.value

    memory = 0
    cpu_ticks = 0
    created: datetime | None = None
    username = ""
    if handle:
        counters = PROCESS_MEMORY_COUNTERS_EX()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            memory = int(counters.WorkingSetSize)

        created_time = wintypes.FILETIME()
        exit_time = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created_time),
            ctypes.byref(exit_time),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            cpu_ticks = _filetime_value(kernel_time) + _filetime_value(user_time)
            created = _filetime_datetime(created_time)
        if include_user:
            username = _token_username(handle)
    return path, memory, cpu_ticks, created, username


class ProcessService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cpu_samples: dict[int, tuple[int, float]] = {}
        self._window_titles: dict[int, str] = {}
        self._last_error = ""

    @property
    def last_error(self) -> str:
        return self._last_error

    # ------------------------------------------------------------------
    def collect(self, include_users: bool = True) -> list[ProcessInfo]:
        with self._lock:
            return self._collect_locked(include_users)

    def _collect_locked(self, include_users: bool) -> list[ProcessInfo]:
        now = time.monotonic()
        self._window_titles = _window_titles()
        cpu_count = os.cpu_count() or 1
        snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            self._last_error = "无法创建进程快照"
            LOGGER.error(self._last_error)
            return []

        entries: list[PROCESSENTRY32W] = []
        try:
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
                self._last_error = "无法读取进程列表"
                return []
            while True:
                # PROCESSENTRY32W 会被 Process32NextW 原地复用，必须复制。
                entries.append(PROCESSENTRY32W.from_buffer_copy(entry))
                if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        finally:
            kernel32.CloseHandle(snapshot)

        pid_names = {int(item.th32ProcessID): item.szExeFile for item in entries}
        new_samples: dict[int, tuple[int, float]] = {}
        results: list[ProcessInfo] = []

        for item in entries:
            pid = int(item.th32ProcessID)
            if pid == 0:
                continue
            name = item.szExeFile
            handle = kernel32.OpenProcess(
                PROCESS_QUERY_INFORMATION | PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION,
                False,
                pid,
            )
            if not handle:
                # 权限不足时仍尝试受限查询，至少读到路径和名字。
                handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            try:
                path, memory, cpu_ticks, created, username = _read_handle_info(
                    handle, include_users
                )
            finally:
                if handle:
                    kernel32.CloseHandle(handle)

            cpu_percent = 0.0
            previous = self._cpu_samples.get(pid)
            if previous and handle:
                delta_ticks = max(0, cpu_ticks - previous[0])
                delta_seconds = max(0.25, now - previous[1])
                cpu_percent = min(
                    100.0,
                    (delta_ticks / 10_000_000.0) / delta_seconds / cpu_count * 100.0,
                )
            new_samples[pid] = (cpu_ticks, now)

            parent_pid = int(item.th32ParentProcessID)
            lower_name = name.casefold()
            is_system = (
                lower_name in SYSTEM_PROCESS_NAMES
                or pid <= 4
                or not path
            )
            title = self._window_titles.get(pid, "")
            results.append(
                ProcessInfo(
                    pid=pid,
                    name=name,
                    parent_pid=parent_pid,
                    parent_name=pid_names.get(parent_pid, ""),
                    cpu_percent=round(cpu_percent, 1),
                    memory_bytes=memory,
                    path=path,
                    username=username or ("SYSTEM" if pid <= 4 else ""),
                    window_title=title,
                    create_time=created,
                    is_background=not bool(title),
                    is_system=is_system,
                    threads=int(item.cntThreads),
                )
            )

        self._cpu_samples = new_samples
        self._last_error = ""
        results.sort(key=lambda item: (-item.cpu_percent, -item.memory_bytes, item.name.casefold()))
        return results

    # ------------------------------------------------------------------
    def is_protected(self, process: ProcessInfo) -> bool:
        return (
            process.is_system
            or process.name.casefold() in SYSTEM_PROCESS_NAMES
            or process.pid == os.getpid()
        )

    def kill(self, process: ProcessInfo) -> tuple[bool, str]:
        if self.is_protected(process):
            return False, "系统进程或工具箱自身受保护，已阻止结束操作。"
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, process.pid)
        if not handle:
            code = ctypes.get_last_error()
            return False, f"无法获取结束权限（错误码 {code}），请尝试以管理员身份运行。"
        try:
            if not kernel32.TerminateProcess(handle, 1):
                code = ctypes.get_last_error()
                return False, f"结束进程失败（错误码 {code}）。"
        finally:
            kernel32.CloseHandle(handle)
        return True, f"已结束 {process.name}（PID {process.pid}）。"

    def stats(self, processes: list[ProcessInfo]) -> dict[str, int | float | str]:
        total_memory = sum(item.memory_bytes for item in processes)
        background = sum(1 for item in processes if item.is_background and not item.is_system)
        foreground = sum(1 for item in processes if not item.is_background)
        return {
            "total": len(processes),
            "background": background,
            "foreground": foreground,
            "memory": total_memory,
            "memory_text": human_bytes(total_memory),
        }
