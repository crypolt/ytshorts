import re
import textwrap
import time
from typing import Any

import requests
from deep_translator import GoogleTranslator

from crypolt_shorts.app.localization import Localizer
from crypolt_shorts.app.settings import AppSettings
from crypolt_shorts.domain.models import Scene
from crypolt_shorts.utils import clean_text


POPULAR_ANIME_TITLES = [
    "Naruto",
    "One Piece",
    "Bleach",
    "Attack on Titan",
    "Demon Slayer",
    "Jujutsu Kaisen",
    "Death Note",
    "Fullmetal Alchemist: Brotherhood",
    "Black Lagoon",
    "Berserk",
    "Tokyo Ghoul",
    "Chainsaw Man",
    "Hunter x Hunter",
    "Dragon Ball Z",
    "JoJo's Bizarre Adventure",
    "Vinland Saga",
    "Code Geass",
    "Steins;Gate",
    "My Hero Academia",
    "Solo Leveling",
    "A Silent Voice",
    "Your Name",
    "Monster",
    "Made in Abyss",
    "Mob Psycho 100",
    "Re:Zero",
    "Spy x Family",
    "Tokyo Revengers",
    "Haikyuu!!",
    "Blue Lock",
    "The Eminence in Shadow",
    "Mushoku Tensei",
    "Classroom of the Elite",
    "Fate/Zero",
    "Fate/stay night: Unlimited Blade Works",
    "Neon Genesis Evangelion",
    "Cowboy Bebop",
    "Samurai Champloo",
    "Akame ga Kill!",
    "The Rising of the Shield Hero",
    "Dr. Stone",
    "Fire Force",
    "Parasyte",
    "Erased",
    "Psycho-Pass",
    "Tokyo Ghoul:re",
    "Sword Art Online",
    "Kuroko's Basketball",
    "Noragami",
    "Overlord",
    "The Apothecary Diaries",
    "Frieren: Beyond Journey's End",
    "Hell's Paradise",
    "Blue Exorcist",
    "Bungo Stray Dogs",
    "The Seven Deadly Sins",
    "Black Clover",
    "Fairy Tail",
    "Gintama",
    "Violet Evergarden",
]


def get_popular_anime_titles() -> list[str]:
    return POPULAR_ANIME_TITLES[:]


def fetch_popular_anime_titles(settings: AppSettings, limit: int = 100) -> list[str]:
    payload = request_json(
        f"{settings.jikan_base_url}/top/anime",
        limit=limit,
        filter="bypopularity",
    )
    items = payload.get("data", [])
    titles: list[str] = []
    for item in items:
        title = item.get("title_english") or item.get("title")
        if title and title not in titles:
            titles.append(title)
    return titles or get_popular_anime_titles()


def request_json(url: str, **params: object) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=45)
    response.raise_for_status()
    return response.json()


def fetch_anime_data(query: str, settings: AppSettings, localizer: Localizer) -> dict[str, Any]:
    search_payload = request_json(f"{settings.jikan_base_url}/anime", q=query, limit=1)
    items = search_payload.get("data", [])
    if not items:
        raise RuntimeError(localizer.t("anime.not_found", query=query))

    anime_id = items[0]["mal_id"]
    time.sleep(1.0)
    details = request_json(f"{settings.jikan_base_url}/anime/{anime_id}/full")
    return details["data"]


def split_synopsis(synopsis: str) -> list[str]:
    cleaned = clean_text(synopsis)
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [part.strip() for part in parts if len(part.strip()) > 45]


def translate_to_ru(text: str, translator: GoogleTranslator) -> str:
    try:
        return clean_text(translator.translate(text))
    except Exception:
        return text


def shorten_for_subtitle(text: str, width: int) -> str:
    return textwrap.shorten(clean_text(text), width=width, placeholder="...")


def infer_mood(anime: dict[str, Any]) -> str:
    labels = {
        item["name"].lower()
        for bucket in ("genres", "themes", "demographics")
        for item in anime.get(bucket, [])
    }
    if labels & {"action", "adventure", "martial arts", "super power", "shounen"}:
        return "energetic"
    if labels & {"psychological", "drama", "horror", "mystery", "suspense"}:
        return "dramatic"
    return "uplifting"


def pick_cover_url(anime: dict[str, Any]) -> str:
    images = anime.get("images", {})
    for fmt in ("webp", "jpg"):
        block = images.get(fmt, {})
        for key in ("large_image_url", "image_url", "small_image_url"):
            value = block.get(key)
            if value:
                return value
    raise RuntimeError("cover_missing")


def format_score(score: float | None) -> str:
    if score is None:
        return "N/A"
    return f"{score:.1f}"


def build_bilingual_scenes(anime: dict[str, Any], localizer: Localizer) -> tuple[dict[str, Any], list[Scene]]:
    title = anime.get("title") or anime.get("title_english") or localizer.t("story.unknown")
    english_title = anime.get("title_english") or title
    score = format_score(anime.get("score"))
    year = anime.get("year") or "?"
    episodes = anime.get("episodes") or "?"
    genres = ", ".join(item["name"] for item in anime.get("genres", [])[:3]) or "anime"
    themes = ", ".join(item["name"] for item in anime.get("themes", [])[:2]) or "intense character arcs"
    synopsis_parts = split_synopsis(anime.get("synopsis", ""))
    synopsis_a = synopsis_parts[0] if synopsis_parts else localizer.t("story.default_synopsis_a", title=english_title)
    synopsis_b = synopsis_parts[1] if len(synopsis_parts) > 1 else localizer.t("story.default_synopsis_b")
    title_caps = english_title.upper()

    translator = GoogleTranslator(source="auto", target="ru")
    mood = infer_mood(anime)
    scenes_blueprint = [
        (localizer.t("story.hook_title_ru", title=title_caps), title_caps, localizer.t("story.hook_en", title=english_title), "energetic", "punch_in"),
        (localizer.t("story.story_title_ru"), localizer.t("story.story_title_en"), synopsis_a, mood, "push_in"),
        (localizer.t("story.why_title_ru"), localizer.t("story.why_title_en"), synopsis_b, mood, "pan"),
        (localizer.t("story.score_title_ru"), localizer.t("story.score_title_en"), localizer.t("story.score_en", score=score, genres=genres), "uplifting", "drift"),
        (localizer.t("story.watch_title_ru"), localizer.t("story.watch_title_en"), localizer.t("story.watch_en", genres=genres, themes=themes), "dramatic", "pulse"),
        (
            localizer.t("story.next_title_ru"),
            localizer.t("story.next_title_en"),
            "Leave a like and comment which anime should get the next crypolt continuation.",
            "energetic",
            "punch_in",
        ),
    ]

    scenes: list[Scene] = []
    for title_ru_seed, title_en, narration_en, scene_mood, animation in scenes_blueprint:
        narration_ru = translate_to_ru(narration_en, translator)
        scenes.append(
            Scene(
                title_ru=title_ru_seed if title_ru_seed == title_caps else translate_to_ru(title_en, translator),
                title_en=title_en,
                subtitle_ru=shorten_for_subtitle(narration_ru, 56),
                subtitle_en=shorten_for_subtitle(narration_en, 62),
                narration_ru=narration_ru,
                narration_en=narration_en,
                mood=scene_mood,
                animation=animation,
            )
        )

    meta = {
        "title": title,
        "title_english": english_title,
        "score": score,
        "year": year,
        "episodes": episodes,
        "genres": genres,
        "themes": themes,
        "language_mode": "bilingual",
        "voice_language": "ru",
        "music_mood": mood,
        "description": localizer.t("meta.description", title=english_title),
    }
    return meta, scenes
