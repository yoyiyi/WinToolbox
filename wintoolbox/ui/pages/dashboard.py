"""概览页：状态卡片、快捷操作、卸载建议预览。"""

from __future__ import annotations

import time
import tkinter as tk
from datetime import datetime
from typing import Any, Callable

from ...models import AppRecord, SystemInfo, WingetInfo
from ...utils import format_datetime, human_bytes, human_duration
from ..theme import C, FONTS, ICON_FONT
from ..widgets import (
    Badge,
    Card,
    EmptyState,
    FlatButton,
    Meter,
    ScrollableFrame,
    StatCard,
    _bind_recursive,
    section_title,
)
from .base import BasePage


class DashboardPage(BasePage):
    page_id = "dashboard"

    def build(self) -> None:
        self._processes_loading = False
        self._system_at = 0.0
        self._active = False
        self._scroll = ScrollableFrame(self, bg=C.BG)
        self._scroll.pack(fill="both", expand=True)
        root = self._scroll.inner
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=1)

        stats = tk.Frame(root, bg=C.BG)
        stats.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        for column in range(4):
            stats.grid_columnconfigure(column, weight=1, uniform="stat")
        self.update_card = StatCard(
            stats,
            "可更新应用",
            "未检测",
            "尚未检查更新",
            "\uE895",
            C.CYAN,
            command=lambda: self.app.navigate("updates"),
        )
        self.apps_card = StatCard(
            stats,
            "已安装应用",
            "读取中",
            "正在读取应用清单",
            "\uE71D",
            C.ACCENT,
            command=lambda: self.app.navigate("uninstall"),
        )
        self.process_card = StatCard(
            stats,
            "后台进程",
            "…",
            "正在统计进程",
            "\uE9D9",
            C.PURPLE,
            command=lambda: self.app.navigate("processes"),
        )
        self.advice_card = StatCard(
            stats,
            "卸载建议",
            "…",
            "基于安装信息推断",
            "\uE74D",
            C.AMBER,
            command=lambda: self.app.navigate("uninstall"),
        )
        for index, card in enumerate(
            (self.update_card, self.apps_card, self.process_card, self.advice_card)
        ):
            card.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(0 if index == 0 else 6, 0 if index == 3 else 6),
            )

        body = tk.Frame(root, bg=C.BG)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=3, uniform="body")
        body.grid_columnconfigure(1, weight=2, uniform="body")

        self._build_quick_actions(body)
        self._build_advice_card(body)
        self._build_system_card(body)
        self._scroll.bind_wheel_recursive()

    # ------------------------------------------------------------------
    def _build_quick_actions(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=16)
        card.grid(row=0, column=0, sticky="ew", padx=(0, 7), pady=(0, 4))
        header = tk.Frame(card.inner, bg=C.SURFACE)
        header.pack(fill="x", pady=(0, 6))
        section_title(header, "快捷操作", "常用任务一键直达").pack(side="left")

        grid = tk.Frame(card.inner, bg=C.SURFACE)
        grid.pack(fill="both", expand=True)
        for column in range(3):
            grid.grid_columnconfigure(column, weight=1, uniform="quick")

        tiles = [
            (
                "\uE945",
                "内存加速",
                "整理后台闲置内存",
                C.GREEN,
                lambda: self.app.navigate("memory"),
            ),
            (
                "\uE895",
                "检查应用更新",
                "扫描更新源",
                C.CYAN,
                lambda: self.app.navigate("updates"),
            ),
            (
                "\uE9D9",
                "查看后台进程",
                "资源占用与路径",
                C.PURPLE,
                lambda: self.app.navigate("processes"),
            ),
            (
                "\uE8B7",
                "大文件扫描",
                "按磁盘扫描",
                C.CYAN,
                lambda: self.app.navigate("largefiles"),
            ),
            (
                "\uE74D",
                "精简已装应用",
                "扫描卸载建议",
                C.AMBER,
                lambda: self.app.navigate("uninstall"),
            ),
            (
                "\uE772",
                "硬件检测",
                "CPU、显卡与磁盘",
                C.GREEN,
                lambda: self.app.navigate("hardware"),
            ),
        ]
        for index, (icon, title, desc, accent, command) in enumerate(tiles):
            tile = self._make_tile(grid, icon, title, desc, accent, command)
            column = index % 3
            row = index // 3
            tile.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 4, 0 if column == 2 else 4),
                pady=0,
            )

    def _make_tile(
        self,
        parent: tk.Misc,
        icon: str,
        title: str,
        desc: str,
        accent: str,
        command: Callable[[], None],
    ) -> tk.Frame:
        frame = tk.Frame(
            parent,
            bg=C.SURFACE_ALT,
            highlightbackground=C.BORDER,
            highlightcolor=C.BORDER,
            highlightthickness=1,
            cursor="hand2",
        )
        icon_box = tk.Label(
            frame,
            text=icon,
            bg=C.SURFACE_ALT,
            fg=accent,
            font=(ICON_FONT, 15),
            width=2,
        )
        icon_box.pack(side="left", padx=(10, 8), pady=12)
        text_box = tk.Frame(frame, bg=C.SURFACE_ALT)
        text_box.pack(side="left", fill="both", expand=True, pady=8)
        title_label = tk.Label(
            text_box,
            text=title,
            bg=C.SURFACE_ALT,
            fg=C.TEXT_SOFT,
            font=FONTS["small_bold"],
            anchor="w",
        )
        title_label.pack(anchor="w")
        desc_label = tk.Label(
            text_box,
            text=desc,
            bg=C.SURFACE_ALT,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        )
        desc_label.pack(anchor="w", pady=(2, 0))

        def enter(_event: tk.Event) -> None:
            frame.configure(highlightbackground=accent)
            frame.configure(bg=C.SURFACE_HOVER)
            for widget in (icon_box, text_box, title_label, desc_label):
                widget.configure(bg=C.SURFACE_HOVER)

        def leave(_event: tk.Event) -> None:
            frame.configure(highlightbackground=C.BORDER, bg=C.SURFACE_ALT)
            for widget in (icon_box, text_box, title_label, desc_label):
                widget.configure(bg=C.SURFACE_ALT)

        _bind_recursive(frame, "<Enter>", enter)
        _bind_recursive(frame, "<Leave>", leave)
        _bind_recursive(frame, "<Button-1>", lambda _e: command())
        return frame

    def _build_advice_card(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=16)
        card.grid(row=1, column=0, sticky="nsew", padx=(0, 7))
        header = tk.Frame(card.inner, bg=C.SURFACE)
        header.pack(fill="x")
        section_title(header, "卸载建议").pack(side="left")
        self._advice_badge = Badge(header, "扫描中", "neutral")
        self._advice_badge.pack(side="left", padx=(8, 0))
        FlatButton(
            header,
            "查看全部",
            command=lambda: self.app.navigate("uninstall"),
            variant="ghost",
            compact=True,
        ).pack(side="right")
        self._advice_body = tk.Frame(card.inner, bg=C.SURFACE)
        self._advice_body.pack(fill="both", expand=True, pady=(10, 0))
        self._advice_loading = tk.Label(
            self._advice_body,
            text="正在扫描已安装应用，稍后给出精简建议…",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["small"],
            anchor="w",
        )
        self._advice_loading.pack(fill="x", pady=(6, 0))

    def _build_system_card(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=14)
        card.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(7, 0))
        header = tk.Frame(card.inner, bg=C.SURFACE)
        header.pack(fill="x")
        section_title(header, "系统状态").pack(side="left")
        self._system_badge = Badge(header, "读取中", "neutral")
        self._system_badge.pack(side="right")

        self._os_label = tk.Label(
            card.inner,
            text="正在读取系统信息…",
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["body_bold"],
            anchor="w",
            justify="left",
            wraplength=330,
        )
        self._os_label.pack(fill="x", pady=(6, 2))
        self._host_label = tk.Label(
            card.inner,
            text="",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        )
        self._host_label.pack(fill="x")

        tk.Frame(card.inner, bg=C.BORDER, height=1).pack(fill="x", pady=8)

        self._cpu_meter = Meter(card.inner, "CPU 占用", "—", "Cyan.Horizontal.TProgressbar")
        self._cpu_meter.pack(fill="x", pady=(0, 7))
        self._mem_meter = Meter(card.inner, "内存", "—")
        self._mem_meter.pack(fill="x", pady=(0, 7))
        self._disk_meter = Meter(
            card.inner, "系统盘", "—", "Green.Horizontal.TProgressbar"
        )
        self._disk_meter.pack(fill="x")

        facts = tk.Frame(card.inner, bg=C.SURFACE)
        facts.pack(fill="x", pady=(10, 0))
        facts.grid_columnconfigure(0, weight=1)
        facts.grid_columnconfigure(1, weight=1)
        self._fact_labels: dict[str, tk.Label] = {}
        fact_defs = (
            ("uptime", "开机时长"),
            ("cores", "处理器"),
            ("user", "当前用户"),
            ("winget", "更新组件"),
        )
        for index, (key, title) in enumerate(fact_defs):
            cell = tk.Frame(facts, bg=C.SURFACE)
            cell.grid(
                row=index // 2,
                column=index % 2,
                sticky="w",
                padx=(0, 8),
                pady=(0, 4),
            )
            tk.Label(
                cell,
                text=title,
                bg=C.SURFACE,
                fg=C.MUTED_DARK,
                font=FONTS["tiny"],
                anchor="w",
            ).pack(anchor="w")
            label = tk.Label(
                cell,
                text="—",
                bg=C.SURFACE,
                fg=C.TEXT_SOFT,
                font=FONTS["small_bold"],
                anchor="w",
                wraplength=150,
                justify="left",
            )
            label.pack(anchor="w", pady=(1, 0))
            self._fact_labels[key] = label

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._active = True
        system = self.state.system
        if system:
            self._render_system(system)
        if time.time() - self._system_at > 12:
            self.app.load_system_async(self._on_system)
        self.app.load_apps_async(self._on_apps)
        self.app.load_winget_async(self._on_winget)
        self._render_updates()
        self._load_processes()
        self._render_advice()
        # 第一次系统采样没有 CPU 差值，稍后再取一次。
        self.after(1300, self._refresh_cpu_once)

    def on_hide(self) -> None:
        self._active = False

    def refresh(self) -> None:
        self.set_status("正在刷新概览…", "busy")
        self.app.load_system_async(self._on_system)
        self.app.load_apps_async(self._on_apps, force=True)
        self._load_processes()
        self._render_updates()

    def _refresh_cpu_once(self) -> None:
        if not self._active:
            return

        def done(info: SystemInfo) -> None:
            if self._active:
                self.state.system = info
                self._cpu_meter.set(info.cpu_percent, f"{info.cpu_percent:.0f}%")

        self.app.runner.submit(
            self.services["system"].collect, done, name="dashboard-cpu"
        )

    def _on_system(self, info: SystemInfo | None, error: str) -> None:
        if info is None:
            self._system_badge.configure(text="读取失败", bg=C.RED_DARK, fg=C.RED)
            self.set_status(f"读取系统信息失败：{error}", "error")
            return
        self._system_at = time.time()
        self._render_system(info)
        if self.app._current_page == "dashboard":
            self.set_status(f"系统状态已更新 · {format_datetime(datetime.now())}")

    def _render_system(self, info: SystemInfo) -> None:
        self._system_badge.configure(
            text="管理员" if info.is_admin else "标准用户",
            bg=C.GREEN_DARK if info.is_admin else C.AMBER_DARK,
            fg=C.GREEN if info.is_admin else C.AMBER,
        )
        self._os_label.configure(text=info.os_name)
        self._host_label.configure(
            text=f"{info.hostname}  ·  {info.cpu_name}"
        )
        self._cpu_meter.set(info.cpu_percent, f"{info.cpu_percent:.0f}%")
        self._mem_meter.set(
            info.memory_percent,
            f"{human_bytes(info.memory_used)} / {human_bytes(info.memory_total)}",
        )
        self._disk_meter.set(
            info.disk_percent,
            f"{human_bytes(info.disk_used)} / {human_bytes(info.disk_total)}",
        )
        self._fact_labels["uptime"].configure(text=human_duration(info.uptime_seconds))
        self._fact_labels["cores"].configure(text=f"{info.cpu_cores} 线程")
        self._fact_labels["user"].configure(text=info.username)
        winget = self.state.winget_info
        if winget is None:
            self._fact_labels["winget"].configure(text="检测中…")
        elif winget.available:
            self._fact_labels["winget"].configure(text=f"winget {winget.version}")
        else:
            self._fact_labels["winget"].configure(text="不可用")
        if self.state.apps:
            self.apps_card.set_value(str(len(self.state.apps)))

    def _on_apps(self, apps: list[AppRecord], error: str) -> None:
        if error:
            self.apps_card.set_value("—", "扫描失败，请查看日志")
            self._advice_loading.configure(text=f"扫描应用失败：{error}")
            return
        recommended = [item for item in apps if item.advice == "可考虑卸载"]
        self.apps_card.set_value(
            str(len(apps)),
            f"其中 {sum(1 for item in apps if item.protected)} 个受保护组件",
        )
        self.advice_card.set_value(str(len(recommended)), "仅供参考，请确认后卸载")
        self._render_advice()

    def _render_advice(self) -> None:
        for child in self._advice_body.winfo_children():
            child.destroy()
        apps = self.state.apps
        if not apps:
            EmptyState(
                self._advice_body,
                "正在整理建议",
                "应用扫描完成后会在这里显示可考虑精简的软件。",
                icon="\uE74D",
            ).pack(fill="both", expand=True)
            self._advice_badge.configure(text="扫描中", bg=C.SURFACE_ALT, fg=C.MUTED)
            return
        candidates = sorted(
            (item for item in apps if item.advice == "可考虑卸载"),
            key=lambda item: (-item.score, item.name.casefold()),
        )
        self._advice_badge.configure(
            text=f"{len(candidates)} 项" if candidates else "暂无",
            bg=C.AMBER_DARK if candidates else C.SURFACE_ALT,
            fg=C.AMBER if candidates else C.MUTED,
        )
        if not candidates:
            EmptyState(
                self._advice_body,
                "没有发现明显冗余",
                f"已检查 {len(apps)} 款应用。卸载建议是启发式判断，不代表实际使用情况。",
                icon="\uE73E",
            ).pack(fill="both", expand=True)
            return

        for index, app in enumerate(candidates[:5]):
            row = tk.Frame(
                self._advice_body,
                bg=C.SURFACE,
                cursor="hand2",
            )
            row.pack(fill="x", pady=(0, 6) if index < 4 else 0)
            rank = tk.Label(
                row,
                text=str(index + 1),
                bg=C.AMBER_DARK,
                fg=C.AMBER,
                font=FONTS["tiny"],
                width=3,
                pady=2,
            )
            rank.pack(side="left", padx=(0, 9))
            text_box = tk.Frame(row, bg=C.SURFACE)
            text_box.pack(side="left", fill="x", expand=True)
            name = tk.Label(
                text_box,
                text=app.name,
                bg=C.SURFACE,
                fg=C.TEXT_SOFT,
                font=FONTS["small_bold"],
                anchor="w",
            )
            name.pack(fill="x")
            reason = app.reasons[0] if app.reasons else "建议确认使用频率后精简"
            hint = tk.Label(
                text_box,
                text=reason,
                bg=C.SURFACE,
                fg=C.MUTED_DARK,
                font=FONTS["tiny"],
                anchor="w",
            )
            hint.pack(fill="x")
            score = Badge(row, f"{app.score}", "amber")
            score.pack(side="right", padx=(8, 0))

            def enter(_event: tk.Event, widgets=(row, text_box, name, hint)) -> None:
                for widget in widgets:
                    widget.configure(bg=C.SURFACE_HOVER)

            def leave(_event: tk.Event, widgets=(row, text_box, name, hint)) -> None:
                for widget in widgets:
                    widget.configure(bg=C.SURFACE)

            _bind_recursive(row, "<Enter>", enter)
            _bind_recursive(row, "<Leave>", leave)
            _bind_recursive(row, "<Button-1>", lambda _e: self.app.navigate("uninstall"))
        self._scroll.bind_wheel_recursive()

    def _on_winget(self, info: WingetInfo) -> None:
        if info.available:
            self._fact_labels["winget"].configure(text=f"winget {info.version}")
        else:
            self._fact_labels["winget"].configure(text="不可用")
        self._render_updates()

    def _render_updates(self) -> None:
        winget = self.state.winget_info
        if self.state.updates_at:
            count = len(self.state.updates)
            checked = datetime.fromtimestamp(self.state.updates_at)
            self.update_card.set_value(
                str(count),
                f"更新于 {checked:%H:%M}" if count else "所有应用均为最新",
            )
        elif winget and not winget.available:
            self.update_card.set_value("不可用", "点击前往更新页修复")
        else:
            self.update_card.set_value("未检测", "尚未检查更新")

    def _load_processes(self) -> None:
        if self._processes_loading:
            return
        self._processes_loading = True
        self.process_card.set_value("…", "正在统计进程")

        def done(processes: list[Any]) -> None:
            self._processes_loading = False
            stats = self.services["processes"].stats(processes)
            self.process_card.set_value(
                str(stats["total"]),
                f"后台 {stats['background']} 个 · {stats['memory_text']}",
            )

        def failed(exc: Exception) -> None:
            self._processes_loading = False
            self.process_card.set_value("—", "读取进程失败")

        self.app.runner.submit(
            lambda: self.services["processes"].collect(include_users=False),
            done,
            failed,
            name="dashboard-processes",
        )
