"""内存加速页：360 风格仪表盘 + 工作集整理。"""

from __future__ import annotations

import math
import time
import tkinter as tk

from ...models import MemoryBoostResult, ProcessInfo, SystemInfo
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


class MemoryGauge(tk.Canvas):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(
            parent,
            width=238,
            height=214,
            bg=C.SURFACE,
            highlightthickness=0,
            bd=0,
        )
        self._box = (26, 16, 212, 202)
        self._center = (119, 109)
        self._radius = 85
        self._track = self.create_arc(
            *self._box,
            start=225,
            extent=-270,
            style="arc",
            outline=C.SURFACE_ALT,
            width=14,
        )
        self._arc = self.create_arc(
            *self._box,
            start=225,
            extent=0,
            style="arc",
            outline=C.GREEN,
            width=14,
        )
        self._start_cap = self.create_oval(0, 0, 0, 0, fill=C.GREEN, outline="")
        self._end_cap = self.create_oval(0, 0, 0, 0, fill=C.GREEN, outline="")
        self._percent = self.create_text(
            self._center[0],
            self._center[1] - 12,
            text="—",
            fill=C.TEXT,
            font=FONTS["display"],
        )
        self.create_text(
            self._center[0],
            self._center[1] + 27,
            text="内存占用",
            fill=C.MUTED,
            font=FONTS["small"],
        )
        self._detail = self.create_text(
            self._center[0],
            self._center[1] + 50,
            text="",
            fill=C.MUTED_DARK,
            font=FONTS["tiny"],
        )
        self._color = C.GREEN

    def set(self, percent: float, used_text: str) -> None:
        percent = max(0.0, min(100.0, float(percent)))
        if percent >= 85:
            color = C.RED
        elif percent >= 70:
            color = C.AMBER
        elif percent >= 50:
            color = C.CYAN
        else:
            color = C.GREEN
        extent = -270.0 * percent / 100.0
        self.itemconfigure(self._arc, extent=extent, outline=color)
        self.itemconfigure(self._percent, text=f"{percent:.0f}%")
        self.itemconfigure(self._detail, text=used_text)
        self._color = color
        self._position_caps(225 + extent, color)

    def _position_caps(self, end_angle: float, color: str) -> None:
        for item, angle in (
            (self._start_cap, 225.0),
            (self._end_cap, end_angle),
        ):
            radians = math.radians(angle)
            x = self._center[0] + self._radius * math.cos(radians)
            y = self._center[1] - self._radius * math.sin(radians)
            self.coords(item, x - 7, y - 7, x + 7, y + 7)
            self.itemconfigure(item, fill=color, state="normal")
        self.tag_raise(self._start_cap)
        self.tag_raise(self._end_cap)
        self.tag_raise(self._percent)
        self.tag_raise(self._detail)


class MemoryPage(BasePage):
    page_id = "memory"

    def build(self) -> None:
        self._boosting = False
        self._processes: list[ProcessInfo] = []
        self._loading_processes = False
        self._scroll = ScrollableFrame(self, bg=C.BG)
        self._scroll.pack(fill="both", expand=True)
        self._content = self._scroll.inner
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(1, weight=1)

        self._build_hero()
        self._build_body()
        self._scroll.refresh_layout()

    # ------------------------------------------------------------------
    def _build_hero(self) -> None:
        hero = Card(self._content, padding=16)
        hero.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        hero.inner.grid_columnconfigure(1, weight=1)

        gauge = MemoryGauge(hero.inner)
        gauge.grid(row=0, column=0, sticky="nw")
        self._gauge = gauge

        center = tk.Frame(hero.inner, bg=C.SURFACE)
        center.grid(row=0, column=1, sticky="nsew", padx=(18, 18))
        title_row = tk.Frame(center, bg=C.SURFACE)
        title_row.pack(fill="x", pady=(0, 2))
        tk.Label(
            title_row,
            text="一键释放闲置内存",
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["title"],
            anchor="w",
        ).pack(side="left")
        Badge(title_row, "工作集整理", "green").pack(
            side="left", padx=(8, 0), pady=(4, 0)
        )
        tk.Label(
            center,
            text=(
                "把后台程序暂时不用的工作集交还 Windows。"
                "不会关闭程序，需要时系统会自动换回内存。"
            ),
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
            justify="left",
            wraplength=380,
        ).pack(fill="x")

        action_row = tk.Frame(center, bg=C.SURFACE)
        action_row.pack(fill="x", pady=(8, 3))
        self._boost_btn = FlatButton(
            action_row,
            "立即加速",
            command=self._boost,
            variant="accent",
            icon="\uE945",
            bold=True,
            padx=24,
            pady=10,
        )
        self._boost_btn.pack(side="left")
        self._boost_progress = tk.Frame(action_row, bg=C.SURFACE)
        self._boost_progress.pack(side="left", padx=(14, 0), pady=6)
        self._boost_spinner = tk.Label(
            self._boost_progress,
            text="正在整理闲置工作集…",
            bg=C.SURFACE,
            fg=C.AMBER,
            font=FONTS["tiny"],
        )
        self._boost_spinner.pack()
        self._boost_progress.pack_forget()

        self._foreground_var = tk.BooleanVar(value=False)
        self._foreground_check = tk.Checkbutton(
            center,
            text="包含前台应用（可能短暂卡顿）",
            variable=self._foreground_var,
            bg=C.SURFACE,
            fg=C.MUTED,
            activebackground=C.SURFACE,
            activeforeground=C.TEXT,
            selectcolor=C.SURFACE_ALT,
            font=FONTS["tiny"],
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self._foreground_check.pack(anchor="w")
        self._hero_status = tk.Label(
            center,
            text="系统进程和前台窗口默认跳过。",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=380,
        )
        self._hero_status.pack(fill="x", pady=(6, 0))

        stats = tk.Frame(
            hero.inner,
            bg=C.SURFACE_ALT,
            highlightbackground=C.BORDER,
            highlightthickness=1,
        )
        stats.grid(row=0, column=2, sticky="nse", padx=(12, 0))
        stats_inner = tk.Frame(stats, bg=C.SURFACE_ALT)
        stats_inner.pack(fill="both", expand=True, padx=13, pady=11)
        self._stat_values: dict[str, tk.Label] = {}
        self._stat_hints: dict[str, tk.Label] = {}
        for index, (key, title, hint) in enumerate(
            (
                ("available", "当前可用", "物理内存"),
                ("background", "后台应用占用", "默认整理范围"),
            )
        ):
            if index:
                tk.Frame(stats_inner, bg=C.BORDER, height=1).pack(fill="x", pady=5)
            tk.Label(
                stats_inner,
                text=title,
                bg=C.SURFACE_ALT,
                fg=C.MUTED_DARK,
                font=FONTS["tiny"],
                anchor="w",
            ).pack(fill="x")
            value = tk.Label(
                stats_inner,
                text="—",
                bg=C.SURFACE_ALT,
                fg=C.TEXT,
                font=FONTS["metric_sm"],
                anchor="w",
            )
            value.pack(fill="x", pady=(1, 0))
            hint_label = tk.Label(
                stats_inner,
                text=hint,
                bg=C.SURFACE_ALT,
                fg=C.MUTED_DARK,
                font=FONTS["tiny"],
                anchor="w",
            )
            hint_label.pack(fill="x")
            self._stat_values[key] = value
            self._stat_hints[key] = hint_label

    def _build_body(self) -> None:
        body = tk.Frame(self._content, bg=C.BG)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=3, uniform="memorybody")
        body.grid_columnconfigure(1, weight=2, uniform="memorybody")

        card = Card(body, padding=14)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        header = tk.Frame(card.inner, bg=C.SURFACE)
        header.pack(fill="x")
        section_title(header, "内存占用较高的程序").pack(side="left")
        FlatButton(
            header,
            "查看全部进程",
            command=lambda: self.app.navigate("processes"),
            variant="ghost",
            compact=True,
        ).pack(side="right")
        self._process_table = DataTable(
            card.inner,
            columns=(
                ("name", "进程", 220, "w"),
                ("memory", "内存", 90, "e"),
                ("kind", "类型", 65, "w"),
                ("user", "用户", 95, "w"),
            ),
            height=6,
            on_double=lambda: self.app.navigate("processes"),
            horizontal_scrollbar=False,
        )
        self._process_table.pack(fill="both", expand=True, pady=(10, 0))
        self._process_table.show_empty("正在读取进程…")

        info = Card(body, padding=16)
        info.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        section_title(info.inner, "关于内存加速").pack(fill="x")
        tips = tk.Label(
            info.inner,
            text=(
                "• 只整理后台程序闲置的工作集\n"
                "• 不结束进程、不关闭窗口\n"
                "• 不删除任何文件\n"
                "• 系统进程和前台窗口默认跳过\n"
                "• Windows 会按需重新加载内存页\n\n"
                "“整理工作集”不等于增加物理内存；"
                "可用内存变化会受系统活动影响。"
            ),
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="nw",
            justify="left",
            wraplength=300,
        )
        tips.pack(fill="x", pady=(12, 0))
        tk.Label(
            info.inner,
            text="提示：内存加速不是增加物理内存，也不能替代关闭真正占用资源的大型程序。",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=300,
        ).pack(fill="x", pady=(14, 0))

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if self.state.system:
            self._render_system(self.state.system)
        if not self._boosting:
            self._set_controls(True)
        self.app.load_system_async(self._on_system)
        self._load_processes()
        if self.app._current_page == "memory":
            self.set_status("内存加速已就绪")

    def refresh(self) -> None:
        if self._boosting:
            self.set_status("正在加速，请稍候…", "busy")
            return
        self.app.load_system_async(self._on_system)
        self._load_processes()
        if self.app._current_page == "memory":
            self.set_status("正在刷新内存信息…", "busy")

    def _on_system(self, info: SystemInfo | None, error: str) -> None:
        if info is None:
            if self.app._current_page == "memory":
                self.set_status(f"读取内存信息失败：{error}", "error")
            return
        self._render_system(info)
        if self.app._current_page == "memory" and not self._boosting:
            self.set_status("内存信息已更新")

    def _render_system(self, info: SystemInfo) -> None:
        available = max(0, info.memory_total - info.memory_used)
        self._gauge.set(
            info.memory_percent,
            f"{human_bytes(info.memory_used)} / {human_bytes(info.memory_total)}",
        )
        self._stat_values["available"].configure(text=human_bytes(available))

    def _set_controls(self, enabled: bool) -> None:
        self._boost_btn.set_enabled(enabled)
        self._foreground_check.configure(state="normal" if enabled else "disabled")

    def _load_processes(self) -> None:
        if self._loading_processes:
            return
        self._loading_processes = True
        self._process_table.show_empty("正在读取进程…")

        def done(processes: list[ProcessInfo]) -> None:
            self._loading_processes = False
            self._processes = processes
            visible = [
                item
                for item in processes
                if not item.is_system and item.pid > 4
            ]
            visible.sort(key=lambda item: item.memory_bytes, reverse=True)
            rows = []
            for item in visible[:8]:
                rows.append(
                    (
                        str(item.pid),
                        (
                            truncate_middle(item.name, 30),
                            human_bytes(item.memory_bytes),
                            item.kind_label,
                            truncate_middle((item.username or "—").split("\\")[-1], 18),
                        ),
                        (),
                    )
                )
            self._process_table.replace(rows, empty_text="没有读取到进程")
            background = [
                item
                for item in processes
                if item.is_background and not item.is_system
            ]
            background_memory = sum(item.memory_bytes for item in background)
            self._stat_values["background"].configure(
                text=human_bytes(background_memory)
            )
            self._stat_hints["background"].configure(
                text=f"{len(background)} 个后台进程"
            )

        def failed(_exc: Exception) -> None:
            self._loading_processes = False
            self._process_table.show_empty("读取进程失败")

        self.app.runner.submit(
            lambda: self.services["processes"].collect(include_users=True),
            done,
            failed,
            name="memory-processes",
        )

    # ------------------------------------------------------------------
    def _boost(self) -> None:
        if self._boosting:
            return
        include_foreground = bool(self._foreground_var.get())
        self._boosting = True
        self._set_controls(False)
        self._boost_progress.pack(side="left", padx=(14, 0), pady=6)
        self._hero_status.configure(
            text="正在整理闲置工作集，请稍候…",
            fg=C.AMBER,
        )
        self.set_status("正在整理内存工作集…", "busy")

        self.app.runner.submit(
            lambda: self.services["memory"].boost(
                include_foreground=include_foreground
            ),
            self._boost_done,
            self._boost_failed,
            name="memory-boost",
        )

    def _boost_done(self, result: MemoryBoostResult) -> None:
        self._boosting = False
        self._boost_progress.pack_forget()
        self._set_controls(True)
        self._gauge.set(
            result.after_percent,
            (
                f"{human_bytes(max(0, result.after_total - result.after_available))}"
                f" / {human_bytes(result.after_total)}"
            ),
        )
        self._stat_values["available"].configure(
            text=human_bytes(result.after_available)
        )
        delta = result.after_available - result.before_available
        delta_text = ("+" if delta >= 0 else "−") + human_bytes(abs(delta))
        if result.trimmed:
            self._hero_status.configure(
                text=(
                    f"已整理 {result.trimmed} 个进程 · 工作集 "
                    f"-{human_bytes(result.working_set_released)}"
                ),
                fg=C.GREEN,
            )
            if self.app._current_page == "memory":
                self.set_status(
                    f"内存加速完成：整理 {result.trimmed} 个进程，可用内存 {delta_text}"
                )
        else:
            self._hero_status.configure(
                text="没有可整理的后台进程，系统内存可能已经比较充足。",
                fg=C.MUTED,
            )
            if self.app._current_page == "memory":
                self.set_status("内存加速完成：没有可整理的后台进程")
        self._process_table.show_empty("正在刷新进程…")
        self.after(450, self._load_processes)

    def _boost_failed(self, exc: Exception) -> None:
        self._boosting = False
        self._boost_progress.pack_forget()
        self._set_controls(True)
        self._hero_status.configure(text=f"加速失败：{exc}", fg=C.RED)
        if self.app._current_page == "memory":
            self.set_status(f"内存加速失败：{exc}", "error")
        show_notice(self, "内存加速失败", "整理工作集时发生错误。", str(exc), "error")
