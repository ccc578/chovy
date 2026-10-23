# -*- coding: utf-8 -*-
"""最近记录与设置的持久化（本地 JSON，完全离线）。"""
from __future__ import annotations

import json
import os
from typing import Optional

_APP_DIR = os.environ.get("CHOVY_CONFIG_DIR") or os.path.join(
    os.path.expanduser("~"), ".chovy")
_CONFIG_PATH = os.path.join(_APP_DIR, "config.json")

_DEFAULT = {
    "recent_files": [],   # [(path, opened_at_epoch), ...] 最新在前
    "recent_folders": [],  # [path, ...]
    "last_open_dir": "",
    "last_save_dir": "",
}


def _ensure_dir() -> None:
    os.makedirs(_APP_DIR, exist_ok=True)


def load() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return dict(_DEFAULT)
    for k, v in _DEFAULT.items():
        data.setdefault(k, v)
    return data


def save(config: dict) -> None:
    _ensure_dir()
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def add_recent_file(config: dict, path: str) -> dict:
    import time
    path = os.path.abspath(path)
    config["recent_files"] = [
        (p, t) for p, t in config.get("recent_files", []) if p != path
    ]
    config["recent_files"].insert(0, (path, time.time()))
    config["recent_files"] = config["recent_files"][:20]
    return config


def add_recent_folder(config: dict, path: str) -> dict:
    path = os.path.abspath(path)
    folders = config.get("recent_folders", [])
    folders = [p for p in folders if p != path]
    folders.insert(0, path)
    config["recent_folders"] = folders[:10]
    return config


def recent_file_paths(config: dict) -> list[str]:
    return [p for p, _ in config.get("recent_files", [])]
