"""启动项页：只读查看，修改交给任务管理器。"""

from __future__ import annotations

import os
import tkinter as tk
from typing import Any

from ...models import StartupEntry
from ...utils import (
    is_admin,
    open_startup_folder,
    open_task_manager,
    reveal_in_explorer,
    truncate_middle,
)
from ..theme import C, FONTS
from ..widgets import (
    Badge,
    Card,
    DataTable,
    FlatButton,
    SearchBox,
    ask_confirm,
    show_notice,
)
from .base import BasePage


class StartupPage(BasePage):
    page_id = "startup"

    def build(self) -> None:
        self._all: list[StartupEntry] = []
        self._selected: StartupEntry | None = None
        self._by_iid: dict[str, StartupEntry] = {}
        self._sort_key = "status"
        self._sort_desc = False
        self._loading = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_banner()
        self._build_toolbar()
        self._build_meta()
        self._build_table()
        self._build_detail()

    def _build_banner(self) -> None:
        banner = tk.Frame(
            self,
            bg=C.SURFACE_ALT,
            highlightbackground=C.BORDER,
            highlightthickness=1,
        )
        banner.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        inner = tk.Frame(banner, bg=C.SURFACE_ALT)
        inner.pack(fill="x", padx=12, pady=8)
        tk.Label(
            inner,
            text="i",
            bg=C.ACCENT_DARK,
            fg=C.ACCENT,
            font=FONTS["tiny"],
            width=2,
        ).pack(side="left", padx=(0, 9))
        tk.Label(
            inner,
            text=(
                "可在本页启用或禁用启动项；所有用户的项目需要管理员权限。"
                "禁用只影响下次登录，不会立即结束正在运行的程序。"
            ),
            bg=C.SURFACE_ALT,
            fg=C.MUTED,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=910,
        ).pack(side="left", fill="x", expand=True)

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=C.BG)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        bar.grid_columnconfigure(2, weight=1)
        self._search = SearchBox(
            bar,
            placeholder="搜索启动项名称或命令…",
            width=27,
            on_change=self._render,
        )
        self._search.grid(row=0, column=0, sticky="w")

        self._count_badge = Badge(bar, "读取中", "neutral")
        self._count_badge.grid(row=0, column=1, padx=(10, 0))

        actions = tk.Frame(bar, bg=C.BG)
        actions.grid(row=0, column=3, sticky="e")
        self._folder_menu = tk.Menu(
            self,
            tearoff=0,
            bg=C.SURFACE_ALT,
            fg=C.TEXT,
            activebackground=C.ACCENT_DARK,
            activeforeground=C.TEXT,
            bd=0,
        )
        self._folder_menu.add_command(
            label="当前用户启动文件夹",
            command=lambda: open_startup_folder(False),
        )
        self._folder_menu.add_command(
            label="所有用户启动文件夹",
            command=lambda: open_startup_folder(True),
        )
        self._folder_btn = FlatButton(
            actions,
            "启动文件夹",
            command=self._popup_folder_menu,
            variant="ghost",
            compact=True,
        )
        self._folder_btn.pack(side="right", padx=(6, 0))
        FlatButton(
            actions,
            "任务管理器",
            command=open_task_manager,
            variant="secondary",
            icon="\uE9D9",
            compact=True,
        ).pack(side="right", padx=(6, 0))
        self._refresh_btn = FlatButton(
            actions,
            "刷新",
            command=self.refresh,
            variant="secondary",
            icon="\uE72C",
            compact=True,
        )
        self._refresh_btn.pack(side="right")

    def _popup_folder_menu(self) -> None:
        x = self._folder_btn.winfo_rootx()
        y = self._folder_btn.winfo_rooty() + self._folder_btn.winfo_height() + 2
        try:
            self._folder_menu.tk_popup(x, y)
        finally:
            self._folder_menu.grab_release()

    def _build_meta(self) -> None:
        meta = tk.Frame(self, bg=C.BG)
        meta.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        self._stats_label = tk.Label(
            meta,
            text="正在读取启动项…",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
        )
        self._stats_label.pack(side="left")
        tk.Label(
            meta,
            text="·  启动项开关在下方详情栏，系统级项目需要管理员",
            bg=C.BG,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
        ).pack(side="left", padx=(10, 0), pady=(2, 0))

    def _build_table(self) -> None:
        self._table = DataTable(
            self,
            columns=(
                ("name", "启动项", 200, "w"),
                ("status", "状态", 76, "w"),
                ("scope", "范围", 115, "w"),
                ("source", "来源", 90, "w"),
                ("command", "命令", 380, "w"),
            ),
            height=13,
            on_sort=self._sort_by,
            on_select=self._on_select,
        )
        self._table.grid(row=3, column=0, sticky="nsew")
        self._table.tree.tag_configure("disabled", foreground=C.MUTED_DARK)
        self._table.tree.tag_configure("enabled", foreground=C.TEXT_SOFT)
        self._table.show_empty("正在读取启动项…")

    def _build_detail(self) -> None:
        card = Card(self, padding=12)
        card.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        inner = card.inner
        top = tk.Frame(inner, bg=C.SURFACE)
        top.pack(fill="x")
        self._detail_name = tk.Label(
            top,
            text="选择一个启动项查看完整命令",
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            font=FONTS["small_bold"],
            anchor="w",
        )
        self._detail_name.pack(side="left")
        self._copy_btn = FlatButton(
            top,
            "复制命令",
            command=self._copy_command,
            variant="ghost",
            compact=True,
        )
        self._copy_btn.pack(side="right")
        self._toggle_btn = FlatButton(
            top,
            "禁用",
            command=self._toggle_selected,
            variant="secondary",
            compact=True,
        )
        self._toggle_btn.pack(side="right", padx=(0, 4))
        self._open_btn = FlatButton(
            top,
            "打开位置",
            command=self._open_location,
            variant="ghost",
            compact=True,
        )
        self._open_btn.pack(side="right", padx=(0, 4))
        self._detail_command = tk.Label(
            inner,
            text="注册表和启动文件夹中的自启动项目会在此汇总。",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["mono_sm"],
            anchor="w",
            justify="left",
            wraplength=980,
        )
        self._detail_command.pack(fill="x", pady=(6, 0))
        self._copy_btn.set_enabled(False)
        self._open_btn.set_enabled(False)
        self._toggle_btn.set_enabled(False)

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self.app.load_startup_async(self._apply)

    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._refresh_btn.set_enabled(False)
        self._stats_label.configure(text="正在刷新启动项…")
        self.app.load_startup_async(self._done, force=True)

    def _done(self, entries: list[StartupEntry], error: str) -> None:
        self._loading = False
        self._refresh_btn.set_enabled(True)
        self._apply(entries, error)
        if not error:
            self.set_status(f"启动项已刷新：{len(entries)} 项")

    def _apply(self, entries: list[StartupEntry], error: str) -> None:
        if error:
            self._stats_label.configure(text="读取启动项失败")
            self._table.show_empty("读取启动项失败")
            self.set_status(f"读取启动项失败：{error}", "error")
            return
        self._all = entries
        self._render()
        if self.app._current_page == "startup":
            enabled = sum(1 for item in entries if item.enabled)
            self.set_status(f"已加载 {len(entries)} 个启动项 · {enabled} 项启用")

    def _sort_by(self, key: str) -> None:
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = False
        self._render()

    def _filtered(self) -> list[StartupEntry]:
        query = self._search.get().casefold()
        entries = [
            item
            for item in self._all
            if not query
            or query in item.name.casefold()
            or query in item.command.casefold()
            or query in item.scope.casefold()
        ]
        if self._sort_key == "name":
            entries.sort(key=lambda item: item.name.casefold(), reverse=self._sort_desc)
        elif self._sort_key == "status":
            entries.sort(
                key=lambda item: (not item.enabled, item.name.casefold()),
                reverse=self._sort_desc,
            )
        elif self._sort_key == "scope":
            entries.sort(key=lambda item: item.scope.casefold(), reverse=self._sort_desc)
        elif self._sort_key == "source":
            entries.sort(key=lambda item: item.source.casefold(), reverse=self._sort_desc)
        elif self._sort_key == "command":
            entries.sort(key=lambda item: item.command.casefold(), reverse=self._sort_desc)
        return entries

    def _render(self) -> None:
        entries = self._filtered()
        rows = []
        self._by_iid = {}
        for index, item in enumerate(entries):
            tag = "enabled" if item.enabled else "disabled"
            iid = f"{index}:{item.name}:{item.command[:30]}"
            self._by_iid[iid] = item
            rows.append(
                (
                    iid,
                    (
                        item.name,
                        "已启用" if item.enabled else "已禁用",
                        item.scope,
                        item.source,
                        item.command,
                    ),
                    (tag,),
                )
            )
        if not self._all:
            empty = "未发现启动项"
        elif not entries:
            empty = "没有匹配的启动项"
        else:
            empty = ""
        self._table.replace(rows, empty_text=empty)
        titles = {
            "name": "启动项",
            "status": "状态",
            "scope": "范围",
            "source": "来源",
            "command": "命令",
        }
        for key, title in titles.items():
            arrow = ""
            if key == self._sort_key:
                arrow = "  ↓" if self._sort_desc else "  ↑"
            self._table.tree.heading(key, text=title + arrow)
        enabled = sum(1 for item in self._all if item.enabled)
        disabled = len(self._all) - enabled
        registry = sum(1 for item in self._all if item.source == "注册表")
        folders = len(self._all) - registry
        self._count_badge.configure(
            text=f"{enabled} 项启用",
            bg=C.AMBER_DARK if enabled else C.GREEN_DARK,
            fg=C.AMBER if enabled else C.GREEN,
        )
        self._stats_label.configure(
            text=f"共 {len(self._all)} 项  ·  已禁用 {disabled} 项  ·  注册表 {registry} / 启动文件夹 {folders}"
        )
        selected_iid = ""
        if self._selected:
            for iid in self._table.tree.get_children():
                values = self._table.tree.item(iid, "values")
                if values and values[0] == self._selected.name and values[4] == self._selected.command:
                    selected_iid = iid
                    break
        elif self._table.tree.get_children():
            selected_iid = self._table.tree.get_children()[0]
        if selected_iid:
            self._table.tree.selection_set(selected_iid)
            self._on_select()
        else:
            self._selected = None
            self._on_select()

    def _on_select(self) -> None:
        iid = self._table.selected_iid
        item = self._by_iid.get(iid) if iid else None
        if not item:
            self._selected = None
            self._detail_name.configure(text="选择一个启动项查看完整命令")
            self._detail_command.configure(text="注册表和启动文件夹中的自启动项目会在此汇总。")
            self._copy_btn.set_enabled(False)
            self._open_btn.set_enabled(False)
            self._toggle_btn.set_enabled(False)
            return
        self._selected = item
        self._detail_name.configure(
            text=f"{item.name}  ·  {'已启用' if item.enabled else '已禁用'}"
        )
        self._detail_command.configure(text=item.command)
        self._copy_btn.set_enabled(True)
        self._open_btn.set_enabled(bool(self._extract_path(item.command)))
        needs_admin = item.scope.startswith("所有用户") and not is_admin()
        self._toggle_btn.set_text(
            "需管理员" if needs_admin else ("禁用" if item.enabled else "启用")
        )
        self._toggle_btn.set_enabled(not needs_admin)
        self.set_status(
            "系统级启动项需要管理员权限"
            if needs_admin
            else f"已选择启动项：{item.name}"
        )

    def _toggle_selected(self) -> None:
        entry = self._selected
        if not entry:
            return
        target = not entry.enabled
        action = "启用" if target else "禁用"
        scope_note = (
            "该项目属于所有用户，可能需要管理员权限。"
            if entry.scope.startswith("所有用户")
            else "该项目属于当前用户。"
        )
        if not ask_confirm(
            self,
            f"{action}启动项",
            f"确定要{action}「{entry.name}」吗？",
            (
                f"{scope_note}\n"
                f"来源：{entry.source} / {entry.scope}\n"
                "修改在下次登录时生效，不会立即结束当前正在运行的程序。"
            ),
            confirm_text=action,
            danger=not target,
        ):
            return
        self._toggle_btn.set_enabled(False)
        self.set_status(f"正在{action}启动项…", "busy")

        def done(result) -> None:
            self._toggle_btn.set_enabled(True)
            self.refresh()
            if result.ok:
                show_notice(self, f"{action}成功", result.message, kind="info")
                self.set_status(result.message)
            else:
                show_notice(self, "修改失败", result.message, kind="warning")
                self.set_status("启动项修改失败", "error")

        def failed(exc: Exception) -> None:
            self._toggle_btn.set_enabled(True)
            self.set_status("启动项修改失败", "error")
            show_notice(self, "修改失败", str(exc), kind="error")

        self.app.runner.submit(
            lambda: self.services["startup"].set_enabled(entry, target),
            done,
            failed,
            name="startup-toggle",
        )

    def _extract_path(self, command: str) -> str:
        from ...utils import command_executable

        path = command_executable(command)
        return path if path and os.path.exists(path) else ""

    def _copy_command(self) -> None:
        if not self._selected:
            return
        self.clipboard_clear()
        self.clipboard_append(self._selected.command)
        self.set_status("启动命令已复制到剪贴板")

    def _open_location(self) -> None:
        if not self._selected:
            return
        path = self._extract_path(self._selected.command)
        if not path:
            show_notice(
                self,
                "无法定位文件",
                "该启动命令没有指向一个存在的文件，可能由系统组件或脚本启动。",
                self._selected.command,
                "warning",
            )
            return
        reveal_in_explorer(path)
