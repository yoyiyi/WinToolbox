"""零第三方依赖的通用工具函数。"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import date, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

APP_DIR_NAME = "WinToolbox"
LOGGER_NAME = "wintoolbox"


# ---------------------------------------------------------------------------
# 路径 / 配置目录
# ---------------------------------------------------------------------------

def resource_path(relative: str) -> Path:
    """返回源码运行或 PyInstaller 单文件运行时的资源路径。"""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


def app_data_dir() -> Path:
    """应用数据目录。可用 WINTOOLBOX_HOME 覆盖，便于便携运行与测试。"""
    override = os.environ.get("WINTOOLBOX_HOME")
    if override:
        path = Path(override).expanduser()
    else:
        local = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        path = Path(local) / APP_DIR_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = app_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def plugins_dir() -> Path:
    path = app_data_dir() / "plugins"
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(debug: bool = False) -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = RotatingFileHandler(
        logs_dir() / "wintoolbox.log",
        maxBytes=1_500_000,
        backupCount=3,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(handler)
    if debug:
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(console)
    logger.propagate = False
    return logger


def get_logger(name: str = "") -> logging.Logger:
    return logging.getLogger(f"{LOGGER_NAME}.{name}" if name else LOGGER_NAME)


_audit_lock = threading.Lock()


def audit(action: str, detail: dict[str, object] | str) -> None:
    """记录会影响系统的操作，不记录任何隐私内容。"""
    payload = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "action": action,
        "detail": detail,
    }
    try:
        with _audit_lock:
            with (logs_dir() / "actions.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except OSError:
        get_logger("audit").exception("写入操作审计日志失败")


# ---------------------------------------------------------------------------
# 格式化
# ---------------------------------------------------------------------------

def human_bytes(value: int | float | None, precision: int = 1) -> str:
    if not value or value <= 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(value)
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    if index == 0:
        return f"{int(size)} B"
    return f"{size:.{precision}f} {units[index]}"


def human_duration(seconds: int | float | None) -> str:
    total = max(0, int(seconds or 0))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days} 天 {hours} 小时"
    if hours:
        return f"{hours} 小时 {minutes} 分钟"
    if minutes:
        return f"{minutes} 分钟"
    return f"{total} 秒"


def format_date(value: date | datetime | None, fallback: str = "—") -> str:
    if not value:
        return fallback
    return value.strftime("%Y-%m-%d")


def format_datetime(value: datetime | None, fallback: str = "—") -> str:
    if not value:
        return fallback
    return value.strftime("%Y-%m-%d %H:%M")


def parse_install_date(value: object) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt != "%Y%m%d" else text[:8], fmt).date()
        except ValueError:
            continue
    compact = re.sub(r"\D", "", text)
    if len(compact) >= 8:
        try:
            return datetime.strptime(compact[:8], "%Y%m%d").date()
        except ValueError:
            return None
    return None


def truncate_middle(text: str, length: int = 60) -> str:
    text = text or ""
    if len(text) <= length:
        return text
    keep = max(3, length - 1)
    left = (keep + 1) // 2
    right = keep // 2
    return f"{text[:left]}…{text[-right:]}"


def truncate_end(text: str, length: int = 60) -> str:
    text = text or ""
    if len(text) <= length:
        return text
    return text[: max(1, length - 1)] + "…"


def strip_ansi(text: str) -> str:
    return re.sub(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)?)", "", text)


def decode_console(data: bytes) -> str:
    """控制台输出在中文 Windows 上可能是 UTF-8 或 CP936，做宽松兼容。"""
    if not data:
        return ""
    candidates: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "mbcs"):
        try:
            candidates.append(data.decode(encoding))
        except (UnicodeDecodeError, LookupError):
            continue
    if not candidates:
        return data.decode("utf-8", errors="replace")
    # 替换字符越少，解码越可信；同分时保留 UTF-8 候选。
    return min(candidates, key=lambda item: item.count("\ufffd"))


# ---------------------------------------------------------------------------
# Windows 集成
# ---------------------------------------------------------------------------

def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def enable_dpi_awareness() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def open_url(url: str) -> None:
    if not url:
        return
    try:
        os.startfile(url)  # type: ignore[attr-defined]
    except OSError:
        get_logger("shell").exception("打开链接失败: %s", url)


def open_folder(path: str | Path) -> bool:
    target = Path(path)
    if not target.exists():
        return False
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
        return True
    except OSError:
        get_logger("shell").exception("打开目录失败: %s", target)
        return False


def reveal_in_explorer(path: str | Path) -> bool:
    target = Path(path)
    if not target.exists():
        return False
    try:
        subprocess.Popen(["explorer.exe", "/select,", str(target)], close_fds=True)
        return True
    except OSError:
        get_logger("shell").exception("在资源管理器中定位失败: %s", target)
        return False


def open_task_manager() -> None:
    try:
        subprocess.Popen(["taskmgr.exe"], close_fds=True)
    except OSError:
        get_logger("shell").exception("启动任务管理器失败")


def open_startup_folder(common: bool = False) -> bool:
    base = os.environ.get("ProgramData") if common else os.environ.get("APPDATA")
    if not base:
        return False
    path = Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return open_folder(path)


def open_store_app_installer() -> None:
    open_url("ms-windows-store://pdp/?ProductId=9NBLGGH4NNS1")


def restart_as_admin() -> bool:
    """通过 UAC 用同一入口重启工具箱。返回是否成功发起了提权。"""
    if is_admin():
        return False
    try:
        if getattr(sys, "frozen", False):
            executable = sys.executable
            params = ""
        else:
            python_exe = Path(sys.executable)
            pythonw = python_exe.with_name("pythonw.exe")
            executable = str(pythonw if pythonw.exists() else python_exe)
            entry = Path(__file__).resolve().parent.parent / "app.py"
            params = f'"{entry}"'
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", executable, params, str(Path.cwd()), 1
        )
        return int(result) > 32
    except (AttributeError, OSError):
        get_logger("shell").exception("请求管理员权限失败")
        return False


def creation_flags() -> int:
    if os.name == "nt":
        return getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return 0


def check_winget_path() -> str | None:
    return shutil.which("winget")


def run_powershell(script: str, timeout: int = 60) -> tuple[int, str]:
    """运行只读 PowerShell 脚本（UTF-16LE 编码，避免引号转义问题）。"""
    import base64

    prefix = (
        "$ErrorActionPreference='SilentlyContinue'\n"
        "$ProgressPreference='SilentlyContinue'\n"
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()\n"
        "$OutputEncoding=[Console]::OutputEncoding\n"
    )
    encoded = base64.b64encode((prefix + script).encode("utf-16-le")).decode("ascii")
    try:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=creation_flags(),
            cwd=os.environ.get("SystemRoot", None),
        )
        return completed.returncode, strip_ansi(decode_console(completed.stdout or b""))
    except subprocess.TimeoutExpired as exc:
        return -1, "PowerShell 查询超时"
    except OSError as exc:
        return -2, str(exc)


def run_command(
    args: Iterable[str],
    timeout: int = 20,
    cwd: str | None = None,
) -> tuple[int, str]:
    """运行短命令并返回 (退出码, 合并后的文本)。"""
    try:
        completed = subprocess.run(
            list(args),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=creation_flags(),
            cwd=cwd,
        )
        return completed.returncode, strip_ansi(decode_console(completed.stdout or b""))
    except subprocess.TimeoutExpired as exc:
        output = decode_console(exc.stdout or b"") if exc.stdout else ""
        return -1, (output + "\n命令执行超时").strip()
    except OSError as exc:
        return -2, str(exc)


def normalize_msi_uninstall(command: str) -> str:
    """注册表里的 MSI UninstallString 有时是 /I，需要改成 /X 才是卸载。"""
    if re.search(r"(?i)msiexec(?:\.exe)?", command):
        command = re.sub(r"(?i)(msiexec(?:\.exe)?\s+)/I(?=\s|\{)", r"\1/X", command, count=1)
    return command.strip()


def command_executable(command: str) -> str:
    """尽量从卸载命令中提取可执行文件路径（仅用于展示/定位）。"""
    text = command.strip()
    if not text:
        return ""
    if text.startswith('"'):
        end = text.find('"', 1)
        if end > 0:
            return text[1:end]
    first = text.split(" ", 1)[0]
    return first.strip('"')


def ensure_windows() -> bool:
    return os.name == "nt"
