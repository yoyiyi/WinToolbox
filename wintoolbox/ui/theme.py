"""深色主题、字体与 ttk 样式。"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


class C:
    BG = "#0A1120"
    SIDEBAR = "#0D1728"
    SIDEBAR_HOVER = "#132139"
    SURFACE = "#111C2E"
    SURFACE_ALT = "#15233A"
    SURFACE_HOVER = "#1A2C48"
    BORDER = "#22334D"
    BORDER_LIGHT = "#304867"
    TEXT = "#EDF4FF"
    TEXT_SOFT = "#C4D2E6"
    MUTED = "#879BB7"
    MUTED_DARK = "#647894"
    ACCENT = "#4F8DFD"
    ACCENT_HOVER = "#6AA1FF"
    ACCENT_DARK = "#1D3A66"
    CYAN = "#22D3EE"
    GREEN = "#34D399"
    GREEN_DARK = "#143C33"
    AMBER = "#FBBF24"
    AMBER_DARK = "#3D3015"
    RED = "#F87171"
    RED_DARK = "#421F27"
    PURPLE = "#A78BFA"
    WHITE = "#FFFFFF"


FONTS: dict[str, tuple] = {}
ICON_FONT = "Segoe MDL2 Assets"


def _pick_font(families: set[str], candidates: tuple[str, ...], fallback: str) -> str:
    for name in candidates:
        if name in families:
            return name
    return fallback


def init_fonts(root: tk.Misc) -> None:
    global ICON_FONT
    families = {name.casefold(): name for name in tkfont.families(root)}
    ui_family = _pick_font(
        families,
        ("microsoft yahei ui", "microsoft yahei", "segoe ui", "noto sans cjk sc"),
        "TkDefaultFont",
    )
    mono_family = _pick_font(
        families, ("cascadia mono", "consolas", "sarasa mono sc"), "Courier New"
    )
    icon_family = _pick_font(
        families, ("segoe fluent icons", "segoe mdl2 assets"), "Segoe UI Symbol"
    )
    ICON_FONT = icon_family
    FONTS.clear()
    FONTS.update(
        {
            "display": (ui_family, 23, "bold"),
            "title": (ui_family, 16, "bold"),
            "subtitle": (ui_family, 11),
            "body": (ui_family, 10),
            "body_bold": (ui_family, 10, "bold"),
            "small": (ui_family, 9),
            "small_bold": (ui_family, 9, "bold"),
            "tiny": (ui_family, 8),
            "metric": (ui_family, 24, "bold"),
            "metric_sm": (ui_family, 17, "bold"),
            "icon": (icon_family, 14),
            "icon_lg": (icon_family, 20),
            "icon_xl": (icon_family, 28),
            "mono": (mono_family, 9),
            "mono_sm": (mono_family, 8),
        }
    )


def apply_theme(root: tk.Tk) -> ttk.Style:
    init_fonts(root)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.configure(bg=C.BG)
    root.option_add("*Menu.background", C.SURFACE_ALT)
    root.option_add("*Menu.foreground", C.TEXT)
    root.option_add("*Menu.activeBackground", C.ACCENT_DARK)
    root.option_add("*Menu.activeForeground", C.TEXT)
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.relief", "flat")
    root.option_add("*TCombobox*Listbox.background", C.SURFACE_ALT)
    root.option_add("*TCombobox*Listbox.foreground", C.TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", C.ACCENT_DARK)
    root.option_add("*TCombobox*Listbox.selectForeground", C.TEXT)

    style.configure(".", background=C.BG, foreground=C.TEXT, font=FONTS["body"])
    style.configure("TFrame", background=C.BG)
    style.configure("Surface.TFrame", background=C.SURFACE)

    style.configure(
        "Treeview",
        background=C.SURFACE,
        fieldbackground=C.SURFACE,
        foreground=C.TEXT_SOFT,
        borderwidth=0,
        relief="flat",
        rowheight=34,
        font=FONTS["small"],
    )
    style.map(
        "Treeview",
        background=[("selected", "#1D3A60")],
        foreground=[("selected", C.WHITE)],
    )
    style.configure(
        "Treeview.Heading",
        background=C.SURFACE_ALT,
        foreground=C.MUTED,
        borderwidth=0,
        relief="flat",
        padding=(10, 9),
        font=FONTS["small_bold"],
    )
    style.map(
        "Treeview.Heading",
        background=[("active", C.SURFACE_HOVER)],
        foreground=[("active", C.TEXT_SOFT)],
    )

    for orient in ("Vertical", "Horizontal"):
        style.configure(
            f"{orient}.TScrollbar",
            background=C.SURFACE_HOVER,
            troughcolor=C.BG,
            bordercolor=C.BG,
            arrowcolor=C.MUTED,
            borderwidth=0,
            width=10 if orient == "Vertical" else 10,
        )
        style.map(
            f"{orient}.TScrollbar",
            background=[("active", C.BORDER_LIGHT), ("pressed", C.ACCENT_DARK)],
        )

    style.configure(
        "TCombobox",
        fieldbackground=C.SURFACE_ALT,
        foreground=C.TEXT,
        background=C.SURFACE_ALT,
        arrowcolor=C.MUTED,
        bordercolor=C.BORDER,
        lightcolor=C.BORDER,
        darkcolor=C.BORDER,
        padding=(8, 6),
        font=FONTS["small"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", C.SURFACE_ALT)],
        foreground=[("readonly", C.TEXT)],
        bordercolor=[("focus", C.ACCENT), ("hover", C.BORDER_LIGHT)],
        arrowcolor=[("active", C.TEXT)],
    )

    style.configure(
        "TCheckbutton",
        background=C.SURFACE,
        foreground=C.TEXT_SOFT,
        font=FONTS["small"],
        focuscolor=C.SURFACE,
        padding=(0, 2),
    )
    style.map(
        "TCheckbutton",
        background=[("active", C.SURFACE)],
        foreground=[("active", C.TEXT)],
        indicatorcolor=[("selected", C.ACCENT), ("!selected", C.SURFACE_ALT)],
    )

    style.configure(
        "TProgressbar",
        background=C.ACCENT,
        troughcolor=C.SURFACE_ALT,
        bordercolor=C.SURFACE_ALT,
        lightcolor=C.ACCENT,
        darkcolor=C.ACCENT,
        thickness=6,
    )
    style.configure(
        "Green.Horizontal.TProgressbar",
        background=C.GREEN,
        lightcolor=C.GREEN,
        darkcolor=C.GREEN,
    )
    style.configure(
        "Amber.Horizontal.TProgressbar",
        background=C.AMBER,
        lightcolor=C.AMBER,
        darkcolor=C.AMBER,
    )
    style.configure(
        "Cyan.Horizontal.TProgressbar",
        background=C.CYAN,
        lightcolor=C.CYAN,
        darkcolor=C.CYAN,
    )

    style.configure("TSeparator", background=C.BORDER)
    style.configure(
        "TNotebook", background=C.BG, borderwidth=0, tabmargins=(0, 0, 0, 0)
    )
    style.configure(
        "TNotebook.Tab",
        background=C.SURFACE,
        foreground=C.MUTED,
        padding=(16, 8),
        borderwidth=0,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", C.SURFACE_ALT)],
        foreground=[("selected", C.TEXT)],
    )
    style.configure(
        "Hardware.TNotebook",
        background=C.BG,
        borderwidth=0,
        tabmargins=(0, 0, 0, 0),
    )
    style.configure(
        "Hardware.TNotebook.Tab",
        background=C.SURFACE,
        foreground=C.MUTED,
        padding=(20, 9),
        borderwidth=0,
        lightcolor=C.SURFACE,
        darkcolor=C.SURFACE,
    )
    style.map(
        "Hardware.TNotebook.Tab",
        background=[("selected", C.SURFACE_ALT), ("active", C.SURFACE_HOVER)],
        foreground=[("selected", C.TEXT), ("active", C.TEXT_SOFT)],
        lightcolor=[("selected", C.SURFACE_ALT)],
        darkcolor=[("selected", C.SURFACE_ALT)],
    )
    return style
