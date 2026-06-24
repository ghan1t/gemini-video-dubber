# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path.cwd()
ffmpeg = root / "vendor" / "macos" / "ffmpeg"
ffprobe = root / "vendor" / "macos" / "ffprobe"
binaries = []
if ffmpeg.exists():
    binaries.append((str(ffmpeg), "bin"))
if ffprobe.exists():
    binaries.append((str(ffprobe), "bin"))

a = Analysis(
    ["src/gemini_video_dubber/__main__.py"],
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
    [],
    exclude_binaries=True,
    name="Gemini Video Dubber",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Gemini Video Dubber",
)
app = BUNDLE(
    coll,
    name="Gemini Video Dubber.app",
    icon=None,
    bundle_identifier="com.example.gemini-video-dubber",
)
