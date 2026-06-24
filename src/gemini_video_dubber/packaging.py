from __future__ import annotations

from pathlib import Path

APP_NAME = "Gemini Video Dubber"


def vendor_binary_paths(root: Path, platform_name: str) -> tuple[Path, Path]:
    suffix = ".exe" if platform_name == "windows" else ""
    return (
        root / "vendor" / platform_name / f"ffmpeg{suffix}",
        root / "vendor" / platform_name / f"ffprobe{suffix}",
    )
