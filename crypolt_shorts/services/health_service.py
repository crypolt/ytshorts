from __future__ import annotations

import subprocess
import sys

import requests

from crypolt_shorts.app.settings import AppSettings
from crypolt_shorts.app.localization import Localizer
from crypolt_shorts.infrastructure.runtime_service import resolve_binary


def _probe_http(url: str, params: dict | None = None, timeout: int = 12) -> tuple[bool, str]:
    try:
        response = requests.get(url, params=params, timeout=timeout)
        if response.status_code == 429:
            return True, "reachable (rate-limited)"
        response.raise_for_status()
        return True, "reachable"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def check_service_health(settings: AppSettings, localizer: Localizer) -> dict[str, dict[str, str | bool]]:
    health: dict[str, dict[str, str | bool]] = {}

    for binary_name in ("ffmpeg", "ffprobe"):
        try:
            resolved = resolve_binary(binary_name, localizer)
            subprocess.run([resolved, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            health[binary_name] = {"ok": True, "message": "ready"}
        except Exception as exc:  # noqa: BLE001
            health[binary_name] = {"ok": False, "message": str(exc)}

    try:
        subprocess.run(
            [sys.executable, "-m", "edge_tts", "--help"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        health["edge_tts"] = {"ok": True, "message": "ready"}
    except Exception as exc:  # noqa: BLE001
        health["edge_tts"] = {"ok": False, "message": str(exc)}

    ok, message = _probe_http(f"{settings.jikan_base_url}/top/anime", {"limit": 1, "filter": "bypopularity"})
    health["jikan"] = {"ok": ok, "message": message}

    ok, message = _probe_http(f"{settings.animechan_base_url}/quotes", {"anime": "Naruto", "page": 1})
    health["animechan"] = {"ok": ok, "message": message}

    if settings.pixabay_api_key:
        ok, message = _probe_http(settings.pixabay_videos_api_url, {"key": settings.pixabay_api_key, "q": "anime", "per_page": 3})
        health["pixabay"] = {"ok": ok, "message": message}
    else:
        health["pixabay"] = {"ok": False, "message": "missing api key"}

    return health
