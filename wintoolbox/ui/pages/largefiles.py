"""大文件页：按磁盘扫描大文件，支持筛选、定位与移入回收站。"""

from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from tkinter import ttk

from ...models import DriveInfo, LargeFile, LargeFileScanResult, RecycleResult
from ...utils import (
    format_datetime,
    human_bytes,
    human_duration,
    reveal_in_explorer,
    truncate_end,
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

THRESHOLDS = {
    "≥ 100 MB": 100 * 1024**2,
    "≥ 500 MB": 500 * 1024**2,
    "≥ 1 GB": 1024**3,
    "≥ 5 GB": 5 * 1024**3,
}


class LargeFilesPage(BasePage):
    page_id = "largefiles"

    def build(self) -> None:
        self._drives: list[DriveInfo] = []
        self._drive_by_display: dict[str, DriveInfo] = {}
        self._selected_drive: DriveInfo | None = None
        self._results: list[LargeFile] = []
        self._by_path: dict[str, LargeFile] = {}
        self._scanning = False
        self._recycling = False
        self._scanned_once = False
        self._cancel_event = threading.Event()
        self._sort_key = "size"
        self._sort_desc = True
        self._scan_result: LargeFileScanResult | None = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_toolbar()
        self._build_meta()
        self._build_table()
        self._build_detail()

    # ------------------------------------------------------------------
    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=C.BG)
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        bar.grid_columnconfigure(4, weight=1)

        tk.Label(
            bar,
            text="磁盘",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
        ).grid(row=0, column=0, padx=(0, 6))
        self._drive_var = tk.StringVar()
        self._drive_box = ttk.Combobox(
            bar,
            textvariable=self._drive_var,
            state="readonly",
            width=27,
            font=FONTS["small"],
        )
        self._drive_box.grid(row=0, column=1, sticky="w")
        self._drive_box.bind("<<ComboboxSelected>>", self._on_drive_change)

        tk.Label(
            bar,
            text="阈值",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
        ).grid(row=0, column=2, padx=(12, 6))
        self._threshold_var = tk.StringVar(value="≥ 500 MB")
        self._threshold_box = ttk.Combobox(
            bar,
            textvariable=self._threshold_var,
            values=tuple(THRESHOLDS),
            state="readonly",
            width=10,
            font=FONTS["small"],
        )
        self._threshold_box.grid(row=0, column=3, sticky="w")
        self._threshold_box.bind("<<ComboboxSelected>>", self._on_threshold_change)

        actions = tk.Frame(bar, bg=C.BG)
        actions.grid(row=0, column=5, sticky="e")
        self._refresh_btn = FlatButton(
            actions,
            "刷新",
            command=self.refresh,
            variant="ghost",
            icon="\uE72C",
            compact=True,
        )
        self._refresh_btn.pack(side="right", padx=(6, 0))
        self._stop_btn = FlatButton(
            actions,
            "停止",
            command=self._stop_scan,
            variant="danger",
            compact=True,
        )
        self._scan_btn = FlatButton(
            actions,
            "开始扫描",
            command=self._start_scan,
            variant="accent",
            icon="\uE895",
        )
        self._scan_btn.pack(side="right")

    def _build_meta(self) -> None:
        meta = tk.Frame(self, bg=C.BG)
        meta.grid(row=1, column=0, sticky="ew", pady=(0, 7))
        meta.grid_columnconfigure(0, weight=1)

        self._summary = tk.Label(
            meta,
            text="正在读取磁盘…",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
        )
        self._summary.grid(row=0, column=0, sticky="w")

        self._skip_system_var = tk.BooleanVar(value=True)
        self._skip_check = tk.Checkbutton(
            meta,
            text="跳过系统目录",
            variable=self._skip_system_var,
            command=self._on_threshold_change,
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
        self._skip_check.grid(row=0, column=1, padx=(12, 0))

        self._progress = ttk.Progressbar(
            meta,
            mode="indeterminate",
            length=90,
            style="Cyan.Horizontal.TProgressbar",
        )
        self._search = SearchBox(
            meta,
            placeholder="筛选文件名或路径…",
            width=22,
            on_change=self._render,
        )
        self._search.grid(row=0, column=3, sticky="e", padx=(12, 0))

    def _build_table(self) -> None:
        self._table = DataTable(
            self,
            columns=(
                ("name", "文件", 460, "w"),
                ("size", "大小", 90, "e"),
                ("modified", "修改日期", 110, "w"),
                ("type", "类型", 110, "w"),
            ),
            height=12,
            selectmode="extended",
            on_sort=self._sort_by,
            on_select=self._on_select,
            on_double=self._open_location,
        )
        self._table.grid(row=2, column=0, sticky="nsew")
        self._table.tree.tag_configure("protected", foreground=C.RED)
        self._table.tree.tag_configure("large", foreground=C.AMBER)
        self._table.show_empty("正在读取磁盘…")

    def _build_detail(self) -> None:
        card = Card(self, padding=12)
        card.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        card.inner.grid_columnconfigure(0, weight=1)

        text_box = tk.Frame(card.inner, bg=C.SURFACE)
        text_box.grid(row=0, column=0, sticky="nsew")
        top = tk.Frame(text_box, bg=C.SURFACE)
        top.pack(fill="x")
        self._detail_name = tk.Label(
            top,
            text="选择一个文件查看详情",
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            font=FONTS["body_bold"],
            anchor="w",
        )
        self._detail_name.pack(side="left")
        self._detail_badge = Badge(top, "未选择", "neutral")
        self._detail_badge.pack(side="left", padx=(8, 0))

        self._detail_path = tk.Label(
            text_box,
            text="扫描结果会显示完整路径、大小和修改时间。",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["mono_sm"],
            anchor="w",
            justify="left",
            wraplength=740,
        )
        self._detail_path.pack(fill="x", pady=(5, 0))
        self._detail_meta = tk.Label(
            text_box,
            text="",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=740,
        )
        self._detail_meta.pack(fill="x", pady=(3, 0))

        actions = tk.Frame(card.inner, bg=C.SURFACE)
        actions.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self._open_btn = FlatButton(
            actions,
            "打开位置",
            command=self._open_location,
            variant="secondary",
            compact=True,
        )
        self._open_btn.pack(fill="x")
        self._copy_btn = FlatButton(
            actions,
            "复制路径",
            command=self._copy_path,
            variant="ghost",
            compact=True,
        )
        self._copy_btn.pack(fill="x", pady=(4, 0))
        self._recycle_btn = FlatButton(
            actions,
            "移入回收站",
            command=self._recycle_selected,
            variant="danger",
            compact=True,
        )
        self._recycle_btn.pack(fill="x", pady=(4, 0))
        self._detail_name.configure(text="选择一个文件查看详情")
        self._update_detail([])

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        self._load_drives()
        if self._scanning:
            self._scan_btn.set_enabled(False)
            self._stop_btn.pack(side="right", padx=(6, 0))
            if not self._progress.winfo_ismapped():
                self._progress.grid(row=0, column=2, padx=(10, 0))
                self._progress.start(10)
        self._render()
        if not self._scanning and self._selected_drive and not self._scanned_once:
            self.set_status(f"已选择磁盘 {self._selected_drive.letter}，选择阈值后开始扫描")

    def refresh(self) -> None:
        if self._scanning:
            self.set_status("扫描仍在进行中，请先停止或等待完成", "busy")
            return
        self._load_drives()
        self._render()

    # ------------------------------------------------------------------
    def _load_drives(self) -> None:
        try:
            drives = self.services["largefiles"].list_drives()
        except Exception as exc:
            show_notice(self, "读取磁盘失败", "无法枚举当前磁盘。", str(exc), "error")
            return
        self._drives = drives
        self._drive_by_display = {
            self._drive_label(drive): drive for drive in drives
        }
        values = tuple(self._drive_by_display)
        self._drive_box.configure(values=values)
        if not drives:
            self._scan_btn.set_enabled(False)
            self._summary.configure(text="没有检测到可用磁盘")
            self._table.show_empty("没有检测到可用磁盘")
            return
        current_root = self._selected_drive.root if self._selected_drive else ""
        target = next((drive for drive in drives if drive.root == current_root), None)
        if target is None:
            target = drives[0]
            if current_root and target.root != current_root:
                self._results = []
                self._by_path = {}
                self._scanned_once = False
                self._scan_result = None
        self._selected_drive = target
        self._drive_var.set(self._drive_label(target))
        if not self._scanning:
            self._scan_btn.set_enabled(True)
        if not self._scanning and not self._scanned_once:
            self._update_idle_summary()

    def _drive_label(self, drive: DriveInfo) -> str:
        if drive.label:
            label = truncate_end(drive.label, 12)
        elif drive.is_system:
            label = "系统"
        else:
            label = drive.drive_type
        return f"{drive.letter}  {label} · 可用 {human_bytes(drive.free)}"

    def _selected_threshold(self) -> int:
        return THRESHOLDS.get(self._threshold_var.get(), 500 * 1024**2)

    def _on_drive_change(self, _event: tk.Event | None = None) -> None:
        if self._scanning:
            return
        drive = self._drive_by_display.get(self._drive_var.get())
        if drive is None:
            return
        self._selected_drive = drive
        self._results = []
        self._by_path = {}
        self._scanned_once = False
        self._scan_result = None
        self._update_idle_summary()
        self._render()
        self._update_detail([])
        self.set_status(f"已选择磁盘 {drive.letter}，点击“开始扫描”")

    def _on_threshold_change(self, _event: tk.Event | None = None) -> None:
        if self._scanning:
            return
        if self._results:
            self._results = []
            self._by_path = {}
            self._scanned_once = False
            self._scan_result = None
            self._render()
            self._update_detail([])
            self.set_status("扫描条件已更改，请重新扫描")
        self._update_idle_summary()

    def _update_idle_summary(self) -> None:
        drive = self._selected_drive
        if drive is None:
            self._summary.configure(text="没有检测到可用磁盘")
            return
        threshold = self._selected_threshold()
        self._summary.configure(
            text=(
                f"{drive.letter} 总 {human_bytes(drive.total)} · 可用 {human_bytes(drive.free)} · "
                f"阈值 {human_bytes(threshold, 0)}"
            )
        )

    # ------------------------------------------------------------------
    def _start_scan(self) -> None:
        drive = self._selected_drive
        if drive is None or self._scanning:
            return
        if not os.path.isdir(drive.root):
            show_notice(self, "磁盘不可用", "当前选择的磁盘无法访问。", drive.root, "warning")
            self._load_drives()
            return
        if drive.drive_type == "网络驱动器":
            confirmed = ask_confirm(
                self,
                "扫描网络驱动器？",
                "网络驱动器扫描速度可能较慢，并且会占用网络带宽。",
                drive.root,
                confirm_text="继续扫描",
                danger=False,
            )
            if not confirmed:
                return

        self._scanning = True
        self._scanned_once = False
        self._results = []
        self._by_path = {}
        self._scan_result = None
        self._cancel_event = threading.Event()
        threshold = self._selected_threshold()
        include_system = not self._skip_system_var.get()
        self._scan_btn.set_enabled(False)
        self._refresh_btn.set_enabled(False)
        self._drive_box.configure(state="disabled")
        self._threshold_box.configure(state="disabled")
        self._skip_check.configure(state="disabled")
        self._stop_btn.pack(side="right", padx=(6, 0))
        self._progress.grid(row=0, column=2, padx=(10, 0))
        self._progress.start(10)
        self._summary.configure(
            text=f"正在扫描 {drive.letter} · 阈值 {human_bytes(threshold, 0)} · 准备中…"
        )
        self._table.replace([], empty_text="正在扫描大文件…")
        self._update_detail([])
        self.set_status(f"正在扫描 {drive.letter}…", "busy")

        def progress(scanned: int, dirs: int, found: int, current: str) -> None:
            def update() -> None:
                if not self._scanning:
                    return
                elapsed = time.monotonic() - started
                self._summary.configure(
                    text=(
                        f"扫描中 · 已检查 {scanned:,} 个文件 · "
                        f"发现 {found} 个 · {human_duration(elapsed)}"
                    )
                )
                if self.app._current_page == "largefiles":
                    self.set_status(f"扫描中：{truncate_middle(current, 88)}", "busy")

            self.app.runner.post(update)

        started = time.monotonic()
        self.app.runner.submit(
            lambda: self.services["largefiles"].scan(
                drive.root,
                threshold,
                include_system=include_system,
                progress=progress,
                cancel_event=self._cancel_event,
            ),
            self._scan_done,
            self._scan_failed,
            name="large-files",
        )

    def _stop_scan(self) -> None:
        if not self._scanning:
            return
        self._cancel_event.set()
        self._stop_btn.set_enabled(False)
        self.set_status("正在停止扫描…", "busy")
        self._summary.configure(text="正在停止扫描，已找到的结果会保留…")

    def _scan_done(self, result: LargeFileScanResult) -> None:
        self._scanning = False
        self._scanned_once = True
        self._scan_result = result
        self._results = result.files
        self._by_path = {item.path: item for item in result.files}
        self._finish_scan_ui()
        self._render()
        self._update_detail([])
        if result.files:
            self._table.select_first()
            self._on_select()
        bits = [
            f"找到 {len(result.files)} 个",
            f"合计 {human_bytes(result.total_size)}",
            f"检查 {result.scanned_files:,} 个文件",
            f"用时 {human_duration(result.elapsed)}",
        ]
        if result.cancelled:
            bits.append("已停止，结果不完整")
        if result.truncated:
            bits.append("达到 5000 条上限")
        elif result.inaccessible:
            bits.append(f"跳过 {result.inaccessible} 个无权限项")
        self._summary.configure(text=" · ".join(bits))
        if self.app._current_page == "largefiles":
            self.set_status(
                "扫描完成" if not result.cancelled else "扫描已停止",
                "normal" if not result.cancelled else "info",
            )

    def _scan_failed(self, exc: Exception) -> None:
        self._scanning = False
        self._finish_scan_ui()
        self._summary.configure(text="扫描失败")
        self.set_status(f"大文件扫描失败：{exc}", "error")
        show_notice(self, "扫描失败", "遍历磁盘时发生错误。", str(exc), "error")

    def _finish_scan_ui(self) -> None:
        self._stop_btn.pack_forget()
        self._progress.stop()
        self._progress.grid_remove()
        self._scan_btn.set_enabled(True)
        self._refresh_btn.set_enabled(True)
        self._drive_box.configure(state="readonly")
        self._threshold_box.configure(state="readonly")
        self._skip_check.configure(state="normal")
        self._stop_btn.set_enabled(True)
        self._render()
        self._update_detail(self._selected_files())

    # ------------------------------------------------------------------
    def _sort_by(self, key: str) -> None:
        if key == self._sort_key:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_key = key
            self._sort_desc = key not in {"name", "modified", "type"}
        self._render()

    def _filtered(self) -> list[LargeFile]:
        query = self._search.get().casefold()
        files = []
        for item in self._results:
            if query and not (
                query in item.name.casefold()
                or query in item.path.casefold()
                or query in item.file_type.casefold()
            ):
                continue
            files.append(item)
        if self._sort_key == "size":
            files.sort(key=lambda item: item.size, reverse=self._sort_desc)
        elif self._sort_key == "name":
            files.sort(key=lambda item: item.name.casefold(), reverse=self._sort_desc)
        elif self._sort_key == "modified":
            files.sort(
                key=lambda item: item.modified.timestamp() if item.modified else 0,
                reverse=self._sort_desc,
            )
        elif self._sort_key == "type":
            files.sort(key=lambda item: item.file_type.casefold(), reverse=self._sort_desc)
        return files

    def _render(self) -> None:
        files = self._filtered()
        rows = []
        for item in files:
            tags = ("protected",) if item.protected else ("large",) if item.size >= 1024**3 else ()
            rows.append(
                (
                    item.path,
                    (
                        truncate_middle(item.name, 62),
                        human_bytes(item.size),
                        item.modified.strftime("%Y-%m-%d") if item.modified else "—",
                        item.file_type,
                    ),
                    tags,
                )
            )
        if self._scanning:
            empty = "正在扫描大文件…"
        elif not self._scanned_once:
            empty = "选择磁盘并开始扫描"
        elif not self._results:
            empty = "没有找到超过当前阈值的大文件"
        elif not files:
            empty = "没有匹配的文件"
        else:
            empty = ""
        self._table.replace(rows, empty_text=empty)
        titles = {
            "name": "文件",
            "size": "大小",
            "modified": "修改日期",
            "type": "类型",
        }
        for key, title in titles.items():
            arrow = ""
            if key == self._sort_key:
                arrow = "  ↓" if self._sort_desc else "  ↑"
            self._table.tree.heading(key, text=title + arrow)
        if not self._table.selected_iid and self._table.tree.get_children():
            self._table.select_first()
            self._on_select()

    def _selected_files(self) -> list[LargeFile]:
        return [
            self._by_path[iid]
            for iid in self._table.tree.selection()
            if iid in self._by_path
        ]

    def _on_select(self) -> None:
        self._update_detail(self._selected_files())

    def _update_detail(self, files: list[LargeFile]) -> None:
        if not files:
            self._detail_name.configure(text="选择一个文件查看详情")
            self._detail_path.configure(
                text="扫描结果会显示完整路径、大小和修改时间。"
            )
            self._detail_meta.configure(text="")
            self._detail_badge.configure(text="未选择", bg=C.SURFACE_ALT, fg=C.MUTED)
            self._open_btn.set_enabled(False)
            self._copy_btn.set_enabled(False)
            self._recycle_btn.set_enabled(False)
            return

        protected = any(item.protected for item in files)
        if len(files) == 1:
            item = files[0]
            self._detail_name.configure(text=truncate_middle(item.name, 80))
            self._detail_path.configure(text=item.path)
            self._detail_meta.configure(
                text=(
                    f"{human_bytes(item.size)} · {format_datetime(item.modified)} · "
                    f"{item.file_type}"
                )
            )
            self._detail_badge.configure(
                text="系统/受保护" if item.protected else "大文件",
                bg=C.RED_DARK if item.protected else C.AMBER_DARK,
                fg=C.RED if item.protected else C.AMBER,
            )
            self._open_btn.set_enabled(os.path.exists(item.path))
            self._copy_btn.set_enabled(True)
        else:
            total = sum(item.size for item in files)
            selected_protected = sum(1 for item in files if item.protected)
            self._detail_name.configure(text=f"已选择 {len(files)} 个文件")
            self._detail_path.configure(text="打开位置和复制路径仅支持单选。")
            self._detail_meta.configure(
                text=(
                    f"合计 {human_bytes(total)}"
                    + (
                        f" · 其中 {selected_protected} 个系统/受保护文件"
                        if selected_protected
                        else ""
                    )
                )
            )
            self._detail_badge.configure(
                text="多选" if not selected_protected else "包含受保护项",
                bg=C.ACCENT_DARK if not selected_protected else C.RED_DARK,
                fg=C.ACCENT if not selected_protected else C.RED,
            )
            self._open_btn.set_enabled(False)
            self._copy_btn.set_enabled(False)
        self._recycle_btn.set_enabled(not protected and not self._scanning and not self._recycling)

    def _open_location(self) -> None:
        files = self._selected_files()
        if len(files) != 1:
            return
        if not reveal_in_explorer(files[0].path):
            show_notice(
                self,
                "无法定位文件",
                "文件可能已被移动或删除。",
                files[0].path,
                "warning",
            )

    def _copy_path(self) -> None:
        files = self._selected_files()
        if len(files) != 1:
            return
        self.clipboard_clear()
        self.clipboard_append(files[0].path)
        self.set_status("文件路径已复制到剪贴板")

    def _recycle_selected(self) -> None:
        if self._scanning or self._recycling:
            return
        files = self._selected_files()
        if not files:
            return
        protected = [item for item in files if item.protected]
        if protected:
            show_notice(
                self,
                "选中的文件受保护",
                "系统目录或系统文件不能在此移入回收站，请取消选择后重试。",
                "\n".join(item.path for item in protected[:6]),
                "warning",
            )
            return
        total = sum(item.size for item in files)
        detail = "\n".join(
            f"{truncate_middle(item.name, 70)}  ({human_bytes(item.size)})"
            for item in files[:10]
        )
        if len(files) > 10:
            detail += f"\n…以及另外 {len(files) - 10} 个文件"
        confirmed = ask_confirm(
            self,
            f"将 {len(files)} 个文件移入回收站？",
            "文件会进入回收站，通常可以恢复。如果该磁盘的回收站不可用，Windows 会再次询问是否永久删除。",
            f"合计大小: {human_bytes(total)}\n{detail}",
            confirm_text="移入回收站",
            danger=True,
        )
        if not confirmed:
            return
        self._recycling = True
        self._recycle_btn.set_enabled(False)
        self.set_status(f"正在将 {len(files)} 个文件移入回收站…", "busy")

        def done(result: RecycleResult) -> None:
            self._recycling = False
            recycled = set(result.recycled)
            if recycled:
                self._results = [item for item in self._results if item.path not in recycled]
                self._by_path = {item.path: item for item in self._results}
                self._render()
                self._update_detail([])
                remaining_size = sum(item.size for item in self._results)
                self._summary.configure(
                    text=(
                        f"找到 {len(self._results)} 个 · 合计 {human_bytes(remaining_size)}"
                        f" · 已移入回收站 {len(result.recycled)} 个"
                    )
                )
            self._render()
            if result.failed:
                detail_text = "\n".join(
                    f"{os.path.basename(path)}: {reason}"
                    for path, reason in result.failed[:8]
                )
                show_notice(
                    self,
                    "部分文件未处理",
                    result.message or "部分文件未能移入回收站。",
                    detail_text,
                    "warning",
                )
                self.set_status(
                    f"已移入回收站 {len(result.recycled)} 个，失败 {len(result.failed)} 个",
                    "warning",
                )
            else:
                self.set_status(result.message, "normal")
            self._update_detail(self._selected_files())

        def failed(exc: Exception) -> None:
            self._recycling = False
            self._recycle_btn.set_enabled(True)
            self.set_status(f"移入回收站失败：{exc}", "error")
            show_notice(self, "操作失败", "调用系统回收站时发生错误。", str(exc), "error")

        self.app.runner.submit(
            lambda: self.services["largefiles"].recycle(files),
            done,
            failed,
            name="recycle-large-files",
        )
