"""验机工具独立页面。"""

from __future__ import annotations

from .base import BasePage
from .tools_panel import ToolsPanel


class ToolsPage(BasePage):
    page_id = "tools"

    def build(self) -> None:
        self._panel = ToolsPanel(self, self.app, self.services)

    def on_show(self) -> None:
        self._panel.on_show()

    def refresh(self) -> None:
        self._panel.refresh()
