"""从注册表读取已安装应用，评估卸载建议并调用应用自带卸载程序。"""

from __future__ import annotations

import ctypes
import os
import re
import subprocess
import winreg
from collections import Counter
from ctypes import wintypes
from datetime import date
from typing import Iterable

from ..models import AppRecord, UninstallResult
from ..utils import (
    audit,
    get_logger,
    is_admin,
    normalize_msi_uninstall,
    parse_install_date,
    truncate_middle,
)

LOGGER = get_logger("apps")

UNINSTALL_KEYS: tuple[tuple[str, int, str, int, str], ...] = (
    (
        "HKCU",
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
        0,
        "64",
    ),
    (
        "HKLM",
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        winreg.KEY_WOW64_64KEY,
        "64",
    ),
    (
        "HKLM",
        winreg.HKEY_LOCAL_MACHINE,
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        winreg.KEY_WOW64_32KEY,
        "32",
    ),
)

PROTECTED_PATTERNS = (
    r"microsoft visual c\+\+",
    r"\.net (?:desktop |framework )?runtime",
    r"windows desktop runtime",
    r"windows sdk",
    r"windows driver package",
    r"windows software development kit",
    r"microsoft edge(?: webview2)?(?: update)?",
    r"webview2 runtime",
    r"directx",
    r"microsoft update health tools",
    r"windows subsystem for",
    r"microsoft windows",
    r"windows 应用",
    r"windows app",
)

SECURITY_PATTERNS = (
    r"defender",
    r"antivirus",
    r"anti-virus",
    r"firewall",
    r"security",
    r"norton",
    r"mcafee",
    r"kaspersky",
    r"bitdefender",
    r"avast",
    r"\bavg\b",
    r"eset",
    r"malwarebytes",
    r"火绒",
    r"杀毒",
    r"安全卫士",
    r"电脑管家",
)

BLOAT_PATTERNS: tuple[tuple[str, int, str], ...] = (
    (
        r"toolbar|工具栏|浏览器助手|上网导航|网址导航|导航首页",
        55,
        "带有浏览器工具栏或导航捆绑特征",
    ),
    (
        r"coupon|优惠券|购物助手|返利|比价",
        50,
        "带有购物推广/返利插件特征",
    ),
    (
        r"driver (?:booster|updater|easy)|驱动(?:精灵|人生|总裁)|一键装驱动",
        45,
        "驱动安装类工具，可能捆绑推广或重复系统更新功能",
    ),
    (
        r"registry (?:cleaner|optimizer)|注册表清理|系统优化|一键优化|加速大师|清理大师",
        45,
        "系统优化/清理类工具，实际收益有限且可能误改设置",
    ),
    (
        r"search (?:protector|toolbar)|web search|搜索助手|主页保护",
        55,
        "带有搜索/主页劫持风险特征",
    ),
    (
        r"wildtangent|game (?:center|box)|游戏盒子|游戏中心|页游",
        35,
        "游戏推广平台，通常非常驻必需",
    ),
    (
        r"pc (?:cleaner|tune|optimizer)|system (?:cleaner|optimizer)|电脑清理|系统清理",
        45,
        "第三方清理/优化工具，可能与系统功能重复",
    ),
    (
        r"windows 11 安装助手|windows 11 installation assistant",
        60,
        "一次性系统升级工具，升级完成后通常不再需要",
    ),
    (
        r"电脑健康状况检查|pc health check",
        45,
        "系统升级前的兼容性检查工具，检查完成后通常不再需要",
    ),
    (
        r"apple software update",
        25,
        "仅用于 Apple 软件更新，可按需保留",
    ),
    (
        r"软件管家|应用管家|桌面助手|桌面整理",
        30,
        "附加型桌面/软件管理工具，可按需保留",
    ),
    (
        r"weather|天气|万年历|日历",
        20,
        "资讯/天气类附加应用，使用频率通常较低",
    ),
)

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("浏览器", ("chrome", "firefox", "edge", "opera", "brave", "vivaldi", "浏览器", "browser")),
    (
        "安全",
        (
            "antivirus",
            "security",
            "防火墙",
            "杀毒",
            "安全卫士",
            "安全软件",
            "电脑管家",
            "火绒",
            "defender",
        ),
    ),
    (
        "优化工具",
        (
            "driver booster",
            "driver updater",
            "driver easy",
            "registry cleaner",
            "pc cleaner",
            "驱动精灵",
            "驱动人生",
            "优化大师",
            "清理大师",
            "鲁大师",
        ),
    ),
    (
        "开发工具",
        (
            "visual studio",
            "vscode",
            "python",
            "git",
            "node.js",
            "jdk",
            "java",
            "android studio",
            "pycharm",
            "idea",
            "webstorm",
            "docker",
            "postman",
            "terminal",
        ),
    ),
    (
        "运行库/驱动",
        (
            "runtime",
            "redistributable",
            "visual c++",
            ".net",
            "sdk",
            "driver",
            "nvidia",
            "intel",
            "realtek",
            "amd chipset",
            "directx",
            "webview",
        ),
    ),
    (
        "办公",
        (
            "office",
            "word",
            "excel",
            "powerpoint",
            "wps",
            "pdf",
            "acrobat",
            "notion",
            "obsidian",
            "笔记",
            "note",
        ),
    ),
    (
        "媒体",
        (
            "player",
            "vlc",
            "potplayer",
            "spotify",
            "music",
            "video",
            "obs",
            "audacity",
            "foobar",
            "itunes",
            "youtube",
            "netflix",
            "bilibili",
            "哔哩哔哩",
            "播放器",
            "音乐",
            "视频",
        ),
    ),
    (
        "游戏",
        (
            "steam",
            "epic games",
            "game",
            "游戏",
            "battle.net",
            "ubisoft",
            "ea app",
            "模拟器",
            "fromsoftware",
            "capcom",
            "neowiz",
            "rockstar",
            "pocketpair",
            "sony interactive",
            "koei tecmo",
            "shift up",
            "cd projekt",
            "mihoyo",
            "leenzee",
            "game science",
            "cold symmetry",
            "valve",
            "neople",
        ),
    ),
    (
        "通讯",
        ("wechat", "微信", "qq", "telegram", "discord", "slack", "zoom", "teams", "钉钉", "飞书"),
    ),
    (
        "系统工具",
        (
            "7-zip",
            "winrar",
            "bandizip",
            "everything",
            "powertoys",
            "ccleaner",
            "截图",
            "snipaste",
            "idm",
            "download",
            "下载",
            "压缩",
            "输入法",
            "网盘",
            "云盘",
        ),
    ),
    ("设计", ("photoshop", "illustrator", "figma", "blender", "canva", "sketch", "剪映")),
)

DUPLICATE_THRESHOLDS = {
    "浏览器": 3,
    "媒体": 3,
    "系统工具": 5,
    "通讯": 3,
    "设计": 3,
}


def _contains(patterns: Iterable[str], text: str) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def classify_app(name: str, publisher: str = "") -> str:
    # 名称优先，避免发布者字段（如 Google\Chrome）盖过应用本身的类型。
    lowered_name = name.casefold()
    for category, keywords in CATEGORY_RULES:
        if any(keyword.casefold() in lowered_name for keyword in keywords):
            return category
    lowered_publisher = publisher.casefold()
    for category, keywords in CATEGORY_RULES:
        if any(keyword.casefold() in lowered_publisher for keyword in keywords):
            return category
    return "其他"


def is_protected_app(name: str, category: str) -> bool:
    if _contains(PROTECTED_PATTERNS, name):
        return True
    if category in {"运行库/驱动", "安全"}:
        return True
    return False


def split_windows_command(command: str) -> tuple[str, str]:
    """按 Windows CommandLineToArgvW 规则拆分注册表卸载命令。

    这样带空格的路径不会被 cmd.exe 二次转义，返回值可直接传给 ShellExecuteEx。
    """
    command = (command or "").strip()
    if not command:
        raise ValueError("卸载命令为空。")
    shell32 = ctypes.windll.shell32
    kernel32 = ctypes.windll.kernel32
    shell32.CommandLineToArgvW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_int),
    ]
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    argc = ctypes.c_int(0)
    argv = shell32.CommandLineToArgvW(command, ctypes.byref(argc))
    if not argv or argc.value <= 0:
        raise ValueError("无法解析卸载命令。")
    try:
        args = [argv[index] or "" for index in range(argc.value)]
    finally:
        kernel32.LocalFree(ctypes.cast(argv, ctypes.c_void_p))
    executable = args[0].strip()
    if not executable:
        raise ValueError("无法解析卸载程序路径。")
    parameters = subprocess.list2cmdline(args[1:]) if len(args) > 1 else ""
    return executable, parameters


def _read_value(key: winreg.HKEYType, names: tuple[str, ...], default: object = "") -> object:
    for name in names:
        try:
            value, _kind = winreg.QueryValueEx(key, name)
            return value
        except OSError:
            continue
    return default


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _as_text(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "").strip()


def _clean_path(value: object) -> str:
    text = _as_text(value)
    if not text:
        return ""
    if text.startswith('"'):
        end = text.find('"', 1)
        if end > 0:
            return text[1:end]
    # DisplayIcon 可能是 "C:\x\app.exe,0"
    text = re.split(r",\s*-?\d+\s*$", text, maxsplit=1)[0]
    return text.strip().strip('"')


def _is_patch_entry(name: str, release_type: str, parent_key: str) -> bool:
    if parent_key:
        return True
    lowered = f"{name} {release_type}".casefold()
    if release_type and any(token in release_type.casefold() for token in ("update", "hotfix", "service pack")):
        return True
    if re.match(r"^(?:update for|security update|hotfix for|service pack|kb\d{6,})\b", lowered):
        return True
    return False


def _enumerate_registry() -> list[AppRecord]:
    records: list[AppRecord] = []
    for hive, root, base_path, view_flag, architecture in UNINSTALL_KEYS:
        try:
            root_key = winreg.OpenKey(root, base_path, 0, winreg.KEY_READ | view_flag)
        except OSError:
            continue
        with root_key:
            try:
                subkey_count = winreg.QueryInfoKey(root_key)[0]
            except OSError:
                continue
            for index in range(subkey_count):
                try:
                    key_name = winreg.EnumKey(root_key, index)
                    subkey = winreg.OpenKey(root_key, key_name, 0, winreg.KEY_READ | view_flag)
                except OSError:
                    continue
                with subkey:
                    name = _as_text(_read_value(subkey, ("DisplayName",), ""))
                    if not name:
                        continue
                    system_component = _as_int(_read_value(subkey, ("SystemComponent",), 0))
                    if system_component == 1:
                        continue
                    release_type = _as_text(_read_value(subkey, ("ReleaseType",), ""))
                    parent_key = _as_text(_read_value(subkey, ("ParentKeyName",), ""))
                    if _is_patch_entry(name, release_type, parent_key):
                        continue

                    uninstall = _as_text(_read_value(subkey, ("UninstallString",), ""))
                    quiet = _as_text(_read_value(subkey, ("QuietUninstallString",), ""))
                    windows_installer = _as_int(_read_value(subkey, ("WindowsInstaller",), 0))
                    if not uninstall and windows_installer and re.fullmatch(
                        r"\{[0-9A-Fa-f-]{36}\}", key_name
                    ):
                        uninstall = f"msiexec.exe /x {key_name}"
                    uninstall = normalize_msi_uninstall(uninstall)
                    quiet = normalize_msi_uninstall(quiet)

                    install_location = _clean_path(
                        _read_value(subkey, ("InstallLocation",), "")
                    )
                    display_icon = _clean_path(_read_value(subkey, ("DisplayIcon",), ""))
                    record = AppRecord(
                        name=name,
                        version=_as_text(_read_value(subkey, ("DisplayVersion",), "")),
                        publisher=_as_text(_read_value(subkey, ("Publisher",), "")),
                        install_date=parse_install_date(
                            _read_value(subkey, ("InstallDate",), "")
                        ),
                        size_kb=max(0, _as_int(_read_value(subkey, ("EstimatedSize",), 0))),
                        install_location=install_location,
                        uninstall_string=uninstall,
                        quiet_uninstall_string=quiet,
                        hive=hive,
                        architecture=architecture,
                        key_path=f"{base_path}\\{key_name}",
                        display_icon=display_icon,
                        url=_as_text(
                            _read_value(subkey, ("URLInfoAbout", "HelpLink"), "")
                        ),
                    )
                    if _as_int(_read_value(subkey, ("NoRemove",), 0)) == 1:
                        record.uninstall_string = ""
                        record.quiet_uninstall_string = ""
                    records.append(record)
    return records


def _deduplicate(records: list[AppRecord]) -> list[AppRecord]:
    grouped: dict[str, AppRecord] = {}
    for record in records:
        key = record.name.casefold()
        current = grouped.get(key)
        if current is None:
            grouped[key] = record
            continue

        def rank(item: AppRecord) -> tuple[int, int, int, int]:
            return (
                1 if item.effective_uninstall_command else 0,
                1 if item.hive == "HKLM" else 0,
                1 if item.architecture == "64" else 0,
                item.size_kb,
            )

        if rank(record) > rank(current):
            grouped[key] = record
    return list(grouped.values())


def recommend_apps(records: list[AppRecord]) -> list[AppRecord]:
    """为每条记录计算类别、保护状态和卸载建议（纯函数，便于测试）。"""
    category_counts = Counter()
    for record in records:
        record.category = classify_app(record.name, record.publisher)
        category_counts[record.category] += 1
        record.can_uninstall = bool(record.effective_uninstall_command)
        record.protected = is_protected_app(record.name, record.category)
        record.score = 0
        record.reasons = []

    today = date.today()
    for record in records:
        if record.protected:
            record.score = 0
            if record.category == "安全":
                record.reasons.append("安全软件，请确认已有替代防护后再手动卸载")
            elif record.category == "运行库/驱动":
                record.reasons.append("运行库或驱动组件，删除可能影响其他软件")
            else:
                record.reasons.append("系统组件，不建议卸载")
            record.advice = "建议保留"
            continue

        haystack = record.name.casefold()
        for pattern, points, reason in BLOAT_PATTERNS:
            if re.search(pattern, haystack, flags=re.IGNORECASE):
                record.score += points
                record.reasons.append(reason)
                break

        threshold = DUPLICATE_THRESHOLDS.get(record.category)
        count = category_counts.get(record.category, 0)
        if threshold is not None and count > threshold:
            record.score += 30
            record.reasons.append(f"同类“{record.category}”软件已有 {count} 款，可精简")

        if record.install_date:
            age_days = (today - record.install_date).days
            if age_days >= 365 * 3 and record.size_kb >= 30 * 1024:
                record.score += 15
                years = age_days // 365
                record.reasons.append(f"安装已超过 {years} 年，且占用超过 30 MB")
            elif age_days >= 365 * 5:
                record.score += 10
                record.reasons.append("安装时间较早，可能已不再使用")

        if not record.publisher and not record.url:
            record.score += 10
            record.reasons.append("缺少发布者与官网信息")

        if not record.can_uninstall:
            record.score = min(record.score, 44)
            record.reasons.append("未提供卸载入口，可能由系统或其他安装器管理")
            record.advice = "无法卸载"
            continue

        record.score = min(100, record.score)
        if record.score >= 45:
            record.advice = "可考虑卸载"
        elif record.score >= 20:
            record.advice = "按需保留"
        else:
            record.advice = "常规应用"

    return sorted(records, key=lambda item: item.name.casefold())


class AppService:
    def scan(self) -> list[AppRecord]:
        records = _deduplicate(_enumerate_registry())
        records = recommend_apps(records)
        LOGGER.info("扫描到 %d 个已安装应用", len(records))
        return records

    # ------------------------------------------------------------------
    def _shell_execute(self, command: str, elevate: bool) -> UninstallResult:
        """用 ShellExecuteEx 启动卸载程序，不再经过 cmd.exe 的二次引号解析。"""
        command = os.path.expandvars(command).strip()
        try:
            executable, parameters = split_windows_command(command)
        except ValueError as exc:
            return UninstallResult(False, message=str(exc), elevated=elevate)
        if not executable:
            return UninstallResult(False, message="卸载命令为空。", elevated=elevate)

        class SHELLEXECUTEINFOW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("fMask", ctypes.c_ulong),
                ("hwnd", wintypes.HWND),
                ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR),
                ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR),
                ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE),
                ("lpIDList", ctypes.c_void_p),
                ("lpClass", wintypes.LPCWSTR),
                ("hkeyClass", wintypes.HANDLE),
                ("dwHotKey", wintypes.DWORD),
                ("hIcon", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE),
            ]

        info = SHELLEXECUTEINFOW()
        info.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
        # NOCLOSEPROCESS | NOASYNC | FLAG_NO_UI
        info.fMask = 0x00000040 | 0x00000100 | 0x00000400
        info.lpVerb = "runas" if elevate else "open"
        info.lpFile = executable
        info.lpParameters = parameters or None
        info.lpDirectory = (
            os.path.dirname(executable)
            if os.path.isabs(executable)
            else None
        )
        info.nShow = 1
        shell32 = ctypes.windll.shell32
        shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(SHELLEXECUTEINFOW)]
        shell32.ShellExecuteExW.restype = wintypes.BOOL
        if not shell32.ShellExecuteExW(ctypes.byref(info)):
            code = ctypes.windll.kernel32.GetLastError()
            if code == 1223:
                return UninstallResult(
                    False,
                    message="已取消管理员授权，未执行卸载。",
                    elevated=elevate,
                )
            error_messages = {
                2: "找不到卸载程序文件",
                3: "找不到卸载程序路径",
                5: "拒绝访问，可能需要管理员权限",
                31: "无法打开卸载程序",
            }
            reason = error_messages.get(code, f"错误码 {code}")
            return UninstallResult(
                False,
                message=f"无法启动卸载程序：{reason}。\n{truncate_middle(command, 240)}",
                elevated=elevate,
            )
        if not info.hProcess:
            return UninstallResult(
                True,
                message="已启动卸载程序，请在应用窗口中完成操作。",
                elevated=elevate,
            )
        try:
            ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
            exit_code = wintypes.DWORD(0)
            ctypes.windll.kernel32.GetExitCodeProcess(
                info.hProcess, ctypes.byref(exit_code)
            )
        finally:
            ctypes.windll.kernel32.CloseHandle(info.hProcess)
        return UninstallResult(
            ok=exit_code.value == 0,
            exit_code=exit_code.value,
            message=(
                "卸载程序已结束。"
                if exit_code.value == 0
                else f"卸载程序退出码：{exit_code.value}"
            ),
            elevated=elevate,
        )

    def launch_uninstall(self, app: AppRecord, use_quiet: bool = False) -> UninstallResult:
        command = app.quiet_uninstall_string if use_quiet else app.uninstall_string
        if not command and use_quiet:
            command = app.uninstall_string
        command = normalize_msi_uninstall(command)
        if not command:
            return UninstallResult(False, message="该应用未提供可用的卸载命令。")
        elevated = app.hive == "HKLM" and not is_admin()
        audit(
            "uninstall_start",
            {
                "app": app.to_audit_dict(),
                "quiet": use_quiet,
                "admin": is_admin(),
                "elevated": elevated,
                "command": truncate_middle(command, 300),
            },
        )
        LOGGER.info(
            "卸载应用 %s，admin=%s elevate=%s，命令: %s",
            app.name,
            is_admin(),
            elevated,
            command,
        )
        result = self._shell_execute(command, elevate=elevated)
        audit(
            "uninstall_finish",
            {
                "app": app.name,
                "ok": result.ok,
                "exit_code": result.exit_code,
                "elevated": result.elevated,
                "message": truncate_middle(result.message, 300),
            },
        )
        return result
