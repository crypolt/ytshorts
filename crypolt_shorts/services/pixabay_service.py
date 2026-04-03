from __future__ import annotations

import random
from pathlib import Path
from typing import Any

import requests

from crypolt_shorts.app.settings import AppSettings
from crypolt_shorts.utils import slugify


def _request_json(url: str, **params: object) -> dict[str, Any]:
    response = requests.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def _keyword_candidates(meta: dict[str, Any]) -> list[str]:
    mood = meta.get("music_mood", "energetic")
    title = str(meta.get("title_english", "")).lower()

    keywords: list[str] = [
        "anime animation",
        "anime character",
        "manga animation",
        "animation fight",
        "animation neon",
        "fantasy animation",
        "cinematic animation",
        "japan animation",
        "stylized animation",
        "animated warrior",
    ]
    if any(token in title for token in ("naruto", "bleach", "one piece", "dragon", "attack")):
        keywords.extend(["anime ninja animation", "anime power animation", "anime battle animation"])

    mood_defaults = {
        "energetic": ["anime action animation", "fast anime animation", "neon anime animation"],
        "dramatic": ["dark anime animation", "dramatic animation", "cinematic anime animation"],
        "uplifting": ["bright anime animation", "hopeful animation", "sunrise anime animation"],
    }
    keywords.extend(mood_defaults.get(mood, ["anime animation", "stylized animation"]))
    return list(dict.fromkeys(keywords))


POSITIVE_TAGS = {
    "anime",
    "animation",
    "animated",
    "manga",
    "cartoon",
    "fantasy",
    "fight",
    "fighter",
    "warrior",
    "samurai",
    "ninja",
    "neon",
    "japan",
    "japanese",
    "magic",
    "power",
    "energy",
    "cinematic",
    "stylized",
    "character",
    "epic",
    "glow",
}

NEGATIVE_TAGS = {
    "car",
    "cars",
    "racing",
    "bike",
    "bicycle",
    "cyclist",
    "runner",
    "running",
    "sports",
    "football",
    "soccer",
    "tennis",
    "beach",
    "ocean",
    "underwater",
    "helicopter",
    "military",
    "army",
    "motor",
    "vehicle",
    "transport",
    "prague",
    "metaverse",
    "vr",
    "dirt",
    "rallye",
    "dust",
    "shore",
}


def _score_hit(hit: dict[str, Any], meta: dict[str, Any]) -> int:
    tags = {tag.strip().lower() for tag in str(hit.get("tags", "")).split(",") if tag.strip()}
    score = 0
    score += 5 * len(tags & POSITIVE_TAGS)
    score -= 6 * len(tags & NEGATIVE_TAGS)
    if hit.get("type") == "animation":
        score += 20
    duration = int(hit.get("duration") or 0)
    if 3 <= duration <= 20:
        score += 6
    views = int(hit.get("views") or 0)
    likes = int(hit.get("likes") or 0)
    score += min(views // 5000, 8)
    score += min(likes, 12)
    mood = meta.get("music_mood", "energetic")
    if mood == "energetic" and {"fight", "energy", "neon"} & tags:
        score += 8
    if mood == "dramatic" and {"cinematic", "dark", "fantasy"} & tags:
        score += 8
    if "anime" in tags or "animation" in tags or "animated" in tags:
        score += 16
    return score


def _is_hit_relevant(hit: dict[str, Any]) -> bool:
    tags = {tag.strip().lower() for tag in str(hit.get("tags", "")).split(",") if tag.strip()}
    if tags & NEGATIVE_TAGS:
        return False
    return bool(tags & POSITIVE_TAGS or hit.get("type") == "animation")


def search_pixabay_videos(meta: dict[str, Any], settings: AppSettings, per_query: int = 6) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for query in _keyword_candidates(meta):
        payload = _request_json(
            settings.pixabay_videos_api_url,
            key=settings.pixabay_api_key,
            q=query,
            order="popular",
            safesearch="true",
            editors_choice="true",
            per_page=per_query,
            video_type="all",
        )
        for hit in payload.get("hits", []):
            video_id = int(hit.get("id", 0))
            if video_id and video_id not in seen_ids and _is_hit_relevant(hit):
                seen_ids.add(video_id)
                results.append(hit)
        if len(results) >= 18:
            break
    return sorted(results, key=lambda hit: _score_hit(hit, meta), reverse=True)


def _best_video_url(hit: dict[str, Any]) -> str | None:
    videos = hit.get("videos", {})
    for key in ("medium", "small", "tiny", "large"):
        block = videos.get(key) or {}
        url = block.get("url")
        if url:
            return str(url)
    return None


def ensure_pixabay_video(hit: dict[str, Any], cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    title = hit.get("tags") or f"pixabay-{hit.get('id', 'clip')}"
    cached_path = cache_dir / f"{slugify(title)}_{hit.get('id', 'clip')}.mp4"
    if cached_path.exists():
        return cached_path

    url = _best_video_url(hit)
    if not url:
        raise RuntimeError("pixabay_video_missing")
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    cached_path.write_bytes(response.content)
    return cached_path


def pick_pixabay_hits(meta: dict[str, Any], settings: AppSettings, count: int) -> list[dict[str, Any]]:
    hits = search_pixabay_videos(meta, settings)
    if not hits:
        return []
    if len(hits) <= count:
        return hits
    top_hits = hits[: max(count * 2, count)]
    random.seed(slugify(meta.get("title_english", "anime")))
    return random.sample(top_hits, count)
