"""硬件信息页：型号、系统、运行时间和详细硬件清单。"""

from __future__ import annotations

import time
import tkinter as tk

from ...models import DiskHealthReport, HardwareInfo, SystemInfo
from ...utils import human_bytes
from ..theme import C, FONTS
from ..widgets import Card, FlatButton, ScrollableFrame, section_title
from .base import BasePage


def _uptime_text(seconds: int) -> str:
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if days:
        return f"{days}天{hours}小时{minutes}分钟{seconds}秒"
    if hours:
        return f"{hours}小时{minutes}分钟{seconds}秒"
    if minutes:
        return f"{minutes}分钟{seconds}秒"
    return f"{seconds}秒"


class HardwareInfoPage(BasePage):
    page_id = "hardwareinfo"

    def build(self) -> None:
        self._info: HardwareInfo | None = None
        self._disk: DiskHealthReport | None = None
        self._system: SystemInfo | None = None
        self._loaded_at = 0.0
        self._loading = False
        self._values: dict[str, tk.Label] = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_toolbar()
        self._scroll = ScrollableFrame(self, bg=C.BG)
        self._scroll.grid(row=1, column=0, sticky="nsew")
        content = self._scroll.inner
        content.grid_columnconfigure(0, weight=1)
        self._build_summary(content)
        self._build_detail(content)
        self._scroll.after(100, self._scroll.refresh_layout)

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=C.BG)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        bar.grid_columnconfigure(0, weight=1)
        tk.Label(
            bar,
            text="本页为硬件清单概览；温度、SMART 和磁盘健康请到“硬件检测”。",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["tiny"],
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self._copy_btn = FlatButton(
            bar,
            "复制信息",
            command=self._copy,
            variant="ghost",
            compact=True,
        )
        self._copy_btn.grid(row=0, column=1, padx=(8, 0))
        self._refresh_btn = FlatButton(
            bar,
            "刷新",
            command=self.refresh,
            variant="secondary",
            icon="\uE72C",
            compact=True,
        )
        self._refresh_btn.grid(row=0, column=2, padx=(6, 0))

    def _build_summary(self, content: tk.Frame) -> None:
        row = tk.Frame(content, bg=C.BG)
        row.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        for column in range(3):
            row.grid_columnconfigure(column, weight=1, uniform="hwsum")
        items = (
            ("model", "型号信息", C.CYAN),
            ("system", "系统信息", C.ACCENT),
            ("uptime", "运行时间", C.GREEN),
        )
        for index, (key, title, accent) in enumerate(items):
            card = Card(row, padding=16)
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 5, 0 if index == 2 else 5),
            )
            tk.Frame(card.inner, bg=accent, height=3, width=32).pack(
                anchor="w", pady=(0, 10)
            )
            tk.Label(
                card.inner,
                text=title,
                bg=C.SURFACE,
                fg=C.MUTED,
                font=FONTS["small"],
                anchor="w",
            ).pack(fill="x")
            value = tk.Label(
                card.inner,
                text="读取中…",
                bg=C.SURFACE,
                fg=C.TEXT,
                font=(FONTS["display"][0], 16, "bold"),
                anchor="w",
                justify="left",
                wraplength=280,
            )
            value.pack(fill="x", pady=(5, 0))
            self._values[key] = value

    def _build_detail(self, content: tk.Frame) -> None:
        card = Card(content, padding=16)
        card.grid(row=1, column=0, sticky="ew")
        section_title(card.inner, "详细信息").pack(fill="x", pady=(0, 8))
        rows = (
            ("cpu", "处理器"),
            ("board", "主板"),
            ("memory", "内存"),
            ("gpu", "显卡"),
            ("monitor", "显示器"),
            ("disk", "磁盘"),
            ("npu", "NPU"),
            ("sound", "声卡"),
            ("network", "网卡"),
        )
        grid = tk.Frame(card.inner, bg=C.SURFACE)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)
        for index, (key, title) in enumerate(rows):
            tk.Label(
                grid,
                text=title,
                bg=C.SURFACE,
                fg=C.MUTED,
                font=FONTS["small"],
                anchor="w",
                width=8,
            ).grid(row=index, column=0, sticky="nw", pady=5)
            value = tk.Label(
                grid,
                text="读取中…",
                bg=C.SURFACE,
                fg=C.TEXT_SOFT,
                font=FONTS["small"],
                anchor="w",
                justify="left",
                wraplength=900,
            )
            value.grid(row=index, column=1, sticky="nw", pady=5)
            self._values[key] = value

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if self._info is None or time.time() - self._loaded_at > 180:
            self._load()

    def refresh(self) -> None:
        self._load(force=True)

    def _load(self, force: bool = False) -> None:
        if self._loading:
            return
        self._loading = True
        self._refresh_btn.set_enabled(False)
        self.set_status("正在读取硬件信息…", "busy")

        def done(payload) -> None:
            self._loading = False
            self._refresh_btn.set_enabled(True)
            self._info, self._disk, self._system = payload
            self._loaded_at = time.time()
            self._render()
            if self.app._current_page == "hardwareinfo":
                self.set_status("硬件信息已更新")

        def failed(exc: Exception) -> None:
            self._loading = False
            self._refresh_btn.set_enabled(True)
            self.set_status(f"硬件信息读取失败：{exc}", "error")

        self.app.runner.submit(
            lambda: (
                self.services["hardware"].collect(),
                self.services["diskhealth"].collect(),
                self.services["system"].collect(),
            ),
            done,
            failed,
            name="hardware-info",
        )

    def _render(self) -> None:
        info = self._info
        system = self._system
        disk = self._disk
        if not info or not system:
            return
        model = " ".join(
            part for part in (info.manufacturer, info.model) if part.strip()
        )
        self._values["model"].configure(text=model or "未报告机型")
        os_name = info.os_name.strip()
        os_parts = [os_name] if os_name else []
        if info.os_build and info.os_build not in os_name:
            os_parts.append(info.os_build)
        if system.architecture and system.architecture not in os_name:
            os_parts.append(system.architecture)
        self._values["system"].configure(
            text=" ".join(os_parts) or "未知系统"
        )
        self._values["uptime"].configure(text=_uptime_text(system.uptime_seconds))

        self._values["cpu"].configure(
            text=(
                f"{info.cpu_name or '未检测到处理器'} "
                f"（{info.cpu_cores} 核 / {info.cpu_threads} 线程"
                + (f" · {info.cpu_max_mhz} MHz" if info.cpu_max_mhz else "")
                + "）"
            )
        )
        self._values["board"].configure(
            text=" ".join(
                part
                for part in (
                    info.board_manufacturer,
                    info.board_product,
                    info.board_version,
                )
                if part
            )
            or "未读取到主板信息"
        )
        memory_parts = []
        if info.memory_total:
            memory_parts.append(human_bytes(info.memory_total))
        if info.modules:
            first = info.modules[0]
            if first.memory_type:
                memory_parts.append(first.memory_type)
            if first.speed_mhz:
                memory_parts.append(f"{first.speed_mhz} MHz")
        if info.modules:
            memory_parts.append(
                "（" + " + ".join(human_bytes(item.capacity) for item in info.modules) + "）"
            )
        self._values["memory"].configure(
            text=" ".join(memory_parts) or "未读取到内存信息"
        )
        self._values["gpu"].configure(
            text="\n".join(
                f"{gpu.name}"
                + (f"（{human_bytes(gpu.vram)}）" if gpu.vram else "")
                for gpu in info.gpus
            )
            or "未检测到显卡"
        )
        self._values["monitor"].configure(
            text="\n".join(
                (
                    f"{monitor.manufacturer} {monitor.name}".strip()
                    if monitor.manufacturer
                    else monitor.name
                )
                + (f"（{monitor.size_inches:g} 英寸）" if monitor.size_inches else "")
                + (
                    f" · {monitor.resolution.replace('x', '×')}"
                    if monitor.resolution
                    else ""
                )
                + (f" · {monitor.connection}" if monitor.connection else "")
                for monitor in info.monitors
            )
            or "未检测到显示器"
        )
        self._values["disk"].configure(
            text="\n".join(
                f"{item.name}（{human_bytes(item.size)} · {item.health}）"
                for item in (disk.disks if disk else [])
            )
            or (disk.error if disk and disk.error else "未读取到磁盘信息")
        )
        self._values["npu"].configure(
            text="\n".join(info.npu_devices) or "未检测到"
        )
        self._values["sound"].configure(
            text="\n".join(info.sound_devices) or "未检测到"
        )
        self._values["network"].configure(
            text="\n".join(
                adapter.name
                + (f"（{adapter.status}）" if adapter.status else "")
                for adapter in info.network
            )
            or "未检测到物理网卡"
        )
        self._values["cpu"].configure(wraplength=900)
        self._scroll.refresh_layout()

    def _copy(self) -> None:
        if not self._info:
            return
        lines = [
            "WinToolbox 硬件信息",
            f"型号: {self._values['model'].cget('text')}",
            f"系统: {self._values['system'].cget('text')}",
            f"运行时间: {self._values['uptime'].cget('text')}",
        ]
        for key, title in (
            ("cpu", "处理器"),
            ("board", "主板"),
            ("memory", "内存"),
            ("gpu", "显卡"),
            ("monitor", "显示器"),
            ("disk", "磁盘"),
            ("npu", "NPU"),
            ("sound", "声卡"),
            ("network", "网卡"),
        ):
            value = self._values[key].cget("text")
            lines.append(f"{title}: {value}")
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.set_status("硬件信息已复制到剪贴板")
