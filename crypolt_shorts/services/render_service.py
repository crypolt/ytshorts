import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from crypolt_shorts.config import FPS, VIDEO_HEIGHT, VIDEO_WIDTH, VOICE_RU
from crypolt_shorts.domain.models import Scene


def load_font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/tahomabd.ttf" if bold else "C:/Windows/Fonts/tahoma.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def make_background(cover_path: Path, output_path: Path, seed: int) -> None:
    import random

    random.seed(seed)
    with Image.open(cover_path).convert("RGB") as image:
        scale = max(VIDEO_WIDTH / image.width, VIDEO_HEIGHT / image.height)
        resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)
        left = max((resized.width - VIDEO_WIDTH) // 2, 0)
        top = max((resized.height - VIDEO_HEIGHT) // 2, 0)
        cropped = resized.crop((left, top, left + VIDEO_WIDTH, top + VIDEO_HEIGHT))
        background = cropped.filter(ImageFilter.GaussianBlur(radius=24))
        background = ImageEnhance.Brightness(background).enhance(0.44)
        background = ImageEnhance.Contrast(background).enhance(1.18)

        overlay = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        accent_colors = [(255, 84, 84, 95), (255, 180, 42, 80), (59, 168, 255, 88), (95, 255, 173, 78)]
        draw.rectangle((0, 0, VIDEO_WIDTH, VIDEO_HEIGHT), fill=(5, 5, 8, 110))
        draw.ellipse((random.randint(-120, 180), random.randint(-120, 240), random.randint(540, 960), random.randint(560, 1040)), fill=random.choice(accent_colors))
        draw.ellipse((random.randint(120, 640), random.randint(820, 1120), random.randint(920, 1260), random.randint(1420, 1940)), fill=random.choice(accent_colors))
        Image.alpha_composite(background.convert("RGBA"), overlay).convert("RGB").save(output_path, format="PNG")


def draw_watermark(draw: ImageDraw.ImageDraw, watermark: str) -> None:
    badge_font = load_font(34, bold=True)
    shadow_font = load_font(34, bold=True)
    footer_font = load_font(28, bold=True)

    badge_bbox = draw.textbbox((0, 0), watermark, font=badge_font)
    badge_width = badge_bbox[2] - badge_bbox[0] + 72
    badge_left = VIDEO_WIDTH - badge_width - 56
    badge_top = 58
    badge_bottom = 132

    draw.rounded_rectangle((badge_left, badge_top, badge_left + badge_width, badge_bottom), radius=26, fill=(0, 0, 0, 132), outline=(255, 255, 255, 160), width=3)
    draw.rounded_rectangle((badge_left + 8, badge_top + 8, badge_left + badge_width - 8, badge_bottom - 8), radius=20, fill=(255, 255, 255, 34))
    text_x = badge_left + 36
    text_y = badge_top + 18
    draw.text((text_x + 2, text_y + 2), watermark, font=shadow_font, fill=(0, 0, 0, 180))
    draw.text((text_x, text_y), watermark, font=badge_font, fill=(255, 255, 255, 255))

    footer_text = f"@{watermark}"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    footer_width = footer_bbox[2] - footer_bbox[0] + 44
    footer_left = VIDEO_WIDTH - footer_width - 62
    footer_top = VIDEO_HEIGHT - 154
    footer_bottom = VIDEO_HEIGHT - 98
    draw.rounded_rectangle((footer_left, footer_top, footer_left + footer_width, footer_bottom), radius=20, fill=(0, 0, 0, 120))
    draw.text((footer_left + 22, footer_top + 11), footer_text, font=footer_font, fill=(255, 255, 255, 215))


def draw_cta_strip(draw: ImageDraw.ImageDraw) -> None:
    base_y = VIDEO_HEIGHT - 220
    subscribe_left = 120
    subscribe_top = base_y
    subscribe_width = 330
    subscribe_height = 88
    like_left = subscribe_left + subscribe_width + 28
    pill_height = 88
    pill_width = 126
    bell_left = like_left + pill_width + 24

    button_font = load_font(34, bold=True)
    icon_font = load_font(32, bold=True)

    draw.rounded_rectangle(
        (subscribe_left, subscribe_top, subscribe_left + subscribe_width, subscribe_top + subscribe_height),
        radius=30,
        fill=(255, 33, 33, 245),
    )
    draw.polygon(
        [
            (subscribe_left + 34, subscribe_top + 24),
            (subscribe_left + 34, subscribe_top + 64),
            (subscribe_left + 68, subscribe_top + 44),
        ],
        fill=(255, 255, 255, 255),
    )
    draw.text((subscribe_left + 92, subscribe_top + 23), "SUBSCRIBE", font=button_font, fill=(255, 255, 255, 255))

    draw.rounded_rectangle(
        (like_left, subscribe_top, like_left + pill_width, subscribe_top + pill_height),
        radius=28,
        fill=(255, 255, 255, 32),
        outline=(255, 255, 255, 120),
        width=2,
    )
    thumb = [
        (like_left + 34, subscribe_top + 54),
        (like_left + 44, subscribe_top + 34),
        (like_left + 58, subscribe_top + 28),
        (like_left + 68, subscribe_top + 36),
        (like_left + 76, subscribe_top + 36),
        (like_left + 80, subscribe_top + 44),
        (like_left + 76, subscribe_top + 58),
        (like_left + 48, subscribe_top + 58),
    ]
    draw.polygon(thumb, fill=(255, 255, 255, 240))
    draw.text((like_left + 88, subscribe_top + 24), "+1", font=icon_font, fill=(255, 255, 255, 255))

    draw.rounded_rectangle(
        (bell_left, subscribe_top, bell_left + pill_width, subscribe_top + pill_height),
        radius=28,
        fill=(255, 255, 255, 32),
        outline=(255, 255, 255, 120),
        width=2,
    )
    bell_center_x = bell_left + 44
    bell_top = subscribe_top + 24
    draw.arc((bell_center_x - 18, bell_top, bell_center_x + 18, bell_top + 32), start=180, end=360, fill=(255, 255, 255, 245), width=4)
    draw.line((bell_center_x - 18, bell_top + 16, bell_center_x - 18, bell_top + 34), fill=(255, 255, 255, 245), width=4)
    draw.line((bell_center_x + 18, bell_top + 16, bell_center_x + 18, bell_top + 34), fill=(255, 255, 255, 245), width=4)
    draw.line((bell_center_x - 20, bell_top + 34, bell_center_x + 20, bell_top + 34), fill=(255, 255, 255, 245), width=4)
    draw.ellipse((bell_center_x - 5, bell_top + 36, bell_center_x + 5, bell_top + 46), fill=(255, 255, 255, 245))
    draw.arc((bell_center_x - 34, bell_top + 2, bell_center_x - 18, bell_top + 26), start=300, end=70, fill=(255, 255, 255, 180), width=3)
    draw.arc((bell_center_x + 18, bell_top + 2, bell_center_x + 34, bell_top + 26), start=110, end=240, fill=(255, 255, 255, 180), width=3)
    draw.text((bell_left + 78, subscribe_top + 24), "ALL", font=icon_font, fill=(255, 255, 255, 255))


def render_scene_card(background_path: Path, cover_path: Path, scene: Scene, anime_title: str, watermark: str, output_path: Path, is_final_scene: bool = False) -> None:
    with Image.open(background_path).convert("RGBA") as canvas, Image.open(cover_path).convert("RGBA") as cover:
        draw = ImageDraw.Draw(canvas)
        title_font = load_font(74, bold=True)
        ru_font = load_font(48, bold=True)
        en_font = load_font(36, bold=False)
        micro_font = load_font(28, bold=False)

        cover_ratio = cover.width / cover.height
        cover_width = 508
        cover_height = int(cover_width / cover_ratio)
        cover = cover.resize((cover_width, cover_height), Image.Resampling.LANCZOS)
        cover_x = (VIDEO_WIDTH - cover_width) // 2
        cover_y = 180

        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle((cover_x - 18, cover_y - 18, cover_x + cover_width + 18, cover_y + cover_height + 18), radius=38, fill=(0, 0, 0, 160))
        canvas = Image.alpha_composite(canvas, shadow)
        canvas.alpha_composite(cover, (cover_x, cover_y))
        draw = ImageDraw.Draw(canvas)

        chip_text = anime_title.upper()
        chip_bbox = draw.textbbox((0, 0), chip_text, font=micro_font)
        chip_width = chip_bbox[2] - chip_bbox[0] + 54
        draw.rounded_rectangle((70, 74, 70 + chip_width, 128), radius=22, fill=(255, 255, 255, 24), outline=(255, 255, 255, 86), width=2)
        draw.text((98, 88), chip_text, font=micro_font, fill=(255, 255, 255, 240))
        draw_watermark(draw, watermark)

        panel_top = VIDEO_HEIGHT - 620
        draw.rounded_rectangle((48, panel_top, VIDEO_WIDTH - 48, VIDEO_HEIGHT - 72), radius=42, fill=(8, 8, 12, 184))

        title_lines = fit_text(draw, scene.title_ru, title_font, VIDEO_WIDTH - 180)
        subtitle_ru_lines = fit_text(draw, scene.subtitle_ru, ru_font, VIDEO_WIDTH - 180)
        subtitle_en_lines = fit_text(draw, scene.subtitle_en, en_font, VIDEO_WIDTH - 180)

        y = panel_top + 48
        for line in title_lines[:2]:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=title_font, fill=(255, 255, 255, 255))
            y += 82

        y += 12
        for line in subtitle_ru_lines[:2]:
            bbox = draw.textbbox((0, 0), line, font=ru_font)
            x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=ru_font, fill=(255, 247, 210, 255))
            y += 60

        y += 12
        for line in subtitle_en_lines[:3]:
            bbox = draw.textbbox((0, 0), line, font=en_font)
            x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=en_font, fill=(222, 228, 235, 245))
            y += 46

        if is_final_scene:
            draw_cta_strip(draw)

        canvas.convert("RGB").save(output_path, format="PNG")


def render_quote_card(
    background_path: Path,
    cover_path: Path,
    scene: Scene,
    anime_title: str,
    watermark: str,
    output_path: Path,
    day_number: int,
    total_days: int,
    is_final_scene: bool = False,
) -> None:
    with Image.open(background_path).convert("RGBA") as canvas, Image.open(cover_path).convert("RGBA") as cover:
        draw = ImageDraw.Draw(canvas)
        kicker_font = load_font(30, bold=True)
        label_font = load_font(26, bold=True)
        label_small_font = load_font(22, bold=True)
        title_font = load_font(58, bold=True)
        quote_ru_font = load_font(44, bold=True)
        quote_en_font = load_font(30, bold=False)
        micro_font = load_font(24, bold=False)

        cover_ratio = cover.width / cover.height
        cover_height = 560
        cover_width = int(cover_height * cover_ratio)
        cover = cover.resize((cover_width, cover_height), Image.Resampling.LANCZOS)
        cover_x = (VIDEO_WIDTH - cover_width) // 2
        cover_y = 132

        glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((cover_x - 120, cover_y + 24, cover_x + cover_width + 120, cover_y + cover_height - 24), fill=(255, 106, 72, 72))
        glow_draw.ellipse((cover_x - 40, cover_y + 300, cover_x + cover_width + 160, cover_y + cover_height + 340), fill=(84, 255, 198, 54))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=26))
        canvas = Image.alpha_composite(canvas, glow)

        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle((cover_x - 18, cover_y - 18, cover_x + cover_width + 18, cover_y + cover_height + 18), radius=34, fill=(0, 0, 0, 165))
        canvas = Image.alpha_composite(canvas, shadow)
        canvas.alpha_composite(cover, (cover_x, cover_y))
        draw = ImageDraw.Draw(canvas)

        draw.rounded_rectangle((62, 56, 312, 108), radius=24, fill=(255, 255, 255, 34), outline=(255, 255, 255, 110), width=2)
        draw.text((90, 69), "CRYPOLT QUOTE", font=kicker_font, fill=(255, 255, 255, 246))
        draw_watermark(draw, watermark)

        panel_top = 760
        panel_bottom = VIDEO_HEIGHT - 70
        draw.rounded_rectangle((54, panel_top, VIDEO_WIDTH - 54, panel_bottom), radius=42, fill=(6, 8, 12, 210))
        draw.rounded_rectangle((84, panel_top + 28, 430, panel_top + 90), radius=22, fill=(255, 120, 54, 230))
        draw.text((110, panel_top + 36), f"DAY {day_number} OF {total_days}", font=label_font, fill=(255, 255, 255, 255))
        draw.text((110, panel_top + 62), f"ДЕНЬ {day_number} ИЗ {total_days}", font=label_small_font, fill=(255, 240, 230, 245))
        draw.text((84, panel_top + 112), f"Day {day_number} quote from {anime_title}", font=label_font, fill=(255, 209, 187, 236))
        draw.text((84, panel_top + 146), f"Цитата дня из {anime_title}", font=label_small_font, fill=(255, 233, 220, 220))

        title_lines = fit_text(draw, scene.title_ru, title_font, VIDEO_WIDTH - 180)
        y = panel_top + 184
        for line in title_lines[:2]:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=title_font, fill=(255, 255, 255, 255))
            y += 70

        draw.rounded_rectangle((92, y + 10, VIDEO_WIDTH - 92, y + 18), radius=4, fill=(255, 130, 76, 215))
        y += 40

        quote_prefix = '"'
        quote_suffix = '"'
        ru_lines = fit_text(draw, f"{quote_prefix}{scene.subtitle_ru}{quote_suffix}", quote_ru_font, VIDEO_WIDTH - 190)
        for line in ru_lines[:4]:
            bbox = draw.textbbox((0, 0), line, font=quote_ru_font)
            x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=quote_ru_font, fill=(255, 247, 219, 255))
            y += 56

        y += 10
        en_lines = fit_text(draw, f"{quote_prefix}{scene.subtitle_en}{quote_suffix}", quote_en_font, VIDEO_WIDTH - 220)
        for line in en_lines[:3]:
            bbox = draw.textbbox((0, 0), line, font=quote_en_font)
            x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=quote_en_font, fill=(219, 228, 240, 235))
            y += 40

        footer_text = "Like this short and comment which anime should get the next quote."
        footer_lines = fit_text(draw, footer_text, micro_font, VIDEO_WIDTH - 220)
        footer_y = panel_bottom - 108
        for line in footer_lines[:2]:
            bbox = draw.textbbox((0, 0), line, font=micro_font)
            x = (VIDEO_WIDTH - (bbox[2] - bbox[0])) // 2
            draw.text((x, footer_y), line, font=micro_font, fill=(203, 214, 229, 215))
            footer_y += 32

        if is_final_scene:
            draw_cta_strip(draw)

        canvas.convert("RGB").save(output_path, format="PNG")


def render_amv_card(background_path: Path, cover_path: Path, scene: Scene, anime_title: str, watermark: str, output_path: Path, is_final_scene: bool = False) -> None:
    with Image.open(background_path).convert("RGBA") as canvas, Image.open(cover_path).convert("RGBA") as cover:
        draw = ImageDraw.Draw(canvas)
        kicker_font = load_font(32, bold=True)
        title_font = load_font(88, bold=True)
        accent_font = load_font(40, bold=True)
        micro_font = load_font(26, bold=False)

        cover_ratio = cover.width / cover.height
        cover_width = 640
        cover_height = int(cover_width / cover_ratio)
        cover = cover.resize((cover_width, cover_height), Image.Resampling.LANCZOS)
        cover_x = (VIDEO_WIDTH - cover_width) // 2
        cover_y = 120

        shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle((cover_x - 26, cover_y - 26, cover_x + cover_width + 26, cover_y + cover_height + 26), radius=48, fill=(0, 0, 0, 175))
        canvas = Image.alpha_composite(canvas, shadow)
        canvas.alpha_composite(cover, (cover_x, cover_y))
        draw = ImageDraw.Draw(canvas)

        draw.rectangle((0, 0, VIDEO_WIDTH, 170), fill=(5, 5, 8, 120))
        draw.rectangle((0, VIDEO_HEIGHT - 240, VIDEO_WIDTH, VIDEO_HEIGHT), fill=(5, 5, 8, 145))
        draw.rectangle((64, 74, VIDEO_WIDTH - 64, 78), fill=(255, 112, 58, 230))
        draw_watermark(draw, watermark)

        kicker = "CRYPOLT AMV EDIT"
        draw.text((82, 94), kicker, font=kicker_font, fill=(255, 196, 150, 245))

        title_lines = fit_text(draw, scene.title_en.upper(), title_font, VIDEO_WIDTH - 160)
        subtitle_lines = fit_text(draw, scene.title_ru, accent_font, VIDEO_WIDTH - 160)
        y = VIDEO_HEIGHT - 228
        for line in title_lines[:2]:
            draw.text((82, y), line, font=title_font, fill=(255, 255, 255, 255))
            y += 96
        for line in subtitle_lines[:1]:
            draw.text((82, y), line, font=accent_font, fill=(255, 180, 140, 245))
            y += 50

        draw.text((82, VIDEO_HEIGHT - 64), anime_title.upper(), font=micro_font, fill=(222, 230, 242, 210))
        if is_final_scene:
            draw_cta_strip(draw)
        canvas.convert("RGB").save(output_path, format="PNG")


def synthesize_voice(text: str, output_path: Path) -> None:
    try:
        subprocess.run(
            [sys.executable, "-m", "edge_tts", "--voice", VOICE_RU, "--rate", "+8%", "--text", text, "--write-media", str(output_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "Voice generation failed. edge-tts is installed, but the selected voice could not be synthesized right now."
        ) from exc


def get_media_duration(media_path: Path, ffprobe_bin: str) -> float:
    result = subprocess.run([ffprobe_bin, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def allocate_scene_durations(scenes: list[Scene], total_duration: float, minimum_duration: float) -> None:
    weights = [max(len(scene.narration_ru.split()), 1) for scene in scenes]
    total_weight = sum(weights)
    target_duration = max(total_duration, minimum_duration)
    remaining = target_duration
    for index, scene in enumerate(scenes):
        min_scene_duration = 1.85 if index < 2 else 1.55
        if index == len(scenes) - 1:
            scene.duration_sec = max(min_scene_duration, round(remaining, 2))
            continue
        share = target_duration * (weights[index] / total_weight)
        if index == 0:
            share *= 0.88
        elif index == 1:
            share *= 0.94
        scene.duration_sec = max(min_scene_duration, round(share, 2))
        remaining -= scene.duration_sec


def allocate_amv_durations(scenes: list[Scene], total_duration: float) -> None:
    target_duration = max(total_duration, len(scenes) * 1.6)
    punch_weights = [1.15, 1.0, 1.05, 0.9, 0.95, 1.05]
    base = target_duration / sum(punch_weights[: len(scenes)])
    remaining = target_duration
    for index, scene in enumerate(scenes):
        if index == len(scenes) - 1:
            scene.duration_sec = round(max(1.35, remaining), 2)
            continue
        duration = max(1.35, round(base * punch_weights[index], 2))
        scene.duration_sec = duration
        remaining -= duration


def motion_filter(animation: str, duration_sec: float) -> str:
    frames = max(int(duration_sec * FPS), FPS)
    if animation == "flash_zoom":
        return (
            f"scale=1320:2346,zoompan=z='if(lte(on,14),1.08+on*0.012,1.25-(on-14)*0.0012)':"
            f"x='iw/2-(iw/zoom/2)+sin(on/5)*22':y='ih/2-(ih/zoom/2)+cos(on/7)*16':"
            f"d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
            "eq=contrast=1.18:saturation=1.24:brightness=0.04,unsharp=5:5:0.8:3:3:0.4,format=yuv420p"
        )
    if animation == "whip":
        return (
            f"scale=1380:2450,zoompan=z='1.10':x='mod(on*9, iw-iw/zoom)':y='ih/2-(ih/zoom/2)+sin(on/4)*18':"
            f"d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
            "eq=contrast=1.14:saturation=1.20:brightness=0.03,format=yuv420p"
        )
    if animation == "punch_in":
        return (
            f"scale=1200:2134,zoompan=z='if(lte(on,12),1+on*0.018,min(1.20,1.22-(on-12)*0.0007))':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
            "eq=contrast=1.08:saturation=1.15:brightness=0.02,format=yuv420p"
        )
    if animation == "pan":
        return (
            f"scale=1320:2346,zoompan=z='1.06':x='min(max(on*2.2,0),iw-iw/zoom)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},eq=contrast=1.06:saturation=1.10,format=yuv420p"
        )
    if animation == "drift":
        return (
            f"scale=1280:2276,zoompan=z='1.05+0.00025*on':x='iw/2-(iw/zoom/2)+sin(on/18)*18':"
            f"y='ih/2-(ih/zoom/2)+cos(on/22)*14':d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},"
            "eq=contrast=1.04:saturation=1.08,format=yuv420p"
        )
    if animation == "pulse":
        return (
            f"scale=1250:2223,zoompan=z='1.04+abs(sin(on/9))*0.02':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},eq=contrast=1.10:saturation=1.14:brightness=0.01,format=yuv420p"
        )
    return (
        f"scale=1240:2205,zoompan=z='min(zoom+0.0007,1.12)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"d={frames}:s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS},eq=contrast=1.07:saturation=1.12,format=yuv420p"
    )


def render_scene_clip(image_path: Path, duration_sec: float, animation: str, output_path: Path, ffmpeg_bin: str) -> None:
    subprocess.run([ffmpeg_bin, "-y", "-loop", "1", "-i", str(image_path), "-vf", motion_filter(animation, duration_sec), "-t", f"{duration_sec:.2f}", "-r", str(FPS), "-pix_fmt", "yuv420p", str(output_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def render_amv_video_clip(video_path: Path, duration_sec: float, animation: str, output_path: Path, ffmpeg_bin: str, seed: int) -> None:
    start_time = max((seed * 0.73) % 3.2, 0.0)
    vf = motion_filter(animation, duration_sec)
    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-ss",
            f"{start_time:.2f}",
            "-i",
            str(video_path),
            "-vf",
            vf,
            "-an",
            "-t",
            f"{duration_sec:.2f}",
            "-r",
            str(FPS),
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def combine_scene_clips(scene_clips: list[Path], scenes: list[Scene], output_path: Path, ffmpeg_bin: str) -> None:
    if len(scene_clips) == 1:
        shutil.copy2(scene_clips[0], output_path)
        return

    overlap = 0.42
    transitions = ["fade", "smoothleft", "smoothup", "fadeblack", "circleopen"]
    command = [ffmpeg_bin, "-y"]
    for clip in scene_clips:
        command.extend(["-i", str(clip)])

    filter_parts = [f"[{index}:v]settb=AVTB,setpts=PTS-STARTPTS[v{index}]" for index in range(len(scene_clips))]
    offset = scenes[0].duration_sec - overlap
    filter_parts.append(f"[v0][v1]xfade=transition={transitions[0]}:duration={overlap:.2f}:offset={offset:.2f}[x1]")
    composed_duration = scenes[0].duration_sec + scenes[1].duration_sec - overlap
    for index in range(2, len(scene_clips)):
        transition = transitions[(index - 1) % len(transitions)]
        offset = composed_duration - overlap
        filter_parts.append(f"[x{index - 1}][v{index}]xfade=transition={transition}:duration={overlap:.2f}:offset={offset:.2f}[x{index}]")
        composed_duration += scenes[index].duration_sec - overlap

    command.extend(["-filter_complex", ";".join(filter_parts), "-map", f"[x{len(scene_clips) - 1}]", "-pix_fmt", "yuv420p", str(output_path)])
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def mix_audio(voice_path: Path | None, music_path: Path | None, output_path: Path, ffmpeg_bin: str, duration_sec: float | None = None) -> None:
    if voice_path is None and music_path is None:
        duration = max(duration_sec or 1.0, 1.0)
        subprocess.run(
            [ffmpeg_bin, "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{duration:.2f}", "-c:a", "aac", str(output_path)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    if voice_path is not None and music_path is None:
        subprocess.run([ffmpeg_bin, "-y", "-i", str(voice_path), "-c:a", "aac", str(output_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return

    if voice_path is None and music_path is not None:
        duration = max(duration_sec or 1.0, 1.0)
        fade_out_start = max(duration - 0.65, 0.0)
        subprocess.run(
            [
                ffmpeg_bin,
                "-y",
                "-stream_loop",
                "-1",
                "-i",
                str(music_path),
                "-t",
                f"{duration:.2f}",
                "-af",
                f"volume=0.28,afade=t=in:st=0:d=0.45,afade=t=out:st={fade_out_start:.2f}:d=0.65",
                "-c:a",
                "aac",
                str(output_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return

    subprocess.run(
        [
            ffmpeg_bin,
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(music_path),
            "-i",
            str(voice_path),
            "-filter_complex",
            "[0:a]volume=0.10,afade=t=in:st=0:d=1.0,afade=t=out:st=99999:d=1.5[music];"
            "[music][1:a]sidechaincompress=threshold=0.02:ratio=10:attack=20:release=250[ducked];"
            "[ducked][1:a]amix=inputs=2:weights='0.55 1.0':normalize=0[aout]",
            "-map",
            "[aout]",
            "-c:a",
            "aac",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def attach_audio(video_path: Path, audio_path: Path, output_path: Path, ffmpeg_bin: str) -> None:
    subprocess.run([ffmpeg_bin, "-y", "-i", str(video_path), "-i", str(audio_path), "-c:v", "copy", "-c:a", "aac", "-shortest", str(output_path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
