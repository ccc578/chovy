#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chovy —— 轻量离线桌面图像处理软件

启动入口。先确保第三方依赖（PySide6 可能安装在 vendor 目录）可被导入，
再运行主程序。
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))

# 让 app 包与 vendor 目录（PySide6 短路径安装目录）可被导入
for _p in (_HERE, os.path.join(_HERE, "vendor")):
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from app.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
