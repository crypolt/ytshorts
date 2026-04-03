import time
import random
import threading
from dataclasses import asdict
from pathlib import Path

from tqdm import tqdm

from crypolt_shorts.app.localization import Localizer
from crypolt_shorts.app.settings import AppSettings
from crypolt_shorts.infrastructure.runtime_service import ensure_runtime
from crypolt_shorts.services.anime_service import build_bilingual_scenes, fetch_anime_data, pick_cover_url
from crypolt_shorts.services.assets_service import (
    build_credits,
    build_publish_metadata,
    download_file,
    ensure_music,
    load_music_catalog,
    pick_music_track,
)
from crypolt_shorts.services.pixabay_service import ensure_pixabay_video, pick_pixabay_hits
from crypolt_shorts.config import VOICE_RU
from crypolt_shorts.services.render_service import (
    allocate_amv_durations,
    allocate_scene_durations,
    attach_audio,
    combine_scene_clips,
    get_media_duration,
    make_background,
    mix_audio,
    render_amv_card,
    render_amv_video_clip,
    render_scene_card,
    render_scene_clip,
    synthesize_voice,
)
from crypolt_shorts.utils import build_run_dir, save_json, slugify


class StepProgress:
    def __init__(self, total_steps: int, localizer: Localizer, callback=None, log_callback=None) -> None:
        self.total_steps = total_steps
        self.completed = 0
        self.started_at = time.perf_counter()
        self.localizer = localizer
        self.callback = callback
        self.log_callback = log_callback
        self.bar = tqdm(total=total_steps, unit="step", ncols=100, ascii=True, bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")

    def update(self, title: str, detail: str) -> None:
        now = time.perf_counter()
        elapsed = now - self.started_at
        average = elapsed / max(self.completed, 1) if self.completed else 0.0
        remaining_steps = self.total_steps - self.completed
        eta_seconds = average * remaining_steps if self.completed else 0.0
        eta_value = f"{eta_seconds:0.0f}s" if eta_seconds else self.localizer.t("progress.eta_pending")
        eta_label = self.localizer.t("progress.eta_label", eta=eta_value)
        self.bar.set_description_str(f"{title} | {detail} | {eta_label}")
        if self.callback:
            self.callback(
                {
                    "title": title,
                    "detail": detail,
                    "eta": eta_value,
                    "completed": self.completed + 1,
                    "total": self.total_steps,
                }
            )
        self.bar.update(1)
        self.completed += 1

    def close(self) -> None:
        self.bar.close()

    def log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)


def _raise_if_cancelled(cancel_event: threading.Event | None, progress: StepProgress) -> None:
    if cancel_event is not None and cancel_event.is_set():
        progress.log("Cancellation requested, stopping pipeline")
        raise RuntimeError("Pipeline cancelled by user")


def run_pipeline(args, progress_callback=None, log_callback=None, cancel_event: threading.Event | None = None) -> None:
    settings = AppSettings()
    localizer = Localizer(settings.locale)
    ffmpeg_bin, ffprobe_bin = ensure_runtime(localizer)
    run_dir = build_run_dir(args.output_dir, args.anime)
    random.seed(slugify(args.anime))
    progress = StepProgress(total_steps=8, localizer=localizer, callback=progress_callback, log_callback=log_callback)

    try:
        mode = getattr(args, "mode", "story")
        progress.log(f"Pipeline booted for anime='{args.anime}' mode='{mode}' output='{run_dir.name}'")
        _raise_if_cancelled(cancel_event, progress)
        progress.log("Fetching anime metadata from Jikan")
        anime = fetch_anime_data(args.anime, settings, localizer)
        _raise_if_cancelled(cancel_event, progress)
        meta, scenes = build_bilingual_scenes(anime, localizer)
        meta["render_mode"] = mode
        progress.log(f"Anime resolved: {meta['title_english']} | scenes planned: {len(scenes)}")
        save_json(run_dir / "anime.json", anime)
        save_json(run_dir / "storyboard.json", {"meta": meta, "scenes": [asdict(scene) for scene in scenes]})
        progress.update(localizer.t("progress.anime.title"), localizer.t("progress.anime.detail", anime=args.anime))

        cover_path = run_dir / "cover.jpg"
        progress.log(f"Downloading cover art to {cover_path.name}")
        download_file(pick_cover_url(anime), cover_path)
        _raise_if_cancelled(cancel_event, progress)
        progress.update(localizer.t("progress.cover.title"), localizer.t("progress.cover.detail"))

        voice_path: Path | None = None
        voice_duration = 0.0
        if mode == "amv_edit":
            progress.log("AMV edit mode enabled: skipping TTS voice generation")
            animations = ["flash_zoom", "pulse", "whip", "punch_in", "drift", "flash_zoom"]
            for index, scene in enumerate(scenes):
                scene.animation = animations[index % len(animations)]
                scene.subtitle_ru = ""
                scene.subtitle_en = ""
            allocate_amv_durations(scenes, args.duration)
            save_json(run_dir / "scene_plan.json", {"voice_duration_sec": 0.0, "scenes": [asdict(scene) for scene in scenes]})
            progress.update(localizer.t("progress.voice.title"), "Voice skipped for AMV edit mode")
        else:
            voice_path = run_dir / "voice.mp3"
            progress.log(f"Synthesizing voice track to {voice_path.name}")
            synthesize_voice(" ".join(scene.narration_ru for scene in scenes), voice_path)
            _raise_if_cancelled(cancel_event, progress)
            voice_duration = get_media_duration(voice_path, ffprobe_bin)
            allocate_scene_durations(scenes, voice_duration, args.duration)
            progress.log(f"Voice duration detected: {voice_duration:.2f}s")
            save_json(run_dir / "scene_plan.json", {"voice_duration_sec": round(voice_duration, 2), "scenes": [asdict(scene) for scene in scenes]})
            progress.update(localizer.t("progress.voice.title"), localizer.t("progress.voice.detail"))

        music_track = None
        music_path = None
        if args.music_mode == "auto":
            progress.log("Loading curated music catalog")
            catalog = load_music_catalog(Path(__file__).resolve().parent / "resources" / "music_catalog.json")
            selected_track = pick_music_track(catalog, "energetic" if mode == "amv_edit" else meta["music_mood"])
            progress.log(f"Selected music track: {selected_track['title']} by {selected_track['artist']}")
            try:
                music_path = ensure_music(selected_track, settings.music_cache_dir, settings)
                music_track = selected_track
                progress.log(f"Music cached at {music_path}")
                credits_text = build_credits(selected_track, settings, localizer)
                (run_dir / "credits.txt").write_text(credits_text, encoding="utf-8")
                (run_dir / "video_description.txt").write_text(credits_text, encoding="utf-8")
            except Exception:
                music_path = None
                progress.log("Music download failed, continuing without background music")
        else:
            progress.log("Music mode is OFF")
        _raise_if_cancelled(cancel_event, progress)
        progress.update(localizer.t("progress.music.title"), localizer.t("progress.music.detail"))

        card_paths: list[Path] = []
        pixabay_hits = []
        if mode == "amv_edit":
            progress.log("Searching Pixabay for open AMV-style video footage")
            pixabay_hits = pick_pixabay_hits(meta, settings, count=len(scenes))
            progress.log(f"Pixabay clips found: {len(pixabay_hits)}")
        _raise_if_cancelled(cancel_event, progress)
        for index, scene in enumerate(scenes, start=1):
            background_path = run_dir / f"scene_{index:02d}_bg.png"
            card_path = run_dir / f"scene_{index:02d}_card.png"
            progress.log(f"Rendering card assets for scene {index}: bg={background_path.name} card={card_path.name}")
            make_background(cover_path, background_path, seed=index)
            is_final_scene = index == len(scenes)
            if mode == "amv_edit":
                render_amv_card(background_path, cover_path, scene, meta["title"], args.watermark, card_path, is_final_scene=is_final_scene)
            else:
                render_scene_card(background_path, cover_path, scene, meta["title"], args.watermark, card_path, is_final_scene=is_final_scene)
            card_paths.append(card_path)
            _raise_if_cancelled(cancel_event, progress)
        progress.update(localizer.t("progress.cards.title"), localizer.t("progress.cards.detail"))

        scene_clips: list[Path] = []
        used_open_video_sources: list[dict[str, object]] = []
        for index, (scene, card_path) in enumerate(zip(scenes, card_paths, strict=True), start=1):
            clip_path = run_dir / f"scene_{index:02d}.mp4"
            progress.log(f"Animating scene {index}: {card_path.name} -> {clip_path.name} ({scene.duration_sec:.2f}s, {scene.animation})")
            if mode == "amv_edit" and index - 1 < len(pixabay_hits):
                try:
                    pixabay_clip = ensure_pixabay_video(pixabay_hits[index - 1], settings.pixabay_video_cache_dir)
                    progress.log(f"Using Pixabay video clip for scene {index}: {pixabay_clip.name}")
                    used_open_video_sources.append(
                        {
                            "scene": index,
                            "id": pixabay_hits[index - 1].get("id"),
                            "tags": pixabay_hits[index - 1].get("tags"),
                            "pageURL": pixabay_hits[index - 1].get("pageURL"),
                            "user": pixabay_hits[index - 1].get("user"),
                            "local_cache": str(pixabay_clip),
                        }
                    )
                    render_amv_video_clip(pixabay_clip, scene.duration_sec, scene.animation, clip_path, ffmpeg_bin, seed=index)
                except Exception:
                    progress.log(f"Pixabay clip failed for scene {index}, using AMV card fallback")
                    render_scene_clip(card_path, scene.duration_sec, scene.animation, clip_path, ffmpeg_bin)
            else:
                render_scene_clip(card_path, scene.duration_sec, scene.animation, clip_path, ffmpeg_bin)
            scene_clips.append(clip_path)
            _raise_if_cancelled(cancel_event, progress)
        progress.update(localizer.t("progress.motion.title"), localizer.t("progress.motion.detail"))

        video_no_audio = run_dir / "video_no_audio.mp4"
        progress.log(f"Combining {len(scene_clips)} scene clips into {video_no_audio.name}")
        combine_scene_clips(scene_clips, scenes, video_no_audio, ffmpeg_bin)
        _raise_if_cancelled(cancel_event, progress)
        mix_path = run_dir / "mix.m4a"
        total_mix_duration = sum(scene.duration_sec for scene in scenes)
        progress.log(f"Mixing audio to {mix_path.name} for {total_mix_duration:.2f}s")
        mix_audio(voice_path, music_path, mix_path, ffmpeg_bin, duration_sec=total_mix_duration)
        _raise_if_cancelled(cancel_event, progress)
        progress.update(localizer.t("progress.mix.title"), localizer.t("progress.mix.detail"))

        final_path = run_dir / "final.mp4"
        progress.log(f"Attaching mixed audio and exporting {final_path.name}")
        attach_audio(video_no_audio, mix_path, final_path, ffmpeg_bin)
        _raise_if_cancelled(cancel_event, progress)

        progress.log("Writing render summary and publish metadata")
        save_json(
            run_dir / "render_summary.json",
            {
                "music_enabled": bool(music_track),
                "music_track": music_track["title"] if music_track else None,
                "watermark": args.watermark,
                "voice": VOICE_RU if voice_path else None,
                "language_mode": args.language_mode,
                "mode": mode,
            },
        )

        publish_metadata = build_publish_metadata(meta, args.watermark, music_track, localizer, mode=mode)
        save_json(run_dir / "publish_metadata.json", publish_metadata)
        (run_dir / "shorts_title.txt").write_text(publish_metadata["title"], encoding="utf-8")
        (run_dir / "shorts_description.txt").write_text(publish_metadata["description"], encoding="utf-8")
        (run_dir / "hashtags.txt").write_text(" ".join(publish_metadata["hashtags"]), encoding="utf-8")
        if used_open_video_sources:
            save_json(run_dir / "open_video_sources.json", {"sources": used_open_video_sources})
        progress.log("Pipeline finished successfully")
        progress.update(localizer.t("progress.export.title"), localizer.t("progress.export.detail"))
    finally:
        progress.close()

    print(f"\n{localizer.t('done.title')}")
    print(localizer.t("done.video", path=final_path.resolve()))
    print(localizer.t("done.materials", path=run_dir.resolve()))
