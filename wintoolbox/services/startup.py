"""只读枚举注册表 Run 项和启动文件夹，禁用操作交给任务管理器。"""

from __future__ import annotations

import os
import winreg
from pathlib import Path

from ..models import StartupEntry
from ..utils import get_logger

LOGGER = get_logger("startup")

RUN_KEYS = (
    (
        "当前用户",
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Run",
        0,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
    ),
    (
        "所有用户",
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run",
        winreg.KEY_WOW64_64KEY,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run",
    ),
    (
        "所有用户 (32 位)",
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Run",
        winreg.KEY_WOW64_64KEY,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run32",
    ),
)


def _is_enabled(root: int, approved_path: str, name: str, view_flag: int) -> bool:
    """StartupApproved 的二进制首字节为奇数通常表示已禁用。"""
    try:
        with winreg.OpenKey(root, approved_path, 0, winreg.KEY_READ | view_flag) as key:
            data, _kind = winreg.QueryValueEx(key, name)
            if isinstance(data, (bytes, bytearray)) and data:
                return data[0] % 2 == 0
    except OSError:
        pass
    return True


def _registry_entries() -> list[StartupEntry]:
    entries: list[StartupEntry] = []
    for scope, root, path, view_flag, approved_path in RUN_KEYS:
        try:
            with winreg.OpenKey(root, path, 0, winreg.KEY_READ | view_flag) as key:
                count = winreg.QueryInfoKey(key)[1]
                for index in range(count):
                    try:
                        name, command, _kind = winreg.EnumValue(key, index)
                    except OSError:
                        continue
                    if not name or not command:
                        continue
                    entries.append(
                        StartupEntry(
                            name=str(name),
                            command=str(command),
                            scope=scope,
                            source="注册表",
                            enabled=_is_enabled(root, approved_path, str(name), view_flag),
                        )
                    )
        except OSError:
            continue
    return entries


def _startup_folder_entries() -> list[StartupEntry]:
    entries: list[StartupEntry] = []
    locations = (
        ("当前用户", os.environ.get("APPDATA"), winreg.HKEY_CURRENT_USER, 0),
        ("所有用户", os.environ.get("ProgramData"), winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
    )
    approved_path = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\StartupFolder"
    for scope, base, root, view_flag in locations:
        if not base:
            continue
        folder = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        if not folder.is_dir():
            continue
        try:
            for item in folder.iterdir():
                if not item.is_file():
                    continue
                entries.append(
                    StartupEntry(
                        name=item.stem,
                        command=str(item),
                        scope=scope,
                        source="启动文件夹",
                        enabled=_is_enabled(root, approved_path, item.name, view_flag),
                    )
                )
        except OSError:
            LOGGER.exception("读取启动文件夹失败: %s", folder)
    return entries


class StartupService:
    def scan(self) -> list[StartupEntry]:
        entries = _registry_entries() + _startup_folder_entries()
        entries.sort(key=lambda item: (not item.enabled, item.scope, item.name.casefold()))
        return entries
