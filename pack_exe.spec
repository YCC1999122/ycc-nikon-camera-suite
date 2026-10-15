# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: single-file windowed exe for the camera suite.
# 打包说明：本机 PATH 里有其他软件自带的旧版 ICU(58) DLL，会被依赖分析误打包
# 导致 Qt6 无法加载；这里过滤掉所有非 PySide6 官方的 icu*.dll，
# 运行时与 venv 一样回退到系统 System32 的 icuuc.dll。

_BLOCK = {"icuuc.dll", "icudt.dll", "icuin.dll", "icudt58.dll", "icuin58.dll",
          "icuuc58.dll", "icudt64.dll", "icuin64.dll", "icuuc64.dll"}

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PIL"],
    noarchive=False,
)


def _base(entry) -> str:
    return entry[0].replace("\\", "/").rsplit("/", 1)[-1].lower()


a.binaries = [b for b in a.binaries if _base(b) not in _BLOCK]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="尼康相机管理",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
