import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    video_width: int = 1080
    video_height: int = 1920
    fps: int = 30
    youtube_base_url: str = os.getenv("CRYPOLT_YOUTUBE_BASE_URL", "https://www.youtube.com")
    youtube_shorts_path: str = os.getenv("CRYPOLT_YOUTUBE_SHORTS_PATH", "shorts")
    pixabay_api_key: str = os.getenv("CRYPOLT_PIXABAY_API_KEY", "55211134-70cd70f8462564627188221cf")
    pixabay_videos_api_url: str = os.getenv("CRYPOLT_PIXABAY_VIDEOS_API_URL", "https://pixabay.com/api/videos/")
    animechan_base_url: str = os.getenv("CRYPOLT_ANIMECHAN_BASE_URL", "https://api.animechan.io/v1")
    jikan_base_url: str = os.getenv("CRYPOLT_JIKAN_BASE_URL", "https://api.jikan.moe/v4")
    incompetech_music_base_url: str = os.getenv(
        "CRYPOLT_INCOMPETECH_MUSIC_BASE_URL",
        "https://incompetech.com/music/royalty-free/mp3-royaltyfree/"
    )
    incompetech_source_page_url: str = os.getenv(
        "CRYPOLT_INCOMPETECH_SOURCE_PAGE_URL",
        "https://incompetech.com/music/royalty-free/music.html"
    )
    cache_dir: Path = Path(".cache")
    music_cache_dir: Path = cache_dir / "music"
    pixabay_video_cache_dir: Path = cache_dir / "pixabay_videos"
    voice_ru: str = os.getenv("CRYPOLT_VOICE_RU", "ru-RU-DmitryNeural")
    locale: str = os.getenv("CRYPOLT_LOCALE", "ru")
