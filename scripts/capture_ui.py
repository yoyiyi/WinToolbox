"""开发辅助：启动界面、切换页面并截图。

用法:
    python scripts/capture_ui.py dashboard .runtime/dashboard.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wintoolbox.ui.app import ToolboxApp  # noqa: E402


def main() -> None:
    page = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
    output = Path(sys.argv[2] if len(sys.argv) > 2 else ".runtime/ui.png")
    output.parent.mkdir(parents=True, exist_ok=True)

    app = ToolboxApp()
    geometry = os.environ.get("CAPTURE_GEOMETRY")
    if geometry:
        app.geometry(geometry)
    app.attributes("-topmost", True)
    app.lift()
    app.focus_force()

    def switch() -> None:
        app.navigate(page)

    def capture() -> None:
        app.update_idletasks()
        x = app.winfo_rootx()
        y = app.winfo_rooty()
        w = app.winfo_width()
        h = app.winfo_height()
        image = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
        image.save(output)
        print(f"saved {output} {image.size}")
        app._on_close()

    delay = int(os.environ.get("CAPTURE_DELAY_MS", "3200"))
    app.after(700, switch)
    app.after(delay, capture)
    app.mainloop()


if __name__ == "__main__":
    main()
