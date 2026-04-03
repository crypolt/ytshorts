from __future__ import annotations

import threading
import time
from pathlib import Path

import requests
from deep_translator import GoogleTranslator

from crypolt_shorts.app.localization import Localizer
from crypolt_shorts.app.settings import AppSettings
from crypolt_shorts.domain.models import Scene
from crypolt_shorts.infrastructure.runtime_service import ensure_runtime
from crypolt_shorts.services.anime_service import (
    fetch_anime_data,
    pick_cover_url,
    shorten_for_subtitle,
    split_synopsis,
    translate_to_ru,
)
from crypolt_shorts.services.assets_service import (
    build_credits,
    build_publish_metadata,
    download_file,
    ensure_music,
    load_music_catalog,
    pick_music_track,
)
from crypolt_shorts.services.render_service import (
    allocate_scene_durations,
    attach_audio,
    get_media_duration,
    make_background,
    mix_audio,
    render_quote_card,
    render_scene_card,
    render_scene_clip,
    synthesize_voice,
)
from crypolt_shorts.utils import build_run_dir, save_json


def _raise_if_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise RuntimeError("Quote series generation cancelled by user")


def _request_json(url: str, **params: object) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            response = requests.get(url, params=params, timeout=45)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            last_error = exc
            if exc.response is not None and exc.response.status_code == 429 and attempt < 3:
                time.sleep(3 * attempt)
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < 3:
                time.sleep(1.5 * attempt)
                continue
            raise
    raise RuntimeError(f"quote_api_failed: {last_error}")


def _is_rate_limited(error: Exception) -> bool:
    text = str(error).lower()
    if "429" in text or "too many requests" in text or "rate limit" in text:
        return True
    if isinstance(error, requests.HTTPError) and error.response is not None:
        return error.response.status_code == 429
    return False


def _coerce_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        parts = [_coerce_text(item) for item in value]
        return " ".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        for key in ("name", "character", "content", "quote", "text", "title", "value"):
            if key in value:
                text = _coerce_text(value.get(key))
                if text:
                    return text
        parts = [_coerce_text(item) for item in value.values()]
        return " ".join(part for part in parts if part).strip()
    return str(value).strip()


def _normalize_quote_entry(quote: dict, anime: str, index: int) -> dict:
    character = _coerce_text(quote.get("character")) or _coerce_text(quote.get("author")) or f"{anime} quote #{index + 1}"
    content = _coerce_text(quote.get("content")) or _coerce_text(quote.get("quote")) or "A memorable line from the anime."
    return {
        "character": character,
        "content": content,
    }


def fetch_anime_quotes(anime: str, settings: AppSettings, limit: int) -> list[dict]:
    candidates = [anime]
    try:
        anime_info = _request_json(f"{settings.animechan_base_url}/anime/{anime}")
        if isinstance(anime_info, dict):
            data = anime_info.get("data", {})
            canonical_name = data.get("name")
            alt_name = data.get("altName")
            for value in (canonical_name, alt_name):
                if value and value not in candidates:
                    candidates.append(value)
    except Exception:
        pass

    for candidate in candidates:
        quotes: list[dict] = []
        page = 1
        try:
            while len(quotes) < limit and page <= max(3, limit):
                payload = _request_json(f"{settings.animechan_base_url}/quotes", anime=candidate, page=page)
                data = payload.get("data") if isinstance(payload, dict) else payload
                if not isinstance(data, list):
                    data = []
                if not data:
                    break
                quotes.extend(data)
                page += 1
        except Exception as exc:  # noqa: BLE001
            if _is_rate_limited(exc):
                raise RuntimeError("quote_api_rate_limited") from exc
            continue
        if quotes:
            return quotes[:limit]
    return []


def _build_quote_scene(anime_title: str, quote: dict) -> Scene:
    character = _coerce_text(quote.get("character")) or "Unknown"
    quote_text = _coerce_text(quote.get("content")) or "A quote from the anime."
    translator = GoogleTranslator(source="auto", target="ru")
    quote_ru = translate_to_ru(quote_text, translator)
    character_ru = translate_to_ru(character, translator)
    return Scene(
        title_ru=character_ru,
        title_en=character,
        subtitle_ru=shorten_for_subtitle(quote_ru, 58),
        subtitle_en=shorten_for_subtitle(quote_text, 62),
        narration_ru=f"{character_ru}. {quote_ru}",
        narration_en=f"{character}. {quote_text}",
        mood="dramatic",
        animation="pulse",
    )


def _build_fallback_quotes(anime_data: dict, anime: str, limit: int) -> list[dict]:
    synopsis_parts = split_synopsis(anime_data.get("synopsis", ""))
    if not synopsis_parts:
        synopsis_parts = [
            f"{anime} still stands out because of its energy, characters, and unforgettable atmosphere.",
            f"Fans keep coming back to {anime} for the emotion, pressure, and payoff.",
        ]
    quotes: list[dict] = []
    for index in range(limit):
        quotes.append(
            {
                "character": f"{anime} quote #{index + 1}",
                "content": synopsis_parts[index % len(synopsis_parts)],
            }
        )
    return quotes


def run_quote_series(
    anime: str,
    days: int,
    output_dir: str,
    watermark: str,
    music_mode: str,
    log_callback=None,
    progress_callback=None,
    cancel_event: threading.Event | None = None,
) -> Path:
    settings = AppSettings()
    localizer = Localizer(settings.locale)
    ffmpeg_bin, ffprobe_bin = ensure_runtime(localizer)
    series_dir = build_run_dir(output_dir, f"{anime}_quote_series")

    def log(message: str) -> None:
        if log_callback:
            log_callback(message)

    anime_data = fetch_anime_data(anime, settings, localizer)
    _raise_if_cancelled(cancel_event)
    cover_path = series_dir / "cover.jpg"
    download_file(pick_cover_url(anime_data), cover_path)
    quotes: list[dict]
    try:
        quotes = fetch_anime_quotes(anime, settings, days)
    except Exception as exc:  # noqa: BLE001
        if _is_rate_limited(exc):
            log("Animechan hit a rate limit, switching to synopsis-based fallback quotes")
            quotes = []
        else:
            log(f"Animechan quotes failed, switching to synopsis fallback quotes: {exc}")
            quotes = []
    if not quotes:
        log("Public quotes unavailable right now, generating quote-style fallback text from the anime synopsis")
        quotes = _build_fallback_quotes(anime_data, anime, days)
    quotes = [_normalize_quote_entry(quote, anime, index) for index, quote in enumerate(quotes)]

    music_track = None
    music_path = None
    if music_mode == "auto":
        catalog = load_music_catalog(Path(__file__).resolve().parent.parent / "resources" / "music_catalog.json")
        music_track = pick_music_track(catalog, "dramatic")
        music_path = ensure_music(music_track, settings.music_cache_dir, settings)
        (series_dir / "credits.txt").write_text(build_credits(music_track, settings, localizer), encoding="utf-8")

    save_json(series_dir / "quotes.json", {"anime": anime, "quotes": quotes})
    generated_days: list[dict] = []
    total = min(days, len(quotes))

    for index in range(total):
        _raise_if_cancelled(cancel_event)
        quote = quotes[index]
        scene = _build_quote_scene(anime, quote)
        day_dir = series_dir / f"day_{index + 1:02d}"
        day_dir.mkdir(parents=True, exist_ok=True)
        bg_path = day_dir / "background.png"
        card_path = day_dir / "card.png"
        voice_path = day_dir / "voice.mp3"
        clip_path = day_dir / "clip.mp4"
        mix_path = day_dir / "mix.m4a"
        final_path = day_dir / "final.mp4"

        log(f"Generating quote video for day {index + 1}: {quote.get('character', 'Unknown')}")
        make_background(cover_path, bg_path, seed=index + 1)
        render_quote_card(
            background_path=bg_path,
            cover_path=cover_path,
            scene=scene,
            anime_title=anime,
            watermark=watermark,
            output_path=card_path,
            day_number=index + 1,
            total_days=total,
            is_final_scene=True,
        )
        synthesize_voice(scene.narration_ru, voice_path)
        voice_duration = get_media_duration(voice_path, ffprobe_bin)
        allocate_scene_durations([scene], voice_duration, 10)
        render_scene_clip(card_path, scene.duration_sec or max(voice_duration, 8.0), scene.animation, clip_path, ffmpeg_bin)
        mix_audio(voice_path, music_path, mix_path, ffmpeg_bin, duration_sec=scene.duration_sec)
        attach_audio(clip_path, mix_path, final_path, ffmpeg_bin)

        publish = build_publish_metadata(
            {
                "title_english": anime,
                "genres": ", ".join(item["name"] for item in anime_data.get("genres", [])[:3]) or "anime",
                "year": anime_data.get("year") or "?",
                "episodes": anime_data.get("episodes") or "?",
            },
            watermark,
            music_track,
            localizer,
            mode="story",
        )
        title = f"{anime} Quote Series | Day {index + 1} | {quote.get('character', 'Anime')}"
        description = (
            f'{title}\n'
            f"Series day: Day {index + 1} of {total}\n"
            f'"{quote.get("content", "")}"\n\n'
            f'Leave a like and comment which anime should get the next quote video.\n\n'
            f'{publish["description"]}'
        )
        (day_dir / "shorts_title.txt").write_text(title, encoding="utf-8")
        (day_dir / "shorts_description.txt").write_text(description, encoding="utf-8")
        (day_dir / "hashtags.txt").write_text(" ".join(publish["hashtags"]), encoding="utf-8")
        save_json(
            day_dir / "quote_metadata.json",
            {
                "day": index + 1,
                "day_number": index + 1,
                "total_days": total,
                "character": quote.get("character"),
                "quote": quote.get("content"),
                "anime": anime,
                "video": str(final_path),
            },
        )
        generated_days.append(
            {
                "day": index + 1,
                "day_number": index + 1,
                "total_days": total,
                "video": str(final_path),
                "character": quote.get("character"),
                "title": title,
            }
        )
        if progress_callback:
            progress_callback({"current": index + 1, "total": total, "detail": f"Day {index + 1}: {quote.get('character', 'Quote')}"})

    save_json(
        series_dir / "series_summary.json",
        {
            "anime": anime,
            "type": "quote_series",
            "total_days": total,
            "days": generated_days,
        },
    )
    return series_dir
