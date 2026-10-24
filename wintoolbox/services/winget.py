"""通过 winget 检测与执行应用升级。

winget 的表格输出没有稳定的 JSON 接口。这里按“来源 / 可用版本 / 当前版本 /
包标识 / 名称”的语义从右向左解析，避免中文表头按显示宽度排版导致的列错位；
无法启动 winget 时会给出错误码与环境/修复提示。
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable

from ..models import UpdatePackage, UpdateScanResult, UpgradeResult, WingetInfo
from ..utils import (
    check_winget_path,
    creation_flags,
    decode_console,
    get_logger,
    run_command,
    strip_ansi,
)

LOGGER = get_logger("winget")

_INSTALL_HINT = (
    "应用更新依赖 Windows 的 winget（应用安装程序）。请打开 Microsoft Store 安装或修复"
    "“应用安装程序 / App Installer”，然后回到本页点“重新检测”。"
)
_SEPARATOR = re.compile(r"^\s*-{8,}\s*$")
_VERSIONISH = re.compile(r"^(?:v?\d[\w.+\-]*|unknown|未知)$", re.IGNORECASE)
_HEADER_WORDS = {
    "name",
    "id",
    "version",
    "available",
    "source",
    "名称",
    "应用",
    "标识",
    "包标识",
    "版本",
    "当前版本",
    "可用",
    "可用版本",
    "源",
    "来源",
}


def _looks_like_summary(line: str) -> bool:
    text = line.strip()
    lowered = text.lower()
    return bool(
        re.match(r"^\d+\s+.*(?:upgrades?|updates?).*(?:available|可用)", lowered)
        or re.match(r"^\d+\s+.*(?:升级|更新).*(?:可用|项|个)", text)
        or lowered.startswith("no installed package")
        or lowered.startswith("no applicable")
        or "找不到" in text
    )


def _looks_like_version(text: str) -> bool:
    return bool(_VERSIONISH.match(text))


def _parse_row_tokens(line: str) -> UpdatePackage | None:
    """按列语义从右向左解析，避免中文表头的显示宽度导致列切片错位。"""
    parts = line.split()
    if len(parts) < 4:
        return None

    has_source = False
    if len(parts) >= 5:
        last = parts[-1]
        if last.casefold() in {"winget", "msstore"}:
            has_source = True
        elif (
            not _looks_like_version(last)
            and _looks_like_version(parts[-2])
            and _looks_like_version(parts[-3])
            and not _looks_like_version(parts[-4])
        ):
            # 自定义 winget source（如私有源）也允许。
            has_source = True

    if has_source:
        source = parts[-1]
        available = parts[-2]
        current = parts[-3]
        package_id = parts[-4]
        name = " ".join(parts[:-4])
    else:
        source = "winget"
        available = parts[-1]
        current = parts[-2]
        package_id = parts[-3]
        name = " ".join(parts[:-3])

    if not name or not package_id or package_id.casefold() in _HEADER_WORDS:
        return None
    if name.casefold() in _HEADER_WORDS:
        return None
    if not re.search(r"[A-Za-z0-9]", package_id) or re.search(r"\s", package_id):
        return None
    if not any(ch.isdigit() for ch in current + available) and not (
        "unknown" in current.casefold()
        or "未知" in current
        or "unknown" in available.casefold()
        or "未知" in available
    ):
        return None
    return UpdatePackage(
        name=name,
        package_id=package_id,
        current_version=current or "未知",
        available_version=available or "未知",
        source=source,
    )


def parse_upgrade_table(output: str) -> list[UpdatePackage]:
    """解析 `winget upgrade` 的表格输出。空输出 = 没有可用更新。"""
    if not output:
        return []
    clean = strip_ansi(output.replace("\r\n", "\n").replace("\r", "\n"))
    lines = [line.rstrip() for line in clean.splitlines()]
    start_index = 0
    for index, line in enumerate(lines):
        if _SEPARATOR.match(line):
            start_index = index + 1
            break

    updates: list[UpdatePackage] = []
    seen: set[str] = set()
    for line in lines[start_index:]:
        if not line.strip():
            continue
        if _looks_like_summary(line):
            break
        if _SEPARATOR.match(line):
            continue
        package = _parse_row_tokens(line)
        if package is None:
            continue
        key = f"{package.package_id}|{package.source}".casefold()
        if key in seen:
            continue
        seen.add(key)
        updates.append(package)
    return updates


class WingetService:
    def __init__(self) -> None:
        self._info: WingetInfo | None = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def probe(self, force: bool = False) -> WingetInfo:
        with self._lock:
            if self._info is not None and not force:
                return self._info
            path = check_winget_path()
            if not path:
                self._info = WingetInfo(
                    available=False,
                    error="未找到 winget 命令。",
                    install_hint=_INSTALL_HINT,
                )
                return self._info
            try:
                stat = Path(path).stat()
                size = stat.st_size
                is_reparse = bool(getattr(stat, "st_file_attributes", 0) & 0x400)
            except OSError:
                size = -1
                is_reparse = False
            code, output = run_command([path, "--version"], timeout=12)
            version_match = re.search(r"v?\d+\.\d+\.\d+(?:[-.\w]+)?", output)
            if code != 0 or not version_match:
                LOGGER.warning(
                    "winget 探测失败: path=%s code=%s output=%r", path, code, output
                )
                detail = output.strip().splitlines()[-1] if output.strip() else "无输出"
                if code < 0 or code >= 0x80000000:
                    code_text = f"0x{code & 0xFFFFFFFF:08X}"
                else:
                    code_text = str(code)
                error = f"winget 无法启动（退出码 {code_text}）：{detail}"
                if size == 0 and not is_reparse:
                    error += " 应用执行别名文件为空，通常表示 App Installer 未正确注册。"
                elif is_reparse:
                    error += (
                        " 应用执行别名存在。如果普通 PowerShell 中 `winget --version` 正常，"
                        "请从资源管理器直接启动工具箱，避免在受限终端/沙箱中运行。"
                    )
                self._info = WingetInfo(
                    available=False,
                    path=path,
                    error=error,
                    install_hint=_INSTALL_HINT,
                )
                return self._info
            LOGGER.info("winget 可用: %s (%s)", version_match.group(0), path)
            self._info = WingetInfo(
                available=True,
                version=version_match.group(0),
                path=path,
            )
            return self._info

    # ------------------------------------------------------------------
    def scan_updates(self) -> UpdateScanResult:
        info = self.probe()
        if not info.available:
            return UpdateScanResult(
                updates=[],
                error=info.error,
                warning=info.install_hint,
                checked_at=datetime.now(),
            )

        command = [
            info.path,
            "upgrade",
            "--include-unknown",
            "--accept-source-agreements",
            "--disable-interactivity",
        ]
        code, output = run_command(command, timeout=240)
        updates = parse_upgrade_table(output)
        no_update_markers = (
            "no installed package",
            "no applicable update",
            "找不到",
            "没有可用",
            "已是最新",
        )
        lowered = output.lower()
        if code != 0 and not updates and not any(marker in lowered for marker in no_update_markers):
            return UpdateScanResult(
                updates=[],
                error=f"检查更新失败（退出码 {code}）。\n{output.strip()[-1200:]}",
                raw_output=output,
                checked_at=datetime.now(),
            )
        return UpdateScanResult(
            updates=updates,
            raw_output=output,
            checked_at=datetime.now(),
        )

    # ------------------------------------------------------------------
    def upgrade_package(
        self,
        package: UpdatePackage,
        on_output: Callable[[str], None] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> UpgradeResult:
        info = self.probe()
        if not info.available:
            return UpgradeResult(
                package_id=package.package_id,
                success=False,
                exit_code=-1,
                error=info.error,
            )
        if cancel_event is not None and cancel_event.is_set():
            return UpgradeResult(
                package_id=package.package_id,
                success=False,
                exit_code=-1,
                error="任务已取消",
            )

        command = [
            info.path,
            "upgrade",
            "--id",
            package.package_id,
            "--exact",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
            "--disable-interactivity",
        ]
        if package.source:
            command.extend(["--source", package.source])
        if on_output:
            on_output("$ " + subprocess.list2cmdline(command))
        LOGGER.info("执行升级: %s", subprocess.list2cmdline(command))

        env = os.environ.copy()
        env.update({"NO_COLOR": "1", "CLICOLOR": "0", "TERM": "dumb"})
        env.pop("WT_SESSION", None)
        output_chunks: list[str] = []
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creation_flags(),
                env=env,
            )
        except OSError as exc:
            return UpgradeResult(
                package_id=package.package_id,
                success=False,
                exit_code=-2,
                error=str(exc),
            )

        timed_out = threading.Event()

        def _kill_on_timeout() -> None:
            if process.poll() is None:
                timed_out.set()
                try:
                    process.kill()
                except OSError:
                    pass

        timer = threading.Timer(1800, _kill_on_timeout)
        timer.daemon = True
        timer.start()
        try:
            assert process.stdout is not None
            for raw in iter(process.stdout.readline, b""):
                if cancel_event is not None and cancel_event.is_set():
                    if on_output:
                        on_output("已请求停止：当前安装完成后将不再继续。")
                line = strip_ansi(decode_console(raw)).rstrip()
                if not line:
                    continue
                output_chunks.append(line)
                if len(output_chunks) > 500:
                    output_chunks = output_chunks[-300:]
                if on_output:
                    try:
                        on_output(line)
                    except Exception:  # UI 回调不应影响升级流程
                        LOGGER.exception("winget 输出回调失败")
            code = process.wait()
        finally:
            timer.cancel()
            try:
                process.stdout.close()  # type: ignore[union-attr]
            except (AttributeError, OSError):
                pass

        output = "\n".join(output_chunks)
        if timed_out.is_set():
            return UpgradeResult(
                package_id=package.package_id,
                success=False,
                exit_code=-1,
                output=output,
                error="升级超时（30 分钟），已终止 winget。",
            )
        if code != 0:
            tail = "\n".join(output_chunks[-12:])
            return UpgradeResult(
                package_id=package.package_id,
                success=False,
                exit_code=code,
                output=output,
                error=f"升级失败（退出码 {code}）\n{tail}",
            )
        return UpgradeResult(
            package_id=package.package_id,
            success=True,
            exit_code=code,
            output=output,
        )
