import shutil
import subprocess
import sys
from pathlib import Path

from crypolt_shorts.app.localization import Localizer


def resolve_binary(binary_name: str, localizer: Localizer) -> str:
    direct_match = shutil.which(binary_name)
    if direct_match:
        return direct_match

    search_roots = [
        Path("C:/ffmpeg-master-latest-win64-gpl-shared/bin"),
        Path("C:/ffmpeg/bin"),
        Path("C:/Program Files/ffmpeg/bin"),
        Path("C:/Program Files/FFmpeg/bin"),
        Path("C:/ProgramData/chocolatey/bin"),
    ]
    for root in search_roots:
        candidate = root / f"{binary_name}.exe"
        if candidate.exists():
            return str(candidate)

    raise RuntimeError(localizer.t("runtime.ffmpeg_missing", binary=binary_name))


def ensure_runtime(localizer: Localizer) -> tuple[str, str]:
    ffmpeg_bin = resolve_binary("ffmpeg", localizer)
    ffprobe_bin = resolve_binary("ffprobe", localizer)
    for binary_path in (ffmpeg_bin, ffprobe_bin):
        subprocess.run([binary_path, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    subprocess.run([sys.executable, "-m", "edge_tts", "--help"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return ffmpeg_bin, ffprobe_bin
