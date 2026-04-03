# Crypolt Studio

AI‑assisted anime Shorts pipeline with bilingual captions, branded motion, and a built‑in project library.

[Live docs (GitHub Pages)](https://crypolt.github.io/ytshorts/)

## Highlights
- One‑click desktop GUI for creating vertical anime Shorts.
- Bilingual RU + EN subtitles with consistent Crypolt branding.
- Quote‑series mode: one video per day with automatic day markers.
- AMV‑style edit mode with dynamic motion and transitions.
- Built‑in project library with previews, metadata, and quick export.

## Quick Start (Windows)
```powershell
& "C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m pip install -r requirements.txt
& "C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe" .\main_gui.py
```

## Build Artifacts
GitHub Actions builds desktop apps for:
- Windows
- macOS

Artifacts are attached to releases.

## Repo Structure
```
crypolt_shorts/
  app/            # GUI + settings
  services/       # pipeline services
  resources/      # locales, music catalog
main_gui.py       # GUI entrypoint
main.py           # CLI entrypoint
```

## Releases
Tag a version to trigger automatic builds and release:
```
git tag v1.0.0
git push origin v1.0.0
```

## License
All rights reserved.
