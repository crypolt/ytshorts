import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def slugify(value: str) -> str:
    normalized = re.sub(r"[^\w\-]+", "-", value.strip().lower(), flags=re.UNICODE)
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    return normalized or "anime"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def build_run_dir(root: str, anime: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = Path(root) / f"{slugify(anime)}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sanitize_hashtag(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-zА-Яа-я0-9]", "", value)
    return cleaned or "anime"
