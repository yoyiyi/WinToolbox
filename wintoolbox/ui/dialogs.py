"""关于、诊断等独立对话框。"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from typing import Any

from .. import APP_NAME, __version__
from ..utils import app_data_dir, is_admin, logs_dir, open_folder, restart_as_admin
from .theme import C, FONTS, ICON_FONT
from .widgets import Badge, FlatButton, ask_confirm, show_notice


class AboutDialog(tk.Toplevel):
    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self.app = app
        self.withdraw()
        self.title("关于 WinToolbox")
        self.configure(bg=C.SURFACE)
        self.resizable(False, False)
        self.transient(app)
        self._build()
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = app.winfo_rootx() + max(0, (app.winfo_width() - self.winfo_reqwidth()) // 2)
        y = app.winfo_rooty() + max(0, (app.winfo_height() - self.winfo_reqheight()) // 2)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.grab_set()
        self.focus_force()

    def _build(self) -> None:
        body = tk.Frame(self, bg=C.SURFACE, padx=28, pady=24)
        body.pack(fill="both", expand=True)

        brand_row = tk.Frame(body, bg=C.SURFACE)
        brand_row.pack(fill="x")
        tk.Label(
            brand_row,
            text="W",
            bg=C.ACCENT,
            fg=C.WHITE,
            font=(FONTS["display"][0], 20, "bold"),
            width=2,
            height=1,
        ).pack(side="left")
        text = tk.Frame(brand_row, bg=C.SURFACE)
        text.pack(side="left", padx=(13, 0))
        tk.Label(
            text,
            text=APP_NAME,
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["display"],
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            text,
            text=f"Windows 桌面工具箱  ·  v{__version__}",
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
        ).pack(anchor="w", pady=(2, 0))
        Badge(brand_row, "本地运行", "green").pack(side="right")

        tk.Label(
            body,
            text="应用更新、后台进程、卸载建议与启动项集中在一个轻量界面中。所有扫描和判断均在本机完成，不上传应用清单或进程信息。",
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            font=FONTS["small"],
            justify="left",
            anchor="w",
            wraplength=540,
        ).pack(fill="x", pady=(18, 16))

        info = tk.Frame(
            body,
            bg=C.SURFACE_ALT,
            highlightbackground=C.BORDER,
            highlightthickness=1,
        )
        info.pack(fill="x")
        grid = tk.Frame(info, bg=C.SURFACE_ALT)
        grid.pack(fill="x", padx=14, pady=12)
        grid.grid_columnconfigure(1, weight=1)

        state = self.app.state
        system = state.system
        winget = state.winget_info
        if system:
            os_text = system.os_name
            user_text = f"{system.username}  ({'管理员' if system.is_admin else '标准用户'})"
        else:
            os_text = "尚未读取"
            user_text = "管理员" if is_admin() else "标准用户"
        if winget is None:
            winget_text = "尚未检测"
        elif winget.available:
            winget_text = f"可用 · {winget.version}"
        else:
            winget_text = "不可用（可在更新页修复）"
        rows = (
            ("系统", os_text),
            ("当前权限", user_text),
            ("更新组件", winget_text),
            ("Python", sys.version.split()[0]),
            ("数据目录", str(app_data_dir())),
            ("日志目录", str(logs_dir())),
        )
        for index, (label, value) in enumerate(rows):
            tk.Label(
                grid,
                text=label,
                bg=C.SURFACE_ALT,
                fg=C.MUTED_DARK,
                font=FONTS["tiny"],
                anchor="w",
            ).grid(row=index, column=0, sticky="nw", padx=(0, 16), pady=3)
            tk.Label(
                grid,
                text=value,
                bg=C.SURFACE_ALT,
                fg=C.TEXT_SOFT,
                font=FONTS["small"],
                anchor="w",
                justify="left",
                wraplength=380,
            ).grid(row=index, column=1, sticky="w", pady=3)

        tk.Label(
            body,
            text=(
                "说明：更新功能依赖 Microsoft 的 winget；卸载建议为启发式判断，不构成必须卸载的建议。"
                "执行卸载和结束进程前请保存工作。"
            ),
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            justify="left",
            anchor="w",
            wraplength=540,
        ).pack(fill="x", pady=(14, 0))

        actions = tk.Frame(body, bg=C.SURFACE)
        actions.pack(fill="x", pady=(18, 0))
        FlatButton(actions, "关闭", command=self.destroy, variant="secondary").pack(side="right")
        FlatButton(
            actions,
            "打开日志目录",
            command=self._open_logs,
            variant="ghost",
            compact=True,
        ).pack(side="right", padx=(0, 8))
        FlatButton(
            actions,
            "复制诊断信息",
            command=self._copy_diagnostics,
            variant="ghost",
            compact=True,
        ).pack(side="right", padx=(0, 8))
        if not (system and system.is_admin) and not is_admin():
            FlatButton(
                actions,
                "以管理员身份重启",
                command=self._restart_admin,
                variant="accent",
                compact=True,
            ).pack(side="left")

    def _open_logs(self) -> None:
        open_folder(logs_dir())

    def _copy_diagnostics(self) -> None:
        system = self.app.state.system
        winget = self.app.state.winget_info
        lines = [
            f"{APP_NAME} v{__version__}",
            f"Python {sys.version.split()[0]}",
            system.os_name if system else "系统信息未读取",
            f"管理员: {system.is_admin if system else is_admin()}",
            f"winget: {winget.version if winget and winget.available else '不可用/未检测'}",
            f"数据目录: {app_data_dir()}",
        ]
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        show_notice(self, "已复制", "诊断信息已复制到剪贴板。", kind="info")

    def _restart_admin(self) -> None:
        confirmed = ask_confirm(
            self,
            "以管理员身份重启？",
            "将以管理员权限重新启动 WinToolbox，系统会弹出 UAC 授权窗口。当前窗口会关闭。",
            confirm_text="重启",
            danger=False,
        )
        if not confirmed:
            return
        if restart_as_admin():
            self.app._on_close()
        else:
            show_notice(
                self,
                "未能提升权限",
                "可能取消了 UAC 授权，或当前环境不允许提权。",
                kind="warning",
            )
