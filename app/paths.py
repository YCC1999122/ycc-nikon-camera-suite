"""Project-root resolution that also works inside a packaged exe.
/ 项目根目录定位：源码运行时取项目目录，打包为 exe 后取 exe 所在目录，
保证 downloads / assets / devices.json 等都在 exe 旁边。"""
from __future__ import annotations

import os
import sys


def project_root() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller bundle / 打包后的 exe
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
