import json
from functools import lru_cache
from pathlib import Path


LOCALES_DIR = Path(__file__).resolve().parent.parent / "resources" / "locales"


@lru_cache(maxsize=8)
def load_locale(locale: str) -> dict[str, str]:
    path = LOCALES_DIR / f"{locale}.json"
    if not path.exists():
        path = LOCALES_DIR / "ru.json"
    return json.loads(path.read_text(encoding="utf-8"))


class Localizer:
    def __init__(self, locale: str) -> None:
        self.messages = load_locale(locale)

    def t(self, key: str, **kwargs) -> str:
        template = self.messages.get(key, key)
        return template.format(**kwargs)
