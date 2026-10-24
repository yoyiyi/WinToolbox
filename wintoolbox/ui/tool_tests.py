"""内置验机测试：屏幕坏点、键盘、鼠标。"""

from __future__ import annotations

import tkinter as tk

from .theme import C, FONTS


def _center(window: tk.Toplevel, width: int, height: int) -> None:
    window.update_idletasks()
    x = max(0, (window.winfo_screenwidth() - width) // 2)
    y = max(0, (window.winfo_screenheight() - height) // 2)
    window.geometry(f"{width}x{height}+{x}+{y}")


class ScreenTestWindow(tk.Toplevel):
    COLORS = (
        ("纯红", "#FF0000"),
        ("纯绿", "#00FF00"),
        ("纯蓝", "#0000FF"),
        ("纯白", "#FFFFFF"),
        ("纯黑", "#000000"),
        ("中灰", "#808080"),
        ("青色", "#00FFFF"),
        ("品红", "#FF00FF"),
        ("黄色", "#FFFF00"),
    )

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("屏幕坏点检测")
        self.attributes("-fullscreen", True)
        self.attributes("-topmost", True)
        self.configure(bg="#000000", cursor="none")
        self._index = 0
        self._hint_job: str | None = None
        self._hint = tk.Label(
            self,
            font=FONTS["body_bold"],
            bd=0,
            padx=12,
            pady=6,
        )
        self._hint.place(relx=0.5, y=22, anchor="n")
        self.bind("<Button-1>", self._next)
        self.bind("<Button-3>", self._next)
        self.bind("<space>", self._next)
        self.bind("<Escape>", lambda _e: self.destroy())
        self.bind("<KeyPress-h>", self._show_hint)
        self.bind("<KeyPress-H>", self._show_hint)
        self.focus_force()
        self._apply(first=True)

    def _contrast(self, color: str) -> str:
        value = color.lstrip("#")
        r, g, b = (int(value[index : index + 2], 16) for index in (0, 2, 4))
        return "#111111" if (r * 299 + g * 587 + b * 114) / 1000 > 150 else "#F5F5F5"

    def _show_hint(self, _event: tk.Event | None = None) -> None:
        name, color = self.COLORS[self._index]
        self._hint.configure(
            text=(
                f"{name}  ·  {self._index + 1}/{len(self.COLORS)}  ·  "
                "左键 / 空格 下一张  ·  Esc 退出  ·  H 显示提示"
            ),
            bg=color,
            fg=self._contrast(color),
        )
        self._hint.lift()

    def _hide_hint(self) -> None:
        self._hint.place_forget()
        self._hint_job = None

    def _apply(self, first: bool = False) -> None:
        _name, color = self.COLORS[self._index]
        self.configure(bg=color)
        self._show_hint()
        if self._hint_job is not None:
            self.after_cancel(self._hint_job)
        self._hint_job = self.after(2500, self._hide_hint)

    def _next(self, _event: tk.Event | None = None) -> None:
        self._index = (self._index + 1) % len(self.COLORS)
        self._apply()


class KeyboardTestWindow(tk.Toplevel):
    ROWS = (
        (("Esc", "Escape", 2), ("F1", "F1", 2), ("F2", "F2", 2), ("F3", "F3", 2),
         ("F4", "F4", 2), ("F5", "F5", 2), ("F6", "F6", 2), ("F7", "F7", 2),
         ("F8", "F8", 2), ("F9", "F9", 2), ("F10", "F10", 2), ("F11", "F11", 2),
         ("F12", "F12", 2)),
        (("`", "grave", 2), ("1", "1", 2), ("2", "2", 2), ("3", "3", 2),
         ("4", "4", 2), ("5", "5", 2), ("6", "6", 2), ("7", "7", 2),
         ("8", "8", 2), ("9", "9", 2), ("0", "0", 2), ("-", "minus", 2),
         ("=", "equal", 2), ("Backspace", "BackSpace", 5)),
        (("Tab", "Tab", 3), ("Q", "q", 2), ("W", "w", 2), ("E", "e", 2),
         ("R", "r", 2), ("T", "t", 2), ("Y", "y", 2), ("U", "u", 2),
         ("I", "i", 2), ("O", "o", 2), ("P", "p", 2), ("[", "bracketleft", 2),
         ("]", "bracketright", 2), ("\\", "backslash", 3)),
        (("Caps", "Caps_Lock", 3), ("A", "a", 2), ("S", "s", 2), ("D", "d", 2),
         ("F", "f", 2), ("G", "g", 2), ("H", "h", 2), ("J", "j", 2),
         ("K", "k", 2), ("L", "l", 2), (";", "semicolon", 2),
         ("'", "apostrophe", 2), ("Enter", "Return", 5)),
        (("Shift", "Shift_L", 5), ("Z", "z", 2), ("X", "x", 2), ("C", "c", 2),
         ("V", "v", 2), ("B", "b", 2), ("N", "n", 2), ("M", "m", 2),
         (",", "comma", 2), (".", "period", 2), ("/", "slash", 2),
         ("Shift", "Shift_R", 5)),
        (("Ctrl", "Control_L", 3), ("Win", "Super_L", 3), ("Alt", "Alt_L", 3),
         ("Space", "space", 9), ("Alt", "Alt_R", 3), ("Win", "Super_R", 3),
         ("Menu", "Menu", 3), ("Ctrl", "Control_R", 3),
         ("←", "Left", 2), ("↑", "Up", 2), ("↓", "Down", 2), ("→", "Right", 2)),
    )

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("键盘测试")
        self.configure(bg=C.BG)
        self.resizable(False, False)
        self._tested: set[str] = set()
        self._labels: dict[str, list[tk.Label]] = {}
        self._alias: dict[str, str] = {}
        _center(self, 1060, 610)

        header = tk.Frame(self, bg=C.BG)
        header.pack(fill="x", padx=22, pady=(18, 8))
        tk.Label(
            header,
            text="键盘测试",
            bg=C.BG,
            fg=C.TEXT,
            font=FONTS["title"],
        ).pack(side="left")
        tk.Label(
            header,
            text="请逐个按下按键，绿色表示已被识别",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
        ).pack(side="left", padx=(14, 0), pady=(3, 0))
        tk.Button(
            header,
            text="关闭",
            command=self.destroy,
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            activebackground=C.SURFACE_HOVER,
            activeforeground=C.TEXT,
            relief="flat",
            bd=0,
            font=FONTS["small"],
            padx=14,
            pady=6,
            cursor="hand2",
        ).pack(side="right")

        self._last = tk.Label(
            self,
            text="等待按键…",
            bg=C.SURFACE,
            fg=C.TEXT,
            font=(FONTS["display"][0], 22, "bold"),
            anchor="w",
            padx=16,
            pady=10,
        )
        self._last.pack(fill="x", padx=22, pady=(0, 6))
        self._stats = tk.Label(
            self,
            text="已测试 0 个按键",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
        )
        self._stats.pack(fill="x", padx=24, pady=(0, 10))

        board = tk.Frame(self, bg=C.BG)
        board.pack(fill="both", expand=True, padx=20)
        for row in self.ROWS:
            row_frame = tk.Frame(board, bg=C.BG)
            row_frame.pack(fill="x", pady=3)
            for text, keysym, width in row:
                label = tk.Label(
                    row_frame,
                    text=text,
                    bg=C.SURFACE_ALT,
                    fg=C.MUTED,
                    font=FONTS["tiny"],
                    width=width,
                    pady=7,
                    bd=0,
                )
                label.pack(side="left", padx=2, expand=True, fill="x")
                self._labels.setdefault(text, []).append(label)
                self._alias[keysym] = text
                self._alias[keysym.casefold()] = text

        footer = tk.Frame(self, bg=C.BG)
        footer.pack(fill="x", padx=22, pady=14)
        tk.Label(
            footer,
            text="按键无反应时先检查连接；机械键盘可继续测试轴体/连点。",
            bg=C.BG,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
        ).pack(side="left")
        tk.Button(
            footer,
            text="重置",
            command=self._reset,
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            activebackground=C.SURFACE_HOVER,
            activeforeground=C.TEXT,
            relief="flat",
            bd=0,
            font=FONTS["small"],
            padx=14,
            pady=6,
            cursor="hand2",
        ).pack(side="right")

        self.bind("<KeyPress>", self._on_press)
        self.bind("<KeyRelease>", self._on_release)
        self.lift()
        self.focus_force()

    def _resolve(self, keysym: str) -> str:
        if keysym in self._alias:
            return self._alias[keysym]
        if len(keysym) == 1:
            for text in (keysym.upper(), keysym):
                if text in self._labels:
                    return text
        return ""

    def _paint(self, text: str, color: str, fg: str) -> None:
        for label in self._labels.get(text, []):
            label.configure(bg=color, fg=fg)

    def _on_press(self, event: tk.Event) -> None:
        keysym = str(event.keysym)
        text = self._resolve(keysym)
        self._last.configure(text=f"最近按键：{keysym}")
        if not text:
            return
        self._tested.add(text)
        self._paint(text, C.ACCENT, C.WHITE)
        self._stats.configure(text=f"已测试 {len(self._tested)} 个按键")

    def _on_release(self, event: tk.Event) -> None:
        text = self._resolve(str(event.keysym))
        if not text:
            return
        if text in self._tested:
            self._paint(text, C.GREEN_DARK, C.GREEN)

    def _reset(self) -> None:
        self._tested.clear()
        for labels in self._labels.values():
            for label in labels:
                label.configure(bg=C.SURFACE_ALT, fg=C.MUTED)
        self._last.configure(text="等待按键…")
        self._stats.configure(text="已测试 0 个按键")


class MouseTestWindow(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("鼠标测试")
        self.configure(bg=C.BG)
        self.resizable(False, False)
        _center(self, 900, 620)
        self._counts = {"left": 0, "right": 0, "middle": 0, "double": 0, "wheel": 0}
        self._dots: list[int] = []

        header = tk.Frame(self, bg=C.BG)
        header.pack(fill="x", padx=22, pady=(18, 8))
        tk.Label(
            header,
            text="鼠标测试",
            bg=C.BG,
            fg=C.TEXT,
            font=FONTS["title"],
        ).pack(side="left")
        tk.Label(
            header,
            text="在下方区域移动、点击、双击和滚轮",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["small"],
        ).pack(side="left", padx=(14, 0), pady=(3, 0))
        tk.Button(
            header,
            text="关闭",
            command=self.destroy,
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            activebackground=C.SURFACE_HOVER,
            activeforeground=C.TEXT,
            relief="flat",
            bd=0,
            font=FONTS["small"],
            padx=14,
            pady=6,
            cursor="hand2",
        ).pack(side="right")

        self._stats = tk.Label(
            self,
            text="左键 0  ·  右键 0  ·  中键 0  ·  双击 0  ·  滚轮 0",
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            font=FONTS["small"],
            anchor="w",
            padx=14,
            pady=9,
        )
        self._stats.pack(fill="x", padx=22, pady=(0, 8))
        self._pos = tk.Label(
            self,
            text="坐标 0, 0",
            bg=C.BG,
            fg=C.MUTED,
            font=FONTS["tiny"],
            anchor="w",
        )
        self._pos.pack(fill="x", padx=24, pady=(0, 5))

        self._canvas = tk.Canvas(
            self,
            bg=C.SURFACE,
            highlightthickness=1,
            highlightbackground=C.BORDER,
            cursor="crosshair",
        )
        self._canvas.pack(fill="both", expand=True, padx=22)
        self._canvas.bind("<Motion>", self._motion)
        self._canvas.bind("<ButtonPress-1>", self._left)
        self._canvas.bind("<ButtonPress-2>", self._middle)
        self._canvas.bind("<ButtonPress-3>", self._right)
        self._canvas.bind("<Double-Button-1>", self._double)
        self._canvas.bind("<MouseWheel>", self._wheel)
        self._canvas.bind("<Configure>", lambda _e: self._grid())
        self.bind("<Left>", lambda _e: self._move(-8, 0))
        self.bind("<Right>", lambda _e: self._move(8, 0))
        self.bind("<Up>", lambda _e: self._move(0, -8))
        self.bind("<Down>", lambda _e: self._move(0, 8))
        self._x = self._y = 0
        self._cross_x = self._cross_y = 0
        self._draw_crosshair()

        footer = tk.Frame(self, bg=C.BG)
        footer.pack(fill="x", padx=22, pady=12)
        tk.Label(
            footer,
            text="双击和单击分别计数；滚轮计数只统计向上/向下滚动。",
            bg=C.BG,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
        ).pack(side="left")
        tk.Button(
            footer,
            text="重置",
            command=self._reset,
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            activebackground=C.SURFACE_HOVER,
            activeforeground=C.TEXT,
            relief="flat",
            bd=0,
            font=FONTS["small"],
            padx=14,
            pady=6,
            cursor="hand2",
        ).pack(side="right")
        self.lift()
        self.focus_force()

    def _grid(self) -> None:
        self._canvas.delete("grid")
        width = max(1, self._canvas.winfo_width())
        height = max(1, self._canvas.winfo_height())
        step = 40
        for x in range(0, width, step):
            self._canvas.create_line(x, 0, x, height, fill=C.BORDER, tags="grid")
        for y in range(0, height, step):
            self._canvas.create_line(0, y, width, y, fill=C.BORDER, tags="grid")
        self._canvas.tag_lower("grid")

    def _draw_crosshair(self) -> None:
        self._canvas.delete("cross")
        width = max(1, self._canvas.winfo_width())
        height = max(1, self._canvas.winfo_height())
        self._canvas.create_line(
            self._cross_x, 0, self._cross_x, height, fill=C.ACCENT, dash=(4, 4), tags="cross"
        )
        self._canvas.create_line(
            0, self._cross_y, width, self._cross_y, fill=C.ACCENT, dash=(4, 4), tags="cross"
        )

    def _motion(self, event: tk.Event) -> None:
        self._x, self._y = event.x, event.y
        self._cross_x, self._cross_y = event.x, event.y
        self._pos.configure(text=f"坐标 {event.x}, {event.y}")
        self._draw_crosshair()

    def _mark(self, event: tk.Event, color: str) -> None:
        dot = self._canvas.create_oval(
            event.x - 5, event.y - 5, event.x + 5, event.y + 5,
            fill=color, outline=color, tags="dot",
        )
        self._dots.append(dot)
        if len(self._dots) > 80:
            self._canvas.delete(self._dots.pop(0))

    def _refresh(self) -> None:
        counts = self._counts
        self._stats.configure(
            text=(
                f"左键 {counts['left']}  ·  右键 {counts['right']}  ·  "
                f"中键 {counts['middle']}  ·  双击 {counts['double']}  ·  "
                f"滚轮 {counts['wheel']}"
            )
        )

    def _left(self, event: tk.Event) -> None:
        self._counts["left"] += 1
        self._mark(event, C.ACCENT)
        self._refresh()

    def _right(self, event: tk.Event) -> None:
        self._counts["right"] += 1
        self._mark(event, C.AMBER)
        self._refresh()

    def _middle(self, event: tk.Event) -> None:
        self._counts["middle"] += 1
        self._mark(event, C.PURPLE)
        self._refresh()

    def _double(self, event: tk.Event) -> None:
        self._counts["double"] += 1
        self._mark(event, C.GREEN)
        self._refresh()

    def _wheel(self, event: tk.Event) -> None:
        if event.delta:
            self._counts["wheel"] += 1
            self._refresh()

    def _move(self, dx: int, dy: int) -> None:
        self._x += dx
        self._y += dy
        self._cross_x, self._cross_y = self._x, self._y
        self._pos.configure(text=f"坐标 {self._x}, {self._y}")
        self._draw_crosshair()

    def _reset(self) -> None:
        self._counts = {key: 0 for key in self._counts}
        self._canvas.delete("dot")
        self._dots.clear()
        self._refresh()
        self._pos.configure(text="坐标 0, 0")
