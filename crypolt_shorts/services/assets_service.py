import json
import random
import time
from pathlib import Path
from typing import Any

import requests

from crypolt_shorts.app.localization import Localizer
from crypolt_shorts.app.settings import AppSettings
from crypolt_shorts.utils import sanitize_hashtag, slugify


def download_file(url: str, output_path: Path, retries: int = 3) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: Exception | None = None
    headers = {"User-Agent": "crypolt-studio/1.0"}

    for attempt in range(1, retries + 1):
        temp_path = output_path.with_suffix(output_path.suffix + ".part")
        try:
            with requests.get(url, timeout=90, stream=True, headers=headers) as response:
                response.raise_for_status()
                with temp_path.open("wb") as file:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            file.write(chunk)
            temp_path.replace(output_path)
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            if attempt < retries:
                time.sleep(1.2 * attempt)

    raise RuntimeError(f"download_failed: {url} | {last_error}") from last_error


def load_music_catalog(catalog_path: Path) -> list[dict[str, Any]]:
    with catalog_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    return payload["tracks"]


def pick_music_track(catalog: list[dict[str, Any]], mood: str) -> dict[str, Any]:
    exact_matches = [track for track in catalog if mood in track.get("moods", [])]
    return random.choice(exact_matches or catalog)


def ensure_music(track: dict[str, Any], cache_dir: Path, settings: AppSettings) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_path = cache_dir / f"{slugify(track['title'])}.mp3"
    if cached_path.exists():
        return cached_path

    download_file(settings.incompetech_music_base_url + track["source_path"], cached_path)
    return cached_path


def build_credits(track: dict[str, Any], settings: AppSettings, localizer: Localizer) -> str:
    return (
        f"{localizer.t('credits.header')}\n"
        f"Track: {track['title']}\n"
        f"Artist: {track['artist']}\n"
        f"License: {track['license']}\n"
        f"Credit: {track['attribution']}\n"
        f"Source: {settings.incompetech_source_page_url}\n"
    )


def build_publish_metadata(
    meta: dict[str, Any],
    watermark: str,
    music_track: dict[str, Any] | None,
    localizer: Localizer,
    mode: str = "story",
) -> dict[str, Any]:
    anime_title = meta["title_english"]
    genres = [item.strip() for item in meta["genres"].split(",") if item.strip()]
    genre_tags = [f"#{sanitize_hashtag(item)}" for item in genres[:3]]
    base_tags = ["#shorts", "#anime", "#anitok", f"#{sanitize_hashtag(anime_title)}", "#crypolt"]

    all_tags: list[str] = []
    for tag in base_tags + genre_tags:
        if tag not in all_tags:
            all_tags.append(tag)

    if mode == "amv_edit":
        title_options = [
            f"{anime_title} AMV edit that feels illegal | {watermark} #shorts",
            f"{anime_title} in Crypolt AMV style | {watermark} #shorts",
            f"{anime_title} edit with pure energy | {watermark} #shorts",
        ]
        description_lines = [
            f"{watermark} AMV edit on {anime_title}.",
            "Fast transitions, music-driven pacing and high-impact visuals made for Shorts/TikTok.",
            localizer.t("publish.description_meta", genres=meta["genres"], year=meta["year"], episodes=meta["episodes"]),
            f"Leave a like and comment which anime should get the next AMV continuation in the {watermark} style.",
            "",
            localizer.t("publish.hashtags_label"),
            " ".join(all_tags + ["#amv", "#edit"]),
        ]
    else:
        title_options = [
            localizer.t("publish.title_1", anime=anime_title, watermark=watermark),
            localizer.t("publish.title_2", anime=anime_title, watermark=watermark),
            localizer.t("publish.title_3", anime=anime_title, watermark=watermark),
        ]

        description_lines = [
            localizer.t("publish.description_intro", watermark=watermark, anime=anime_title),
            localizer.t("publish.description_body"),
            localizer.t("publish.description_meta", genres=meta["genres"], year=meta["year"], episodes=meta["episodes"]),
            f"Leave a like and comment which anime you want a continuation for next in the {watermark} style.",
            "",
            localizer.t("publish.hashtags_label"),
            " ".join(all_tags),
        ]
    if music_track:
        description_lines.extend(["", localizer.t("publish.music_line", title=music_track["title"], artist=music_track["artist"]), music_track["attribution"]])

    hashtags = list(all_tags)
    if mode == "amv_edit":
        for tag in ("#amv", "#edit"):
            if tag not in hashtags:
                hashtags.append(tag)

    return {"title": title_options[0], "title_options": title_options, "description": "\n".join(description_lines), "hashtags": hashtags}
