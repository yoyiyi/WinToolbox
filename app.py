"""WinToolbox 入口。

直接运行：
    python app.py
"""

from __future__ import annotations

import sys


def main() -> int:
    if "--version" in sys.argv:
        from wintoolbox import __version__

        print(__version__)
        return 0
    if "--headless" in sys.argv or "--report" in sys.argv:
        from wintoolbox.headless import run_headless

        return run_headless(sys.argv[1:])
    from wintoolbox.ui.app import run

    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
