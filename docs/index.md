---
title: Crypolt Studio
---

# Crypolt Studio

AI‑assisted anime Shorts pipeline with bilingual captions, branded motion, and a built‑in project library.

## What It Does
- Generates vertical Shorts from anime titles.
- Builds bilingual subtitles (RU + EN).
- Adds consistent Crypolt motion branding and watermark.
- Supports AMV‑style edits with dynamic transitions.
- Produces title, description, hashtags, and publish metadata.
- Manages projects with preview and export inside the GUI.

## Modes
### Story
Automatic narration + subtitles + branded cards.

### AMV Edit
No voice‑over, high‑energy motion cuts and transitions.

### Quote Series
One quote video per day, with day indicators and metadata.

## Install
```powershell
& "C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m pip install -r requirements.txt
```

## Run GUI
```powershell
& "C:\Users\User\AppData\Local\Python\pythoncore-3.14-64\python.exe" .\main_gui.py
```

## Build Artifacts
GitHub Actions produces installers for Windows and macOS.  
Artifacts are attached to Releases.

## Release Flow
Create a tag to build and publish:
```
git tag v1.0.0
git push origin v1.0.0
```

## Repo
https://github.com/crypolt/ytshorts
