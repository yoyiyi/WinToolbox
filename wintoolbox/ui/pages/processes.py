"""后台进程页：进程列表、详情、结束进程与定位文件。"""

from __future__ import annotations

import os
import tkinter as tk
from datetime import datetime
from tkinter import ttk
from typing import Any

from ...models import ProcessInfo
from ...utils import (
    audit,
    format_datetime,
    human_bytes,
    reveal_in_explorer,
    truncate_middle,
)
from ..theme import C, FONTS
from ..widgets import (
    Badge,
    Card,
    DataTable,
    FlatButton,
    ScrollableFrame,
    SearchBox,
    ask_confirm,
    show_notice,
)
from .base import BasePage


class ProcessesPage(BasePage):
    page_id = "processes"

    def build(self) -> None:
        self._all: list[ProcessInfo] = []
        self._by_pid: dict[int, ProcessInfo] = {}
        self._loading = False
        self._active = False
        self._after_id: str | None = None
        self._filter = "全部进程"
        self._sort_key = "cpu"
        self._sort_desc = True
        self._selected_pid: int | None = None
        self._auto_var = tk.BooleanVar(
            value=bool(self.app.config_store.get("process_auto_refresh", True))
        )

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._build_toolbar()
        self._build_meta()
        self._build_body()

    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=C.BG)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.grid_columnconfigure(3, weight=1)
        self._search = SearchBox(
            bar,
            placeholder="搜索进程名、路径或用户…",
            width=27,
            on_change=self._render,
        )
        self._search.grid(row=0, column=0, sticky="w")

        self._filter_var = tk.StringVar(value=self._filter)
        self._filter_box = ttk.Combobox(
            bar,
            textvariable=self._filter_var,
            values=("全部进程", "后台进程", "前台窗口", "高占用", "系统进程"),
            state="readonly",
            width=9,
            font=FONTS["small"],
        )
        self._filter_box.grid(row=0, column=1, padx=(10, 0))
        self._filter_box.bind("<<ComboboxSelected>>", self._on_filter)

        self._auto_check = tk.Checkbutton(
            bar,
            text="自动刷新 4s",
            variable=self._auto_var,
            command=self._toggle_auto,
            bg=C.BG,
            fg=C.MUTED,
            activebackground=C.BG,
            activeforeground=C.TEXT,
            selectcolor=C.SURFACE_ALT,
            font=FONTS["tiny"],
            bd=0,
            highlightthickness=0,
            cursor="hand2",
        )
        self._auto_check.grid(row=0, column=2, padx=(12, 0))

        self._refresh_btn = FlatButton(
            bar,
            "刷新",
            command=self.refresh,
            variant="secondary",
            icon="\uE72C",
            compact=True,
        )
        self._refresh_btn.grid(row=0, column=4, sticky="e")

    def _build_meta(self) -> None:
        meta = tk.Frame(self, bg=C.BG)
        meta.grid(row=1, column=0, sticky="ew", pady=(0, 7))
        self._summary = tk.Label(
            meta,
            text="正在读取进程…",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
        )
        self._summary.pack(side="left")
        tk.Label(
            meta,
            text="·  首次加载的 CPU 数据会在下一次采样后出现",
            bg=C.BG,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
        ).pack(side="left", padx=(10, 0), pady=(2, 0))

    def _build_body(self) -> None:
        body = tk.Frame(self, bg=C.BG)
        body.grid(row=2, column=0, sticky="nsew")
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=0, minsize=340)
        detail_host = tk.Frame(body, bg=C.BG, width=340)
        detail_host.grid(row=0, column=1, sticky="nsew")
        detail_host.grid_propagate(False)
        detail_host.grid_rowconfigure(0, weight=1)
        detail_host.grid_columnconfigure(0, weight=1)

        self._table = DataTable(
            body,
            columns=(
                ("name", "进程", 235, "w"),
                ("pid", "PID", 65, "e"),
                ("cpu", "CPU", 65, "e"),
                ("memory", "内存", 90, "e"),
                ("kind", "类型", 60, "w"),
                ("user", "用户", 80, "w"),
            ),
            height=14,
            on_sort=self._sort_by,
            on_select=self._on_select,
            on_double=self._open_location,
        )
        self._table.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._table.tree.tag_configure("system", foreground=C.MUTED)
        self._table.tree.tag_configure("high", foreground=C.AMBER)
        self._table.show_empty("正在读取进程列表…")

        self._build_detail(detail_host)

    def _build_detail(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=16)
        card.grid(row=0, column=0, sticky="nsew")
        header = tk.Frame(card.inner, bg=C.SURFACE)
        header.pack(fill="x")
        tk.Label(
            header,
            text="进程详情",
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["body_bold"],
        ).pack(side="left")
        self._kind_badge = Badge(header, "未选择", "neutral")
        self._kind_badge.pack(side="right")

        # 先占住底部操作区，窗口较矮时按钮也始终可用。
        self._actions_holder = tk.Frame(card.inner, bg=C.SURFACE)
        self._actions_holder.pack(side="bottom", fill="x", pady=(10, 0))

        self._detail_scroll = ScrollableFrame(card.inner, bg=C.SURFACE)
        self._detail_scroll.pack(fill="both", expand=True, pady=(10, 0))
        body = self._detail_scroll.inner

        self._detail_name = tk.Label(
            body,
            text="选择一个进程",
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["title"],
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._detail_name.pack(fill="x")
        self._detail_title = tk.Label(
            body,
            text="从左侧列表选择，查看路径、用户和启动时间。",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._detail_title.pack(fill="x", pady=(4, 0))

        tk.Frame(body, bg=C.BORDER, height=1).pack(fill="x", pady=9)

        self._detail_values: dict[str, tk.Label] = {}
        fields = (
            ("pid", "PID"),
            ("cpu", "CPU"),
            ("memory", "内存"),
            ("kind", "运行类型"),
            ("user", "用户"),
            ("parent", "父进程"),
            ("started", "启动时间"),
        )
        grid = tk.Frame(body, bg=C.SURFACE)
        grid.pack(fill="x")
        grid.grid_columnconfigure(1, weight=1)
        for index, (key, label) in enumerate(fields):
            tk.Label(
                grid,
                text=label,
                bg=C.SURFACE,
                fg=C.MUTED_DARK,
                font=FONTS["tiny"],
                anchor="w",
            ).grid(row=index, column=0, sticky="w", pady=3)
            value = tk.Label(
                grid,
                text="—",
                bg=C.SURFACE,
                fg=C.TEXT_SOFT,
                font=FONTS["small"],
                anchor="e",
                justify="right",
                wraplength=210,
            )
            value.grid(row=index, column=1, sticky="e", pady=3)
            self._detail_values[key] = value

        self._detail_path = tk.Label(
            body,
            text="—",
            bg=C.SURFACE_ALT,
            fg=C.MUTED,
            font=FONTS["mono_sm"],
            anchor="w",
            justify="left",
            wraplength=270,
            padx=8,
            pady=5,
        )
        self._detail_path.pack(fill="x", pady=(9, 0))

        self._detail_hint = tk.Label(
            body,
            text="",
            bg=C.SURFACE,
            fg=C.AMBER,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._detail_hint.pack(fill="x", pady=(8, 0))

        actions = tk.Frame(self._actions_holder, bg=C.SURFACE)
        actions.pack(fill="x")
        self._kill_btn = FlatButton(
            actions,
            "结束进程",
            command=self._kill_selected,
            variant="danger",
            compact=True,
        )
        self._kill_btn.pack(fill="x")
        ghost_row = tk.Frame(actions, bg=C.SURFACE)
        ghost_row.pack(fill="x", pady=(6, 0))
        self._open_btn = FlatButton(
            ghost_row,
            "打开位置",
            command=self._open_location,
            variant="secondary",
            compact=True,
        )
        self._open_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self._copy_btn = FlatButton(
            ghost_row,
            "复制路径",
            command=self._copy_path,
            variant="ghost",
            compact=True,
        )
        self._copy_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))
        self._detail_scroll.bind_wheel_recursive()
        self._update_detail(None)

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._active = True
        self._load()

    def on_hide(self) -> None:
        self._active = False
        self._cancel_timer()

    def refresh(self) -> None:
        self._cancel_timer()
        self._load()

    def _cancel_timer(self) -> None:
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _schedule(self) -> None:
        self._cancel_timer()
        if self._active and self._auto_var.get() and not self._loading:
            self._after_id = self.after(4000, self._auto_tick)

    def _auto_tick(self) -> None:
        self._after_id = None
        if self._active and self._auto_var.get():
            self._load()

    def _toggle_auto(self) -> None:
        enabled = bool(self._auto_var.get())
        self.app.config_store.set("process_auto_refresh", enabled)
        if enabled:
            self.set_status("已开启自动刷新（每 4 秒）")
            self._schedule()
        else:
            self._cancel_timer()
            self.set_status("已关闭自动刷新")

    def _load(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._cancel_timer()
        self._refresh_btn.set_enabled(False)
        self._table.show_empty("正在读取进程列表…")
        self.set_status("正在读取进程列表…", "busy")

        def done(processes: list[ProcessInfo]) -> None:
            self._loading = False
            self._refresh_btn.set_enabled(True)
            self._all = processes
            self._by_pid = {item.pid: item for item in processes}
            self.app.state.last_processes = processes
            self._render()
            stats = self.services["processes"].stats(processes)
            self.set_status(
                f"已加载 {stats['total']} 个进程 · 后台应用 {stats['background']} 个"
            )
            self._schedule()

        def failed(exc: Exception) -> None:
            self._loading = False
            self._refresh_btn.set_enabled(True)
            self._table.show_empty("读取进程列表失败")
            self.set_status(f"读取进程失败：{exc}", "error")
            self._schedule()

        self.app.runner.submit(
            lambda: self.services["processes"].collect(include_users=True),
            done,
            failed,
            name="processes",
        )

    def _on_filter(self, _event: tk.Event | None = None) -> None:
        self._filter = self._filter_var.get()
        self._render()

    def _sort_by(self, key: str) -> None:
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = key not in {"name", "kind", "user"}
        self._render()

    def _filtered(self) -> list[ProcessInfo]:
        query = self._search.get().casefold()
        processes = []
        for item in self._all:
            if self._filter == "后台进程" and (not item.is_background or item.is_system):
                continue
            if self._filter == "前台窗口" and item.is_background:
                continue
            if self._filter == "高占用" and not (
                item.cpu_percent >= 5 or item.memory_bytes >= 500 * 1024 * 1024
            ):
                continue
            if self._filter == "系统进程" and not item.is_system:
                continue
            if query and not (
                query in item.name.casefold()
                or query in item.path.casefold()
                or query in item.username.casefold()
            ):
                continue
            processes.append(item)
        return processes

    def _sorted(self, processes: list[ProcessInfo]) -> list[ProcessInfo]:
        key = self._sort_key
        reverse = self._sort_desc
        if key == "name":
            processes.sort(key=lambda item: item.name.casefold(), reverse=reverse)
        elif key == "pid":
            processes.sort(key=lambda item: item.pid, reverse=reverse)
        elif key == "cpu":
            processes.sort(key=lambda item: item.cpu_percent, reverse=reverse)
        elif key == "memory":
            processes.sort(key=lambda item: item.memory_bytes, reverse=reverse)
        elif key == "kind":
            processes.sort(key=lambda item: item.kind_label, reverse=reverse)
        elif key == "user":
            processes.sort(key=lambda item: item.username.casefold(), reverse=reverse)
        return processes

    def _render(self) -> None:
        processes = self._sorted(self._filtered())
        rows = []
        for item in processes:
            tags: list[str] = []
            if item.is_system:
                tags.append("system")
            if item.cpu_percent >= 10 or item.memory_bytes >= 800 * 1024 * 1024:
                tags.append("high")
            rows.append(
                (
                    str(item.pid),
                    (
                        item.name,
                        item.pid,
                        f"{item.cpu_percent:.1f}%",
                        human_bytes(item.memory_bytes),
                        item.kind_label,
                        (item.username or "—").split("\\")[-1],
                    ),
                    tags,
                )
            )
        if not self._all:
            empty = "正在读取进程列表…" if self._loading else "没有读取到进程"
        elif not processes:
            empty = "没有匹配的进程"
        else:
            empty = ""
        self._table.replace(rows, empty_text=empty)
        titles = {
            "name": "进程",
            "pid": "PID",
            "cpu": "CPU",
            "memory": "内存",
            "kind": "类型",
            "user": "用户",
        }
        for key, title in titles.items():
            arrow = ""
            if key == self._sort_key:
                arrow = "  ↓" if self._sort_desc else "  ↑"
            self._table.tree.heading(key, text=title + arrow)
        stats = self.services["processes"].stats(self._all)
        self._summary.configure(
            text=(
                f"共 {stats['total']} 个进程  ·  后台应用 {stats['background']} 个  ·  "
                f"内存 {stats['memory_text']}"
            )
        )
        children = self._table.tree.get_children()
        if self._selected_pid is not None and str(self._selected_pid) in children:
            self._table.tree.selection_set(str(self._selected_pid))
        elif self._table.selected_iid:
            self._selected_pid = int(self._table.selected_iid)
        elif children:
            # 首次进入时自动选中资源占用最高的进程，右侧详情即刻可见。
            self._table.tree.selection_set(children[0])
            self._on_select()

    def _selected_process(self) -> ProcessInfo | None:
        iid = self._table.selected_iid
        if not iid:
            return None
        try:
            return self._by_pid.get(int(iid))
        except ValueError:
            return None

    def _on_select(self) -> None:
        process = self._selected_process()
        if process:
            self._selected_pid = process.pid
        self._update_detail(process)

    def _update_detail(self, process: ProcessInfo | None) -> None:
        if process is None:
            self._detail_name.configure(text="选择一个进程")
            self._detail_title.configure(
                text="从左侧列表选择，查看路径、用户和启动时间。"
            )
            self._kind_badge.configure(text="未选择", bg=C.SURFACE_ALT, fg=C.MUTED)
            for value in self._detail_values.values():
                value.configure(text="—")
            self._detail_path.configure(text="—")
            self._detail_hint.configure(text="")
            self._kill_btn.set_enabled(False)
            self._open_btn.set_enabled(False)
            self._copy_btn.set_enabled(False)
            self._detail_scroll.refresh_layout()
            return

        self._detail_name.configure(text=process.name)
        title = process.window_title or (
            "后台运行，没有可见窗口" if process.is_background else "窗口程序"
        )
        self._detail_title.configure(text=title)
        kind_variant = "red" if process.is_system else ("purple" if process.is_background else "green")
        self._kind_badge.configure(
            text=process.kind_label,
            bg={
                "red": C.RED_DARK,
                "purple": "#2A2442",
                "green": C.GREEN_DARK,
            }[kind_variant],
            fg={
                "red": C.RED,
                "purple": C.PURPLE,
                "green": C.GREEN,
            }[kind_variant],
        )
        self._detail_values["pid"].configure(text=str(process.pid))
        self._detail_values["cpu"].configure(text=f"{process.cpu_percent:.1f}%")
        self._detail_values["memory"].configure(text=human_bytes(process.memory_bytes))
        self._detail_values["kind"].configure(
            text="系统进程" if process.is_system else ("后台" if process.is_background else "前台窗口")
        )
        self._detail_values["user"].configure(
            text=truncate_middle((process.username or "—").split("\\")[-1], 24)
        )
        if process.parent_name:
            parent_text = f"{process.parent_name} ({process.parent_pid})"
        elif process.parent_pid:
            parent_text = f"PID {process.parent_pid}"
        else:
            parent_text = "—"
        self._detail_values["parent"].configure(text=parent_text)
        self._detail_values["started"].configure(
            text=format_datetime(process.create_time) if process.create_time else "—"
        )
        path = process.path or "（无法读取路径，可能权限不足）"
        self._detail_path.configure(text=truncate_middle(path, 110))
        protected = self.services["processes"].is_protected(process)
        if protected:
            self._detail_hint.configure(
                text="系统进程或工具箱自身受保护，不能从此处结束。",
                fg=C.AMBER,
            )
        elif not process.path:
            self._detail_hint.configure(
                text="无法读取文件路径；结束进程可能需要管理员权限。",
                fg=C.MUTED_DARK,
            )
        else:
            self._detail_hint.configure(text="")
        self._kill_btn.set_enabled(not protected)
        self._open_btn.set_enabled(bool(process.path and os.path.exists(process.path)))
        self._copy_btn.set_enabled(bool(process.path))
        self._detail_scroll.refresh_layout()

    # ------------------------------------------------------------------
    def _kill_selected(self) -> None:
        process = self._selected_process()
        if process is None:
            return
        if self.services["processes"].is_protected(process):
            show_notice(self, "受保护的进程", "系统进程或工具箱自身不能从此处结束。", kind="warning")
            return
        confirmed = ask_confirm(
            self,
            f"结束 {process.name}？",
            "强制结束进程可能导致未保存的数据丢失，正在执行的任务也可能中断。",
            f"PID: {process.pid}\n路径: {process.path or '未知'}\n内存: {human_bytes(process.memory_bytes)}",
            confirm_text="结束进程",
            danger=True,
        )
        if not confirmed:
            return
        audit("kill_process", {"pid": process.pid, "name": process.name, "path": process.path})
        self._kill_btn.set_enabled(False)
        self.set_status(f"正在结束 {process.name}…", "busy")

        def done(result: tuple[bool, str]) -> None:
            ok, message = result
            self._kill_btn.set_enabled(True)
            self.set_status(message, "normal" if ok else "error")
            if ok:
                self.after(500, self._load)
            else:
                show_notice(self, "无法结束进程", message, kind="error")

        self.app.runner.submit(
            lambda: self.services["processes"].kill(process), done, name="kill-process"
        )

    def _open_location(self) -> None:
        process = self._selected_process()
        if process is None:
            return
        if not process.path or not os.path.exists(process.path):
            show_notice(
                self,
                "无法定位文件",
                "该进程没有可读取的文件路径，可能因为权限不足或进程已退出。",
                kind="warning",
            )
            return
        reveal_in_explorer(process.path)

    def _copy_path(self) -> None:
        process = self._selected_process()
        if process is None or not process.path:
            return
        self.clipboard_clear()
        self.clipboard_append(process.path)
        self.set_status("文件路径已复制到剪贴板")
