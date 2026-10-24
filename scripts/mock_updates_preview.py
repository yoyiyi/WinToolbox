"""开发辅助：用假数据预览更新列表布局（不会执行升级）。"""

from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from wintoolbox.models import UpdatePackage, UpdateScanResult, WingetInfo  # noqa: E402
from wintoolbox.ui.app import ToolboxApp  # noqa: E402


class FakeWinget:
    def probe(self, force: bool = False) -> WingetInfo:
        return WingetInfo(available=True, version="v1.9.25200", path="C:\\winget.exe")

    def scan_updates(self) -> UpdateScanResult:
        packages = [
            ("Mozilla Firefox", "Mozilla.Firefox", "128.0.3", "130.0.1", "winget"),
            ("7-Zip 24.09 (x64)", "7zip.7zip", "24.09", "24.10", "winget"),
            ("Microsoft Teams", "Microsoft.Teams", "24152.1", "24215.2", "msstore"),
            ("Visual Studio Code", "Microsoft.VisualStudioCode", "1.94.2", "1.95.0", "winget"),
            ("PowerToys (Preview)", "Microsoft.PowerToys", "0.85.1", "0.86.0", "winget"),
            ("Git", "Git.Git", "2.46.0", "2.47.1", "winget"),
            ("Node.js LTS", "OpenJS.NodeJS.LTS", "20.18.0", "22.11.0", "winget"),
            ("VLC media player", "VideoLAN.VLC", "3.0.21", "3.0.22", "winget"),
            ("Spotify", "Spotify.Spotify", "1.2.45", "1.2.47", "winget"),
            ("Python 3.12", "Python.Python.3.12", "3.12.7", "3.12.8", "winget"),
        ]
        updates = [
            UpdatePackage(
                name=name,
                package_id=pid,
                current_version=current,
                available_version=available,
                source=source,
            )
            for name, pid, current, available, source in packages
        ]
        return UpdateScanResult(updates=updates, checked_at=datetime.now())


def main() -> None:
    output = Path(sys.argv[1] if len(sys.argv) > 1 else ".runtime/mock-updates.png")
    output.parent.mkdir(parents=True, exist_ok=True)
    app = ToolboxApp()
    app.attributes("-topmost", True)

    def configure() -> None:
        fake = FakeWinget()
        app.services["winget"] = fake
        result = fake.scan_updates()
        app.state.winget_info = fake.probe()
        app.state.winget_at = time.time()
        app.state.updates = result.updates
        app.state.updates_at = time.time()
        app.navigate("updates")
        page = app._pages["updates"]
        children = page._table.tree.get_children()
        if len(children) >= 2:
            page._table.tree.selection_set(children[:2])
            page._update_buttons()

    def capture() -> None:
        app.update_idletasks()
        x, y = app.winfo_rootx(), app.winfo_rooty()
        w, h = app.winfo_width(), app.winfo_height()
        ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True).save(output)
        print(f"saved {output} {w}x{h}")
        app._on_close()

    app.after(700, configure)
    app.after(3000, capture)
    app.mainloop()


if __name__ == "__main__":
    main()
