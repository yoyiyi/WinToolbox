"""应用更新页：winget 环境检测、更新列表和串行升级。"""

from __future__ import annotations

import threading
import time
import tkinter as tk
from datetime import datetime
from typing import Any

from ...models import UpdatePackage, UpdateScanResult, UpgradeResult, WingetInfo
from ...utils import format_datetime, open_store_app_installer, truncate_middle
from ..theme import C, FONTS
from ..widgets import (
    Badge,
    DataTable,
    FlatButton,
    LogView,
    SearchBox,
    ask_confirm,
    show_notice,
    section_title,
)
from .base import BasePage


class UpdatesPage(BasePage):
    page_id = "updates"

    def build(self) -> None:
        self._scanning = False
        self._upgrading = False
        self._updates: list[UpdatePackage] = []
        self._sort_key = "name"
        self._sort_desc = False
        self._cancel_event = threading.Event()
        self._log_visible = True
        self._last_error = ""
        self._intro_logged = False
        self._winget_logged = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self._build_banner()
        self._build_toolbar()
        self._build_meta()
        self._build_table()
        self._build_log()

    # ------------------------------------------------------------------
    def _build_banner(self) -> None:
        self._banner = tk.Frame(
            self,
            bg=C.AMBER_DARK,
            highlightbackground="#6B5420",
            highlightthickness=1,
        )
        inner = tk.Frame(self._banner, bg=C.AMBER_DARK)
        inner.pack(fill="x", padx=14, pady=11)
        self._banner_icon = tk.Label(
            inner,
            text="!",
            bg="#5A4315",
            fg=C.AMBER,
            font=FONTS["body_bold"],
            width=2,
        )
        self._banner_icon.pack(side="left", padx=(0, 10))
        text_box = tk.Frame(inner, bg=C.AMBER_DARK)
        text_box.pack(side="left", fill="x", expand=True)
        self._banner_title = tk.Label(
            text_box,
            text="",
            bg=C.AMBER_DARK,
            fg=C.AMBER,
            font=FONTS["small_bold"],
            anchor="w",
        )
        self._banner_title.pack(fill="x")
        self._banner_message = tk.Label(
            text_box,
            text="",
            bg=C.AMBER_DARK,
            fg="#D6C28A",
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=640,
        )
        self._banner_message.pack(fill="x", pady=(2, 0))
        self._banner_btn = FlatButton(
            inner,
            "处理",
            command=None,
            variant="ghost",
            compact=True,
        )
        self._banner_btn.pack(side="right", padx=(12, 0))
        self._banner.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self._banner.grid_remove()

    def _show_banner(self, title: str, message: str, action_text: str, command) -> None:
        self._banner_title.configure(text=title)
        self._banner_message.configure(text=message)
        self._banner_btn.set_text(action_text)
        self._banner_btn.set_command(command)
        self._banner.grid()

    def _hide_banner(self) -> None:
        self._banner.grid_remove()

    def _build_toolbar(self) -> None:
        toolbar = tk.Frame(self, bg=C.BG)
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        toolbar.grid_columnconfigure(2, weight=1)

        self._search = SearchBox(
            toolbar,
            placeholder="搜索应用名、ID 或来源…",
            width=27,
            on_change=self._render,
        )
        self._search.grid(row=0, column=0, sticky="w")
        self._env_badge = Badge(toolbar, "winget 检测中", "neutral")
        self._env_badge.grid(row=0, column=1, padx=(12, 0))

        actions = tk.Frame(toolbar, bg=C.BG)
        actions.grid(row=0, column=3, sticky="e")
        self._cancel_btn = FlatButton(
            actions,
            "停止后续升级",
            command=self._cancel_upgrade,
            variant="danger",
            compact=True,
        )
        self._all_btn = FlatButton(
            actions,
            "全部升级",
            command=lambda: self._upgrade(all_packages=True),
            variant="ghost",
        )
        self._all_btn.pack(side="right", padx=(6, 0))
        self._upgrade_btn = FlatButton(
            actions,
            "升级所选",
            command=lambda: self._upgrade(all_packages=False),
            variant="secondary",
            icon="\uE74A",
        )
        self._upgrade_btn.pack(side="right", padx=(6, 0))
        self._scan_btn = FlatButton(
            actions,
            "检查更新",
            command=lambda: self.start_scan(force=True),
            variant="accent",
            icon="\uE895",
        )
        self._scan_btn.pack(side="right")
        self._update_buttons()

    def _build_meta(self) -> None:
        meta = tk.Frame(self, bg=C.BG)
        meta.grid(row=2, column=0, sticky="ew", pady=(0, 7))
        self._summary_label = tk.Label(
            meta,
            text="尚未检查更新",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
        )
        self._summary_label.pack(side="left")
        tk.Label(
            meta,
            text="·  升级只调用官方 winget 源",
            bg=C.BG,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
        ).pack(side="left", padx=(10, 0), pady=(2, 0))

    def _build_table(self) -> None:
        self._table = DataTable(
            self,
            columns=(
                ("name", "应用", 300, "w"),
                ("current", "当前版本", 145, "w"),
                ("available", "可用版本", 210, "w"),
                ("source", "来源", 80, "w"),
                ("package_id", "包标识", 190, "w"),
            ),
            height=12,
            selectmode="extended",
            on_sort=self._sort_by,
            on_select=self._update_buttons,
        )
        self._table.grid(row=3, column=0, sticky="nsew")
        self._table.tree.tag_configure("store", foreground=C.CYAN)
        self._table.show_empty("正在检查更新…")

    def _build_log(self) -> None:
        wrapper = tk.Frame(self, bg=C.BG)
        wrapper.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        header = tk.Frame(wrapper, bg=C.BG)
        header.pack(fill="x", pady=(0, 6))
        section_title(header, "任务输出", "winget 的实时输出").pack(side="left")
        self._log_toggle = FlatButton(
            header,
            "收起",
            command=self._toggle_log,
            variant="ghost",
            compact=True,
        )
        self._log_toggle.pack(side="right")
        FlatButton(
            header,
            "清空",
            command=lambda: self._log.clear(),
            variant="ghost",
            compact=True,
        ).pack(side="right", padx=(0, 4))
        self._log = LogView(wrapper, height=7)
        self._log.pack(fill="x")

    def _toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        if self._log_visible:
            self._log.pack(fill="x")
            self._log_toggle.set_text("收起")
        else:
            self._log.pack_forget()
            self._log_toggle.set_text("展开")

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._render()
        if not self._intro_logged:
            self._log.append("应用更新由 winget 提供。升级过程在本机执行。", "muted")
            self._intro_logged = True
        self.app.load_winget_async(self._on_winget_info)
        if self.state.updates_at:
            self._apply_scan_result(
                self.state.winget_info,
                UpdateScanResult(
                    updates=self.state.updates,
                    error=self.state.updates_error,
                ),
                from_cache=True,
            )

    def refresh(self) -> None:
        self.start_scan(force=True)

    # ------------------------------------------------------------------
    def _on_winget_info(self, info: WingetInfo) -> None:
        self.app.state.winget_info = info
        self.app.state.winget_at = time.time()
        self.app._update_env_text()
        self._set_env_badge(info)
        if not info.available:
            self._show_banner(
                "未检测到可用的 winget",
                info.error + ("\n" + info.install_hint if info.install_hint else ""),
                "打开应用安装程序",
                open_store_app_installer,
            )
            self._summary_label.configure(text="更新组件不可用")
            self._table.show_empty("未检测到可用的 winget")
            if not self._winget_logged:
                self._log.append(f"环境检查失败：{info.error}", "error")
                self._winget_logged = True
            self.set_status("winget 不可用，请安装或修复应用安装程序", "error")
            self._update_buttons()
            return
        self._hide_banner()
        if not self._winget_logged:
            self._log.append(f"winget 可用：{info.version}", "success")
            self._winget_logged = True
        self.set_status(f"winget {info.version} 已就绪")
        if not self.state.updates_at and not self._scanning:
            self.start_scan(force=False)

    def _set_env_badge(self, info: WingetInfo | None) -> None:
        if info is None:
            self._env_badge.configure(text="winget 检测中", bg=C.SURFACE_ALT, fg=C.MUTED)
        elif info.available:
            self._env_badge.configure(
                text=f"winget {info.version}", bg=C.GREEN_DARK, fg=C.GREEN
            )
        else:
            self._env_badge.configure(
                text="winget 不可用", bg=C.RED_DARK, fg=C.RED
            )

    # ------------------------------------------------------------------
    def start_scan(self, force: bool = False) -> None:
        if self._scanning or self._upgrading:
            return
        self._scanning = True
        self._last_error = ""
        self._update_buttons()
        self._summary_label.configure(text="正在查询 winget…")
        self._table.replace([], empty_text="正在检查可用更新…")
        self._log.append("")
        self._log.append("开始检查应用更新…", "command")
        self.set_status("正在检查应用更新…", "busy")

        def work() -> tuple[WingetInfo, UpdateScanResult]:
            info = self.services["winget"].probe(force=force)
            if not info.available:
                return info, UpdateScanResult(
                    updates=[],
                    error=info.error,
                    warning=info.install_hint,
                    checked_at=datetime.now(),
                )
            return info, self.services["winget"].scan_updates()

        self.app.runner.submit(work, self._scan_done, self._scan_failed, name="winget-scan")

    def _scan_done(self, payload: tuple[WingetInfo, UpdateScanResult]) -> None:
        self._scanning = False
        info, result = payload
        self.app.state.winget_info = info
        self.app.state.winget_at = time.time()
        self.app._update_env_text()
        self._set_env_badge(info)
        self._apply_scan_result(info, result)
        self._update_buttons()

    def _apply_scan_result(
        self,
        info: WingetInfo | None,
        result: UpdateScanResult,
        from_cache: bool = False,
    ) -> None:
        self._last_error = result.error
        if result.error:
            self._summary_label.configure(text="检查失败")
            self._table.show_empty("检查更新失败")
            if info is not None and not info.available:
                self._show_banner(
                    "未检测到可用的 winget",
                    (info.error + "\n" + info.install_hint).strip(),
                    "打开应用安装程序",
                    open_store_app_installer,
                )
            else:
                self._show_banner(
                    "检查更新失败",
                    truncate_middle(result.error, 420),
                    "重试",
                    lambda: self.start_scan(force=True),
                )
            self._log.append(f"检查失败：{result.error}", "error")
            self.set_status("检查更新失败", "error")
            return

        if not from_cache:
            self.app.state.updates_at = time.time()
        self.app.state.updates = list(result.updates)
        self.app.state.updates_error = ""
        self._updates = list(result.updates)
        self._hide_banner()
        checked_at = (
            datetime.fromtimestamp(self.app.state.updates_at)
            if self.app.state.updates_at
            else datetime.now()
        )
        when = format_datetime(checked_at)
        if self._updates:
            self._summary_label.configure(
                text=f"{len(self._updates)} 个应用可更新 · 检查于 {when}"
            )
            self._log.append(f"发现 {len(self._updates)} 个可用更新。", "success")
        else:
            self._summary_label.configure(text=f"所有应用均为最新 · 检查于 {when}")
            self._log.append("未发现可用更新。", "success")
        self._render()
        if not from_cache:
            self.set_status(
                f"更新检查完成：{len(self._updates)} 个可用更新"
            )
            self._log.append("检查完成。", "muted")

    def _scan_failed(self, exc: Exception) -> None:
        self._scanning = False
        self._summary_label.configure(text="检查失败")
        self._show_banner(
            "检查更新时发生错误",
            str(exc),
            "重试",
            lambda: self.start_scan(force=True),
        )
        self._log.append(f"错误：{exc}", "error")
        self.set_status("检查更新失败", "error")
        self._update_buttons()

    # ------------------------------------------------------------------
    def _sort_by(self, key: str) -> None:
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = False
        self._render()

    def _sorted_updates(self) -> list[UpdatePackage]:
        updates = list(self._updates)
        reverse = self._sort_desc
        if self._sort_key == "name":
            updates.sort(key=lambda item: item.name.casefold(), reverse=reverse)
        elif self._sort_key == "available":
            updates.sort(key=lambda item: item.available_version.casefold(), reverse=reverse)
        elif self._sort_key == "current":
            updates.sort(key=lambda item: item.current_version.casefold(), reverse=reverse)
        elif self._sort_key == "source":
            updates.sort(key=lambda item: item.source.casefold(), reverse=reverse)
        elif self._sort_key == "package_id":
            updates.sort(key=lambda item: item.package_id.casefold(), reverse=reverse)
        return updates

    def _render(self) -> None:
        query = self._search.get().casefold() if hasattr(self, "_search") else ""
        updates = self._sorted_updates()
        if query:
            updates = [
                item
                for item in updates
                if query in item.name.casefold()
                or query in item.package_id.casefold()
                or query in item.source.casefold()
            ]
        rows = []
        for item in updates:
            tags = ("store",) if item.source.casefold() == "msstore" else ()
            rows.append(
                (
                    item.identity,
                    (
                        item.name,
                        item.current_version,
                        item.available_version,
                        item.source,
                        item.package_id,
                    ),
                    tags,
                )
            )
        if not self._updates:
            empty = "未发现可用更新，所有应用都是最新版本" if self.state.updates_at else "尚未检查更新"
        elif not updates:
            empty = "没有匹配的更新"
        else:
            empty = ""
        self._table.replace(rows, empty_text=empty)
        titles = {
            "name": "应用",
            "current": "当前版本",
            "available": "可用版本",
            "source": "来源",
            "package_id": "包标识",
        }
        for key, title in titles.items():
            arrow = ""
            if key == self._sort_key:
                arrow = "  ↓" if self._sort_desc else "  ↑"
            self._table.tree.heading(key, text=title + arrow)
        self._update_buttons()

    def _selected_packages(self) -> list[UpdatePackage]:
        selected = set(self._table.tree.selection())
        return [item for item in self._updates if item.identity in selected]

    def _update_buttons(self) -> None:
        busy = self._scanning or self._upgrading
        selected_count = len(self._table.tree.selection()) if hasattr(self, "_table") else 0
        if hasattr(self, "_scan_btn"):
            self._scan_btn.set_enabled(not busy)
            self._upgrade_btn.set_enabled(not busy and selected_count > 0)
            self._all_btn.set_enabled(not busy and bool(self._updates))
        if hasattr(self, "_cancel_btn"):
            if self._upgrading:
                if not self._cancel_btn.winfo_ismapped():
                    self._cancel_btn.pack(side="right", padx=(6, 0))
            else:
                self._cancel_btn.pack_forget()

    # ------------------------------------------------------------------
    def _upgrade(self, all_packages: bool = False) -> None:
        if self._scanning or self._upgrading:
            return
        packages = self._updates if all_packages else self._selected_packages()
        if not packages:
            show_notice(self, "没有选择应用", "请先在列表中选中要升级的应用。", kind="info")
            return
        detail_lines = [
            f"{item.name}  {item.current_version} → {item.available_version}"
            for item in packages[:12]
        ]
        if len(packages) > 12:
            detail_lines.append(f"…以及另外 {len(packages) - 12} 个应用")
        confirmed = ask_confirm(
            self,
            f"升级 {len(packages)} 个应用",
            "将调用 winget 依次执行静默升级。过程中可能出现 UAC 授权，请保持窗口开启。",
            "\n".join(detail_lines),
            confirm_text="开始升级",
            danger=False,
        )
        if not confirmed:
            return
        self._run_upgrade(packages)

    def _run_upgrade(self, packages: list[UpdatePackage]) -> None:
        self._upgrading = True
        self._cancel_event = threading.Event()
        self._cancel_btn.set_enabled(True)
        self._update_buttons()
        self._log.append("")
        self._log.append(f"开始升级 {len(packages)} 个应用…", "command")
        self.set_status("正在升级应用，请勿关闭窗口…", "busy")

        def emit(line: str, kind: str = "normal") -> None:
            self.app.runner.post(lambda: self._log.append(line, kind))

        def work() -> tuple[list[UpgradeResult], bool]:
            results: list[UpgradeResult] = []
            for index, package in enumerate(packages, start=1):
                if self._cancel_event.is_set():
                    break
                emit(f"")
                emit(f"[{index}/{len(packages)}] {package.name}  {package.current_version} → {package.available_version}", "command")
                result = self.services["winget"].upgrade_package(
                    package,
                    on_output=lambda line: emit(line),
                    cancel_event=self._cancel_event,
                )
                results.append(result)
                if result.success:
                    emit(f"✓ {package.name} 升级完成", "success")
                else:
                    emit(f"✗ {package.name} 升级失败：{result.error}", "error")
            return results, self._cancel_event.is_set()

        self.app.runner.submit(work, self._upgrade_done, self._upgrade_failed, name="winget-upgrade")

    def _cancel_upgrade(self) -> None:
        if not self._upgrading:
            return
        self._cancel_event.set()
        self._cancel_btn.set_enabled(False)
        self._log.append("已请求停止：当前安装完成后不再继续。", "muted")
        self.set_status("将在当前应用安装完成后停止…", "busy")

    def _upgrade_done(self, payload: tuple[list[UpgradeResult], bool]) -> None:
        results, cancelled = payload
        self._upgrading = False
        self._cancel_event.set()
        self._update_buttons()
        succeeded = sum(1 for item in results if item.success)
        failed = len(results) - succeeded
        self._log.append("")
        self._log.append(
            f"升级任务结束：成功 {succeeded}，失败 {failed}"
            + ("，已按请求停止。" if cancelled else "。"),
            "success" if failed == 0 else "error",
        )
        self.set_status(
            f"升级结束：成功 {succeeded}，失败 {failed}",
            "normal" if failed == 0 else "error",
        )
        if failed:
            failures = "\n".join(
                f"{item.package_id}: {item.error}" for item in results if not item.success
            )
            self._show_banner(
                "部分应用升级失败",
                "请查看下方任务输出，或尝试以管理员身份运行后重试。",
                "重试检查",
                lambda: self.start_scan(force=True),
            )
            self._log.append(failures, "error")
        self.after(800, lambda: self.start_scan(force=True))

    def _upgrade_failed(self, exc: Exception) -> None:
        self._upgrading = False
        self._update_buttons()
        self._log.append(f"升级任务异常：{exc}", "error")
        self._show_banner(
            "升级任务异常",
            str(exc),
            "重试检查",
            lambda: self.start_scan(force=True),
        )
        self.set_status("升级任务异常", "error")
