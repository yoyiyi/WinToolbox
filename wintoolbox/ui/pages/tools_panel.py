"""验机工具面板：内置键鼠/屏幕测试 + 第三方工具检测、启动、安装。"""

from __future__ import annotations

import time
import tkinter as tk

from ...services.tools import ToolActionResult, ToolService, ToolSpec, ToolStatus
from ...utils import truncate_middle
from ..theme import C, FONTS
from ..tool_tests import KeyboardTestWindow, MouseTestWindow, ScreenTestWindow
from ..widgets import (
    Badge,
    Card,
    FlatButton,
    ScrollableFrame,
    ask_confirm,
    section_title,
    show_notice,
)


class ToolsPanel:
    def __init__(self, parent: tk.Misc, app, services: dict) -> None:
        self.parent = parent
        self.app = app
        self.services = services
        self.service: ToolService = services["tools"]
        self._loaded = False
        self._loading = False
        self._last_at = 0.0
        self._installing: set[str] = set()
        self._statuses: dict[str, ToolStatus] = {}
        self._cards: dict[str, dict] = {}
        self._build()

    def _build(self) -> None:
        self._scroll = ScrollableFrame(self.parent, bg=C.BG)
        self._scroll.pack(fill="both", expand=True)
        content = self._scroll.inner
        content.grid_columnconfigure(0, weight=1)

        intro = tk.Frame(content, bg=C.BG)
        intro.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        intro.grid_columnconfigure(0, weight=1)
        tk.Label(
            intro,
            text="第三方工具不随工具箱分发；安装/下载需自行确认来源。",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=420,
        ).grid(row=0, column=0, sticky="w")
        self._summary = tk.Label(
            intro,
            text="正在检测…",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="e",
        )
        self._summary.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self._refresh_btn = FlatButton(
            intro,
            "重新检测",
            command=self.refresh,
            variant="ghost",
            icon="\uE72C",
            compact=True,
        )
        self._refresh_btn.grid(row=0, column=2, padx=(8, 0))

        self._build_builtin(content)
        self._build_external(content, "必用", 3)
        self._build_external(content, "进阶", 5)
        self._scroll.after(100, self._scroll.refresh_layout)

    def _build_builtin(self, content: tk.Frame) -> None:
        section_title(content, "内置检测", "无需安装，直接运行").grid(
            row=1, column=0, sticky="w", pady=(0, 8)
        )
        row = tk.Frame(content, bg=C.BG)
        row.grid(row=2, column=0, sticky="ew", pady=(0, 14))
        for column in range(3):
            row.grid_columnconfigure(column, weight=1, uniform="builtin")

        items = (
            (
                "屏幕坏点检测",
                "纯色全屏循环，检查坏点、亮点、漏光和色带。",
                "\uE7F4",
                C.CYAN,
                self._open_screen,
            ),
            (
                "键盘测试",
                "逐个按键高亮，检查失灵、串键和连点。",
                "\uE765",
                C.PURPLE,
                self._open_keyboard,
            ),
            (
                "鼠标测试",
                "移动、左右中键、双击和滚轮计数。",
                "\uE962",
                C.GREEN,
                self._open_mouse,
            ),
        )
        for column, (title, desc, icon, accent, command) in enumerate(items):
            card = Card(row, padding=13)
            card.grid(
                row=0,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 4, 0 if column == 2 else 4),
            )
            head = tk.Frame(card.inner, bg=C.SURFACE)
            head.pack(fill="x")
            tk.Label(
                head,
                text=icon,
                bg=C.SURFACE,
                fg=accent,
                font=("Segoe MDL2 Assets", 18),
            ).pack(side="left", padx=(0, 8))
            tk.Label(
                head,
                text=title,
                bg=C.SURFACE,
                fg=C.TEXT,
                font=FONTS["body_bold"],
            ).pack(side="left")
            tk.Label(
                card.inner,
                text=desc,
                bg=C.SURFACE,
                fg=C.MUTED,
                font=FONTS["tiny"],
                anchor="w",
                justify="left",
                wraplength=250,
            ).pack(fill="x", pady=(7, 10))
            FlatButton(
                card.inner,
                "开始检测",
                command=command,
                variant="secondary",
                compact=True,
            ).pack(anchor="w")

    def _build_external(self, content: tk.Frame, category: str, row_index: int) -> None:
        specs = [spec for spec in self.service.specs() if spec.category == category]
        title = "验机必用" if category == "必用" else "进阶工具"
        subtitle = "常用检测与烤机" if category == "必用" else "按需使用"
        section_title(content, title, subtitle).grid(
            row=row_index, column=0, sticky="w", pady=(0, 8)
        )
        grid = tk.Frame(content, bg=C.BG)
        grid.grid(row=row_index + 1, column=0, sticky="ew", pady=(0, 14))
        for column in range(2):
            grid.grid_columnconfigure(column, weight=1, uniform="tool")
        for index, spec in enumerate(specs):
            column = index % 2
            row = index // 2
            card = self._build_tool_card(grid, spec)
            card.grid(
                row=row,
                column=column,
                sticky="nsew",
                padx=(0 if column == 0 else 5, 0 if column == 1 else 5),
                pady=4,
            )

    def _build_tool_card(self, parent: tk.Frame, spec: ToolSpec) -> Card:
        card = Card(parent, padding=13)
        head = tk.Frame(card.inner, bg=C.SURFACE)
        head.pack(fill="x")
        tk.Label(
            head,
            text=spec.name,
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["body_bold"],
        ).pack(side="left")
        Badge(
            head,
            "必用" if spec.category == "必用" else "进阶",
            "cyan" if spec.category == "必用" else "purple",
        ).pack(side="left", padx=(7, 0))
        status_label = tk.Label(
            head,
            text="检测中…",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["tiny"],
        )
        status_label.pack(side="right")
        tk.Label(
            card.inner,
            text=spec.description,
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["tiny"],
            anchor="w",
            justify="left",
            wraplength=390,
        ).pack(fill="x", pady=(6, 0))
        if spec.note:
            tk.Label(
                card.inner,
                text=spec.note,
                bg=C.SURFACE,
                fg=C.AMBER,
                font=FONTS["tiny"],
                anchor="w",
                justify="left",
                wraplength=390,
            ).pack(fill="x", pady=(2, 0))
        path_label = tk.Label(
            card.inner,
            text="",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        )
        path_label.pack(fill="x", pady=(3, 7))

        actions = tk.Frame(card.inner, bg=C.SURFACE)
        actions.pack(fill="x")
        action = FlatButton(
            actions,
            "启动",
            command=lambda: self._action(spec),
            variant="accent",
            compact=True,
        )
        action.pack(side="left")
        action.set_enabled(False)
        official = FlatButton(
            actions,
            "官网",
            command=lambda: self._open_official(spec),
            variant="ghost",
            compact=True,
        )
        official.pack(side="left", padx=(6, 0))
        self._cards[spec.key] = {
            "status": status_label,
            "path": path_label,
            "action": action,
            "official": official,
        }
        return card

    # ------------------------------------------------------------------
    def on_show(self) -> None:
        if not self._loaded or time.time() - self._last_at > 120:
            self.refresh()

    def refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        self._refresh_btn.set_enabled(False)
        self._summary.configure(text="正在检测已安装工具…")
        self.app.set_status("正在检测验机工具…", "busy")

        def done(statuses: list[ToolStatus]) -> None:
            self._loading = False
            self._loaded = True
            self._last_at = time.time()
            self._refresh_btn.set_enabled(True)
            self._statuses = {status.spec.key: status for status in statuses}
            self._render()

        def failed(exc: Exception) -> None:
            self._loading = False
            self._refresh_btn.set_enabled(True)
            self._summary.configure(text=f"检测失败：{exc}", fg=C.RED)
            self.app.set_status("验机工具检测失败", "error")

        self.app.runner.submit(self.service.detect, done, failed, name="tools-detect")

    def _render(self) -> None:
        installed = sum(1 for status in self._statuses.values() if status.installed)
        self._summary.configure(
            text=f"已识别 {installed} / {len(self._statuses)} 个外部工具",
            fg=C.GREEN if installed else C.MUTED,
        )
        for key, status in self._statuses.items():
            card = self._cards.get(key)
            if not card:
                continue
            spec = status.spec
            if status.installed:
                card["status"].configure(text="● 已安装", fg=C.GREEN)
                card["path"].configure(
                    text=truncate_middle(status.path, 78), fg=C.MUTED_DARK
                )
                card["action"].set_text("启动")
                card["action"].set_command(lambda s=status: self._launch(s))
                card["action"].set_enabled(True)
                card["official"].pack(side="left", padx=(6, 0))
            else:
                card["status"].configure(text="○ 未安装", fg=C.MUTED)
                card["path"].configure(
                    text="未检测到本地安装，可从官方渠道获取。", fg=C.MUTED_DARK
                )
                if spec.winget_id:
                    card["action"].set_text("一键安装")
                    card["action"].set_command(lambda s=spec: self._install(s))
                    card["action"].set_enabled(True)
                    card["official"].pack(side="left", padx=(6, 0))
                else:
                    card["action"].set_text("官网下载")
                    card["action"].set_command(
                        lambda s=spec: self._open_official(s)
                    )
                    card["action"].set_enabled(True)
                    card["official"].pack_forget()
            if key in self._installing:
                card["action"].set_text("安装中…")
                card["action"].set_enabled(False)
                card["status"].configure(text="◌ 正在安装", fg=C.AMBER)
        self._scroll.refresh_layout()
        if self.app._current_page == "hardware":
            self.app.set_status("验机工具状态已更新")

    # ------------------------------------------------------------------
    def _action(self, spec: ToolSpec) -> None:
        status = self._statuses.get(spec.key)
        if status and status.installed:
            self._launch(status)
        elif spec.winget_id:
            self._install(spec)
        else:
            self._open_official(spec)

    def _launch(self, status: ToolStatus) -> None:
        result = self.service.launch(status)
        if not result.ok:
            show_notice(
                self.parent, "无法启动", result.message, kind="error"
            )
            self.refresh()
            return
        self.app.set_status(result.message)

    def _install(self, spec: ToolSpec) -> None:
        if spec.key in self._installing:
            return
        confirmed = ask_confirm(
            self.parent,
            "安装验机工具",
            f"将从 winget 官方源安装 {spec.name}。",
            (
                f"包标识：{spec.winget_id}\n"
                "安装会修改系统，可能需要 UAC 授权；请确认来源可信。\n"
                "如果 winget 不可用，可改用“官网”下载。"
            ),
            confirm_text="开始安装",
        )
        if not confirmed:
            return
        self._installing.add(spec.key)
        card = self._cards.get(spec.key)
        if card:
            card["action"].set_text("安装中…")
            card["action"].set_enabled(False)
            card["status"].configure(text="◌ 正在安装", fg=C.AMBER)
        self.app.set_status(f"正在安装 {spec.name}…", "busy")

        def done(result: ToolActionResult) -> None:
            self._installing.discard(spec.key)
            if result.ok:
                self.refresh()
                show_notice(
                    self.parent,
                    "安装完成",
                    result.message,
                    "已重新检测工具状态；若仍显示未安装，请从官网手动安装。",
                    "info",
                )
                self.app.set_status(f"{spec.name} 安装完成")
            else:
                self.refresh()
                show_notice(
                    self.parent,
                    "安装未完成",
                    result.message,
                    (result.output or "")[-1000:],
                    "warning",
                )
                self.app.set_status(f"{spec.name} 安装未完成", "warning")

        def failed(exc: Exception) -> None:
            self._installing.discard(spec.key)
            self.refresh()
            show_notice(self.parent, "安装失败", str(exc), kind="error")

        self.app.runner.submit(
            lambda: self.service.install(spec, self.services["winget"]),
            done,
            failed,
            name=f"install-{spec.key}",
        )

    def _open_official(self, spec: ToolSpec) -> None:
        result = self.service.open_official(spec)
        if not result.ok:
            show_notice(self.parent, "无法打开官网", result.message, kind="error")
            return
        self.app.set_status(result.message)

    def _open_screen(self) -> None:
        ScreenTestWindow(self.parent.winfo_toplevel())

    def _open_keyboard(self) -> None:
        KeyboardTestWindow(self.parent.winfo_toplevel())

    def _open_mouse(self) -> None:
        MouseTestWindow(self.parent.winfo_toplevel())
