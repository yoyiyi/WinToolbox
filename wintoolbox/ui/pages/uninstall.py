"""应用卸载页：应用清单、启发式建议、调用原厂卸载程序。"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Any

from ...models import AppRecord, UninstallResult
from ...utils import (
    format_date,
    human_bytes,
    open_folder,
    truncate_end,
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


class UninstallPage(BasePage):
    page_id = "uninstall"

    def build(self) -> None:
        self._all: list[AppRecord] = []
        self._by_identity: dict[str, AppRecord] = {}
        self._by_name: dict[str, AppRecord] = {}
        self._selected_identity = ""
        self._filter = "全部应用"
        self._sort_key = "advice"
        self._sort_desc = True
        self._loading = False
        self._uninstalling = False
        self._quiet_var = tk.BooleanVar(
            value=bool(self.app.config_store.get("uninstall_use_quiet", False))
        )
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_banner()
        self._build_toolbar()
        self._build_meta()
        self._build_body()

    # ------------------------------------------------------------------
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
                "卸载建议根据安装信息、同类软件数量与常见捆绑特征推断，仅作参考，不代表实际使用情况。"
                "卸载会启动应用自带程序，请先保存工作。"
            ),
            bg=C.SURFACE_ALT,
            fg=C.MUTED,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=930,
        ).pack(side="left", fill="x", expand=True)

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=C.BG)
        bar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        bar.grid_columnconfigure(2, weight=1)
        self._search = SearchBox(
            bar,
            placeholder="搜索应用名、发布者或类别…",
            width=28,
            on_change=self._render,
        )
        self._search.grid(row=0, column=0, sticky="w")

        self._filter_var = tk.StringVar(value=self._filter)
        self._filter_box = ttk.Combobox(
            bar,
            textvariable=self._filter_var,
            values=("全部应用", "可考虑卸载", "按需保留", "系统 / 受保护", "可卸载"),
            state="readonly",
            width=12,
            font=FONTS["small"],
        )
        self._filter_box.grid(row=0, column=1, padx=(10, 0))
        self._filter_box.bind("<<ComboboxSelected>>", self._on_filter)

        self._scan_btn = FlatButton(
            bar,
            "重新扫描",
            command=self.refresh,
            variant="secondary",
            icon="\uE72C",
            compact=True,
        )
        self._scan_btn.grid(row=0, column=3, sticky="e")

    def _build_meta(self) -> None:
        meta = tk.Frame(self, bg=C.BG)
        meta.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        self._stats_label = tk.Label(
            meta,
            text="正在读取应用清单…",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
        )
        self._stats_label.pack(side="left")
        tk.Label(
            meta,
            text="·  卸载由应用自带程序执行",
            bg=C.BG,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
        ).pack(side="left", padx=(10, 0), pady=(2, 0))

    def _build_body(self) -> None:
        body = tk.Frame(self, bg=C.BG)
        body.grid(row=3, column=0, sticky="nsew")
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
                ("name", "应用", 245, "w"),
                ("publisher", "发布者", 155, "w"),
                ("size", "大小", 82, "e"),
                ("category", "类别", 80, "w"),
                ("advice", "建议", 100, "w"),
            ),
            height=14,
            on_sort=self._sort_by,
            on_select=self._on_select,
        )
        self._table.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        self._table.tree.tag_configure("recommended", foreground=C.RED)
        self._table.tree.tag_configure("optional", foreground=C.AMBER)
        self._table.tree.tag_configure("protected", foreground=C.MUTED)
        self._table.tree.tag_configure("normal", foreground=C.TEXT_SOFT)
        self._table.show_empty("正在读取已安装应用…")

        self._build_detail(detail_host)

    def _build_detail(self, parent: tk.Frame) -> None:
        card = Card(parent, padding=16)
        card.grid(row=0, column=0, sticky="nsew")
        header = tk.Frame(card.inner, bg=C.SURFACE)
        header.pack(fill="x")
        tk.Label(
            header,
            text="应用详情",
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["body_bold"],
        ).pack(side="left")
        self._advice_badge = Badge(header, "未选择", "neutral")
        self._advice_badge.pack(side="right")

        self._actions_holder = tk.Frame(card.inner, bg=C.SURFACE)
        self._actions_holder.pack(side="bottom", fill="x", pady=(8, 0))

        self._detail_scroll = ScrollableFrame(card.inner, bg=C.SURFACE)
        self._detail_scroll.pack(fill="both", expand=True, pady=(10, 0))
        body = self._detail_scroll.inner

        self._name_label = tk.Label(
            body,
            text="选择一个应用",
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["title"],
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._name_label.pack(fill="x")
        self._meta_label = tk.Label(
            body,
            text="从左侧列表选择应用，查看版本、大小与判断依据。",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._meta_label.pack(fill="x", pady=(4, 0))

        tk.Frame(body, bg=C.BORDER, height=1).pack(fill="x", pady=9)

        fields = tk.Frame(body, bg=C.SURFACE)
        fields.pack(fill="x")
        fields.grid_columnconfigure(1, weight=1)
        self._field_values: dict[str, tk.Label] = {}
        field_defs = (
            ("version", "版本 / 大小"),
            ("date", "安装日期"),
        )
        for index, (key, label) in enumerate(field_defs):
            tk.Label(
                fields,
                text=label,
                bg=C.SURFACE,
                fg=C.MUTED_DARK,
                font=FONTS["tiny"],
                anchor="w",
            ).grid(row=index, column=0, sticky="w", pady=2)
            value = tk.Label(
                fields,
                text="—",
                bg=C.SURFACE,
                fg=C.TEXT_SOFT,
                font=FONTS["small"],
                anchor="e",
                justify="right",
                wraplength=205,
            )
            value.grid(row=index, column=1, sticky="e", pady=2)
            self._field_values[key] = value

        self._location_label = tk.Label(
            body,
            text="—",
            bg=C.SURFACE_ALT,
            fg=C.MUTED,
            font=FONTS["mono_sm"],
            anchor="w",
            justify="left",
            wraplength=270,
            padx=8,
            pady=4,
        )
        self._location_label.pack(fill="x", pady=(6, 0))

        self._reason_label = tk.Label(
            body,
            text="—",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._reason_label.pack(fill="x", pady=(8, 0), before=self._location_label)

        self._hint_label = tk.Label(
            body,
            text="",
            bg=C.SURFACE,
            fg=C.AMBER,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=280,
        )
        self._hint_label.pack(fill="x", pady=(7, 0))

        actions = tk.Frame(self._actions_holder, bg=C.SURFACE)
        actions.pack(fill="x")
        self._quiet_check = ttk.Checkbutton(
            actions,
            text="使用静默卸载（如应用支持）",
            variable=self._quiet_var,
            command=self._on_quiet_toggle,
        )
        self._quiet_check.pack(anchor="w", pady=(0, 5))
        row = tk.Frame(actions, bg=C.SURFACE)
        row.pack(fill="x")
        self._uninstall_btn = FlatButton(
            row,
            "卸载此应用",
            command=self._uninstall_selected,
            variant="danger",
            compact=True,
        )
        self._uninstall_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self._open_btn = FlatButton(
            row,
            "打开位置",
            command=self._open_location,
            variant="secondary",
            compact=True,
        )
        self._open_btn.pack(side="left", padx=(3, 0))
        self._copy_btn = FlatButton(
            row,
            "复制命令",
            command=self._copy_command,
            variant="ghost",
            compact=True,
        )
        self._copy_btn.pack(side="left", padx=(3, 0))
        self._detail_scroll.bind_wheel_recursive()
        self._update_detail(None)

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if self.state.apps:
            self._on_apps(self.state.apps, "")
        else:
            self._table.show_empty("正在读取已安装应用…")
        self.app.load_apps_async(self._on_apps)

    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._scan_btn.set_enabled(False)
        self._stats_label.configure(text="正在重新扫描应用…")
        self.set_status("正在扫描已安装应用…", "busy")

        def done(apps: list[AppRecord], error: str) -> None:
            self._loading = False
            self._scan_btn.set_enabled(True)
            self._on_apps(apps, error)
            if not error:
                self.set_status(f"扫描完成：{len(apps)} 个应用")

        self.app.load_apps_async(done, force=True)

    def _on_apps(self, apps: list[AppRecord], error: str) -> None:
        if error:
            self._stats_label.configure(text="扫描应用失败")
            self._table.show_empty("扫描应用失败，请查看日志")
            self.set_status(f"扫描应用失败：{error}", "error")
            return
        self._all = apps
        self._by_identity = {item.identity: item for item in apps}
        self._by_name = {item.name: item for item in apps}
        self._render_stats()
        self._render()
        if self.app._current_page == "uninstall":
            self.set_status(f"已加载 {len(apps)} 个已安装应用")
        if self._selected_identity and self._selected_identity in self._by_identity:
            self._table.tree.selection_set(self._selected_identity)
            self._update_detail(self._by_identity.get(self._selected_identity))
        elif self._table.tree.get_children():
            self._table.select_first()
            self._on_select()

    def _render_stats(self) -> None:
        recommended = sum(1 for item in self._all if item.advice == "可考虑卸载")
        protected = sum(1 for item in self._all if item.protected)
        total_size = sum(item.size_bytes for item in self._all)
        self._stats_label.configure(
            text=(
                f"已安装 {len(self._all)} 个应用  ·  建议关注 {recommended} 个  ·  "
                f"受保护 {protected} 个  ·  已知占用 {human_bytes(total_size)}"
            )
        )

    def _on_filter(self, _event: tk.Event | None = None) -> None:
        self._filter = self._filter_var.get()
        self._render()

    def _sort_by(self, key: str) -> None:
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = key in {"advice", "size", "date"}
        self._render()

    def _filtered(self) -> list[AppRecord]:
        query = self._search.get().casefold()
        apps: list[AppRecord] = []
        for item in self._all:
            if self._filter == "可考虑卸载" and item.advice != "可考虑卸载":
                continue
            if self._filter == "按需保留" and item.advice != "按需保留":
                continue
            if self._filter == "系统 / 受保护" and not item.protected:
                continue
            if self._filter == "可卸载" and not item.can_uninstall:
                continue
            if query and not (
                query in item.name.casefold()
                or query in item.publisher.casefold()
                or query in item.category.casefold()
                or any(query in reason.casefold() for reason in item.reasons)
            ):
                continue
            apps.append(item)
        return apps

    def _sorted(self, apps: list[AppRecord]) -> list[AppRecord]:
        key = self._sort_key
        reverse = self._sort_desc
        if key == "name":
            apps.sort(key=lambda item: item.name.casefold(), reverse=reverse)
        elif key == "version":
            apps.sort(key=lambda item: item.version.casefold(), reverse=reverse)
        elif key == "publisher":
            apps.sort(key=lambda item: item.publisher.casefold(), reverse=reverse)
        elif key == "size":
            apps.sort(key=lambda item: item.size_bytes, reverse=reverse)
        elif key == "category":
            apps.sort(key=lambda item: item.category.casefold(), reverse=reverse)
        elif key == "advice":
            apps.sort(key=lambda item: (item.score, item.name.casefold()), reverse=reverse)
        return apps

    def _render(self) -> None:
        apps = self._sorted(self._filtered())
        rows = []
        for item in apps:
            if item.advice == "可考虑卸载":
                tag = "recommended"
            elif item.advice == "按需保留":
                tag = "optional"
            elif item.advice in {"建议保留", "无法卸载"}:
                tag = "protected"
            else:
                tag = "normal"
            rows.append(
                (
                    item.identity,
                    (
                        truncate_middle(item.name, 27),
                        truncate_end(item.publisher or "—", 14),
                        human_bytes(item.size_bytes, 0),
                        item.category,
                        item.advice,
                    ),
                    (tag,),
                )
            )
        if not self._all:
            empty = "正在读取已安装应用…" if self._loading else "没有读取到已安装应用"
        elif not apps:
            empty = "没有匹配的应用"
        else:
            empty = ""
        self._table.replace(rows, empty_text=empty)
        titles = {
            "name": "应用",
            "publisher": "发布者",
            "size": "大小",
            "category": "类别",
            "advice": "建议",
        }
        for key, title in titles.items():
            arrow = ""
            if key == self._sort_key:
                arrow = "  ↓" if self._sort_desc else "  ↑"
            self._table.tree.heading(key, text=title + arrow)
        if self._selected_identity and self._selected_identity in self._by_identity:
            if self._table.selected_iid != self._selected_identity:
                self._table.tree.selection_set(self._selected_identity)
        if self._table.selected_iid:
            self._selected_identity = self._table.selected_iid
            self._update_detail(self._by_identity.get(self._selected_identity))
        else:
            self._update_detail(None)

    def _on_select(self) -> None:
        identity = self._table.selected_iid
        if identity:
            self._selected_identity = identity
        self._update_detail(self._by_identity.get(identity) if identity else None)

    def _selected_app(self) -> AppRecord | None:
        identity = self._table.selected_iid
        return self._by_identity.get(identity) if identity else None

    def _update_detail(self, app: AppRecord | None) -> None:
        if app is None:
            self._name_label.configure(text="选择一个应用")
            self._meta_label.configure(
                text="从左侧列表选择应用，查看版本、大小与判断依据。"
            )
            self._advice_badge.configure(text="未选择", bg=C.SURFACE_ALT, fg=C.MUTED)
            for value in self._field_values.values():
                value.configure(text="—")
            self._location_label.configure(text="—")
            self._reason_label.configure(text="—")
            self._hint_label.configure(text="")
            self._quiet_check.configure(state="disabled")
            self._uninstall_btn.set_enabled(False)
            self._open_btn.set_enabled(False)
            self._copy_btn.set_enabled(False)
            self._detail_scroll.refresh_layout()
            return

        self._name_label.configure(text=app.name)
        self._meta_label.configure(
            text=(
                f"{app.publisher or '未知发布者'}  ·  {app.category}\n"
                f"{'所有用户' if app.hive == 'HKLM' else '当前用户'} · {app.architecture} 位"
            )
        )
        variant = {
            "可考虑卸载": "red",
            "按需保留": "amber",
            "建议保留": "green",
            "无法卸载": "neutral",
        }.get(app.advice, "accent")
        self._advice_badge.configure(
            text=app.advice,
            bg={
                "red": C.RED_DARK,
                "amber": C.AMBER_DARK,
                "green": C.GREEN_DARK,
                "neutral": C.SURFACE_ALT,
                "accent": C.ACCENT_DARK,
            }[variant],
            fg={
                "red": C.RED,
                "amber": C.AMBER,
                "green": C.GREEN,
                "neutral": C.MUTED,
                "accent": C.ACCENT,
            }[variant],
        )
        size_text = human_bytes(app.size_bytes, 0) if app.size_bytes else "大小未知"
        self._field_values["version"].configure(
            text=f"{app.version or '未知'}  ·  {size_text}"
        )
        self._field_values["date"].configure(text=format_date(app.install_date))
        location = app.install_location or app.display_icon or "未记录安装路径"
        self._location_label.configure(text=truncate_middle(location, 50))
        reasons = app.reasons or ["未发现明显冗余特征"]
        self._reason_label.configure(text=f"依据：{truncate_middle(reasons[0], 70)}")
        if app.protected:
            self._hint_label.configure(
                text="受保护：系统组件、运行库或安全软件，不建议从此处卸载。",
                fg=C.AMBER,
            )
        elif not app.can_uninstall:
            self._hint_label.configure(text="该应用未提供卸载命令。", fg=C.AMBER)
        else:
            self._hint_label.configure(text="")
        self._quiet_check.configure(
            state="normal" if app.quiet_uninstall_string else "disabled"
        )
        self._quiet_var.set(
            bool(self.app.config_store.get("uninstall_use_quiet", False))
            and bool(app.quiet_uninstall_string)
        )
        self._uninstall_btn.set_enabled(app.can_uninstall and not self._uninstalling)
        self._open_btn.set_enabled(bool(app.install_location and os.path.isdir(app.install_location)))
        self._copy_btn.set_enabled(bool(app.effective_uninstall_command))
        self._detail_scroll.refresh_layout()

    def _on_quiet_toggle(self) -> None:
        self.app.config_store.set("uninstall_use_quiet", bool(self._quiet_var.get()))

    # ------------------------------------------------------------------
    def _uninstall_selected(self) -> None:
        app = self._selected_app()
        if app is None or self._uninstalling:
            return
        if not app.can_uninstall:
            show_notice(self, "无法卸载", "该应用未提供可用的卸载入口。", kind="warning")
            return
        use_quiet = bool(self._quiet_var.get() and app.quiet_uninstall_string)
        command = app.quiet_uninstall_string if use_quiet else app.uninstall_string
        elevation_note = "需要通过 UAC 管理员授权" if app.hive == "HKLM" else "无需管理员权限"
        confirmed = ask_confirm(
            self,
            f"卸载 {app.name}？",
            "将启动该应用自带的卸载程序，工具箱无法撤销此操作。请先保存正在编辑的文件。",
            (
                f"版本: {app.version or '未知'}\n"
                f"发布者: {app.publisher or '未知'}\n"
                f"模式: {'静默卸载' if use_quiet else '交互式卸载'}\n"
                f"权限: {elevation_note}\n"
                f"命令: {truncate_middle(command, 260)}"
            ),
            confirm_text="开始卸载",
            danger=True,
        )
        if not confirmed:
            return
        self._uninstalling = True
        self._uninstall_btn.set_enabled(False)
        self._scan_btn.set_enabled(False)
        self.set_status(f"正在等待「{app.name}」卸载程序结束…", "busy")

        def done(result: UninstallResult) -> None:
            self._uninstalling = False
            self._scan_btn.set_enabled(True)
            self._uninstall_btn.set_enabled(app.can_uninstall)
            self._quiet_check.configure(
                state="normal" if app.quiet_uninstall_string else "disabled"
            )
            if result.ok:
                self.set_status(f"「{app.name}」卸载程序已结束，正在刷新应用清单…")
                self.after(900, self.refresh)
            else:
                self.set_status(f"「{app.name}」卸载未完成", "error")
                show_notice(
                    self,
                    "卸载未完成",
                    result.message or "卸载程序返回了非零退出码。",
                    (
                        f"退出码: {result.exit_code if result.exit_code is not None else '未知'}\n"
                        "常见原因：应用仍在运行、取消了 UAC 授权，或卸载器不支持当前参数。\n"
                        "请关闭该应用后重试；如果使用了静默卸载，可取消静默再试。"
                    ),
                    "warning",
                )

        self.app.runner.submit(
            lambda: self.services["apps"].launch_uninstall(app, use_quiet=use_quiet),
            done,
            self._uninstall_failed,
            name="uninstall",
        )

    def _uninstall_failed(self, exc: Exception) -> None:
        self._uninstalling = False
        self._scan_btn.set_enabled(True)
        app = self._selected_app()
        if app:
            self._uninstall_btn.set_enabled(app.can_uninstall)
        self.set_status(f"卸载失败：{exc}", "error")
        show_notice(self, "卸载失败", "调用卸载程序时发生错误。", str(exc), "error")

    def _open_location(self) -> None:
        app = self._selected_app()
        if app is None:
            return
        path = app.install_location or app.display_icon
        if not path or not os.path.exists(path):
            show_notice(
                self,
                "无法打开安装位置",
                "该应用没有记录安装目录，或目录已被移动。",
                path or "未记录路径",
                "warning",
            )
            return
        if os.path.isdir(path):
            open_folder(path)
        else:
            import subprocess

            subprocess.Popen(["explorer.exe", "/select,", path])

    def _copy_command(self) -> None:
        app = self._selected_app()
        if app is None or not app.effective_uninstall_command:
            return
        self.clipboard_clear()
        self.clipboard_append(app.effective_uninstall_command)
        self.set_status("卸载命令已复制到剪贴板")
