"""页面基类。"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from ..theme import C


class BasePage(tk.Frame):
    page_id = "base"
    page_title = ""
    page_subtitle = ""

    def __init__(self, app: Any, parent: tk.Misc) -> None:
        super().__init__(parent, bg=C.BG)
        self.app = app
        self.services = app.services
        self.state = app.state
        self.build()

    def build(self) -> None:
        raise NotImplementedError

    def on_show(self) -> None:
        pass

    def on_hide(self) -> None:
        pass

    def refresh(self) -> None:
        """F5 / 刷新按钮调用。"""

    def set_status(self, text: str, kind: str = "normal") -> None:
        self.app.set_status(text, kind)
