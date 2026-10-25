"""枚举并启用/禁用注册表 Run 项和启动文件夹项目。"""

from __future__ import annotations

import os
import struct
import time
import winreg
from pathlib import Path

from ..models import StartupEntry, StartupToggleResult
from ..utils import audit, get_logger, is_admin

LOGGER = get_logger("startup")
DISABLED_SUFFIX = ".wintoolbox-disabled"
SKIP_FILES = {"desktop.ini", "thumbs.db"}


def approval_blob(enabled: bool) -> bytes:
    """StartupApproved 的 12 字节状态值；首字节 2=启用，3=禁用。"""
    if enabled:
        return b"\x02" + b"\x00" * 11
    filetime = int((time.time() + 11644473600) * 10_000_000)
    return b"\x03\x00\x00\x00" + struct.pack("<Q", filetime)

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
    """StartupApproved 首字节 3 表示禁用；1/2/6 均视为启用。"""
    try:
        with winreg.OpenKey(root, approved_path, 0, winreg.KEY_READ | view_flag) as key:
            data, _kind = winreg.QueryValueEx(key, name)
            if isinstance(data, (bytes, bytearray)) and data:
                return data[0] != 3
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
                            registry_root=root,
                            registry_path=path,
                            approved_path=approved_path,
                            view_flag=view_flag,
                            value_name=str(name),
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
                if not item.is_file() or item.name.casefold() in SKIP_FILES:
                    continue
                disabled = item.name.endswith(DISABLED_SUFFIX)
                if disabled:
                    original_name = item.name[: -len(DISABLED_SUFFIX)]
                    if not original_name:
                        continue
                    original = item.with_name(original_name)
                else:
                    original = item
                entries.append(
                    StartupEntry(
                        name=Path(original.name).stem,
                        command=str(original),
                        scope=scope,
                        source="启动文件夹",
                        enabled=(
                            not disabled
                            and _is_enabled(
                                root, approved_path, str(original), view_flag
                            )
                        ),
                        registry_root=root,
                        approved_path=approved_path,
                        view_flag=view_flag,
                        value_name=str(original),
                        folder_path=str(item),
                    )
                )
        except OSError:
            LOGGER.exception("读取启动文件夹失败: %s", folder)
    return entries


def _write_approval(entry: StartupEntry, enabled: bool) -> None:
    if not entry.approved_path or not entry.value_name:
        raise OSError("缺少 StartupApproved 信息")
    with winreg.CreateKeyEx(
        entry.registry_root,
        entry.approved_path,
        0,
        winreg.KEY_SET_VALUE | entry.view_flag,
    ) as key:
        winreg.SetValueEx(
            key,
            entry.value_name,
            0,
            winreg.REG_BINARY,
            approval_blob(enabled),
        )


class StartupService:
    def scan(self) -> list[StartupEntry]:
        entries = _registry_entries() + _startup_folder_entries()
        entries.sort(key=lambda item: (not item.enabled, item.scope, item.name.casefold()))
        return entries

    def set_enabled(self, entry: StartupEntry, enabled: bool) -> StartupToggleResult:
        if entry.registry_root == winreg.HKEY_LOCAL_MACHINE and not is_admin():
            return StartupToggleResult(
                False,
                entry.enabled,
                "该启动项属于所有用户，需要以管理员身份重启工具箱后才能修改。",
            )
        try:
            if entry.source == "注册表":
                _write_approval(entry, enabled)
            else:
                _write_approval(entry, enabled)
                path = Path(entry.folder_path)
                original = Path(entry.command)
                if enabled and path.name.endswith(DISABLED_SUFFIX):
                    if original.exists():
                        raise OSError(f"原文件已存在：{original}")
                    path.rename(original)
                elif not enabled and not path.name.endswith(DISABLED_SUFFIX):
                    target = path.with_name(path.name + DISABLED_SUFFIX)
                    if target.exists():
                        raise OSError(f"禁用文件已存在：{target}")
                    path.rename(target)
        except OSError as exc:
            LOGGER.exception("切换启动项失败: %s", entry.name)
            return StartupToggleResult(False, entry.enabled, f"修改失败：{exc}")
        audit(
            "startup_toggle",
            {
                "name": entry.name,
                "source": entry.source,
                "scope": entry.scope,
                "enabled": enabled,
                "admin": is_admin(),
            },
        )
        state = "启用" if enabled else "禁用"
        return StartupToggleResult(True, enabled, f"已{state}启动项「{entry.name}」。")
