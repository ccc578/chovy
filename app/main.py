# -*- coding: utf-8 -*-
"""程序入口。"""
from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # 自检模式：无界面运行核心逻辑并退出（隔离配置目录，避免污染真实记录）
    if "--selftest" in argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import tempfile
        os.environ.setdefault("CHOVY_CONFIG_DIR",
                              tempfile.mkdtemp(prefix="chovy_cfg_"))

    from PySide6.QtWidgets import QApplication

    app = QApplication(argv)
    app.setApplicationName("Chovy")
    app.setOrganizationName("Chovy")

    from app.theme import DARK_QSS
    app.setStyleSheet(DARK_QSS)

    from app import __version__
    from app.mainwindow import MainWindow

    window = MainWindow()
    window.show()

    # 支持命令行直接打开图片/文件夹
    for arg in argv[1:]:
        if arg.startswith("-"):
            continue
        if os.path.isdir(arg):
            window.open_folder(arg)
        elif os.path.isfile(arg):
            window.open_image(arg)
        break

    if "--selftest" in argv:
        from app.selftest import run
        return run(window, app)

    return app.exec()
