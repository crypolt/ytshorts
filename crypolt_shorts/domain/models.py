from dataclasses import dataclass


@dataclass
class Scene:
    title_ru: str
    title_en: str
    subtitle_ru: str
    subtitle_en: str
    narration_ru: str
    narration_en: str
    mood: str
    animation: str
    duration_sec: float = 0.0
