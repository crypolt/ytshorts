from __future__ import annotations

from datetime import datetime
from statistics import mean
from typing import Any, Callable
from urllib.parse import urlparse

from yt_dlp import YoutubeDL

from crypolt_shorts.app.settings import AppSettings


AnalyticsCallback = Callable[[str], None]


def _create_ydl(**overrides: Any) -> YoutubeDL:
    options = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": False,
        "playlistend": 12,
    }
    options.update(overrides)
    return YoutubeDL(options)


def _is_youtube_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and "youtube.com" in parsed.netloc


def _normalize_channel_url(value: str, settings: AppSettings) -> str:
    candidate = value.strip()
    if candidate.startswith("@"):
        return f"{settings.youtube_base_url}/{candidate}"
    if _is_youtube_url(candidate):
        return candidate.rstrip("/")
    return candidate


def _resolve_channel_url(query_or_url: str, settings: AppSettings, callback: AnalyticsCallback | None = None) -> str:
    candidate = _normalize_channel_url(query_or_url, settings)
    if candidate.startswith("http"):
        return candidate

    if callback:
        callback("Searching YouTube for the requested channel")
    with _create_ydl(extract_flat=True, playlistend=5) as ydl:
        info = ydl.extract_info(f"ytsearch5:{candidate}", download=False)
    entries = info.get("entries", [])
    for entry in entries:
        uploader_url = entry.get("uploader_url")
        channel_url = entry.get("channel_url")
        if uploader_url and "youtube.com" in uploader_url:
            return uploader_url.rstrip("/")
        if channel_url and "youtube.com" in channel_url:
            return channel_url.rstrip("/")
    raise RuntimeError(f'YouTube channel was not found for "{query_or_url}"')


def _format_date(upload_date: str | None) -> str:
    if not upload_date:
        return "-"
    try:
        return datetime.strptime(upload_date, "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return upload_date


def _build_short_url(entry: dict[str, Any], settings: AppSettings) -> str:
    for key in ("webpage_url", "url", "original_url"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith("http"):
            return value
    video_id = entry.get("id")
    if video_id:
        return f"{settings.youtube_base_url}/shorts/{video_id}"
    return ""


def _extract_short_details(short_url: str, callback: AnalyticsCallback | None = None) -> dict[str, Any]:
    if callback:
        callback(f"Loading short data: {short_url}")
    with _create_ydl(extract_flat=False) as ydl:
        info = ydl.extract_info(short_url, download=False)
    return {
        "title": info.get("title") or "Untitled short",
        "url": info.get("webpage_url") or short_url,
        "view_count": int(info.get("view_count") or 0),
        "like_count": int(info.get("like_count") or 0),
        "comment_count": int(info.get("comment_count") or 0),
        "duration": int(info.get("duration") or 0),
        "upload_date": _format_date(info.get("upload_date")),
        "channel": info.get("channel"),
    }


def analyze_channel_shorts(
    query_or_url: str,
    settings: AppSettings,
    limit: int = 12,
    callback: AnalyticsCallback | None = None,
) -> dict[str, Any]:
    channel_url = _resolve_channel_url(query_or_url, settings, callback)
    if callback:
        callback("Loading channel profile")
    with _create_ydl(extract_flat=True) as ydl:
        channel_info = ydl.extract_info(channel_url, download=False)

    shorts_url = f"{channel_url}/{settings.youtube_shorts_path}".rstrip("/")
    if callback:
        callback("Fetching public Shorts list")
    with _create_ydl(extract_flat=True, playlistend=limit) as ydl:
        shorts_feed = ydl.extract_info(shorts_url, download=False)

    shorts: list[dict[str, Any]] = []
    for entry in shorts_feed.get("entries", [])[:limit]:
        short_url = _build_short_url(entry, settings)
        if not short_url:
            continue
        try:
            shorts.append(_extract_short_details(short_url, callback))
        except Exception:
            continue

    if not shorts:
        raise RuntimeError("No public Shorts were found for this channel")

    shorts_sorted = sorted(shorts, key=lambda item: item["view_count"], reverse=True)
    total_views = sum(item["view_count"] for item in shorts_sorted)
    total_likes = sum(item["like_count"] for item in shorts_sorted)
    avg_views = int(mean(item["view_count"] for item in shorts_sorted))
    avg_likes = int(mean(item["like_count"] for item in shorts_sorted))
    top_short = shorts_sorted[0]

    return {
        "channel": {
            "title": channel_info.get("channel") or channel_info.get("title") or "Unknown channel",
            "url": channel_url,
            "handle": channel_info.get("uploader_id") or channel_info.get("channel_id") or "-",
            "followers": int(channel_info.get("channel_follower_count") or 0),
            "description": channel_info.get("description") or "",
            "shorts_url": shorts_url,
        },
        "summary": {
            "shorts_analyzed": len(shorts_sorted),
            "total_views": total_views,
            "total_likes": total_likes,
            "avg_views": avg_views,
            "avg_likes": avg_likes,
            "top_short_title": top_short["title"],
            "top_short_views": top_short["view_count"],
        },
        "shorts": shorts_sorted,
    }
