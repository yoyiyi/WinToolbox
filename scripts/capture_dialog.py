"""开发辅助：打开关于对话框并截图。"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wintoolbox.ui.app import ToolboxApp  # noqa: E402


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else ".runtime/about.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    app = ToolboxApp()
    app.attributes("-topmost", True)
    app.after(1200, app.open_about)

    def capture() -> None:
        children = [child for child in app.winfo_children() if child.winfo_class() == "Toplevel"]
        dialog = children[-1] if children else app
        dialog.update_idletasks()
        x, y = dialog.winfo_rootx(), dialog.winfo_rooty()
        w, h = dialog.winfo_width(), dialog.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(output)
        print(f"saved {output} {w}x{h}")
        app._on_close()

    app.after(3000, capture)
    app.mainloop()


if __name__ == "__main__":
    main()
