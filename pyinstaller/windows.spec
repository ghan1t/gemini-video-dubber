# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path.cwd()
ffmpeg = root / "vendor" / "windows" / "ffmpeg.exe"
ffprobe = root / "vendor" / "windows" / "ffprobe.exe"
binaries = []
if ffmpeg.exists():
    binaries.append((str(ffmpeg), "bin"))
if ffprobe.exists():
    binaries.append((str(ffprobe), "bin"))

a = Analysis(
    [str(root / "src" / "gemini_video_dubber" / "__main__.py")],
    pathex=[str(root / "src")],
    binaries=binaries,
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Gemini Video Dubber",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
)
