"""主窗口。"""

from __future__ import annotations

import time
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .. import APP_TITLE, __version__
from ..config import Config
from ..models import (
    AppRecord,
    ProcessInfo,
    StartupEntry,
    SystemInfo,
    UpdatePackage,
    WingetInfo,
)
from ..services.apps import AppService
from ..services.hardware import DiskHealthService, HardwareService
from ..services.largefiles import LargeFileService
from ..services.memory import MemoryBoostService
from ..services.processes import ProcessService
from ..services.tools import ToolService
from ..services.startup import StartupService
from ..services.system import SystemService
from ..services.winget import WingetService
from ..utils import (
    enable_dpi_awareness,
    get_logger,
    resource_path,
    setup_logging,
)
from .theme import C, FONTS, ICON_FONT, apply_theme
from .widgets import Badge, FlatButton, SidebarItem, show_notice
from .worker import TaskRunner


@dataclass
class AppState:
    system: SystemInfo | None = None
    apps: list[AppRecord] = field(default_factory=list)
    apps_at: float = 0.0
    apps_error: str = ""
    startup: list[StartupEntry] = field(default_factory=list)
    startup_at: float = 0.0
    updates: list[UpdatePackage] = field(default_factory=list)
    updates_at: float = 0.0
    updates_error: str = ""
    winget_info: WingetInfo | None = None
    winget_at: float = 0.0
    last_processes: list[ProcessInfo] = field(default_factory=list)


class ToolboxApp(tk.Tk):
    def __init__(self) -> None:
        enable_dpi_awareness()
        super().__init__()
        self.logger = setup_logging()
        self.withdraw()
        self.title(APP_TITLE)
        self.minsize(1200, 740)
        self.configure(bg=C.BG)
        self._set_icon()
        apply_theme(self)

        self.config_store = Config()
        self.runner = TaskRunner(self)
        self.services = {
            "system": SystemService(),
            "apps": AppService(),
            "processes": ProcessService(),
            "largefiles": LargeFileService(),
            "hardware": HardwareService(),
            "diskhealth": DiskHealthService(),
            "tools": ToolService(),
            "startup": StartupService(),
            "winget": WingetService(),
        }
        self.services["memory"] = MemoryBoostService(
            self.services["system"], self.services["processes"]
        )
        self.state = AppState()
        self._apps_waiters: list[Callable[[list[AppRecord], str], None]] = []
        self._apps_loading = False
        self._startup_waiters: list[Callable[[list[StartupEntry], str], None]] = []
        self._startup_loading = False
        self._winget_waiters: list[Callable[[WingetInfo], None]] = []
        self._winget_loading = False
        self._current_page = ""
        self._pages: dict[str, Any] = {}
        self._nav_items: dict[str, SidebarItem] = {}
        self._page_defs = self._build_page_defs()

        self._build_shell()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.report_callback_exception = self._report_callback_exception

        geometry = str(self.config_store.get("geometry", "1360x860"))
        try:
            self.geometry(geometry)
        except tk.TclError:
            self.geometry("1360x860")
        self.update_idletasks()
        self._center_window()
        self.deiconify()
        start_page = str(self.config_store.get("last_page", "dashboard"))
        if start_page not in {item["id"] for item in self._page_defs}:
            start_page = "dashboard"
        self.navigate(start_page)
        self.after(350, self._initial_probe)
        self.logger.info("WinToolbox %s 启动", __version__)

    # ------------------------------------------------------------------
    def _build_page_defs(self) -> list[dict[str, Any]]:
        from .pages.dashboard import DashboardPage
        from .pages.hardware import HardwarePage
        from .pages.largefiles import LargeFilesPage
        from .pages.memory import MemoryPage
        from .pages.processes import ProcessesPage
        from .pages.startup import StartupPage
        from .pages.tools import ToolsPage
        from .pages.uninstall import UninstallPage
        from .pages.updates import UpdatesPage

        return [
            {
                "id": "dashboard",
                "title": "概览",
                "subtitle": "系统状态、待处理事项和快捷入口",
                "icon": "\uE80F",
                "factory": DashboardPage,
            },
            {
                "id": "memory",
                "title": "内存加速",
                "subtitle": "整理后台闲置工作集，释放可用内存",
                "icon": "\uE945",
                "factory": MemoryPage,
            },
            {
                "id": "updates",
                "title": "应用更新",
                "subtitle": "通过 winget 检测并升级已安装应用",
                "icon": "\uE895",
                "factory": UpdatesPage,
            },
            {
                "id": "processes",
                "title": "后台进程",
                "subtitle": "查看正在运行的程序、资源占用与后台活动",
                "icon": "\uE9D9",
                "factory": ProcessesPage,
            },
            {
                "id": "hardware",
                "title": "硬件检测",
                "subtitle": "硬件信息与磁盘健康状态",
                "icon": "\uE772",
                "factory": HardwarePage,
            },
            {
                "id": "tools",
                "title": "验机工具",
                "subtitle": "屏幕/键盘/鼠标测试与常用验机软件",
                "icon": "\uE74C",
                "factory": ToolsPage,
            },
            {
                "id": "largefiles",
                "title": "大文件扫描",
                "subtitle": "选择磁盘，扫描占用空间较大的文件",
                "icon": "\uE8B7",
                "factory": LargeFilesPage,
            },
            {
                "id": "uninstall",
                "title": "应用卸载",
                "subtitle": "扫描已安装应用，识别可精简的软件",
                "icon": "\uE74D",
                "factory": UninstallPage,
            },
            {
                "id": "startup",
                "title": "启动项",
                "subtitle": "检查开机自启动程序，减少不必要的后台负担",
                "icon": "\uE7E8",
                "factory": StartupPage,
            },
        ]

    def _set_icon(self) -> None:
        try:
            icon = resource_path("assets/app.ico")
            if icon.exists():
                self.iconbitmap(str(icon))
        except tk.TclError:
            pass

    def _center_window(self) -> None:
        width = self.winfo_width()
        height = self.winfo_height()
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 18)
        self.geometry(f"+{x}+{y}")

    # ------------------------------------------------------------------
    def _build_shell(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0, minsize=232)
        self.grid_columnconfigure(1, weight=1)

        sidebar = tk.Frame(self, bg=C.SIDEBAR, width=232)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        self._build_sidebar(sidebar)

        main = tk.Frame(self, bg=C.BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(1, weight=1)
        main.grid_columnconfigure(0, weight=1)

        self._build_topbar(main)
        self.page_host = tk.Frame(main, bg=C.BG)
        self.page_host.grid(row=1, column=0, sticky="nsew", padx=26, pady=(0, 12))
        self.page_host.grid_rowconfigure(0, weight=1)
        self.page_host.grid_columnconfigure(0, weight=1)
        self._build_statusbar(main)

    def _build_sidebar(self, sidebar: tk.Frame) -> None:
        brand = tk.Frame(sidebar, bg=C.SIDEBAR)
        brand.pack(fill="x", padx=20, pady=(24, 28))
        logo = tk.Label(
            brand,
            text="W",
            bg=C.ACCENT,
            fg=C.WHITE,
            font=(FONTS["display"][0], 17, "bold"),
            width=2,
            height=1,
        )
        logo.pack(side="left")
        text_box = tk.Frame(brand, bg=C.SIDEBAR)
        text_box.pack(side="left", padx=(10, 0))
        tk.Label(
            text_box,
            text="WinToolbox",
            bg=C.SIDEBAR,
            fg=C.TEXT,
            font=(FONTS["body_bold"][0], 13, "bold"),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            text_box,
            text="Windows 工具箱",
            bg=C.SIDEBAR,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        ).pack(anchor="w")

        tk.Label(
            sidebar,
            text="工 具",
            bg=C.SIDEBAR,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        ).pack(fill="x", padx=24, pady=(0, 8))

        for index, definition in enumerate(self._page_defs, start=1):
            item = SidebarItem(
                sidebar,
                icon=definition["icon"],
                text=definition["title"],
                command=lambda pid=definition["id"]: self.navigate(pid),
                shortcut=f"Ctrl+{index}",
            )
            item.pack(fill="x", padx=12, pady=2)
            self._nav_items[definition["id"]] = item

        spacer = tk.Frame(sidebar, bg=C.SIDEBAR)
        spacer.pack(fill="both", expand=True)

        env_card = tk.Frame(
            sidebar,
            bg=C.SURFACE,
            highlightbackground=C.BORDER,
            highlightthickness=1,
        )
        env_card.pack(fill="x", padx=16, pady=(12, 10))
        env_inner = tk.Frame(env_card, bg=C.SURFACE)
        env_inner.pack(fill="x", padx=12, pady=10)
        title_row = tk.Frame(env_inner, bg=C.SURFACE)
        title_row.pack(fill="x")
        tk.Label(
            title_row,
            text="运行环境",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        ).pack(side="left")
        self._env_dot = tk.Label(
            title_row, text="●", bg=C.SURFACE, fg=C.AMBER, font=FONTS["tiny"]
        )
        self._env_dot.pack(side="right")
        self._env_text = tk.Label(
            env_inner,
            text="正在检测…",
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            font=FONTS["small"],
            anchor="w",
            justify="left",
            wraplength=170,
        )
        self._env_text.pack(fill="x", pady=(6, 0))

        FlatButton(
            sidebar,
            "关于与诊断",
            command=self.open_about,
            variant="sidebar",
            icon="\uE713",
            compact=True,
        ).pack(fill="x", padx=16)
        tk.Label(
            sidebar,
            text=f"v{__version__} · 本地运行",
            bg=C.SIDEBAR,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
        ).pack(pady=(8, 18))

    def _build_topbar(self, main: tk.Frame) -> None:
        topbar = tk.Frame(main, bg=C.BG)
        topbar.grid(row=0, column=0, sticky="ew", padx=26, pady=(20, 14))
        topbar.grid_columnconfigure(0, weight=1)
        text_box = tk.Frame(topbar, bg=C.BG)
        text_box.grid(row=0, column=0, sticky="w")
        self._title_label = tk.Label(
            text_box,
            text="",
            bg=C.BG,
            fg=C.TEXT,
            font=FONTS["display"],
            anchor="w",
        )
        self._title_label.pack(anchor="w")
        self._subtitle_label = tk.Label(
            text_box,
            text="",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["body"],
            anchor="w",
        )
        self._subtitle_label.pack(anchor="w", pady=(4, 0))

        right = tk.Frame(topbar, bg=C.BG)
        right.grid(row=0, column=1, sticky="e")
        self._admin_badge = Badge(right, "正在检测权限", "neutral")
        self._admin_badge.pack(side="left", padx=(0, 10))
        self._local_badge = Badge(right, "本地处理", "green")
        self._local_badge.pack(side="left")
        FlatButton(
            right,
            "刷新",
            command=self.refresh_current,
            variant="ghost",
            icon="\uE72C",
            compact=True,
        ).pack(side="left", padx=(12, 0))

    def _build_statusbar(self, main: tk.Frame) -> None:
        bar = tk.Frame(main, bg=C.BG, height=30)
        bar.grid(row=2, column=0, sticky="ew", padx=26, pady=(0, 8))
        bar.grid_columnconfigure(1, weight=1)
        self._status_dot = tk.Label(
            bar, text="●", bg=C.BG, fg=C.GREEN, font=FONTS["tiny"]
        )
        self._status_dot.grid(row=0, column=0, sticky="w")
        self._status_var = tk.StringVar(value="就绪")
        self._status_label = tk.Label(
            bar,
            textvariable=self._status_var,
            bg=C.BG,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        )
        self._status_label.grid(row=0, column=1, sticky="w", padx=(5, 0))
        tk.Label(
            bar,
            text="F5 刷新   ·   Ctrl+1~9 切换   ·   数据仅在本机处理",
            bg=C.BG,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
        ).grid(row=0, column=2, sticky="e")

    # ------------------------------------------------------------------
    def navigate(self, page_id: str) -> None:
        definition = next((item for item in self._page_defs if item["id"] == page_id), None)
        if definition is None:
            return
        if self._current_page == page_id and page_id in self._pages:
            return
        if self._current_page in self._pages:
            self._pages[self._current_page].on_hide()
            self._pages[self._current_page].grid_forget()
        if page_id not in self._pages:
            try:
                page = definition["factory"](self, self.page_host)
            except Exception as exc:
                self.logger.exception("创建页面失败: %s", page_id)
                show_notice(self, "页面加载失败", f"无法打开「{definition['title']}」。", str(exc), "error")
                return
            page.grid(row=0, column=0, sticky="nsew")
            self._pages[page_id] = page
        page = self._pages[page_id]
        page.grid(row=0, column=0, sticky="nsew")
        page.tkraise()
        self._current_page = page_id
        self._title_label.configure(text=definition["title"])
        self._subtitle_label.configure(text=definition["subtitle"])
        for pid, item in self._nav_items.items():
            item.set_selected(pid == page_id)
        self.config_store.set("last_page", page_id)
        page.on_show()

    def refresh_current(self) -> None:
        page = self._pages.get(self._current_page)
        if page is None:
            return
        try:
            page.refresh()
        except Exception as exc:
            self.logger.exception("刷新页面失败")
            show_notice(self, "刷新失败", "当前页面刷新时发生错误。", str(exc), "error")

    def _bind_shortcuts(self) -> None:
        self.bind("<F5>", lambda _e: self.refresh_current())
        for index, definition in enumerate(self._page_defs, start=1):
            self.bind(
                f"<Control-Key-{index}>",
                lambda _e, pid=definition["id"]: self.navigate(pid),
            )

    # ------------------------------------------------------------------
    def set_status(self, text: str, kind: str = "normal") -> None:
        self._status_var.set(text)
        colors = {
            "normal": C.GREEN,
            "busy": C.AMBER,
            "warning": C.AMBER,
            "error": C.RED,
            "info": C.ACCENT,
        }
        self._status_dot.configure(fg=colors.get(kind, C.GREEN))
        self._status_label.configure(
            fg=C.MUTED if kind == "normal" else colors.get(kind, C.MUTED)
        )

    def _initial_probe(self) -> None:
        self._admin_badge.configure(text="权限检测中")
        self.load_system_async(self._apply_system_badge)
        self.load_winget_async(self._apply_winget_sidebar)
        # 提前预热应用清单，避免用户首次进入卸载页等待。
        self.load_apps_async(lambda _apps, _err: None)

    def _apply_system_badge(self, info: SystemInfo | None, error: str) -> None:
        if info is None:
            self._admin_badge.configure(text="权限未知", bg=C.SURFACE_ALT, fg=C.MUTED)
            return
        if info.is_admin:
            self._admin_badge.configure(text="管理员", bg=C.GREEN_DARK, fg=C.GREEN)
            self._env_dot.configure(fg=C.GREEN)
        else:
            self._admin_badge.configure(text="标准用户", bg=C.AMBER_DARK, fg=C.AMBER)
            self._env_dot.configure(fg=C.AMBER)
        self._update_env_text()

    def _apply_winget_sidebar(self, info: WingetInfo) -> None:
        self.state.winget_info = info
        self._update_env_text()

    def _update_env_text(self) -> None:
        info = self.state.winget_info
        parts = []
        system = self.state.system
        if system:
            parts.append("管理员权限" if system.is_admin else "标准用户")
        if info is None:
            parts.append("winget 检测中")
        elif info.available:
            parts.append(f"winget {info.version}")
        else:
            parts.append("winget 不可用")
        self._env_text.configure(text=" · ".join(parts) if parts else "正在检测…")

    # ------------------------------------------------------------------
    def load_system_async(self, callback: Callable[[SystemInfo | None, str], None]) -> None:
        def work() -> SystemInfo:
            return self.services["system"].collect()

        def done(info: SystemInfo) -> None:
            self.state.system = info
            self._update_env_text()
            callback(info, "")

        def failed(exc: Exception) -> None:
            callback(None, str(exc))

        self.runner.submit(work, done, failed, name="system")

    def load_apps_async(
        self,
        callback: Callable[[list[AppRecord], str], None],
        force: bool = False,
    ) -> None:
        fresh = self.state.apps and (time.time() - self.state.apps_at) < 300
        if fresh and not force:
            callback(self.state.apps, "")
            return
        self._apps_waiters.append(callback)
        if self._apps_loading:
            return
        self._apps_loading = True
        self.set_status("正在扫描已安装应用…", "busy")
        self.runner.submit(
            self.services["apps"].scan,
            self._apps_loaded,
            self._apps_failed,
            name="apps",
        )

    def _apps_loaded(self, records: list[AppRecord]) -> None:
        self._apps_loading = False
        self.state.apps = records
        self.state.apps_at = time.time()
        self.state.apps_error = ""
        if self._current_page in {"dashboard", "uninstall"}:
            self.set_status(f"已扫描 {len(records)} 个已安装应用")
        waiters, self._apps_waiters = self._apps_waiters, []
        for callback in waiters:
            callback(records, "")

    def _apps_failed(self, exc: Exception) -> None:
        self._apps_loading = False
        self.state.apps_error = str(exc)
        if self._current_page in {"dashboard", "uninstall"}:
            self.set_status("应用扫描失败", "error")
        waiters, self._apps_waiters = self._apps_waiters, []
        for callback in waiters:
            callback([], str(exc))

    def load_startup_async(
        self,
        callback: Callable[[list[StartupEntry], str], None],
        force: bool = False,
    ) -> None:
        fresh = self.state.startup and (time.time() - self.state.startup_at) < 600
        if fresh and not force:
            callback(self.state.startup, "")
            return
        self._startup_waiters.append(callback)
        if self._startup_loading:
            return
        self._startup_loading = True
        self.runner.submit(
            self.services["startup"].scan,
            self._startup_loaded,
            self._startup_failed,
            name="startup",
        )

    def _startup_loaded(self, entries: list[StartupEntry]) -> None:
        self._startup_loading = False
        self.state.startup = entries
        self.state.startup_at = time.time()
        waiters, self._startup_waiters = self._startup_waiters, []
        for callback in waiters:
            callback(entries, "")

    def _startup_failed(self, exc: Exception) -> None:
        self._startup_loading = False
        waiters, self._startup_waiters = self._startup_waiters, []
        for callback in waiters:
            callback([], str(exc))

    def load_winget_async(
        self, callback: Callable[[WingetInfo], None], force: bool = False
    ) -> None:
        if not force and self.state.winget_info and (time.time() - self.state.winget_at) < 60:
            callback(self.state.winget_info)
            return
        self._winget_waiters.append(callback)
        if self._winget_loading:
            return
        self._winget_loading = True

        def done(info: WingetInfo) -> None:
            self._winget_loading = False
            self.state.winget_info = info
            self.state.winget_at = time.time()
            self._update_env_text()
            waiters, self._winget_waiters = self._winget_waiters, []
            for waiter in waiters:
                waiter(info)

        def failed(exc: Exception) -> None:
            self.logger.error(
                "winget 探测异常", exc_info=(type(exc), exc, exc.__traceback__)
            )
            self._winget_loading = False
            info = WingetInfo(available=False, error=str(exc))
            self.state.winget_info = info
            self.state.winget_at = time.time()
            self._update_env_text()
            waiters, self._winget_waiters = self._winget_waiters, []
            for waiter in waiters:
                waiter(info)

        self.runner.submit(self.services["winget"].probe, done, failed, name="winget")

    # ------------------------------------------------------------------
    def open_about(self) -> None:
        from .dialogs import AboutDialog

        AboutDialog(self)

    def _report_callback_exception(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.logger.error("界面回调异常", exc_info=(exc_type, exc, tb))
        self.set_status(f"发生错误：{exc}", "error")
        try:
            show_notice(
                self,
                "操作未完成",
                "界面处理时发生了一个异常，详细信息已写入日志。",
                f"{exc_type.__name__}: {exc}",
                "error",
            )
        except tk.TclError:
            pass

    def _on_close(self) -> None:
        try:
            self.config_store.set("geometry", self.geometry())
            self.config_store.save()
        except Exception:
            self.logger.exception("保存窗口状态失败")
        self.runner.shutdown()
        self.destroy()


def run() -> None:
    app = ToolboxApp()
    app.mainloop()


if __name__ == "__main__":
    run()
