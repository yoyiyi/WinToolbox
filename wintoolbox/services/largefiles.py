"""磁盘枚举、大文件扫描与回收站操作。"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..models import DriveInfo, LargeFile, LargeFileScanResult, RecycleResult
from ..utils import audit, get_logger

LOGGER = get_logger("largefiles")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32.GetLogicalDrives.restype = wintypes.DWORD
kernel32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
kernel32.GetDriveTypeW.restype = wintypes.UINT
kernel32.GetDiskFreeSpaceExW.argtypes = [
    wintypes.LPCWSTR,
    ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.POINTER(ctypes.c_ulonglong),
    ctypes.POINTER(ctypes.c_ulonglong),
]
kernel32.GetDiskFreeSpaceExW.restype = wintypes.BOOL
kernel32.GetVolumeInformationW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPWSTR,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPWSTR,
    wintypes.DWORD,
]
kernel32.GetVolumeInformationW.restype = wintypes.BOOL

DRIVE_TYPES = {
    2: "可移动磁盘",
    3: "本地磁盘",
    4: "网络驱动器",
    5: "光驱",
    6: "RAM 磁盘",
}

SYSTEM_TOP_DIRS = {
    "$recycle.bin",
    "system volume information",
    "windows",
    "program files",
    "program files (x86)",
    "programdata",
    "recovery",
    "perflogs",
}

PROTECTED_FILE_NAMES = {
    "pagefile.sys",
    "hiberfil.sys",
    "swapfile.sys",
    "dumpstack.log.tmp",
    "bootmgr",
    "bootnxt",
}

FILE_TYPE_GROUPS: tuple[tuple[str, set[str]], ...] = (
    (
        "视频",
        {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts", ".rmvb"},
    ),
    ("镜像", {".iso", ".img", ".vhd", ".vhdx", ".wim", ".esd"}),
    ("压缩包", {".zip", ".7z", ".rar", ".tar", ".gz", ".bz2", ".xz", ".cab"}),
    ("安装包", {".exe", ".msi", ".msix", ".msixbundle", ".appx", ".appxbundle"}),
    ("备份", {".bak", ".backup", ".old", ".dump"}),
    ("图片", {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".psd", ".raw"}),
    ("音频", {".mp3", ".flac", ".wav", ".ape", ".m4a", ".aac"}),
    ("文档", {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt"}),
    ("数据库", {".db", ".sqlite", ".mdb", ".accdb"}),
)


def _volume_type_name(code: int) -> str:
    return DRIVE_TYPES.get(code, "磁盘")


def list_drives() -> list[DriveInfo]:
    """枚举当前可用的本地/可移动/网络磁盘。"""
    drives: list[DriveInfo] = []
    try:
        mask = kernel32.GetLogicalDrives()
    except (AttributeError, OSError):
        return drives
    system_drive = (os.environ.get("SystemDrive") or "C:").upper()
    for index in range(26):
        if not mask & (1 << index):
            continue
        letter = f"{chr(65 + index)}:"
        root = letter + "\\"
        try:
            type_code = kernel32.GetDriveTypeW(root)
        except OSError:
            continue
        if type_code in (0, 1, 5):
            continue
        free = ctypes.c_ulonglong()
        total = ctypes.c_ulonglong()
        total_free = ctypes.c_ulonglong()
        try:
            if not kernel32.GetDiskFreeSpaceExW(
                root,
                ctypes.byref(free),
                ctypes.byref(total),
                ctypes.byref(total_free),
            ):
                continue
        except (AttributeError, OSError):
            continue
        if total.value <= 0:
            continue
        volume_name = ctypes.create_unicode_buffer(261)
        fs_name = ctypes.create_unicode_buffer(64)
        try:
            kernel32.GetVolumeInformationW(
                root,
                volume_name,
                len(volume_name),
                None,
                None,
                None,
                fs_name,
                len(fs_name),
            )
        except (AttributeError, OSError):
            volume_name = ctypes.create_unicode_buffer("")
            fs_name = ctypes.create_unicode_buffer("")
        drives.append(
            DriveInfo(
                letter=letter,
                root=root,
                label=volume_name.value.strip(),
                filesystem=fs_name.value.strip(),
                drive_type=_volume_type_name(type_code),
                total=int(total.value),
                free=int(free.value),
                is_system=letter.upper() == system_drive,
            )
        )
    priority = {"本地磁盘": 0, "可移动磁盘": 1, "网络驱动器": 2, "RAM 磁盘": 3}
    drives.sort(
        key=lambda item: (
            0 if item.is_system else 1,
            priority.get(item.drive_type, 9),
            item.letter,
        )
    )
    return drives


def _file_type(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    if not suffix:
        return "无扩展名"
    for category, extensions in FILE_TYPE_GROUPS:
        if suffix in extensions:
            return f"{category} · {suffix[1:].upper()}"
    return suffix[1:].upper()


def is_protected_path(path: str) -> bool:
    normalized = os.path.abspath(path)
    drive, tail = os.path.splitdrive(normalized)
    parts = [part for part in tail.replace("/", "\\").split("\\") if part]
    if parts and parts[0].casefold() in SYSTEM_TOP_DIRS:
        return True
    if os.path.basename(normalized).casefold() in PROTECTED_FILE_NAMES:
        return True
    return False


class LargeFileService:
    def list_drives(self) -> list[DriveInfo]:
        return list_drives()

    def scan(
        self,
        root: str,
        min_size: int,
        include_system: bool = False,
        progress: Callable[[int, int, int, str], None] | None = None,
        cancel_event: threading.Event | None = None,
        max_results: int = 5000,
    ) -> LargeFileScanResult:
        start = time.monotonic()
        root = os.path.abspath(root)
        result = LargeFileScanResult(root=root, min_size=min_size)
        if not os.path.isdir(root):
            raise FileNotFoundError(f"磁盘不存在或不可访问：{root}")

        stack = [root]
        last_progress = 0.0
        cancellation = cancel_event or threading.Event()

        def emit(current: str, force: bool = False) -> None:
            nonlocal last_progress
            now = time.monotonic()
            if not force and now - last_progress < 0.25:
                return
            last_progress = now
            if progress:
                progress(
                    result.scanned_files,
                    result.scanned_dirs,
                    len(result.files),
                    current,
                )

        emit(root, force=True)
        while stack:
            if cancellation.is_set():
                result.cancelled = True
                break
            directory = stack.pop()
            result.scanned_dirs += 1
            try:
                with os.scandir(directory) as entries:
                    for entry in entries:
                        if cancellation.is_set():
                            result.cancelled = True
                            break
                        try:
                            if entry.is_symlink() or (
                                hasattr(entry, "is_junction") and entry.is_junction()
                            ):
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                if not include_system:
                                    relative = os.path.relpath(entry.path, root)
                                    top = relative.split(os.sep, 1)[0].casefold()
                                    if top in SYSTEM_TOP_DIRS:
                                        continue
                                stack.append(entry.path)
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            stat = entry.stat(follow_symlinks=False)
                            result.scanned_files += 1
                            if stat.st_size < min_size:
                                continue
                            try:
                                modified = datetime.fromtimestamp(stat.st_mtime)
                            except (OSError, OverflowError, ValueError):
                                modified = None
                            result.files.append(
                                LargeFile(
                                    path=entry.path,
                                    size=int(stat.st_size),
                                    modified=modified,
                                    file_type=_file_type(entry.path),
                                    protected=is_protected_path(entry.path),
                                )
                            )
                            if len(result.files) >= max_results:
                                result.truncated = True
                                stack.clear()
                                break
                        except OSError:
                            result.inaccessible += 1
            except OSError:
                result.inaccessible += 1
            emit(directory)
            if result.truncated:
                break

        if result.cancelled:
            result.cancelled = True
        result.files.sort(key=lambda item: item.size, reverse=True)
        result.elapsed = time.monotonic() - start
        emit(root, force=True)
        LOGGER.info(
            "大文件扫描完成: root=%s files=%d scanned=%d cancelled=%s elapsed=%.1fs",
            root,
            len(result.files),
            result.scanned_files,
            result.cancelled,
            result.elapsed,
        )
        return result

    # ------------------------------------------------------------------
    def recycle(self, files: list[LargeFile]) -> RecycleResult:
        """通过 Shell 移到回收站；不会静默永久删除。"""
        result = RecycleResult()
        unique: dict[str, LargeFile] = {}
        for item in files:
            path = os.path.abspath(item.path)
            if item.protected or is_protected_path(path):
                result.failed.append((path, "系统文件或受保护目录，已跳过"))
                continue
            if not os.path.isfile(path):
                result.failed.append((path, "文件不存在或不是普通文件"))
                continue
            unique.setdefault(path.casefold(), item)
        if not unique:
            result.message = "没有可移入回收站的文件。"
            return result

        paths = list(unique.keys())
        buffer = ctypes.create_unicode_buffer("\0".join(paths) + "\0")

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("wFunc", wintypes.UINT),
                ("pFrom", ctypes.c_void_p),
                ("pTo", wintypes.LPCWSTR),
                ("fFlags", ctypes.c_ushort),
                ("fAnyOperationsAborted", wintypes.BOOL),
                ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", wintypes.LPCWSTR),
            ]

        operation = SHFILEOPSTRUCTW()
        operation.wFunc = 3  # FO_DELETE
        operation.pFrom = ctypes.cast(buffer, ctypes.c_void_p)
        operation.pTo = None
        # ALLOWUNDO + WANTNUKEWARNING + NOERRORUI
        # 回收站不可用时，系统会警告即将永久删除。
        operation.fFlags = 0x0040 | 0x4000 | 0x0400
        try:
            ctypes.windll.ole32.CoInitializeEx(None, 0x2)
        except (AttributeError, OSError):
            pass
        try:
            shell32.SHFileOperationW.argtypes = [ctypes.POINTER(SHFILEOPSTRUCTW)]
            shell32.SHFileOperationW.restype = ctypes.c_int
            code = shell32.SHFileOperationW(ctypes.byref(operation))
        except (AttributeError, OSError) as exc:
            result.message = f"调用系统回收站失败：{exc}"
            return result
        finally:
            try:
                ctypes.windll.ole32.CoUninitialize()
            except (AttributeError, OSError):
                pass

        if code != 0:
            result.message = f"系统回收站操作返回错误码 {code}。"
            LOGGER.warning("SHFileOperationW 失败: code=%s", code)
        for path in paths:
            if os.path.exists(path):
                result.failed.append((path, "文件仍存在（可能被取消、占用或无权限）"))
            else:
                result.recycled.append(path)
                audit("recycle_large_file", {"path": path})
        if operation.fAnyOperationsAborted:
            result.message = "操作被系统取消。"
        elif not result.message:
            result.message = f"已将 {len(result.recycled)} 个文件移入回收站。"
        return result
