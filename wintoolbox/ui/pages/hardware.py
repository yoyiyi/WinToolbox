"""硬件检测页：系统硬件概览与物理磁盘健康。"""

from __future__ import annotations

import time
import tkinter as tk

from ...models import (
    DiskHealthReport,
    HardwareInfo,
    PhysicalDisk,
    VolumeHealth,
)
from ...utils import human_bytes, truncate_middle
from ..theme import C, FONTS
from ..widgets import (
    Badge,
    Card,
    DataTable,
    FlatButton,
    ScrollableFrame,
    section_title,
    show_notice,
)
from .base import BasePage


def _speed_text(bps: int) -> str:
    if not bps or bps > 10**15:
        return "—"
    if bps >= 1_000_000_000:
        return f"{bps / 1_000_000_000:.1f} Gbps"
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.0f} Mbps"
    return f"{bps / 1000:.0f} Kbps"


class HardwarePage(BasePage):
    page_id = "hardware"

    def build(self) -> None:
        self._hardware: HardwareInfo | None = None
        self._disk_report: DiskHealthReport | None = None
        self._hardware_at = 0.0
        self._disk_at = 0.0
        self._hardware_loading = False
        self._disk_loading = False
        self._selected_disk_id = ""
        self._selected_tab = 0
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_toolbar()
        self._build_tabs()
        self._hw_tab = tk.Frame(self._tab_host, bg=C.BG)
        self._disk_tab = tk.Frame(self._tab_host, bg=C.BG)
        for tab in (self._hw_tab, self._disk_tab):
            tab.grid(row=0, column=0, sticky="nsew")
        self._tab_host.grid_rowconfigure(0, weight=1)
        self._tab_host.grid_columnconfigure(0, weight=1)
        self._build_hardware_tab()
        self._build_disk_tab()
        self._disk_tab.grid_remove()
        self._select_tab(0)

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=C.BG)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        bar.grid_columnconfigure(0, weight=1)
        self._data_note = tk.Label(
            bar,
            text="数据来自 CIM / SMART，部分硬盘和驱动不提供温度、磨损或通电时间。",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["tiny"],
            anchor="w",
        )
        self._data_note.grid(row=0, column=0, sticky="w")
        self._copy_btn = FlatButton(
            bar,
            "复制当前报告",
            command=self._copy_report,
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

    def _build_tabs(self) -> None:
        bar = tk.Frame(self, bg=C.BG)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        self._tab_buttons: list[tuple[tk.Frame, tk.Label, tk.Frame]] = []
        for index, text in enumerate(("硬件概览", "磁盘健康")):
            tab = tk.Frame(bar, bg=C.BG, cursor="hand2")
            tab.pack(side="left", padx=(0, 6))
            label = tk.Label(
                tab,
                text=text,
                bg=C.SURFACE,
                fg=C.MUTED,
                font=FONTS["small_bold"],
                padx=18,
                pady=7,
                cursor="hand2",
            )
            label.pack(fill="x")
            underline = tk.Frame(tab, bg=C.BG, height=2)
            underline.pack(fill="x")
            for widget in (tab, label):
                widget.bind("<Button-1>", lambda _e, idx=index: self._select_tab(idx))
            self._tab_buttons.append((tab, label, underline))
        self._tab_host = tk.Frame(self, bg=C.BG)
        self._tab_host.grid(row=2, column=0, sticky="nsew")

    def _select_tab(self, index: int) -> None:
        self._selected_tab = index
        frames = (self._hw_tab, self._disk_tab)
        for tab_index, tab in enumerate(frames):
            if tab_index == index:
                tab.grid()
                tab.tkraise()
            else:
                tab.grid_remove()
        if index == 0:
            self._hw_scroll.canvas.yview_moveto(0)
        if index == 1 and self._disk_report:
            self._render_disks(self._disk_report)
        for idx, (_tab, label, underline) in enumerate(self._tab_buttons):
            active = idx == index
            label.configure(
                bg=C.SURFACE_ALT if active else C.SURFACE,
                fg=C.TEXT if active else C.MUTED,
            )
            underline.configure(bg=C.ACCENT if active else C.BG)

    # ------------------------------------------------------------------
    def _build_hardware_tab(self) -> None:
        scroll = ScrollableFrame(self._hw_tab, bg=C.BG)
        scroll.pack(fill="both", expand=True)
        self._hw_scroll = scroll
        content = scroll.inner
        content.grid_columnconfigure(0, weight=1)

        summary = Card(content, padding=16)
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        summary.inner.grid_columnconfigure(0, weight=1)
        left = tk.Frame(summary.inner, bg=C.SURFACE)
        left.grid(row=0, column=0, sticky="nsew")
        self._hw_host = tk.Label(
            left,
            text="正在读取硬件信息…",
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["title"],
            anchor="w",
        )
        self._hw_host.pack(fill="x")
        self._hw_model = tk.Label(
            left,
            text="",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self._hw_model.pack(fill="x", pady=(3, 0))
        self._hw_os = tk.Label(
            left,
            text="",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        )
        self._hw_os.pack(fill="x", pady=(3, 0))
        self._hw_display = tk.Label(
            left,
            text="",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        )
        self._hw_display.pack(fill="x", pady=(1, 0))
        self._hw_warning = tk.Label(
            left,
            text="",
            bg=C.SURFACE,
            fg=C.AMBER,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=760,
        )
        self._hw_warning.pack(fill="x", pady=(5, 0))

        badges = tk.Frame(summary.inner, bg=C.SURFACE)
        badges.grid(row=0, column=1, sticky="ne", padx=(14, 0))
        self._hw_badges = badges
        for key in ("cpu", "memory", "gpu"):
            Badge(badges, "—", "neutral").pack(anchor="e", pady=(0, 4))

        row = tk.Frame(content, bg=C.BG)
        row.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        row.grid_columnconfigure(0, weight=1, uniform="hwrow")
        row.grid_columnconfigure(1, weight=1, uniform="hwrow")
        self._build_cpu_card(row)
        self._build_gpu_card(row)

        self._build_board_card(content)
        self._build_monitor_card(content)
        self._build_memory_card(content)
        self._build_network_card(content)
        self._hw_scroll.after(100, self._hw_scroll.refresh_layout)

    def _value_label(self, parent: tk.Misc, label: str) -> tk.Label:
        box = tk.Frame(parent, bg=C.SURFACE)
        box.pack(side="left", fill="x", expand=True, padx=(0, 14))
        tk.Label(
            box,
            text=label,
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        ).pack(fill="x")
        value = tk.Label(
            box,
            text="—",
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            font=FONTS["small_bold"],
            anchor="w",
            justify="left",
            wraplength=230,
        )
        value.pack(fill="x", pady=(2, 0))
        return value

    def _build_cpu_card(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=14)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        section_title(card.inner, "处理器").pack(fill="x")
        self._cpu_name = tk.Label(
            card.inner,
            text="读取中…",
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["body_bold"],
            anchor="w",
            justify="left",
            wraplength=370,
        )
        self._cpu_name.pack(fill="x", pady=(8, 0))
        values = tk.Frame(card.inner, bg=C.SURFACE)
        values.pack(fill="x", pady=(9, 0))
        self._cpu_core_value = self._value_label(values, "核心 / 线程")
        self._cpu_clock_value = self._value_label(values, "最大频率")
        self._cpu_socket_value = self._value_label(values, "插槽")

    def _build_gpu_card(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=14)
        card.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        section_title(card.inner, "图形处理器", "来自显示适配器").pack(fill="x")
        self._gpu_box = tk.Frame(card.inner, bg=C.SURFACE)
        self._gpu_box.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(
            self._gpu_box,
            text="读取中…",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
        ).pack(fill="x")

    def _build_board_card(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=14)
        card.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        section_title(card.inner, "主板与 BIOS").pack(fill="x")
        grid = tk.Frame(card.inner, bg=C.SURFACE)
        grid.pack(fill="x", pady=(9, 0))
        grid.grid_columnconfigure(1, weight=1)
        self._board_values: dict[str, tk.Label] = {}
        rows = (
            ("board", "主板"),
            ("bios", "BIOS"),
            ("date", "BIOS 日期"),
        )
        for index, (key, label) in enumerate(rows):
            tk.Label(
                grid,
                text=label,
                bg=C.SURFACE,
                fg=C.MUTED_DARK,
                font=FONTS["tiny"],
                anchor="w",
                width=10,
            ).grid(row=index, column=0, sticky="w", pady=3)
            value = tk.Label(
                grid,
                text="—",
                bg=C.SURFACE,
                fg=C.TEXT_SOFT,
                font=FONTS["small"],
                anchor="w",
                justify="left",
                wraplength=760,
            )
            value.grid(row=index, column=1, sticky="w", pady=3)
            self._board_values[key] = value

    def _build_monitor_card(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=14)
        card.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        header = tk.Frame(card.inner, bg=C.SURFACE)
        header.pack(fill="x")
        section_title(header, "显示器", "EDID / 当前会话").pack(side="left")
        self._monitor_summary = tk.Label(
            header,
            text="—",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["tiny"],
        )
        self._monitor_summary.pack(side="right")
        self._monitor_table = DataTable(
            card.inner,
            columns=(
                ("name", "显示器", 220, "w"),
                ("vendor", "厂商", 80, "w"),
                ("size", "尺寸", 80, "e"),
                ("resolution", "分辨率", 110, "e"),
                ("year", "年份", 60, "e"),
                ("connection", "接口", 90, "w"),
                ("serial", "序列号", 150, "w"),
                ("state", "状态", 70, "w"),
            ),
            height=3,
            horizontal_scrollbar=False,
        )
        self._monitor_table.pack(fill="x", pady=(9, 0))
        self._monitor_table.tree.tag_configure("active", foreground=C.GREEN)
        self._monitor_table.tree.tag_configure("inactive", foreground=C.MUTED)
        self._monitor_table.show_empty("正在读取显示器信息…")

    def _build_memory_card(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=14)
        card.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        header = tk.Frame(card.inner, bg=C.SURFACE)
        header.pack(fill="x")
        section_title(header, "内存插槽").pack(side="left")
        self._memory_total = tk.Label(
            header,
            text="—",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["tiny"],
        )
        self._memory_total.pack(side="right")
        self._memory_table = DataTable(
            card.inner,
            columns=(
                ("slot", "插槽", 180, "w"),
                ("capacity", "容量", 100, "e"),
                ("type", "类型 / 频率", 150, "w"),
                ("vendor", "厂商", 130, "w"),
                ("part", "型号", 220, "w"),
            ),
            height=3,
            horizontal_scrollbar=False,
        )
        self._memory_table.pack(fill="x", pady=(9, 0))
        self._memory_table.configure(bg=C.SURFACE)
        self._memory_table.show_empty("正在读取内存信息…")

    def _build_network_card(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=14)
        card.grid(row=5, column=0, sticky="ew")
        section_title(card.inner, "网络适配器", "物理网卡").pack(fill="x")
        self._network_table = DataTable(
            card.inner,
            columns=(
                ("name", "名称", 230, "w"),
                ("status", "状态", 90, "w"),
                ("speed", "速率", 100, "w"),
                ("ip", "IP 地址", 220, "w"),
                ("mac", "MAC", 150, "w"),
            ),
            height=3,
            horizontal_scrollbar=False,
        )
        self._network_table.pack(fill="x", pady=(9, 0))
        self._network_table.show_empty("正在读取网络适配器…")

    # ------------------------------------------------------------------
    def _build_disk_tab(self) -> None:
        self._disk_tab.grid_columnconfigure(0, weight=1)
        self._disk_tab.grid_rowconfigure(1, weight=1)

        summary = Card(self._disk_tab, padding=12)
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        header = tk.Frame(summary.inner, bg=C.SURFACE)
        header.pack(fill="x")
        section_title(header, "物理磁盘").pack(side="left")
        self._disk_summary = tk.Label(
            header,
            text="正在读取磁盘健康…",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["small"],
        )
        self._disk_summary.pack(side="right")
        self._disk_warning = tk.Label(
            summary.inner,
            text="",
            bg=C.SURFACE,
            fg=C.AMBER,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=920,
        )
        self._disk_warning.pack(fill="x", pady=(4, 0))
        self._volume_summary = tk.Label(
            summary.inner,
            text="",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=920,
        )
        self._volume_summary.pack(fill="x", pady=(2, 0))

        table_card = Card(self._disk_tab, padding=12)
        table_card.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        self._disk_table = DataTable(
            table_card.inner,
            columns=(
                ("name", "磁盘", 260, "w"),
                ("media", "类型", 80, "w"),
                ("bus", "总线", 70, "w"),
                ("size", "容量", 100, "e"),
                ("health", "健康", 80, "w"),
                ("temp", "温度", 75, "e"),
                ("wear", "磨损", 75, "e"),
                ("hours", "通电", 90, "e"),
            ),
            height=4,
            on_select=self._on_disk_select,
            horizontal_scrollbar=False,
        )
        self._disk_table.pack(fill="both", expand=True)
        self._disk_table.tree.tag_configure("healthy", foreground=C.GREEN)
        self._disk_table.tree.tag_configure("warning", foreground=C.AMBER)
        self._disk_table.tree.tag_configure("unhealthy", foreground=C.RED)
        self._disk_table.tree.tag_configure("unknown", foreground=C.MUTED)
        self._disk_table.show_empty("正在读取物理磁盘…")

        self._build_disk_detail()

    def _build_disk_detail(self) -> None:
        card = Card(self._disk_tab, padding=12)
        card.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        header = tk.Frame(card.inner, bg=C.SURFACE)
        header.pack(fill="x")
        self._disk_detail_name = tk.Label(
            header,
            text="选择磁盘查看详情",
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            font=FONTS["body_bold"],
            anchor="w",
        )
        self._disk_detail_name.pack(side="left")
        self._disk_detail_health = Badge(header, "—", "neutral")
        self._disk_detail_health.pack(side="left", padx=(8, 0))
        self._disk_detail_meta = tk.Label(
            card.inner,
            text="温度、磨损和通电时间可能因硬盘/驱动而不提供。",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=980,
        )
        self._disk_detail_meta.pack(fill="x", pady=(5, 0))

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        now = time.time()
        if self._hardware is None or now - self._hardware_at > 180:
            self._load_hardware()
        if self._disk_report is None or now - self._disk_at > 180:
            self._load_disks()
        if self._hardware is not None:
            self._render_hardware(self._hardware)
        if self._disk_report is not None:
            self._render_disks(self._disk_report)
        if not self._hardware_loading and not self._disk_loading:
            self.set_status("硬件检测已就绪")

    def refresh(self) -> None:
        self._load_hardware(force=True)
        self._load_disks(force=True)

    def _load_hardware(self, force: bool = False) -> None:
        if self._hardware_loading:
            return
        self._hardware_loading = True
        self._refresh_btn.set_enabled(False)
        self._hw_warning.configure(text="正在查询硬件信息，首次读取可能需要几秒…", fg=C.MUTED)
        self.set_status("正在读取硬件信息…", "busy")

        def done(info: HardwareInfo) -> None:
            self._hardware_loading = False
            self._hardware = info
            self._hardware_at = time.time()
            self._redraw_after_load(info, self._disk_report)

        def failed(exc: Exception) -> None:
            self._hardware_loading = False
            self._hw_warning.configure(text=f"硬件信息读取失败：{exc}", fg=C.RED)
            self._redraw_after_load(None, self._disk_report)

        self.app.runner.submit(self.services["hardware"].collect, done, failed, name="hardware")

    def _load_disks(self, force: bool = False) -> None:
        if self._disk_loading:
            return
        self._disk_loading = True
        self._refresh_btn.set_enabled(False)
        self._disk_warning.configure(text="正在读取物理磁盘健康信息…", fg=C.MUTED)
        self.set_status("正在读取磁盘健康信息…", "busy")

        def done(report: DiskHealthReport) -> None:
            self._disk_loading = False
            self._disk_report = report
            self._disk_at = time.time()
            self._render_disks(report)
            self._redraw_after_load(self._hardware, report)

        def failed(exc: Exception) -> None:
            self._disk_loading = False
            self._disk_warning.configure(text=f"磁盘健康读取失败：{exc}", fg=C.RED)
            self._redraw_after_load(self._hardware, None)

        self.app.runner.submit(
            self.services["diskhealth"].collect, done, failed, name="disk-health"
        )

    def _redraw_after_load(
        self, info: HardwareInfo | None, report: DiskHealthReport | None
    ) -> None:
        if not self._hardware_loading and not self._disk_loading:
            self._refresh_btn.set_enabled(True)
            if self.app._current_page == "hardware":
                self.set_status("硬件信息已更新")
        if info:
            self._render_hardware(info)
        if report:
            self._render_disks(report)

    # ------------------------------------------------------------------
    def _render_hardware(self, info: HardwareInfo) -> None:
        self._hw_host.configure(text=info.hostname or "未知主机")
        model = " ".join(
            part for part in (info.manufacturer, info.model) if part.strip()
        )
        self._hw_model.configure(text=model or "未报告机型")
        os_text = " ".join(part for part in (info.os_name, info.os_build) if part)
        self._hw_os.configure(
            text=f"{os_text or '未知系统'}  ·  {info.cpu_socket or '未知插槽'}"
        )
        if info.display_count:
            display_text = (
                f"显示器 {info.display_count} 台 · "
                f"{info.screen_width}×{info.screen_height}"
            )
            if info.screen_refresh:
                display_text += f" @ {info.screen_refresh}Hz"
        else:
            display_text = "未检测到显示器（headless / 无显示输出）"
        if info.remote_session:
            display_text += " · 远程会话"
        self._hw_display.configure(text=display_text)
        self._hw_warning.configure(
            text="；".join(info.errors), fg=C.AMBER if info.errors else C.MUTED
        )
        for child in self._hw_badges.winfo_children():
            child.destroy()
        cpu_badge = f"CPU {info.cpu_cores}C/{info.cpu_threads}T" if info.cpu_threads else "CPU —"
        Badge(self._hw_badges, cpu_badge, "cyan").pack(anchor="e", pady=(0, 4))
        Badge(
            self._hw_badges,
            f"内存 {human_bytes(info.memory_total)}",
            "purple",
        ).pack(anchor="e", pady=(0, 4))
        Badge(
            self._hw_badges,
            f"显卡 {len(info.gpus)}",
            "green",
        ).pack(anchor="e")
        self._cpu_name.configure(text=info.cpu_name or "未检测到处理器")
        self._cpu_core_value.configure(
            text=f"{info.cpu_cores or '—'} / {info.cpu_threads or '—'}"
        )
        self._cpu_clock_value.configure(
            text=f"{info.cpu_max_mhz} MHz" if info.cpu_max_mhz else "—"
        )
        self._cpu_socket_value.configure(text=info.cpu_socket or "—")
        self._render_gpus(info)
        board = " ".join(
            part
            for part in (
                info.board_manufacturer,
                info.board_product,
                info.board_version,
            )
            if part.strip()
        )
        self._board_values["board"].configure(text=board or "—")
        bios = " ".join(
            part for part in (info.bios_vendor, info.bios_version) if part.strip()
        )
        self._board_values["bios"].configure(text=bios or "—")
        self._board_values["date"].configure(text=info.bios_date or "—")
        monitor_count = max(info.display_count, len(info.monitors))
        if monitor_count:
            summary = f"{monitor_count} 台 · {info.screen_width}×{info.screen_height}"
            if info.screen_refresh:
                summary += f" @ {info.screen_refresh}Hz"
            self._monitor_summary.configure(text=summary, fg=C.MUTED)
        else:
            self._monitor_summary.configure(
                text="未检测到显示器（headless / 远程会话）", fg=C.AMBER
            )
        connection_short = {
            "DisplayPort": "DP",
            "HDMI": "HDMI",
            "DVI": "DVI",
            "DVI-D": "DVI-D",
            "VGA": "VGA",
            "eDP": "eDP",
        }
        monitor_rows = []
        for index, monitor in enumerate(info.monitors):
            monitor_rows.append(
                (
                    str(index),
                    (
                        truncate_middle(monitor.name, 24),
                        monitor.manufacturer or "—",
                        f'{monitor.size_inches:g}"' if monitor.size_inches else "—",
                        monitor.resolution.replace("x", "×")
                        if monitor.resolution
                        else "—",
                        str(monitor.year) if monitor.year else "—",
                        connection_short.get(monitor.connection, monitor.connection or "—"),
                        truncate_middle(monitor.serial or "—", 18),
                        "活动" if monitor.active else "非活动",
                    ),
                    ("active",) if monitor.active else ("inactive",),
                )
            )
        self._monitor_table.replace(
            monitor_rows,
            empty_text=(
                "未读取到 EDID 详情；当前会话分辨率 "
                f"{info.screen_width}×{info.screen_height}"
                if monitor_count
                else "未检测到显示器（无头/远程环境仍可读取其他硬件）"
            ),
        )
        self._memory_total.configure(
            text=f"共 {human_bytes(info.memory_total)} · {len(info.modules)} 条"
        )
        rows = []
        for index, module in enumerate(info.modules):
            rows.append(
                (
                    str(index),
                    (
                        module.slot,
                        human_bytes(module.capacity),
                        f"{module.memory_type} / {module.speed_mhz} MHz"
                        if module.speed_mhz
                        else module.memory_type,
                        module.manufacturer or "—",
                        module.part_number or "—",
                    ),
                    (),
                )
            )
        self._memory_table.replace(
            rows, empty_text="未读取到内存条信息（可能不支持 SMBIOS 查询）"
        )
        net_rows = []
        for index, adapter in enumerate(info.network):
            net_rows.append(
                (
                    str(index),
                    (
                        truncate_middle(adapter.name, 30),
                        adapter.status or "—",
                        _speed_text(adapter.speed_bps),
                        truncate_middle(adapter.ip_addresses or "—", 28),
                        adapter.mac or "—",
                    ),
                    ("connected",) if adapter.connected else (),
                )
            )
        self._network_table.tree.tag_configure("connected", foreground=C.GREEN)
        self._network_table.replace(
            net_rows, empty_text="未读取到物理网络适配器"
        )
        self._hw_scroll.refresh_layout()

    def _render_gpus(self, info: HardwareInfo) -> None:
        for child in self._gpu_box.winfo_children():
            child.destroy()
        if not info.gpus:
            tk.Label(
                self._gpu_box,
                text="未检测到显示适配器",
                bg=C.SURFACE,
                fg=C.MUTED,
                font=FONTS["small"],
                anchor="w",
            ).pack(fill="x")
            return
        for gpu in info.gpus:
            box = tk.Frame(self._gpu_box, bg=C.SURFACE)
            box.pack(fill="x", pady=(0, 6))
            tk.Label(
                box,
                text=gpu.name or "未知显卡",
                bg=C.SURFACE,
                fg=C.TEXT_SOFT,
                font=FONTS["small_bold"],
                anchor="w",
                justify="left",
                wraplength=370,
            ).pack(fill="x")
            detail = f"驱动 {gpu.driver or '—'}"
            if gpu.vram:
                detail += f"  ·  显存 {human_bytes(gpu.vram)}"
            tk.Label(
                box,
                text=detail,
                bg=C.SURFACE,
                fg=C.MUTED_DARK,
                font=FONTS["tiny"],
                anchor="w",
            ).pack(fill="x")

    # ------------------------------------------------------------------
    def _render_disks(self, report: DiskHealthReport) -> None:
        healthy = sum(1 for disk in report.disks if disk.health == "健康")
        total_size = sum(disk.size for disk in report.disks)
        self._disk_summary.configure(
            text=(
                f"{len(report.disks)} 块磁盘 · {healthy} 块健康 · "
                f"共 {human_bytes(total_size)} · {len(report.volumes)} 个卷"
            )
        )
        self._disk_warning.configure(
            text=report.error or (
                "部分硬盘/驱动不提供温度、磨损、通电时间或错误计数，显示为“—”。"
            ),
            fg=C.AMBER if report.error else C.MUTED,
        )
        self._volume_summary.configure(
            text="卷  " + "   ·   ".join(
                f"{volume.letter} {volume.label or ''} "
                f"{human_bytes(volume.free)} 可用 / {human_bytes(volume.total)}"
                for volume in report.volumes
            ),
        )
        rows = []
        for index, disk in enumerate(report.disks):
            tag = "healthy"
            if disk.health in {"警告", "降级", "压力", "预测故障"}:
                tag = "warning"
            elif disk.health in {"异常", "错误"}:
                tag = "unhealthy"
            elif disk.health not in {"健康", "正常"}:
                tag = "unknown"
            rows.append(
                (
                    disk.device_id or f"{index}",
                    (
                        truncate_middle(disk.name, 34),
                        disk.media_type or "—",
                        disk.bus_type or "—",
                        human_bytes(disk.size),
                        disk.health,
                        f"{disk.temperature}°C" if disk.temperature is not None else "—",
                        f"{disk.wear}%" if disk.wear is not None else "—",
                        f"{disk.power_on_hours} h" if disk.power_on_hours is not None else "—",
                    ),
                    (tag,),
                )
            )
        self._disk_table.replace(rows, empty_text="未读取到物理磁盘信息")
        if report.disks:
            children = self._disk_table.tree.get_children()
            if children and not self._disk_table.selected_iid:
                self._disk_table.tree.selection_set(children[0])
                self._on_disk_select()
        else:
            self._update_disk_detail(None)

    def _on_disk_select(self) -> None:
        if not self._disk_report:
            return
        iid = self._disk_table.selected_iid
        disk = next(
            (
                item
                for index, item in enumerate(self._disk_report.disks)
                if (item.device_id or str(index)) == iid
            ),
            None,
        )
        self._selected_disk_id = iid
        self._update_disk_detail(disk)

    def _update_disk_detail(self, disk: PhysicalDisk | None) -> None:
        if disk is None:
            self._disk_detail_name.configure(text="选择磁盘查看详情")
            self._disk_detail_health.configure(text="—", bg=C.SURFACE_ALT, fg=C.MUTED)
            self._disk_detail_meta.configure(
                text="温度、磨损和通电时间可能因硬盘/驱动而不提供。"
            )
            return
        self._disk_detail_name.configure(text=disk.name)
        variant = "green"
        if disk.health in {"警告", "降级", "压力", "预测故障"}:
            variant = "amber"
        elif disk.health in {"异常", "错误"}:
            variant = "red"
        elif disk.health not in {"健康", "正常"}:
            variant = "neutral"
        self._disk_detail_health.configure(
            text=disk.health,
            bg={
                "green": C.GREEN_DARK,
                "amber": C.AMBER_DARK,
                "red": C.RED_DARK,
                "neutral": C.SURFACE_ALT,
            }[variant],
            fg={
                "green": C.GREEN,
                "amber": C.AMBER,
                "red": C.RED,
                "neutral": C.MUTED,
            }[variant],
        )
        parts = [
            f"序列号 {disk.serial or '—'}",
            f"固件 {disk.firmware or '—'}",
            f"容量 {human_bytes(disk.size)}",
            f"{disk.media_type or '未知类型'} / {disk.bus_type or '未知总线'}",
            f"温度 {disk.temperature if disk.temperature is not None else '—'}",
            f"磨损 {disk.wear if disk.wear is not None else '—'}%",
            f"通电 {disk.power_on_hours if disk.power_on_hours is not None else '—'} 小时",
            f"卷 {', '.join(disk.volumes) or '—'}",
        ]
        if disk.read_errors is not None or disk.write_errors is not None:
            parts.append(
                f"错误计数 读 {disk.read_errors if disk.read_errors is not None else '—'}"
                f" / 写 {disk.write_errors if disk.write_errors is not None else '—'}"
            )
        parts.append(f"状态 {disk.operational or '—'}")
        self._disk_detail_meta.configure(text="  ·  ".join(parts))

    # ------------------------------------------------------------------
    def _copy_report(self) -> None:
        index = self._selected_tab
        if index == 1:
            if not self._disk_report:
                show_notice(self, "暂无数据", "磁盘健康数据尚未读取完成。", kind="info")
                return
            text = self.services["diskhealth"].format_report(self._disk_report)
            label = "磁盘健康报告"
        else:
            if not self._hardware:
                show_notice(self, "暂无数据", "硬件信息尚未读取完成。", kind="info")
                return
            text = self.services["hardware"].format_report(self._hardware)
            label = "硬件报告"
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status(f"{label}已复制到剪贴板")
