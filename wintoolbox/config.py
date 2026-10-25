"""轻量配置持久化。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .utils import app_data_dir, get_logger

DEFAULT_CONFIG: dict[str, Any] = {
    "geometry": "1360x860",
    "process_auto_refresh": True,
    "uninstall_use_quiet": False,
    "last_page": "dashboard",
}


class Config:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (app_data_dir() / "config.json")
        self.data: dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
                if isinstance(raw, dict):
                    self.data.update(raw)
        except (OSError, ValueError):
            get_logger("config").exception("读取配置失败，使用默认配置")

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(
                prefix="config-", suffix=".tmp", dir=str(self.path.parent)
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh, ensure_ascii=False, indent=2)
            os.replace(temp_name, self.path)
        except OSError:
            get_logger("config").exception("保存配置失败")
