import argparse
import os
import sys

import requests
from dotenv import load_dotenv

from crypolt_shorts.app.localization import Localizer
from crypolt_shorts.app.settings import AppSettings
from crypolt_shorts.pipeline import run_pipeline


def parse_args() -> argparse.Namespace:
    load_dotenv()
    settings = AppSettings()
    localizer = Localizer(settings.locale)
    parser = argparse.ArgumentParser(
        description=localizer.t("cli.description")
    )
    parser.add_argument("--anime", required=True, help=localizer.t("cli.anime_help"))
    parser.add_argument(
        "--language-mode",
        default=os.getenv("CRYPOLT_LANGUAGE_MODE", "bilingual"),
        choices=["bilingual"],
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=int(os.getenv("CRYPOLT_DURATION", "18")),
        help=localizer.t("cli.duration_help"),
    )
    parser.add_argument(
        "--voice",
        default=os.getenv("CRYPOLT_VOICE_MODE", "auto"),
        help=localizer.t("cli.voice_help"),
    )
    parser.add_argument(
        "--music-mode",
        default=os.getenv("CRYPOLT_MUSIC_MODE", "auto"),
        choices=["auto", "off"],
    )
    parser.add_argument(
        "--mode",
        default=os.getenv("CRYPOLT_RENDER_MODE", "story"),
        choices=["story", "amv_edit"],
        help="Rendering mode: story or amv_edit.",
    )
    parser.add_argument(
        "--watermark",
        default=os.getenv("CRYPOLT_WATERMARK", "crypolt"),
        help=localizer.t("cli.watermark_help"),
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("CRYPOLT_OUTPUT_DIR", "output"),
        help=localizer.t("cli.output_dir_help"),
    )
    return parser.parse_args()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    settings = AppSettings()
    localizer = Localizer(settings.locale)
    args = parse_args()
    try:
        run_pipeline(args)
        return 0
    except requests.HTTPError as exc:
        details = exc.response.text if exc.response is not None else str(exc)
        print(localizer.t("error.http", details=details), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if message == "cover_missing":
            message = localizer.t("anime.cover_missing")
        print(localizer.t("error.generic", details=message), file=sys.stderr)
        return 1
