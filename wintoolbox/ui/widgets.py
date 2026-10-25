"""可复用的 Tkinter 控件。"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable, Sequence
from tkinter import ttk
from typing import Any

from .theme import C, FONTS, ICON_FONT


def _bind_recursive(widget: tk.Misc, sequence: str, callback: Callable) -> None:
    widget.bind(sequence, callback)
    for child in widget.winfo_children():
        _bind_recursive(child, sequence, callback)


class FlatButton(tk.Frame):
    VARIANTS = {
        "accent": (C.ACCENT, C.WHITE, C.ACCENT_HOVER, C.ACCENT, C.ACCENT_DARK),
        "secondary": (C.SURFACE_ALT, C.TEXT_SOFT, C.SURFACE_HOVER, C.BORDER, C.MUTED_DARK),
        "ghost": (C.SURFACE, C.MUTED, C.SURFACE_ALT, C.SURFACE, C.MUTED_DARK),
        "danger": (C.RED_DARK, C.RED, "#56252F", "#6B303B", "#8A5A62"),
        "success": (C.GREEN_DARK, C.GREEN, "#1B4A3F", "#27604F", "#6B8F85"),
        "sidebar": (C.SIDEBAR, C.TEXT_SOFT, C.SIDEBAR_HOVER, C.SIDEBAR, C.MUTED_DARK),
    }

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None] | None = None,
        variant: str = "secondary",
        icon: str = "",
        compact: bool = False,
        bold: bool = False,
        padx: int = 14,
        pady: int = 8,
    ) -> None:
        self._enabled = True
        self._command = command
        self._variant = variant
        bg, fg, hover, border, disabled = self.VARIANTS.get(variant, self.VARIANTS["secondary"])
        super().__init__(
            parent,
            bg=bg,
            highlightthickness=0 if variant in {"accent", "ghost", "sidebar"} else 1,
            highlightbackground=border,
            highlightcolor=border,
            cursor="hand2",
        )
        self._bg, self._fg, self._hover, self._border = bg, fg, hover, border
        self._disabled_fg = disabled
        self._labels: list[tk.Label] = []
        inner_padx = 9 if compact else padx
        inner_pady = 5 if compact else pady
        if icon:
            icon_label = tk.Label(
                self,
                text=icon,
                bg=bg,
                fg=fg,
                font=(ICON_FONT, 12 if compact else 13),
                padx=0,
                pady=0,
            )
            icon_label.pack(side="left", padx=(inner_padx, 6), pady=inner_pady)
            self._labels.append(icon_label)
        text_label = tk.Label(
            self,
            text=text,
            bg=bg,
            fg=fg,
            font=FONTS["small_bold"] if (bold or variant == "accent") else FONTS["small"],
            padx=0,
            pady=0,
        )
        text_label.pack(
            side="left",
            padx=(0 if icon else inner_padx, inner_padx),
            pady=inner_pady,
        )
        self._labels.append(text_label)
        self._text_label = text_label
        _bind_recursive(self, "<Enter>", self._on_enter)
        _bind_recursive(self, "<Leave>", self._on_leave)
        _bind_recursive(self, "<Button-1>", self._on_click)

    def _on_enter(self, _event: tk.Event) -> None:
        if self._enabled:
            self.configure(bg=self._hover)
            for label in self._labels:
                label.configure(bg=self._hover)

    def _on_leave(self, _event: tk.Event) -> None:
        if self._enabled:
            self.configure(bg=self._bg)
            for label in self._labels:
                label.configure(bg=self._bg)

    def _on_click(self, _event: tk.Event) -> None:
        if self._enabled and self._command:
            self._command()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        fg = self._fg if enabled else self._disabled_fg
        for label in self._labels:
            label.configure(fg=fg)
        if not enabled:
            self.configure(bg=self._bg)
            for label in self._labels:
                label.configure(bg=self._bg)

    def set_text(self, text: str) -> None:
        self._text_label.configure(text=text)

    def set_command(self, command: Callable[[], None] | None) -> None:
        self._command = command


class SidebarItem(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        icon: str,
        text: str,
        command: Callable[[], None],
        shortcut: str = "",
    ) -> None:
        super().__init__(parent, bg=C.SIDEBAR, height=36, cursor="hand2")
        self._command = command
        self._selected = False
        self.pack_propagate(False)
        self._bar = tk.Frame(self, bg=C.SIDEBAR, width=3)
        self._bar.pack(side="left", fill="y")
        self._icon = tk.Label(
            self,
            text=icon,
            bg=C.SIDEBAR,
            fg=C.MUTED,
            font=(ICON_FONT, 14),
            width=3,
        )
        self._icon.pack(side="left", padx=(4, 0))
        self._text = tk.Label(
            self,
            text=text,
            bg=C.SIDEBAR,
            fg=C.TEXT_SOFT,
            font=FONTS["body"],
            anchor="w",
        )
        self._text.pack(side="left", fill="x", expand=True)
        self._shortcut = tk.Label(
            self,
            text=shortcut,
            bg=C.SIDEBAR,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            padx=14,
        )
        self._shortcut.pack(side="right")
        self._parts = (self._bar, self._icon, self._text, self._shortcut)
        for part in self._parts:
            part.bind("<Button-1>", self._click)
            part.bind("<Enter>", self._enter)
            part.bind("<Leave>", self._leave)
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    def _click(self, _event: tk.Event) -> None:
        self._command()

    def _enter(self, _event: tk.Event) -> None:
        if not self._selected:
            self._paint(C.SIDEBAR_HOVER, C.TEXT, C.ACCENT)

    def _leave(self, _event: tk.Event) -> None:
        if not self._selected:
            self._paint(C.SIDEBAR, C.TEXT_SOFT, C.MUTED)

    def _paint(self, bg: str, text_fg: str, icon_fg: str, bar_bg: str | None = None) -> None:
        self.configure(bg=bg)
        for part in self._parts:
            if part is not self._bar:
                part.configure(bg=bg)
        self._text.configure(fg=text_fg)
        self._icon.configure(fg=icon_fg)
        if bar_bg is not None:
            self._bar.configure(bg=bar_bg)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self._paint(C.SIDEBAR_HOVER, C.TEXT, C.ACCENT, C.ACCENT)
        else:
            self._paint(C.SIDEBAR, C.TEXT_SOFT, C.MUTED, C.SIDEBAR)


class Card(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        padding: int = 18,
        border: str = C.BORDER,
        bg: str = C.SURFACE,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            parent,
            bg=bg,
            highlightbackground=border,
            highlightcolor=border,
            highlightthickness=1,
            bd=0,
            **kwargs,
        )
        self.inner = tk.Frame(self, bg=bg)
        self.inner.pack(fill="both", expand=True, padx=padding, pady=padding)


class StatCard(Card):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        value: str,
        hint: str,
        icon: str,
        accent: str,
        command: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent, padding=14)
        self._command = command
        self._accent = accent
        self._normal_border = C.BORDER
        top = tk.Frame(self.inner, bg=C.SURFACE)
        top.pack(fill="x")
        self._title = tk.Label(
            top,
            text=title,
            bg=C.SURFACE,
            fg=C.MUTED,
            font=FONTS["small"],
            anchor="w",
        )
        self._title.pack(side="left")
        self._icon = tk.Label(
            top,
            text=icon,
            bg=C.SURFACE,
            fg=accent,
            font=(ICON_FONT, 16),
        )
        self._icon.pack(side="right")
        self._value = tk.Label(
            self.inner,
            text=value,
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["metric"] if str(value).isdigit() else FONTS["metric_sm"],
            anchor="w",
        )
        self._value.pack(fill="x", pady=(5, 1))
        self._hint = tk.Label(
            self.inner,
            text=hint,
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
            anchor="w",
        )
        self._hint.pack(fill="x")
        if command:
            self.configure(cursor="hand2")
            _bind_recursive(self, "<Enter>", self._enter)
            _bind_recursive(self, "<Leave>", self._leave)
            _bind_recursive(self, "<Button-1>", self._click)

    def set_value(self, value: str, hint: str | None = None) -> None:
        font = FONTS["metric"] if str(value).isdigit() else FONTS["metric_sm"]
        self._value.configure(text=value, font=font)
        if hint is not None:
            self._hint.configure(text=hint)

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self._icon.configure(fg=accent)

    def _enter(self, _event: tk.Event) -> None:
        self.configure(highlightbackground=self._accent, highlightcolor=self._accent)

    def _leave(self, _event: tk.Event) -> None:
        self.configure(highlightbackground=self._normal_border, highlightcolor=self._normal_border)

    def _click(self, _event: tk.Event) -> None:
        if self._command:
            self._command()


class SearchBox(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        placeholder: str = "搜索…",
        width: int = 30,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(
            parent,
            bg=C.SURFACE_ALT,
            highlightbackground=C.BORDER,
            highlightcolor=C.BORDER,
            highlightthickness=1,
        )
        self._placeholder = placeholder
        self._showing_placeholder = False
        self._on_change = on_change
        self._icon = tk.Label(
            self,
            text="\uE721",
            bg=C.SURFACE_ALT,
            fg=C.MUTED_DARK,
            font=(ICON_FONT, 11),
            padx=9,
        )
        self._icon.pack(side="left")
        self.var = tk.StringVar()
        self.entry = tk.Entry(
            self,
            textvariable=self.var,
            bg=C.SURFACE_ALT,
            fg=C.TEXT_SOFT,
            insertbackground=C.TEXT,
            relief="flat",
            bd=0,
            font=FONTS["small"],
            width=width,
        )
        self.entry.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=7)
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.entry.bind("<KeyRelease>", self._changed)
        self.entry.bind("<Escape>", lambda _e: self.clear())
        self._show_placeholder()

    def _show_placeholder(self) -> None:
        if not self.var.get():
            self._showing_placeholder = True
            self.var.set(self._placeholder)
            self.entry.configure(fg=C.MUTED_DARK)

    def _focus_in(self, _event: tk.Event) -> None:
        self.configure(highlightbackground=C.ACCENT, highlightcolor=C.ACCENT)
        if self._showing_placeholder:
            self.var.set("")
            self._showing_placeholder = False
            self.entry.configure(fg=C.TEXT_SOFT)

    def _focus_out(self, _event: tk.Event) -> None:
        self.configure(highlightbackground=C.BORDER, highlightcolor=C.BORDER)
        if not self.var.get().strip():
            self._show_placeholder()

    def _changed(self, _event: tk.Event) -> None:
        if self._showing_placeholder:
            return
        if self._on_change:
            self._on_change()

    def get(self) -> str:
        if self._showing_placeholder:
            return ""
        return self.var.get().strip()

    def clear(self) -> None:
        self._showing_placeholder = False
        self.var.set("")
        self.entry.configure(fg=C.TEXT_SOFT)
        if self._on_change:
            self._on_change()

    def set_text(self, text: str) -> None:
        self._showing_placeholder = False
        self.var.set(text)
        self.entry.configure(fg=C.TEXT_SOFT)


class Badge(tk.Label):
    VARIANTS = {
        "neutral": (C.SURFACE_ALT, C.MUTED),
        "accent": (C.ACCENT_DARK, "#9EC1FF"),
        "green": (C.GREEN_DARK, C.GREEN),
        "amber": (C.AMBER_DARK, C.AMBER),
        "red": (C.RED_DARK, C.RED),
        "cyan": ("#103B45", C.CYAN),
        "purple": ("#2A2442", C.PURPLE),
    }

    def __init__(
        self,
        parent: tk.Misc,
        text: str,
        variant: str = "neutral",
        font: tuple | None = None,
        padx: int = 9,
        pady: int = 3,
    ) -> None:
        bg, fg = self.VARIANTS.get(variant, self.VARIANTS["neutral"])
        super().__init__(
            parent,
            text=text,
            bg=bg,
            fg=fg,
            font=font or FONTS["tiny"],
            padx=padx,
            pady=pady,
        )


class Meter(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        label: str,
        value: str = "",
        color_style: str = "TProgressbar",
        bg: str = C.SURFACE,
    ) -> None:
        super().__init__(parent, bg=bg)
        top = tk.Frame(self, bg=bg)
        top.pack(fill="x")
        self._label = tk.Label(
            top, text=label, bg=bg, fg=C.MUTED, font=FONTS["small"], anchor="w"
        )
        self._label.pack(side="left")
        self._value = tk.Label(
            top, text=value, bg=bg, fg=C.TEXT_SOFT, font=FONTS["small_bold"], anchor="e"
        )
        self._value.pack(side="right")
        self.bar = ttk.Progressbar(
            self,
            style=color_style,
            maximum=100,
            mode="determinate",
            length=200,
        )
        self.bar.pack(fill="x", pady=(7, 0))

    def set(self, percent: float, value: str | None = None) -> None:
        self.bar["value"] = max(0.0, min(100.0, percent))
        if value is not None:
            self._value.configure(text=value)


class DataTable(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        columns: Sequence[tuple[str, str, int, str]],
        height: int = 12,
        selectmode: str = "browse",
        on_sort: Callable[[str], None] | None = None,
        on_select: Callable[[], None] | None = None,
        on_double: Callable[[], None] | None = None,
        horizontal_scrollbar: bool = True,
    ) -> None:
        super().__init__(parent, bg=C.SURFACE)
        self._columns = list(columns)
        self._on_sort = on_sort
        self._show_hscroll = horizontal_scrollbar
        keys = [column[0] for column in columns]
        self.tree = ttk.Treeview(
            self,
            columns=keys,
            show="headings",
            selectmode=selectmode,
            height=height,
        )
        for index, (key, title, width, anchor) in enumerate(columns):
            heading_options = {"text": title}
            if on_sort:
                heading_options["command"] = lambda k=key: self._on_sort(k)
            self.tree.heading(key, **heading_options)
            self.tree.column(
                key,
                width=width,
                minwidth=max(50, width // 2),
                anchor=anchor,
                stretch=(index == len(columns) - 1),
            )
        self.tree.grid(row=0, column=0, sticky="nsew")
        vscroll = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self._hscroll = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vscroll.set, xscrollcommand=self._hscroll.set)
        vscroll.grid(row=0, column=1, sticky="ns")
        if self._show_hscroll:
            self._hscroll.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._column_width = sum(column[2] for column in columns)
        self.tree.bind("<Configure>", self._sync_hscroll, add="+")
        self.after_idle(self._sync_hscroll)
        self.tree.tag_configure("odd", background=C.SURFACE)
        self.tree.tag_configure("even", background="#0F1A2B")
        self._empty = tk.Label(
            self,
            text="",
            bg=C.SURFACE,
            fg=C.MUTED_DARK,
            font=FONTS["body"],
            justify="center",
        )
        self._empty_visible = False
        if on_select:
            self.tree.bind("<<TreeviewSelect>>", lambda _e: on_select())
        if on_double:
            self.tree.bind("<Double-1>", lambda _e: on_double())

    def replace(
        self,
        rows: Iterable[tuple[str, Sequence[Any], Sequence[str]]],
        empty_text: str = "暂无数据",
    ) -> None:
        yview = self.tree.yview()
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        count = 0
        for iid, values, tags in rows:
            zebra = "odd" if count % 2 == 0 else "even"
            all_tags = (zebra,) + tuple(tags)
            self.tree.insert("", "end", iid=iid, values=tuple(values), tags=all_tags)
            count += 1
        if count == 0:
            self.show_empty(empty_text)
        else:
            self.hide_empty()
            still_present = [iid for iid in selected if self.tree.exists(iid)]
            if still_present:
                self.tree.selection_set(still_present)
            try:
                self.tree.yview_moveto(yview[0])
            except tk.TclError:
                pass

    def _sync_hscroll(self, _event: tk.Event | None = None) -> None:
        if not self._show_hscroll:
            return
        try:
            width = self.tree.winfo_width()
        except tk.TclError:
            return
        if width <= 1:
            return
        if width >= self._column_width - 4:
            self._hscroll.grid_remove()
        else:
            self._hscroll.grid()

    def show_empty(self, text: str) -> None:
        self._empty.configure(text=text)
        self._empty.place(relx=0.5, rely=0.5, anchor="center")
        self._empty.lift()
        self._empty_visible = True

    def hide_empty(self) -> None:
        if self._empty_visible:
            self._empty.place_forget()
            self._empty_visible = False

    @property
    def selected_iid(self) -> str:
        selection = self.tree.selection()
        return selection[0] if selection else ""

    def selected_values(self) -> tuple[Any, ...]:
        iid = self.selected_iid
        if not iid:
            return ()
        return tuple(self.tree.item(iid, "values"))

    def select_first(self) -> None:
        children = self.tree.get_children()
        if children and not self.tree.selection():
            self.tree.selection_set(children[0])
            self.tree.focus(children[0])


class EmptyState(tk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        message: str,
        icon: str = "\uE7C3",
        bg: str = C.SURFACE,
    ) -> None:
        super().__init__(parent, bg=bg)
        tk.Label(
            self,
            text=icon,
            bg=bg,
            fg=C.MUTED_DARK,
            font=(ICON_FONT, 28),
        ).pack(pady=(0, 6))
        tk.Label(
            self,
            text=title,
            bg=bg,
            fg=C.TEXT_SOFT,
            font=FONTS["body_bold"],
        ).pack()
        tk.Label(
            self,
            text=message,
            bg=bg,
            fg=C.MUTED_DARK,
            font=FONTS["small"],
            wraplength=320,
            justify="center",
        ).pack(pady=(5, 0))


class ScrollableFrame(tk.Frame):
    """带自动隐藏滚动条的纵向滚动区域。内容放在 `.inner` 中。"""

    def __init__(self, parent: tk.Misc, bg: str = C.SURFACE) -> None:
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(
            self,
            bg=bg,
            highlightthickness=0,
            bd=0,
            relief="flat",
        )
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self._scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._on_content)
        self.canvas.bind("<Configure>", self._on_canvas)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.after_idle(self._sync)
        self.after(120, self._sync)

    def _on_content(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._sync()

    def _on_canvas(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)
        self._sync()

    def _sync(self) -> None:
        try:
            bbox = self.canvas.bbox("all")
            content_height = (bbox[3] - bbox[1]) if bbox else 0
            view_height = self.canvas.winfo_height()
        except tk.TclError:
            return
        if content_height > view_height + 2:
            if not self._scroll.winfo_ismapped():
                self._scroll.grid(row=0, column=1, sticky="ns")
        else:
            if self._scroll.winfo_ismapped():
                self._scroll.grid_remove()
            self.canvas.yview_moveto(0)

    def refresh_layout(self) -> None:
        self.after_idle(self._sync)
        self.after(80, self._sync)

    def _on_wheel(self, event: tk.Event) -> str:
        if self._scroll.winfo_ismapped():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def bind_wheel_recursive(self) -> None:
        def bind(widget: tk.Misc) -> None:
            widget.bind("<MouseWheel>", self._on_wheel)
            for child in widget.winfo_children():
                bind(child)

        bind(self.inner)
        bind(self.canvas)


class LogView(tk.Frame):
    def __init__(self, parent: tk.Misc, height: int = 8) -> None:
        super().__init__(
            parent,
            bg=C.SURFACE_ALT,
            highlightbackground=C.BORDER,
            highlightcolor=C.BORDER,
            highlightthickness=1,
        )
        self.text = tk.Text(
            self,
            height=height,
            bg="#09111F",
            fg=C.TEXT_SOFT,
            insertbackground=C.TEXT,
            relief="flat",
            bd=0,
            font=FONTS["mono_sm"],
            padx=10,
            pady=8,
            wrap="word",
            state="disabled",
        )
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.text.tag_configure("command", foreground=C.CYAN)
        self.text.tag_configure("error", foreground=C.RED)
        self.text.tag_configure("success", foreground=C.GREEN)
        self.text.tag_configure("muted", foreground=C.MUTED_DARK)

    def append(self, line: str, kind: str = "normal") -> None:
        self.text.configure(state="normal")
        tag = () if kind == "normal" else (kind,)
        self.text.insert("end", line.rstrip() + "\n", tag)
        # 限制内存占用
        line_count = int(self.text.index("end-1c").split(".")[0])
        if line_count > 1600:
            self.text.delete("1.0", f"{line_count - 1200}.0")
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


class _Modal(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, width: int = 520) -> None:
        super().__init__(parent)
        self.result: Any = None
        self.withdraw()
        self.title(title)
        self.configure(bg=C.SURFACE)
        self.resizable(False, False)
        self.transient(parent)
        self._width = width
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.bind("<Escape>", lambda _e: self._cancel())

    def _center(self) -> None:
        self.update_idletasks()
        parent = self.master
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
        except tk.TclError:
            px = py = 0
            pw, ph = self.winfo_screenwidth(), self.winfo_screenheight()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        x = max(0, px + (pw - w) // 2)
        y = max(0, py + (ph - h) // 2)
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.grab_set()
        self.focus_force()

    def _cancel(self) -> None:
        self.result = False
        self.destroy()


class ConfirmDialog(_Modal):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        message: str,
        detail: str = "",
        confirm_text: str = "确认",
        danger: bool = False,
        width: int = 540,
    ) -> None:
        super().__init__(parent, title, width)
        self.result = False
        body = tk.Frame(self, bg=C.SURFACE, padx=24, pady=22)
        body.pack(fill="both", expand=True)
        head = tk.Frame(body, bg=C.SURFACE)
        head.pack(fill="x")
        tk.Label(
            head,
            text="!" if danger else "i",
            bg=C.RED_DARK if danger else C.ACCENT_DARK,
            fg=C.RED if danger else C.ACCENT,
            font=(FONTS["title"][0], 15, "bold"),
            width=2,
            height=1,
        ).pack(side="left", padx=(0, 12))
        tk.Label(
            head,
            text=title,
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["title"],
            anchor="w",
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            body,
            text=message,
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            font=FONTS["body"],
            anchor="w",
            justify="left",
            wraplength=width - 60,
        ).pack(fill="x", pady=(16, 0))
        if detail:
            detail_frame = tk.Frame(
                body,
                bg=C.SURFACE_ALT,
                highlightbackground=C.BORDER,
                highlightthickness=1,
            )
            detail_frame.pack(fill="x", pady=(14, 0))
            tk.Label(
                detail_frame,
                text=detail,
                bg=C.SURFACE_ALT,
                fg=C.MUTED,
                font=FONTS["mono_sm"],
                justify="left",
                anchor="w",
                wraplength=width - 80,
            ).pack(fill="x", padx=12, pady=10)
        actions = tk.Frame(body, bg=C.SURFACE)
        actions.pack(fill="x", pady=(20, 0))
        FlatButton(
            actions,
            confirm_text,
            command=self._confirm,
            variant="danger" if danger else "accent",
            padx=18,
        ).pack(side="right")
        FlatButton(
            actions,
            "取消",
            command=self._cancel,
            variant="secondary",
            padx=18,
        ).pack(side="right", padx=(0, 8))
        self.bind("<Return>", lambda _e: self._confirm())
        self._center()
        self.wait_window(self)

    def _confirm(self) -> None:
        self.result = True
        self.destroy()


def ask_confirm(
    parent: tk.Misc,
    title: str,
    message: str,
    detail: str = "",
    confirm_text: str = "确认",
    danger: bool = False,
) -> bool:
    dialog = ConfirmDialog(
        parent,
        title=title,
        message=message,
        detail=detail,
        confirm_text=confirm_text,
        danger=danger,
    )
    return bool(dialog.result)


class NoticeDialog(_Modal):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        message: str,
        detail: str = "",
        kind: str = "info",
        width: int = 540,
    ) -> None:
        super().__init__(parent, title, width)
        self.result = True
        body = tk.Frame(self, bg=C.SURFACE, padx=24, pady=22)
        body.pack(fill="both", expand=True)
        color = C.RED if kind == "error" else (C.AMBER if kind == "warning" else C.ACCENT)
        bg = C.RED_DARK if kind == "error" else (C.AMBER_DARK if kind == "warning" else C.ACCENT_DARK)
        mark = "!" if kind in {"error", "warning"} else "i"
        head = tk.Frame(body, bg=C.SURFACE)
        head.pack(fill="x")
        tk.Label(
            head,
            text=mark,
            bg=bg,
            fg=color,
            font=(FONTS["title"][0], 15, "bold"),
            width=2,
            height=1,
        ).pack(side="left", padx=(0, 12))
        tk.Label(
            head,
            text=title,
            bg=C.SURFACE,
            fg=C.TEXT,
            font=FONTS["title"],
            anchor="w",
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        tk.Label(
            body,
            text=message,
            bg=C.SURFACE,
            fg=C.TEXT_SOFT,
            font=FONTS["body"],
            anchor="w",
            justify="left",
            wraplength=width - 60,
        ).pack(fill="x", pady=(16, 0))
        if detail:
            text = tk.Text(
                body,
                height=min(12, max(3, detail.count("\n") + 1)),
                bg=C.SURFACE_ALT,
                fg=C.MUTED,
                relief="flat",
                bd=0,
                font=FONTS["mono_sm"],
                padx=10,
                pady=8,
                wrap="word",
            )
            text.pack(fill="both", expand=True, pady=(12, 0))
            text.insert("1.0", detail)
            text.configure(state="disabled")
        actions = tk.Frame(body, bg=C.SURFACE)
        actions.pack(fill="x", pady=(18, 0))
        FlatButton(
            actions, "知道了", command=self._ok, variant="accent", padx=20
        ).pack(side="right")
        self.bind("<Return>", lambda _e: self._ok())
        self._center()
        self.wait_window(self)

    def _ok(self) -> None:
        self.result = True
        self.destroy()


def show_notice(
    parent: tk.Misc,
    title: str,
    message: str,
    detail: str = "",
    kind: str = "info",
) -> None:
    NoticeDialog(parent, title=title, message=message, detail=detail, kind=kind)


def section_title(
    parent: tk.Misc,
    title: str,
    subtitle: str = "",
    bg: str = C.SURFACE,
) -> tk.Frame:
    frame = tk.Frame(parent, bg=bg)
    tk.Label(
        frame, text=title, bg=bg, fg=C.TEXT, font=FONTS["body_bold"], anchor="w"
    ).pack(side="left")
    if subtitle:
        tk.Label(
            frame,
            text=subtitle,
            bg=bg,
            fg=C.MUTED_DARK,
            font=FONTS["tiny"],
        ).pack(side="left", padx=(10, 0), pady=(2, 0))
    return frame
