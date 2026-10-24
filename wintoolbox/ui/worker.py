"""主线程安全的后台任务调度。"""

from __future__ import annotations

import queue
import threading
import traceback
from collections.abc import Callable
from typing import Any

import tkinter as tk

from ..utils import get_logger


class TaskRunner:
    """每个任务一个 daemon 线程；结果通过队列回到 Tk 主线程。"""

    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self._queue: queue.Queue[tuple[str, Callable | None, Any]] = queue.Queue()
        self._closed = False
        self._after_id = self.root.after(40, self._drain)

    def submit(
        self,
        work: Callable[[], Any],
        on_done: Callable[[Any], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
        name: str = "task",
    ) -> None:
        if self._closed:
            return

        def runner() -> None:
            try:
                result = work()
            except Exception as exc:  # 所有后台异常都必须返回主线程
                get_logger(name).exception("后台任务失败: %s", name)
                self._queue.put(("error", on_error, (exc, traceback.format_exc())))
            else:
                self._queue.put(("done", on_done, result))

        thread = threading.Thread(target=runner, name=f"wintoolbox-{name}", daemon=True)
        thread.start()

    def post(self, callback: Callable[[], Any]) -> None:
        """从任意线程投递一个主线程回调。"""
        if not self._closed:
            self._queue.put(("call", None, callback))

    def _drain(self) -> None:
        if self._closed:
            return
        for _ in range(80):
            try:
                kind, callback, payload = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                if kind == "done" and callback:
                    callback(payload)
                elif kind == "error" and callback:
                    callback(payload[0])
                elif kind == "call" and payload:
                    payload()
            except Exception:
                get_logger("ui").exception("主线程任务回调失败")
        try:
            self._after_id = self.root.after(40, self._drain)
        except tk.TclError:
            self._closed = True

    def shutdown(self) -> None:
        self._closed = True
        try:
            self.root.after_cancel(self._after_id)
        except (tk.TclError, AttributeError):
            pass
