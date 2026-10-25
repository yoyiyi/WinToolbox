"""WinToolbox 入口。

直接运行：
    python app.py
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def _write_startup_error() -> None:
    """窗口化 exe 没有控制台，把早期异常落盘以便诊断。"""
    detail = traceback.format_exc()
    candidates = []
    local = Path.home() / "AppData" / "Local"
    candidates.append(local / "WinToolbox" / "logs" / "startup-error.log")
    candidates.append(Path(__file__).resolve().parent / "startup-error.log")
    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(detail, encoding="utf-8")
            return
        except OSError:
            continue


def main() -> int:
    if "--version" in sys.argv:
        from wintoolbox import __version__

        print(__version__)
        return 0
    if "--headless" in sys.argv or "--report" in sys.argv:
        from wintoolbox.headless import run_headless

        return run_headless(sys.argv[1:])
    if not os.environ.get("WINTOOLBOX_HOME"):
        local = os.environ.get("LOCALAPPDATA") or str(
            Path.home() / "AppData" / "Local"
        )
        os.environ["WINTOOLBOX_HOME"] = str(Path(local) / "WinToolboxData")
    try:
        from wintoolbox.ui.app import run

        run()
    except BaseException:
        _write_startup_error()
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
