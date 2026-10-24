"""无显示器/远程 Windows 环境下的硬件检测报告。

不创建 Tk 窗口，不依赖桌面会话；只调用 CIM、注册表和显示会话 API。
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .services.hardware import (
    DiskHealthService,
    HardwareService,
    display_session_info,
)
from .utils import app_data_dir


def _output(message: str, error: bool = False) -> None:
    """窗口化 exe 中 stdout/stderr 可能为 None，不能直接 print。"""
    stream = sys.stderr if error else sys.stdout
    if stream is None:
        return
    try:
        stream.write(message + "\n")
        stream.flush()
    except (OSError, AttributeError):
        pass


def build_text(hardware, disks, generated_at: datetime) -> str:
    lines = [
        "WinToolbox 无界面硬件检测报告",
        f"生成时间: {generated_at.isoformat(timespec='seconds')}",
        "模式: headless（不创建图形界面，不要求显示器）",
        "",
        "===== 硬件 =====",
        HardwareService.format_report(hardware),
        "",
        "===== 磁盘健康 =====",
    ]
    if disks.error:
        lines.append(f"提示: {disks.error}")
    lines.append(DiskHealthService.format_report(disks))
    lines.extend(
        [
            "",
            "说明: 未连接显示器时仍可采集 CPU、主板、内存、磁盘等信息。",
            "温度、磨损和 SMART 细项取决于硬盘、驱动和权限。",
        ]
    )
    return "\n".join(lines)


def build_json(hardware, disks, generated_at: datetime) -> str:
    payload = {
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "mode": "headless",
        "display": display_session_info(),
        "hardware": asdict(hardware),
        "disks": asdict(disks),
    }
    payload["disks"]["collected_at"] = (
        disks.collected_at.isoformat(timespec="seconds") if disks.collected_at else None
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def run_headless(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="WinToolbox --headless",
        description="不打开 GUI，采集硬件与磁盘健康并写入报告。",
    )
    parser.add_argument("--headless", action="store_true", help="启用无界面模式")
    parser.add_argument("--report", action="store_true", help="同 --headless")
    parser.add_argument(
        "-o",
        "--output",
        help="报告文件路径（默认写入本机应用数据目录的 reports 文件夹）",
    )
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    generated_at = datetime.now().astimezone()
    hardware = HardwareService().collect()
    disks = DiskHealthService().collect()
    text = build_json(hardware, disks, generated_at) if args.json else build_text(
        hardware, disks, generated_at
    )

    _output(text)
    if args.output:
        output = Path(args.output).expanduser()
    else:
        output = app_data_dir() / "reports" / (
            "hardware-report.json" if args.json else "hardware-report.txt"
        )
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
        _output(f"\n报告已写入: {output}")
    except OSError as exc:
        _output(f"\n报告写入失败: {exc}", error=True)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(run_headless())
