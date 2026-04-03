from __future__ import annotations

import json
import os
import io
import subprocess
import sys
import threading
import webbrowser
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from queue import Empty, Queue
import tkinter as tk
from tkinter import messagebox, ttk

import imageio.v2 as imageio
import requests
from crypolt_shorts.pipeline import run_pipeline
from crypolt_shorts.app.settings import AppSettings
from crypolt_shorts.app.localization import Localizer
from crypolt_shorts.services.anime_service import fetch_anime_data, fetch_popular_anime_titles, get_popular_anime_titles, pick_cover_url
from crypolt_shorts.services.health_service import check_service_health
from crypolt_shorts.services.quote_series_service import run_quote_series
from crypolt_shorts.services.youtube_analytics_service import analyze_channel_shorts
from PIL import Image, ImageTk


OUTPUT_DIR = Path("output")


def open_path(path: Path | str) -> None:
    raw = str(path)
    if raw.startswith(("http://", "https://")):
        webbrowser.open(raw)
        return
    resolved = path.resolve()
    if os.name == "nt":
        os.startfile(str(resolved))  # type: ignore[attr-defined]
        return
    if sys.platform == "darwin":
        subprocess.run(["open", str(resolved)], check=False)
        return
    subprocess.run(["xdg-open", str(resolved)], check=False)


class CrypoltGUI:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("crypolt studio")
        self.root.geometry("1440x900")
        self.root.minsize(1180, 780)
        self.root.configure(bg="#07111f")

        self.queue: Queue[tuple[str, object]] = Queue()
        self.settings = AppSettings()
        self.localizer = Localizer(self.settings.locale)
        self.popular_anime_titles = get_popular_anime_titles()
        self.worker: threading.Thread | None = None
        self.analytics_worker: threading.Thread | None = None
        self.preview_worker: threading.Thread | None = None
        self.popular_titles_worker: threading.Thread | None = None
        self.quote_series_worker: threading.Thread | None = None
        self.health_worker: threading.Thread | None = None
        self.generation_cancel_event: threading.Event | None = None
        self.active_loader_operation: str | None = None
        self.analytics_request_id = 0
        self.preview_request_id = 0
        self.projects: list[Path] = []
        self.project_records: list[dict] = []
        self.current_project: Path | None = None
        self.service_health: dict[str, dict[str, str | bool]] = {}
        self.analytics_result: dict | None = None
        self.anime_preview_result: dict | None = None
        self.preview_image = None
        self.anime_cover_image = None
        self.anime_cover_source = None
        self.video_reader = None
        self.video_path: Path | None = None
        self.video_playing = False
        self.video_after_id = None
        self.preview_size = (620, 348)
        self.scroll_canvases: list[tk.Canvas] = []

        self.anime_var = tk.StringVar(value="Naruto")
        self.watermark_var = tk.StringVar(value="crypolt")
        self.duration_var = tk.StringVar(value="18")
        self.music_var = tk.StringVar(value="auto")
        self.mode_var = tk.StringVar(value="story")
        self.quote_series_anime_var = tk.StringVar(value="Naruto")
        self.quote_series_days_var = tk.StringVar(value="7")
        self.progress_var = tk.StringVar(value="Ready to create the next short")
        self.eta_var = tk.StringVar(value="ETA: -")
        self.step_var = tk.StringVar(value="Pipeline is idle")
        self.anime_preview_query_var = tk.StringVar(value="Naruto")
        self.anime_preview_status_var = tk.StringVar(value="Search for an anime to preview its info before rendering")
        self.analytics_query_var = tk.StringVar(value="")
        self.analytics_status_var = tk.StringVar(value="Enter a YouTube channel URL or a channel name")
        self.project_title_var = tk.StringVar(value="No project selected")
        self.project_meta_var = tk.StringVar(value="Select a generated video from the library")
        self.project_date_var = tk.StringVar(value="")
        self.preview_status_var = tk.StringVar(value="No video loaded")
        self.library_count_var = tk.StringVar(value="0 projects")
        self.last_result_var = tk.StringVar(value="No completed render yet")
        self.loader_status_var = tk.StringVar(value="Loading...")
        self.runtime_status_var = tk.StringVar(value="Checking...")
        self.jikan_runtime_status_var = tk.StringVar(value="Checking...")
        self.animechan_runtime_status_var = tk.StringVar(value="Checking...")
        self.pixabay_runtime_status_var = tk.StringVar(value="Checking...")

        self._build_styles()
        self._build_layout()
        self._build_loader_overlay()
        self._load_projects()
        self.root.after(150, self._pump_queue)
        self.root.after(220, self._start_popular_titles_refresh)
        self.root.after(300, self._start_anime_preview)
        self.root.after(340, self._start_service_health_check)

    def _build_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")

        base_bg = "#07111f"
        shell_bg = "#091423"
        card_bg = "#111c2d"
        tab_bg = "#0c1727"
        accent = "#ff7a18"
        accent_alt = "#ff4268"
        text = "#f4f8ff"
        muted = "#9db0c9"
        input_bg = "#0c1727"
        border = "#233247"

        style.configure("App.TFrame", background=base_bg)
        style.configure("Shell.TFrame", background=shell_bg)
        style.configure("Card.TFrame", background=card_bg)
        style.configure("Panel.TFrame", background=tab_bg)
        style.configure("TLabel", background=base_bg, foreground=text, font=("Segoe UI", 11))
        style.configure("Muted.TLabel", background=card_bg, foreground=muted, font=("Segoe UI", 10))
        style.configure("HeroTitle.TLabel", background=base_bg, foreground=text, font=("Segoe UI Semibold", 28))
        style.configure("HeroBody.TLabel", background=base_bg, foreground="#d6e4ff", font=("Segoe UI", 11))
        style.configure("Section.TLabel", background=card_bg, foreground=text, font=("Segoe UI Semibold", 13))
        style.configure("Info.TLabel", background=card_bg, foreground="#dce7fb", font=("Segoe UI", 11))
        style.configure("Metric.TLabel", background=card_bg, foreground=text, font=("Segoe UI Semibold", 18))
        style.configure("TButton", font=("Segoe UI Semibold", 10), padding=(14, 10))
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 11))
        style.map("Primary.TButton", background=[("active", accent_alt), ("!disabled", accent)], foreground=[("!disabled", "#ffffff")])
        style.configure("TEntry", fieldbackground=input_bg, foreground=text, bordercolor=border, insertcolor=text)
        style.configure("TCombobox", fieldbackground=input_bg, foreground=text, bordercolor=border, arrowsize=14, padding=8)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", input_bg), ("!disabled", input_bg)],
            foreground=[("readonly", text), ("!disabled", text)],
            selectbackground=[("readonly", "#13243b"), ("!disabled", "#13243b")],
            selectforeground=[("readonly", text), ("!disabled", text)],
        )
        style.configure(
            "Horizontal.TProgressbar",
            troughcolor="#0e1827",
            background=accent,
            bordercolor="#0e1827",
            lightcolor=accent,
            darkcolor=accent_alt,
        )
        style.configure("App.TNotebook", background=base_bg, borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "App.TNotebook.Tab",
            background="#0a1321",
            foreground="#aebed6",
            padding=(20, 12),
            font=("Segoe UI Semibold", 10),
            borderwidth=0,
        )
        style.map(
            "App.TNotebook.Tab",
            background=[("selected", card_bg), ("active", "#122036")],
            foreground=[("selected", "#ffffff"), ("active", "#ffffff")],
        )

    def _build_layout(self) -> None:
        shell = ttk.Frame(self.root, style="App.TFrame", padding=18)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        header = ttk.Frame(shell, style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="crypolt studio", style="HeroTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            header,
            text="AI-assisted anime Shorts pipeline with bilingual captions, branded motion and a built-in project library.",
            style="HeroBody.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.notebook = ttk.Notebook(shell, style="App.TNotebook")
        self.notebook.grid(row=1, column=0, sticky="nsew")

        self.preview_tab = self._make_scrollable_tab("Anime Preview")
        self.create_tab = self._make_scrollable_tab("New Video")
        self.quote_series_tab = self._make_scrollable_tab("Quote Series")
        self.projects_tab = self._make_scrollable_tab("Projects")
        self.analytics_tab = self._make_scrollable_tab("Analytics")

        self._build_preview_tab()
        self._build_create_tab()
        self._build_quote_series_tab()
        self._build_projects_tab()
        self._build_analytics_tab()
        self.root.bind("<Configure>", self._handle_resize)
        self.root.bind("<space>", lambda _event: self._toggle_playback())
        self.root.bind_all("<MouseWheel>", self._on_global_mousewheel, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.notebook.select(0)

    def _build_loader_overlay(self) -> None:
        self.loader_overlay = tk.Frame(self.root, bg="#050b15")
        self.loader_card = ttk.Frame(self.loader_overlay, style="Card.TFrame", padding=24)
        self.loader_card.place(relx=0.5, rely=0.5, anchor="center")
        ttk.Label(self.loader_card, text="Please wait", style="Section.TLabel").pack(anchor="w")
        ttk.Label(self.loader_card, textvariable=self.loader_status_var, style="Muted.TLabel", wraplength=420, justify="left").pack(anchor="w", pady=(8, 14))
        self.loader_progress = ttk.Progressbar(self.loader_card, mode="indeterminate", length=320)
        self.loader_progress.pack(fill="x")
        self.loader_cancel_button = ttk.Button(self.loader_card, text="Cancel", command=self._cancel_active_operation)
        self.loader_cancel_button.pack(anchor="e", pady=(16, 0))

    def _show_loader(self, operation: str, message: str, cancellable: bool = True) -> None:
        self.active_loader_operation = operation
        self.loader_status_var.set(message)
        if cancellable:
            self.loader_cancel_button.state(["!disabled"])
        else:
            self.loader_cancel_button.state(["disabled"])
        self.loader_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.loader_overlay.lift()
        self.loader_progress.start(10)

    def _hide_loader(self, operation: str | None = None) -> None:
        if operation is not None and self.active_loader_operation != operation:
            return
        self.active_loader_operation = None
        self.loader_progress.stop()
        self.loader_overlay.place_forget()

    def _update_loader(self, operation: str, message: str) -> None:
        if self.active_loader_operation == operation:
            self.loader_status_var.set(message)

    def _cancel_active_operation(self) -> None:
        operation = self.active_loader_operation
        if operation == "generation" and self.generation_cancel_event is not None:
            self.generation_cancel_event.set()
            self.loader_status_var.set("Cancelling generation after the current step...")
            self._append_output("[loader] Cancelling generation...")
        elif operation == "quote_series" and self.generation_cancel_event is not None:
            self.generation_cancel_event.set()
            self.loader_status_var.set("Cancelling quote series after the current day...")
            self._append_output("[loader] Cancelling quote series...")
        elif operation == "anime_preview":
            self.preview_request_id += 1
            self._hide_loader("anime_preview")
            self.anime_preview_button.state(["!disabled"])
            self.anime_preview_status_var.set("Anime preview cancelled")
            self._append_output("[loader] Anime preview cancelled")
        elif operation == "analytics":
            self.analytics_request_id += 1
            self._hide_loader("analytics")
            self.analytics_button.state(["!disabled"])
            self.analytics_status_var.set("Channel analytics cancelled")
            self._append_output("[loader] Channel analytics cancelled")

    def _build_preview_tab(self) -> None:
        self.preview_tab.columnconfigure(0, weight=4)
        self.preview_tab.columnconfigure(1, weight=6)
        self.preview_tab.rowconfigure(1, weight=1)

        top_card = ttk.Frame(self.preview_tab, style="Card.TFrame", padding=20)
        top_card.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        top_card.columnconfigure(0, weight=1)

        ttk.Label(top_card, text="Anime preview", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            top_card,
            text="Check anime info, synopsis, score and cover art before launching a new Crypolt short.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 14))

        search_row = ttk.Frame(top_card, style="Card.TFrame")
        search_row.grid(row=2, column=0, sticky="ew")
        search_row.columnconfigure(0, weight=1)
        self.anime_preview_combo = ttk.Combobox(
            search_row,
            textvariable=self.anime_preview_query_var,
            values=self.popular_anime_titles,
            height=20,
        )
        self.anime_preview_combo.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.anime_preview_combo.bind("<<ComboboxSelected>>", self._on_preview_anime_selected)
        self._register_scroll_safe_widget(self.anime_preview_combo)
        self.anime_preview_button = ttk.Button(search_row, text="Preview Anime", style="Primary.TButton", command=self._start_anime_preview)
        self.anime_preview_button.grid(row=0, column=1, sticky="e")
        ttk.Button(search_row, text="Use for Generation", command=self._use_preview_for_generation).grid(row=0, column=2, sticky="e", padx=(10, 0))
        ttk.Label(top_card, textvariable=self.anime_preview_status_var, style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(12, 0))

        cover_card = ttk.Frame(self.preview_tab, style="Card.TFrame", padding=18)
        cover_card.grid(row=1, column=0, sticky="nsew", padx=(0, 10))
        cover_card.columnconfigure(0, weight=1)
        ttk.Label(cover_card, text="Cover", style="Section.TLabel").grid(row=0, column=0, sticky="w")

        cover_shell = tk.Frame(cover_card, bg="#08111d", highlightthickness=1, highlightbackground="#283447")
        cover_shell.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        cover_shell.configure(height=640, width=420)
        cover_shell.grid_propagate(False)
        cover_card.rowconfigure(1, weight=1)
        self.cover_shell = cover_shell
        self.anime_cover_label = tk.Label(
            cover_shell,
            text="No anime selected yet",
            bg="#08111d",
            fg="#d7e5ff",
            font=("Segoe UI", 13),
            anchor="center",
            justify="center",
        )
        self.anime_cover_label.pack(fill="both", expand=True)
        self.anime_cover_label.bind("<Configure>", lambda _event: self._refresh_cover_image())

        info_shell = ttk.Frame(self.preview_tab, style="Shell.TFrame")
        info_shell.grid(row=1, column=1, sticky="nsew", padx=(10, 0))
        info_shell.columnconfigure(0, weight=1)
        info_shell.rowconfigure(0, weight=0)
        info_shell.rowconfigure(1, weight=1)

        meta_card = ttk.Frame(info_shell, style="Card.TFrame", padding=18)
        meta_card.grid(row=0, column=0, sticky="ew")
        meta_card.columnconfigure(0, weight=1)
        meta_card.columnconfigure(1, weight=1)
        ttk.Label(meta_card, text="Anime details", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.anime_preview_title_var = tk.StringVar(value="No anime loaded")
        self.anime_preview_meta_var = tk.StringVar(value="Search by anime title to load metadata.")
        ttk.Label(meta_card, textvariable=self.anime_preview_title_var, style="Info.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 4))
        ttk.Label(meta_card, textvariable=self.anime_preview_meta_var, style="Muted.TLabel", wraplength=560, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

        self.anime_preview_score_var = tk.StringVar(value="-")
        self.anime_preview_year_var = tk.StringVar(value="-")
        self.anime_preview_episodes_var = tk.StringVar(value="-")
        self.anime_preview_genres_var = tk.StringVar(value="-")
        self._metric_card(meta_card, "Score", self.anime_preview_score_var, 3)
        self._metric_card(meta_card, "Year", self.anime_preview_year_var, 4)
        self._metric_card(meta_card, "Episodes", self.anime_preview_episodes_var, 5)
        self._metric_card(meta_card, "Genres", self.anime_preview_genres_var, 6)

        synopsis_card = ttk.Frame(info_shell, style="Card.TFrame", padding=18)
        synopsis_card.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        synopsis_card.columnconfigure(0, weight=1)
        synopsis_card.rowconfigure(1, weight=1)
        ttk.Label(synopsis_card, text="Synopsis", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.anime_synopsis_box = tk.Text(
            synopsis_card,
            height=16,
            bg="#0c1727",
            fg="#dce7fb",
            relief="flat",
            wrap="word",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            padx=12,
            pady=12,
        )
        self.anime_synopsis_box.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.anime_synopsis_box.insert("end", "Anime synopsis will appear here.\n")
        self.anime_synopsis_box.configure(state="disabled")

    def _make_scrollable_tab(self, title: str) -> ttk.Frame:
        outer = ttk.Frame(self.notebook, style="Shell.TFrame")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(0, weight=1)

        canvas = tk.Canvas(outer, bg="#091423", highlightthickness=0, bd=0)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        canvas.configure(yscrollcommand=scrollbar.set)

        inner = ttk.Frame(canvas, style="Shell.TFrame", padding=18)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def on_configure(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def on_canvas_configure(event) -> None:
            canvas.itemconfigure(window_id, width=event.width)

        inner.bind("<Configure>", on_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        canvas.bind("<Enter>", lambda _event: setattr(self, "_active_scroll_canvas", canvas))
        canvas.bind("<Leave>", lambda _event: setattr(self, "_active_scroll_canvas", None))

        self.scroll_canvases.append(canvas)
        self.notebook.add(outer, text=title)
        setattr(inner, "_tab_outer", outer)
        return inner

    def _select_tab(self, inner_tab: ttk.Frame) -> None:
        outer = getattr(inner_tab, "_tab_outer", inner_tab)
        self.notebook.select(outer)

    def _on_global_mousewheel(self, event) -> None:
        canvas = getattr(self, "_active_scroll_canvas", None)
        if canvas is None:
            current = self.notebook.select()
            for child in self.notebook.winfo_children():
                if str(child) == current:
                    widgets = [widget for widget in child.winfo_children() if isinstance(widget, tk.Canvas)]
                    canvas = widgets[0] if widgets else None
                    break
        if canvas is None:
            return
        delta = -1 * int(event.delta / 120) if event.delta else 0
        if delta:
            canvas.yview_scroll(delta, "units")

    def _register_scroll_safe_widget(self, widget) -> None:
        widget.bind("<Enter>", lambda _event: setattr(self, "_active_scroll_canvas", None), add="+")
        widget.bind("<MouseWheel>", lambda _event: "break", add="+")

    def _build_create_tab(self) -> None:
        self.create_tab.columnconfigure(0, weight=5)
        self.create_tab.columnconfigure(1, weight=4)
        self.create_tab.rowconfigure(2, weight=1)

        hero = ttk.Frame(self.create_tab, style="Card.TFrame", padding=22)
        hero.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        hero.columnconfigure(0, weight=1)
        hero.columnconfigure(1, weight=1)
        hero.columnconfigure(2, weight=1)

        ttk.Label(hero, text="Create a new short", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            hero,
            text="Set the anime, tune the render options and launch the full pipeline from one focused workspace.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 18))

        form = ttk.Frame(hero, style="Card.TFrame")
        form.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=(0, 16))
        form.columnconfigure(0, weight=1)
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Anime title", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(8, 6))
        self.anime_combo = ttk.Combobox(form, textvariable=self.anime_var, values=self.popular_anime_titles, height=20)
        self.anime_combo.grid(row=1, column=0, sticky="ew", padx=(0, 12))
        self.anime_combo.bind("<<ComboboxSelected>>", self._on_create_anime_selected)
        self._register_scroll_safe_widget(self.anime_combo)
        self._field(form, "Watermark", self.watermark_var, 0, 1)
        self._field(form, "Duration (sec)", self.duration_var, 2, 0)

        ttk.Label(form, text="Music mode", style="Section.TLabel").grid(row=2, column=1, sticky="w", pady=(8, 6))
        music_combo = ttk.Combobox(form, textvariable=self.music_var, values=["auto", "off"], state="readonly")
        music_combo.grid(row=3, column=1, sticky="ew", padx=(0, 12))
        self._register_scroll_safe_widget(music_combo)
        ttk.Label(form, text="Render mode", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=(8, 6))
        mode_combo = ttk.Combobox(form, textvariable=self.mode_var, values=["story", "amv_edit"], state="readonly")
        mode_combo.grid(row=5, column=0, sticky="ew", padx=(0, 12))
        self._register_scroll_safe_widget(mode_combo)

        metrics = ttk.Frame(hero, style="Card.TFrame")
        metrics.grid(row=2, column=2, sticky="nsew")
        metrics.columnconfigure(0, weight=1)

        self._metric_card(metrics, "Library", self.library_count_var, 0)
        self._metric_card(metrics, "Last export", self.last_result_var, 1)

        controls = ttk.Frame(self.create_tab, style="Shell.TFrame")
        controls.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        self.generate_button = ttk.Button(controls, text="Generate Video", style="Primary.TButton", command=self._start_generation)
        self.generate_button.pack(side="left")
        ttk.Button(controls, text="Check Services", command=self._start_service_health_check).pack(side="left", padx=(10, 0))
        ttk.Button(controls, text="Open Latest Folder", command=self._open_selected_folder).pack(side="left", padx=(10, 0))
        ttk.Button(controls, text="Go to Projects", command=lambda: self._select_tab(self.projects_tab)).pack(side="left", padx=(10, 0))

        health_card = ttk.Frame(self.create_tab, style="Card.TFrame", padding=20)
        health_card.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 16))
        for column in range(4):
            health_card.columnconfigure(column, weight=1)
        ttk.Label(health_card, text="Service status", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(health_card, text="Availability of runtime and public APIs before launch.", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=4, sticky="w", pady=(4, 14)
        )
        self._service_badge(health_card, "edge-tts", self.runtime_status_var, 2, 0)
        self._service_badge(health_card, "Jikan", self.jikan_runtime_status_var, 2, 1)
        self._service_badge(health_card, "Animechan", self.animechan_runtime_status_var, 2, 2)
        self._service_badge(health_card, "Pixabay", self.pixabay_runtime_status_var, 2, 3)

        pipeline_card = ttk.Frame(self.create_tab, style="Card.TFrame", padding=20)
        pipeline_card.grid(row=3, column=0, sticky="nsew", padx=(0, 10))
        pipeline_card.columnconfigure(0, weight=1)
        pipeline_card.rowconfigure(4, weight=1)

        ttk.Label(pipeline_card, text="Pipeline status", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(pipeline_card, textvariable=self.progress_var, style="Info.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 6))
        ttk.Label(pipeline_card, textvariable=self.step_var, style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Label(pipeline_card, textvariable=self.eta_var, style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(4, 12))
        self.progressbar = ttk.Progressbar(pipeline_card, maximum=8, mode="determinate")
        self.progressbar.grid(row=4, column=0, sticky="ew")

        log_card = ttk.Frame(self.create_tab, style="Card.TFrame", padding=20)
        log_card.grid(row=3, column=1, sticky="nsew", padx=(10, 0))
        log_card.columnconfigure(0, weight=1)
        log_card.rowconfigure(1, weight=1)
        ttk.Label(log_card, text="Activity log", style="Section.TLabel").grid(row=0, column=0, sticky="w")

        self.output_box = tk.Text(
            log_card,
            height=20,
            bg="#0c1727",
            fg="#eef4ff",
            insertbackground="#ffffff",
            relief="flat",
            wrap="word",
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 10),
            padx=14,
            pady=14,
        )
        self.output_box.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.output_box.insert("end", "Pick an anime title and start the next Crypolt render.\n")
        self.output_box.configure(state="disabled")

    def _build_projects_tab(self) -> None:
        self.projects_tab.columnconfigure(0, weight=3)
        self.projects_tab.columnconfigure(1, weight=7)
        self.projects_tab.rowconfigure(0, weight=1)

        library_card = ttk.Frame(self.projects_tab, style="Card.TFrame", padding=18)
        library_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        library_card.columnconfigure(0, weight=1)
        library_card.rowconfigure(1, weight=1)

        ttk.Label(library_card, text="Project library", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(library_card, text="Browse completed Crypolt video projects.", style="Muted.TLabel").grid(row=0, column=1, sticky="e")

        list_frame = ttk.Frame(library_card, style="Card.TFrame")
        list_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(14, 12))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.project_list = tk.Listbox(
            list_frame,
            bg="#0c1727",
            fg="#eef4ff",
            selectbackground="#ff5f3d",
            selectforeground="#ffffff",
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 11),
            width=34,
        )
        self.project_list.grid(row=0, column=0, sticky="nsew")
        self.project_list.bind("<<ListboxSelect>>", self._on_project_select)

        list_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.project_list.yview)
        list_scroll.grid(row=0, column=1, sticky="ns")
        self.project_list.configure(yscrollcommand=list_scroll.set)

        actions = ttk.Frame(library_card, style="Card.TFrame")
        actions.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Button(actions, text="Refresh", command=self._load_projects).pack(side="left")
        ttk.Button(actions, text="Open Folder", command=self._open_selected_folder).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Open Video", command=self._open_selected_video).pack(side="left", padx=(8, 0))

        project_shell = ttk.Frame(self.projects_tab, style="Shell.TFrame")
        project_shell.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        project_shell.columnconfigure(0, weight=1)
        project_shell.rowconfigure(0, weight=1)
        project_shell.rowconfigure(1, weight=1)

        metadata_card = ttk.Frame(project_shell, style="Card.TFrame", padding=18)
        metadata_card.grid(row=0, column=0, sticky="nsew")
        metadata_card.columnconfigure(0, weight=1)
        metadata_card.columnconfigure(1, weight=1)
        metadata_card.rowconfigure(5, weight=1)

        ttk.Label(metadata_card, text="Project details", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(metadata_card, textvariable=self.project_title_var, style="Info.TLabel").grid(row=1, column=0, sticky="w", pady=(10, 4))
        ttk.Label(metadata_card, textvariable=self.project_meta_var, style="Muted.TLabel", wraplength=420, justify="left").grid(
            row=2, column=0, sticky="w"
        )
        ttk.Label(metadata_card, textvariable=self.project_date_var, style="Muted.TLabel").grid(row=3, column=0, sticky="w", pady=(8, 0))

        ttk.Label(metadata_card, text="Shorts title", style="Section.TLabel").grid(row=4, column=0, sticky="w", pady=(16, 6))
        self.title_box = self._text_panel(metadata_card, 3, "#eef4ff", ("Segoe UI Semibold", 10))
        self.title_box.grid(row=5, column=0, sticky="nsew", padx=(0, 12))

        right_meta = ttk.Frame(metadata_card, style="Card.TFrame")
        right_meta.grid(row=1, column=1, rowspan=5, sticky="nsew")
        right_meta.columnconfigure(0, weight=1)
        right_meta.rowconfigure(1, weight=1)
        right_meta.rowconfigure(3, weight=0)

        ttk.Label(right_meta, text="Description", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(52, 6))
        self.description_box = self._text_panel(right_meta, 10, "#d8e6ff", ("Segoe UI", 10))
        self.description_box.grid(row=1, column=0, sticky="nsew")

        ttk.Label(right_meta, text="Hashtags", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=(16, 6))
        self.hashtags_box = self._text_panel(right_meta, 4, "#ffb07f", ("Consolas", 10))
        self.hashtags_box.grid(row=3, column=0, sticky="ew")

        preview_card = ttk.Frame(project_shell, style="Card.TFrame", padding=18)
        preview_card.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        preview_card.columnconfigure(0, weight=1)
        ttk.Label(preview_card, text="Video preview", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(preview_card, text="Preview the generated final.mp4 without leaving the app.", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", pady=(4, 12)
        )

        preview_shell = tk.Frame(preview_card, bg="#08111d", highlightthickness=1, highlightbackground="#283447", height=420)
        preview_shell.grid(row=2, column=0, sticky="nsew")
        preview_shell.grid_propagate(False)
        preview_card.rowconfigure(2, weight=1)
        self.preview_shell = preview_shell

        self.preview_label = tk.Label(
            preview_shell,
            text="Select a project to preview video\n\nClick here or press Play to start",
            bg="#08111d",
            fg="#d7e5ff",
            font=("Segoe UI", 13),
            width=64,
            height=22,
            cursor="hand2",
        )
        self.preview_label.pack(fill="both", expand=True)
        self.preview_label.bind("<Button-1>", lambda _event: self._toggle_playback())

        preview_controls = ttk.Frame(preview_card, style="Card.TFrame")
        preview_controls.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.play_button = ttk.Button(preview_controls, text="Start Preview", command=self._toggle_playback)
        self.play_button.pack(side="left")
        ttk.Button(preview_controls, text="Restart", command=self._restart_video).pack(side="left", padx=(8, 0))
        ttk.Button(preview_controls, text="Open Video", command=self._open_selected_video).pack(side="left", padx=(8, 0))
        ttk.Button(preview_controls, text="Open Result Folder", command=self._open_selected_folder).pack(side="left", padx=(8, 0))
        ttk.Label(preview_controls, textvariable=self.preview_status_var, style="Muted.TLabel").pack(side="right")

        for widget in (self.title_box, self.description_box, self.hashtags_box):
            widget.configure(state="disabled")

    def _build_quote_series_tab(self) -> None:
        self.quote_series_tab.columnconfigure(0, weight=1)
        self.quote_series_tab.rowconfigure(1, weight=1)

        top_card = ttk.Frame(self.quote_series_tab, style="Card.TFrame", padding=20)
        top_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        top_card.columnconfigure(0, weight=1)
        top_card.columnconfigure(1, weight=1)

        ttk.Label(top_card, text="Quote series generator", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            top_card,
            text="Create one anime quote video per day using public quotes and your existing Crypolt visual style.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 18))

        ttk.Label(top_card, text="Anime title", style="Section.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 6))
        self.quote_series_combo = ttk.Combobox(top_card, textvariable=self.quote_series_anime_var, values=self.popular_anime_titles, height=20)
        self.quote_series_combo.grid(row=3, column=0, sticky="ew", padx=(0, 12))
        self._register_scroll_safe_widget(self.quote_series_combo)

        ttk.Label(top_card, text="Number of days", style="Section.TLabel").grid(row=2, column=1, sticky="w", pady=(8, 6))
        quote_days_entry = ttk.Entry(top_card, textvariable=self.quote_series_days_var)
        quote_days_entry.grid(row=3, column=1, sticky="ew")

        actions = ttk.Frame(top_card, style="Card.TFrame")
        actions.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(18, 0))
        self.quote_series_button = ttk.Button(actions, text="Generate Quote Series", style="Primary.TButton", command=self._start_quote_series)
        self.quote_series_button.pack(side="left")
        ttk.Button(actions, text="Open Projects", command=lambda: self._select_tab(self.projects_tab)).pack(side="left", padx=(10, 0))

        info_card = ttk.Frame(self.quote_series_tab, style="Card.TFrame", padding=18)
        info_card.grid(row=1, column=0, sticky="nsew")
        info_card.columnconfigure(0, weight=1)
        info_card.rowconfigure(1, weight=1)
        ttk.Label(info_card, text="Quote series notes", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.quote_series_info = tk.Text(
            info_card,
            height=14,
            bg="#0c1727",
            fg="#dce7fb",
            relief="flat",
            wrap="word",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            padx=12,
            pady=12,
        )
        self.quote_series_info.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self.quote_series_info.insert(
            "end",
            "This mode creates a folder with day_01, day_02, ... Each day gets one quote-based short with cover, quote, voice, music and CTA.\n",
        )
        self.quote_series_info.configure(state="disabled")

    def _build_analytics_tab(self) -> None:
        self.analytics_tab.columnconfigure(0, weight=1)
        self.analytics_tab.rowconfigure(1, weight=1)

        top_card = ttk.Frame(self.analytics_tab, style="Card.TFrame", padding=20)
        top_card.grid(row=0, column=0, sticky="ew", pady=(0, 16))
        top_card.columnconfigure(0, weight=1)
        top_card.columnconfigure(1, weight=0)

        ttk.Label(top_card, text="Channel analytics", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            top_card,
            text="Analyze public Shorts performance by channel URL, @handle or channel name.",
            style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 14))

        search_row = ttk.Frame(top_card, style="Card.TFrame")
        search_row.grid(row=2, column=0, columnspan=2, sticky="ew")
        search_row.columnconfigure(0, weight=1)
        self.analytics_entry = ttk.Entry(search_row, textvariable=self.analytics_query_var)
        self.analytics_entry.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.analytics_button = ttk.Button(search_row, text="Analyze Channel", style="Primary.TButton", command=self._start_analytics)
        self.analytics_button.grid(row=0, column=1, sticky="e")
        ttk.Label(top_card, textvariable=self.analytics_status_var, style="Muted.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

        content = ttk.Frame(self.analytics_tab, style="Shell.TFrame")
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=4)
        content.columnconfigure(1, weight=6)
        content.rowconfigure(0, weight=1)

        metrics_card = ttk.Frame(content, style="Card.TFrame", padding=18)
        metrics_card.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        metrics_card.columnconfigure(0, weight=1)
        metrics_card.columnconfigure(1, weight=1)
        metrics_card.rowconfigure(3, weight=1)

        ttk.Label(metrics_card, text="Channel snapshot", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.analytics_channel_title = tk.StringVar(value="No channel loaded")
        self.analytics_channel_meta = tk.StringVar(value="Run an analysis to fill this panel.")
        ttk.Label(metrics_card, textvariable=self.analytics_channel_title, style="Info.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 4))
        ttk.Label(metrics_card, textvariable=self.analytics_channel_meta, style="Muted.TLabel", wraplength=420, justify="left").grid(
            row=2, column=0, columnspan=2, sticky="w"
        )

        self.analytics_followers = tk.StringVar(value="-")
        self.analytics_shorts_count = tk.StringVar(value="-")
        self.analytics_total_views = tk.StringVar(value="-")
        self.analytics_avg_views = tk.StringVar(value="-")
        self._metric_card(metrics_card, "Followers", self.analytics_followers, 3)
        self._metric_card(metrics_card, "Shorts analyzed", self.analytics_shorts_count, 4)
        self._metric_card(metrics_card, "Total views", self.analytics_total_views, 5)
        self._metric_card(metrics_card, "Average views", self.analytics_avg_views, 6)

        summary_frame = ttk.Frame(metrics_card, style="Panel.TFrame", padding=16)
        summary_frame.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        summary_frame.columnconfigure(0, weight=1)
        ttk.Label(summary_frame, text="Shorts summary", style="Section.TLabel").grid(row=0, column=0, sticky="w")
        self.analytics_summary_box = tk.Text(
            summary_frame,
            height=9,
            bg="#0c1727",
            fg="#dce7fb",
            relief="flat",
            wrap="word",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            padx=12,
            pady=12,
        )
        self.analytics_summary_box.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        self.analytics_summary_box.insert("end", "Channel-level patterns will appear here.\n")
        self.analytics_summary_box.configure(state="disabled")

        table_card = ttk.Frame(content, style="Card.TFrame", padding=18)
        table_card.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        table_card.columnconfigure(0, weight=1)
        table_card.rowconfigure(1, weight=1)

        ttk.Label(table_card, text="Top Shorts", style="Section.TLabel").grid(row=0, column=0, sticky="w")

        table_frame = ttk.Frame(table_card, style="Card.TFrame")
        table_frame.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("date", "views", "likes", "comments", "duration")
        self.analytics_tree = ttk.Treeview(table_frame, columns=columns, show="tree headings", height=16)
        self.analytics_tree.heading("#0", text="Short title")
        self.analytics_tree.heading("date", text="Date")
        self.analytics_tree.heading("views", text="Views")
        self.analytics_tree.heading("likes", text="Likes")
        self.analytics_tree.heading("comments", text="Comments")
        self.analytics_tree.heading("duration", text="Duration")
        self.analytics_tree.column("#0", width=390, stretch=True)
        self.analytics_tree.column("date", width=88, anchor="center", stretch=False)
        self.analytics_tree.column("views", width=90, anchor="e", stretch=False)
        self.analytics_tree.column("likes", width=82, anchor="e", stretch=False)
        self.analytics_tree.column("comments", width=88, anchor="e", stretch=False)
        self.analytics_tree.column("duration", width=80, anchor="center", stretch=False)
        self.analytics_tree.grid(row=0, column=0, sticky="nsew")
        self.analytics_tree.bind("<<TreeviewSelect>>", self._on_analytics_short_select)

        tree_scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.analytics_tree.yview)
        tree_scroll.grid(row=0, column=1, sticky="ns")
        self.analytics_tree.configure(yscrollcommand=tree_scroll.set)

        analytics_actions = ttk.Frame(table_card, style="Card.TFrame")
        analytics_actions.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        ttk.Button(analytics_actions, text="Open Channel", command=self._open_analytics_channel).pack(side="left")
        ttk.Button(analytics_actions, text="Open Selected Short", command=self._open_selected_short).pack(side="left", padx=(8, 0))
        ttk.Button(analytics_actions, text="Copy Summary", command=self._copy_analytics_summary).pack(side="left", padx=(8, 0))

    def _field(self, parent: ttk.Frame, label: str, variable: tk.StringVar, row: int, column: int) -> None:
        ttk.Label(parent, text=label, style="Section.TLabel").grid(row=row, column=column, sticky="w", pady=(8, 6))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row + 1, column=column, sticky="ew", padx=(0, 12))

    def _metric_card(self, parent: ttk.Frame, title: str, variable: tk.StringVar, row: int) -> None:
        card = ttk.Frame(parent, style="Panel.TFrame", padding=16)
        card.grid(row=row, column=0, sticky="ew", pady=(0, 12))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=title, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, textvariable=variable, style="Metric.TLabel").grid(row=1, column=0, sticky="w", pady=(6, 0))

    def _service_badge(self, parent: ttk.Frame, title: str, variable: tk.StringVar, row: int, column: int) -> None:
        card = ttk.Frame(parent, style="Panel.TFrame", padding=14)
        card.grid(row=row, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0), pady=(0, 4))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=title, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(card, textvariable=variable, style="Info.TLabel").grid(row=1, column=0, sticky="w", pady=(8, 0))

    def _text_panel(self, parent: ttk.Frame, height: int, fg: str, font: tuple[str, int] | tuple[str, int, str]) -> tk.Text:
        return tk.Text(
            parent,
            height=height,
            bg="#0c1727",
            fg=fg,
            relief="flat",
            wrap="word",
            borderwidth=0,
            highlightthickness=0,
            font=font,
            padx=12,
            pady=12,
        )

    def _format_health_value(self, ok: bool, message: str) -> str:
        status = "OK" if ok else "Offline"
        compact = message.strip().replace("\n", " ")
        if len(compact) > 42:
            compact = compact[:39] + "..."
        return f"{status} | {compact}"

    def _apply_service_health(self, health: dict[str, dict[str, str | bool]]) -> None:
        self.service_health = health
        self.runtime_status_var.set(self._format_health_value(bool(health.get("edge_tts", {}).get("ok")), str(health.get("edge_tts", {}).get("message", "-"))))
        self.jikan_runtime_status_var.set(self._format_health_value(bool(health.get("jikan", {}).get("ok")), str(health.get("jikan", {}).get("message", "-"))))
        self.animechan_runtime_status_var.set(self._format_health_value(bool(health.get("animechan", {}).get("ok")), str(health.get("animechan", {}).get("message", "-"))))
        self.pixabay_runtime_status_var.set(self._format_health_value(bool(health.get("pixabay", {}).get("ok")), str(health.get("pixabay", {}).get("message", "-"))))

    def _start_service_health_check(self) -> None:
        if self.health_worker and self.health_worker.is_alive():
            return

        self.runtime_status_var.set("Checking...")
        self.jikan_runtime_status_var.set("Checking...")
        self.animechan_runtime_status_var.set("Checking...")
        self.pixabay_runtime_status_var.set("Checking...")
        self._append_output("[health] Checking runtime and public APIs...")

        def worker() -> None:
            try:
                result = check_service_health(self.settings, self.localizer)
                self.queue.put(("service_health_done", result))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("service_health_error", str(exc)))

        self.health_worker = threading.Thread(target=worker, daemon=True)
        self.health_worker.start()

    def _preflight_ready(self, mode: str) -> tuple[bool, str]:
        if not self.service_health:
            return True, ""
        required = ["ffmpeg", "ffprobe", "jikan"]
        if mode != "amv_edit":
            required.append("edge_tts")
        missing = [name for name in required if not bool(self.service_health.get(name, {}).get("ok"))]
        if not missing:
            return True, ""
        return False, f"Unavailable right now: {', '.join(missing)}"

    def _append_output(self, text: str) -> None:
        self.output_box.configure(state="normal")
        self.output_box.insert("end", text + "\n")
        self.output_box.see("end")
        self.output_box.configure(state="disabled")

    def _set_text_widget(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("end", text)
        widget.configure(state="disabled")

    def _set_analytics_summary(self, text: str) -> None:
        self.analytics_summary_box.configure(state="normal")
        self.analytics_summary_box.delete("1.0", "end")
        self.analytics_summary_box.insert("end", text)
        self.analytics_summary_box.configure(state="disabled")

    def _on_preview_anime_selected(self, _event=None) -> None:
        value = self.anime_preview_query_var.get().strip()
        if value:
            self.anime_var.set(value)

    def _on_create_anime_selected(self, _event=None) -> None:
        value = self.anime_var.get().strip()
        if value:
            self.anime_preview_query_var.set(value)

    def _start_popular_titles_refresh(self) -> None:
        if self.popular_titles_worker and self.popular_titles_worker.is_alive():
            return

        def worker() -> None:
            try:
                titles = fetch_popular_anime_titles(self.settings, limit=100)
                self.queue.put(("popular_titles_done", titles))
            except Exception:
                self.queue.put(("popular_titles_error", None))

        self.popular_titles_worker = threading.Thread(target=worker, daemon=True)
        self.popular_titles_worker.start()

    def _apply_popular_titles(self, titles: list[str]) -> None:
        merged: list[str] = []
        for title in titles + self.popular_anime_titles:
            if title and title not in merged:
                merged.append(title)
        self.popular_anime_titles = merged
        if hasattr(self, "anime_preview_combo"):
            self.anime_preview_combo.configure(values=self.popular_anime_titles)
        if hasattr(self, "anime_combo"):
            self.anime_combo.configure(values=self.popular_anime_titles)
        self._append_output(f"[anime-list] Loaded {len(self.popular_anime_titles)} anime titles from Jikan/fallback")

    def _set_anime_synopsis(self, text: str) -> None:
        self.anime_synopsis_box.configure(state="normal")
        self.anime_synopsis_box.delete("1.0", "end")
        self.anime_synopsis_box.insert("end", text)
        self.anime_synopsis_box.configure(state="disabled")

    def _load_cover_image_from_url(self, url: str) -> None:
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            self.anime_cover_source = Image.open(io.BytesIO(response.content)).convert("RGB")
            self._refresh_cover_image()
        except Exception:
            self.anime_cover_label.configure(image="", text="Cover preview unavailable")
            self.anime_cover_label.image = None
            self.anime_cover_image = None
            self.anime_cover_source = None

    def _refresh_cover_image(self) -> None:
        if self.anime_cover_source is None:
            return
        live_w = self.anime_cover_label.winfo_width()
        live_h = self.anime_cover_label.winfo_height()
        max_w = max(260, live_w - 24) if live_w > 40 else 396
        max_h = max(360, live_h - 24) if live_h > 40 else 616
        image = self.anime_cover_source.copy()
        width, height = image.size
        scale = min(max_w / width, max_h / height)
        resized = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(resized)
        self.anime_cover_label.configure(image=photo, text="")
        self.anime_cover_label.image = photo
        self.anime_cover_image = photo

    def _project_dirs(self) -> list[Path]:
        if not OUTPUT_DIR.exists():
            return []
        return sorted((path for path in OUTPUT_DIR.iterdir() if path.is_dir()), key=lambda path: path.stat().st_mtime, reverse=True)

    def _build_project_records(self) -> list[dict]:
        records: list[dict] = []
        for project in self._project_dirs():
            series_summary = self._read_json(project / "series_summary.json") or {}
            day_dirs = sorted((path for path in project.iterdir() if path.is_dir() and path.name.startswith("day_")), key=lambda path: path.name)
            is_quote_series = series_summary.get("type") == "quote_series" or bool(day_dirs)
            if is_quote_series:
                anime = series_summary.get("anime") or project.name
                days = series_summary.get("days") or []
                total_days = int(series_summary.get("total_days") or len(days) or 0)
                day_labels = ", ".join(f"Day {item.get('day_number') or item.get('day')}" for item in days[:8] if isinstance(item, dict))
                if not day_labels and day_dirs:
                    day_labels = ", ".join(f"Day {index + 1}" for index, _ in enumerate(day_dirs[:8]))
                if len(days) > 8:
                    day_labels += ", ..."
                records.append(
                    {
                        "path": project,
                        "display": f"{anime} Quote Series",
                        "kind": "quote_series_root",
                        "anime": anime,
                        "total_days": total_days,
                        "day_summary": day_labels,
                    }
                )
                for day_dir in day_dirs:
                    quote_meta = self._read_json(day_dir / "quote_metadata.json") or {}
                    day_number = int(quote_meta.get("day_number") or quote_meta.get("day") or 0)
                    records.append(
                        {
                            "path": day_dir,
                            "display": f"{anime} | Day {day_number}",
                            "kind": "quote_series_day",
                            "anime": anime,
                            "day_number": day_number,
                            "total_days": int(quote_meta.get("total_days") or total_days or 0),
                            "character": quote_meta.get("character") or "",
                            "parent_series": project.name,
                        }
                    )
                continue

            records.append(
                {
                    "path": project,
                    "display": project.name,
                    "kind": "project",
                }
            )
        return records

    def _load_projects(self) -> None:
        self.project_records = self._build_project_records()
        self.projects = [record["path"] for record in self.project_records]
        self.project_list.delete(0, "end")
        for record in self.project_records:
            self.project_list.insert("end", record["display"])

        self.library_count_var.set(f"{len(self.project_records)} projects")
        if self.project_records:
            latest = self.project_records[0]["path"]
            self.last_result_var.set(self.project_records[0]["display"])
            self.project_list.selection_clear(0, "end")
            self.project_list.selection_set(0)
            self.project_list.event_generate("<<ListboxSelect>>")
        else:
            self.last_result_var.set("No renders yet")
            self.current_project = None
            self.project_title_var.set("No projects yet")
            self.project_meta_var.set("Generate the first short in the New Video tab.")
            self.project_date_var.set("")
            self._set_text_widget(self.title_box, "")
            self._set_text_widget(self.description_box, "")
            self._set_text_widget(self.hashtags_box, "")
            self._clear_video_preview()

    def _read_json(self, path: Path) -> dict | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except Exception:
            return ""

    def _on_project_select(self, _event=None) -> None:
        selection = self.project_list.curselection()
        if not selection:
            return
        record = self.project_records[selection[0]]
        self.current_project = record["path"]
        project = self.current_project

        storyboard = self._read_json(project / "storyboard.json") or {}
        summary = self._read_json(project / "render_summary.json") or {}
        quote_meta = self._read_json(project / "quote_metadata.json") or {}
        series_summary = self._read_json(project / "series_summary.json") or {}
        meta = storyboard.get("meta", {})
        title = (
            meta.get("title_english")
            or meta.get("anime_title")
            or quote_meta.get("anime")
            or series_summary.get("anime")
            or project.name
        )
        music = summary.get("music_track") or "none"
        created = datetime.fromtimestamp(project.stat().st_mtime).strftime("%Y-%m-%d %H:%M")

        if record["kind"] == "quote_series_day":
            day_number = int(record.get("day_number") or 0)
            total_days = int(record.get("total_days") or 0)
            self.project_title_var.set(f"{title} | Day {day_number}")
            self.project_meta_var.set(
                f"Folder: {project.name}\n"
                f"Series: {record.get('parent_series')}\n"
                f"Day: Day {day_number} of {total_days}\n"
                f"Character: {record.get('character') or '-'}\n"
                f"Mode: quote_series_day\n"
                f"Music: {music}"
            )
        elif record["kind"] == "quote_series_root":
            total_days = int(record.get("total_days") or 0)
            self.project_title_var.set(f"{title} Quote Series")
            self.project_meta_var.set(
                f"Folder: {project.name}\n"
                f"Mode: quote_series\n"
                f"Days: {total_days}\n"
                f"Available: {record.get('day_summary') or '-'}\n"
                f"Watermark: {summary.get('watermark', 'crypolt')}\n"
                f"Music: {music}"
            )
        else:
            self.project_title_var.set(title)
            self.project_meta_var.set(
                f"Folder: {project.name}\n"
                f"Mode: {summary.get('mode', 'story')}\n"
                f"Watermark: {summary.get('watermark', 'crypolt')}\n"
                f"Voice: {summary.get('voice') or '-'}\n"
                f"Music: {music}"
            )
        self.project_date_var.set(f"Created: {created}")
        title_text = self._read_text(project / "shorts_title.txt")
        description_text = self._read_text(project / "shorts_description.txt")
        hashtags_text = self._read_text(project / "hashtags.txt")
        if record["kind"] == "quote_series_root":
            title_text = f"{title} Quote Series"
            description_text = (
                f"Quote series for {title}\n"
                f"Total days: {record.get('total_days') or 0}\n"
                f"Available days: {record.get('day_summary') or '-'}"
            )
            hashtags_text = "#quoteseries #anime #crypolt"
        self._set_text_widget(self.title_box, title_text)
        self._set_text_widget(self.description_box, description_text)
        self._set_text_widget(self.hashtags_box, hashtags_text)
        if record["kind"] == "quote_series_root":
            first_day = project / "day_01" / "final.mp4"
            self._load_video_preview(first_day if first_day.exists() else project / "final.mp4")
        else:
            self._load_video_preview(project / "final.mp4")

    def _start_anime_preview(self) -> None:
        if self.preview_worker and self.preview_worker.is_alive():
            messagebox.showinfo("crypolt studio", "Anime preview is already loading.")
            return

        query = self.anime_preview_query_var.get().strip()
        if not query:
            messagebox.showerror("crypolt studio", "Enter an anime title.")
            return

        self.anime_preview_button.state(["disabled"])
        self.anime_preview_status_var.set("Loading anime information...")
        self.preview_request_id += 1
        request_id = self.preview_request_id
        self._show_loader("anime_preview", f"Loading anime info for {query}...", cancellable=True)

        def worker() -> None:
            try:
                self.queue.put(("log", f"Anime preview lookup started for '{query}'"))
                anime = fetch_anime_data(query, self.settings, self.localizer)
                self.queue.put(("anime_preview_done", {"request_id": request_id, "anime": anime}))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("anime_preview_error", {"request_id": request_id, "error": str(exc)}))

        self.preview_worker = threading.Thread(target=worker, daemon=True)
        self.preview_worker.start()

    def _populate_anime_preview(self, anime: dict) -> None:
        self.anime_preview_result = anime
        title = anime.get("title_english") or anime.get("title") or "Unknown anime"
        genres = ", ".join(item["name"] for item in anime.get("genres", [])[:4]) or "-"
        themes = ", ".join(item["name"] for item in anime.get("themes", [])[:3])
        score = anime.get("score")
        year = anime.get("year") or "-"
        episodes = anime.get("episodes") or "-"
        status = anime.get("status") or "-"
        rating = anime.get("rating") or "-"

        self.anime_preview_title_var.set(title)
        self.anime_preview_meta_var.set(
            f'Status: {status}\n'
            f'Rating: {rating}\n'
            f'Themes: {themes or "-"}'
        )
        self.anime_preview_score_var.set(f"{score:.1f}" if isinstance(score, (int, float)) else "-")
        self.anime_preview_year_var.set(str(year))
        self.anime_preview_episodes_var.set(str(episodes))
        self.anime_preview_genres_var.set(genres)
        self._set_anime_synopsis(anime.get("synopsis") or "Synopsis is unavailable for this anime.")
        try:
            self._load_cover_image_from_url(pick_cover_url(anime))
        except Exception:
            self.anime_cover_label.configure(image="", text="Cover preview unavailable")
            self.anime_cover_label.image = None
            self.anime_cover_image = None
            self.anime_cover_source = None

    def _use_preview_for_generation(self) -> None:
        title = None
        if self.anime_preview_result:
            title = self.anime_preview_result.get("title_english") or self.anime_preview_result.get("title")
        if not title:
            title = self.anime_preview_query_var.get().strip()
        if not title:
            messagebox.showinfo("crypolt studio", "Load an anime preview first.")
            return
        self.anime_var.set(title)
        self._select_tab(self.create_tab)

    def _open_selected_folder(self) -> None:
        if self.current_project:
            open_path(self.current_project)
            return
        latest_projects = self._project_dirs()
        if latest_projects:
            open_path(latest_projects[0])
            return
        messagebox.showinfo("crypolt studio", "No generated project folder is available yet.")

    def _open_selected_video(self) -> None:
        if not self.current_project:
            messagebox.showinfo("crypolt studio", "Select a project first.")
            return
        video = self.current_project / "final.mp4"
        if not video.exists():
            messagebox.showinfo("crypolt studio", "This project does not have final.mp4 yet.")
            return
        open_path(video)

    def _clear_video_preview(self) -> None:
        self._stop_video()
        if self.video_reader:
            try:
                self.video_reader.close()
            except Exception:
                pass
            self.video_reader = None
        self.preview_label.configure(image="", text="Select a project to preview video\n\nClick here or press Start Preview")
        self.preview_label.image = None
        self.preview_status_var.set("No video loaded")
        self.video_path = None

    def _load_video_preview(self, video: Path) -> None:
        self._clear_video_preview()
        if not video.exists():
            self.preview_label.configure(image="", text="This project does not have final.mp4 yet")
            self.preview_label.image = None
            self.preview_status_var.set("Missing final.mp4")
            return
        self.video_path = video
        self.preview_status_var.set(video.name)
        try:
            self.video_reader = imageio.get_reader(str(video))
            frame = self.video_reader.get_next_data()
            self._show_frame(frame)
            self.play_button.configure(text="Start Preview")
        except Exception:
            self.preview_label.configure(image="", text="Preview unavailable for this video")
            self.preview_label.image = None
            self.preview_status_var.set("Preview unavailable")

    def _show_frame(self, frame) -> None:
        image = Image.fromarray(frame).convert("RGB")
        width, height = image.size
        live_w = self.preview_label.winfo_width()
        live_h = self.preview_label.winfo_height()
        max_w, max_h = self.preview_size
        if live_w > 40 and live_h > 40:
            max_w = max(max_w, live_w - 24)
            max_h = max(max_h, live_h - 24)
        scale = min(max_w / width, max_h / height)
        resized = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(resized)
        self.preview_label.configure(image=photo, text="")
        self.preview_label.image = photo
        self.preview_image = photo

    def _play_video_step(self) -> None:
        if not self.video_playing or not self.video_reader:
            return
        try:
            frame = self.video_reader.get_next_data()
        except Exception:
            self._restart_video()
            return
        self._show_frame(frame)
        delay = 42
        meta = self.video_reader.get_meta_data()
        fps = meta.get("fps") if isinstance(meta, dict) else None
        if fps:
            delay = max(15, int(1000 / float(fps)))
        self.video_after_id = self.root.after(delay, self._play_video_step)

    def _toggle_playback(self) -> None:
        if not self.video_path:
            messagebox.showinfo("crypolt studio", "Select a project with a final video first.")
            return
        if self.video_playing:
            self._stop_video()
            return
        if not self.video_reader:
            self._load_video_preview(self.video_path)
        self.video_playing = True
        self.play_button.configure(text="Pause")
        self.preview_status_var.set(f"Playing: {self.video_path.name}")
        self._play_video_step()

    def _stop_video(self) -> None:
        self.video_playing = False
        self.play_button.configure(text="Start Preview")
        if self.video_after_id:
            self.root.after_cancel(self.video_after_id)
            self.video_after_id = None
        if self.video_path:
            self.preview_status_var.set(self.video_path.name)

    def _restart_video(self) -> None:
        if not self.video_path:
            return
        path = self.video_path
        self._load_video_preview(path)
        self._toggle_playback()

    def _on_close(self) -> None:
        try:
            self._stop_video()
            if self.video_reader:
                self.video_reader.close()
                self.video_reader = None
        finally:
            self.root.destroy()

    def _start_analytics(self) -> None:
        if self.analytics_worker and self.analytics_worker.is_alive():
            messagebox.showinfo("crypolt studio", "Channel analytics is already running.")
            return

        query = self.analytics_query_var.get().strip()
        if not query:
            messagebox.showerror("crypolt studio", "Enter a YouTube channel URL, @handle or channel name.")
            return

        self.analytics_button.state(["disabled"])
        self.analytics_status_var.set("Starting public Shorts analysis...")
        self._set_analytics_summary("Collecting public YouTube channel data...\n")
        self._select_tab(self.analytics_tab)
        self.analytics_request_id += 1
        request_id = self.analytics_request_id
        self._show_loader("analytics", f"Analyzing YouTube channel: {query}", cancellable=True)

        def worker() -> None:
            try:
                self.queue.put(("log", f"Channel analytics started for '{query}'"))
                result = analyze_channel_shorts(
                    query,
                    self.settings,
                    limit=12,
                    callback=lambda message: self.queue.put(("analytics_status", {"request_id": request_id, "message": message})),
                )
                self.queue.put(("analytics_done", {"request_id": request_id, "result": result}))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("analytics_error", {"request_id": request_id, "error": str(exc)}))

        self.analytics_worker = threading.Thread(target=worker, daemon=True)
        self.analytics_worker.start()

    def _populate_analytics(self, result: dict) -> None:
        self.analytics_result = result
        channel = result["channel"]
        summary = result["summary"]
        shorts = result["shorts"]

        self.analytics_channel_title.set(channel["title"])
        self.analytics_channel_meta.set(
            f'Handle: {channel["handle"]}\n'
            f'URL: {channel["url"]}\n'
            f'Top short: {summary["top_short_title"]}'
        )
        self.analytics_followers.set(f'{channel["followers"]:,}')
        self.analytics_shorts_count.set(str(summary["shorts_analyzed"]))
        self.analytics_total_views.set(f'{summary["total_views"]:,}')
        self.analytics_avg_views.set(f'{summary["avg_views"]:,}')

        summary_text = (
            f'Analyzed {summary["shorts_analyzed"]} public Shorts.\n'
            f'Total views: {summary["total_views"]:,}\n'
            f'Average views per short: {summary["avg_views"]:,}\n'
            f'Total likes: {summary["total_likes"]:,}\n'
            f'Average likes per short: {summary["avg_likes"]:,}\n'
            f'Best-performing short: "{summary["top_short_title"]}" with {summary["top_short_views"]:,} views.'
        )
        self._set_analytics_summary(summary_text)

        for item in self.analytics_tree.get_children():
            self.analytics_tree.delete(item)
        for index, short in enumerate(shorts):
            self.analytics_tree.insert(
                "",
                "end",
                iid=f"short_{index}",
                text=short["title"],
                values=(
                    short["upload_date"],
                    f'{short["view_count"]:,}',
                    f'{short["like_count"]:,}',
                    f'{short["comment_count"]:,}',
                    f'{short["duration"]}s',
                ),
            )
        if shorts:
            self.analytics_tree.selection_set("short_0")
            self.analytics_tree.focus("short_0")

    def _on_analytics_short_select(self, _event=None) -> None:
        if not self.analytics_result:
            return
        selection = self.analytics_tree.selection()
        if not selection:
            return
        index = int(selection[0].split("_")[1])
        short = self.analytics_result["shorts"][index]
        self.analytics_status_var.set(
            f'Selected short: {short["title"]} | {short["view_count"]:,} views | {short["upload_date"]}'
        )

    def _open_analytics_channel(self) -> None:
        if not self.analytics_result:
            messagebox.showinfo("crypolt studio", "Run channel analytics first.")
            return
        open_path(self.analytics_result["channel"]["url"])

    def _open_selected_short(self) -> None:
        if not self.analytics_result:
            messagebox.showinfo("crypolt studio", "Run channel analytics first.")
            return
        selection = self.analytics_tree.selection()
        if not selection:
            messagebox.showinfo("crypolt studio", "Select a short in the analytics table first.")
            return
        index = int(selection[0].split("_")[1])
        open_path(self.analytics_result["shorts"][index]["url"])

    def _copy_analytics_summary(self) -> None:
        summary = self.analytics_summary_box.get("1.0", "end").strip()
        if not summary:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(summary)
        self.analytics_status_var.set("Analytics summary copied to clipboard")

    def _handle_resize(self, _event=None) -> None:
        width = max(560, int(self.root.winfo_width() * 0.38))
        height = max(315, int(width * 9 / 16))
        self.preview_size = (width, height)
        if hasattr(self, "preview_shell"):
            self.preview_shell.configure(height=height + 28)
        if hasattr(self, "cover_shell"):
            cover_height = max(520, int(self.root.winfo_height() * 0.58))
            self.cover_shell.configure(height=cover_height)
        self._refresh_cover_image()

    def _start_generation(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("crypolt studio", "Generation is already running.")
            return

        anime = self.anime_var.get().strip()
        if not anime:
            messagebox.showerror("crypolt studio", "Enter an anime title.")
            return

        try:
            duration = int(self.duration_var.get())
        except ValueError:
            messagebox.showerror("crypolt studio", "Duration must be a number.")
            return

        ready, reason = self._preflight_ready(self.mode_var.get())
        if not ready:
            self._append_output(f"[health] Preflight blocked generation: {reason}")
            messagebox.showerror("crypolt studio", f"Generation is blocked for now.\n\n{reason}\n\nPress 'Check Services' and try again.")
            return

        args = Namespace(
            anime=anime,
            language_mode="bilingual",
            duration=duration,
            voice="auto",
            music_mode=self.music_var.get(),
            mode=self.mode_var.get(),
            watermark=self.watermark_var.get().strip() or "crypolt",
            output_dir="output",
        )

        self.progressbar["value"] = 0
        self.progress_var.set("Preparing generation pipeline...")
        self.step_var.set("Collecting anime data and scheduling render steps")
        self.eta_var.set("ETA: estimating...")
        self._append_output(f"Starting generation for {anime}")
        self.generate_button.state(["disabled"])
        self._select_tab(self.create_tab)
        self.generation_cancel_event = threading.Event()
        self._show_loader("generation", f"Generating {anime} in {self.mode_var.get()} mode...", cancellable=True)

        def worker() -> None:
            try:
                run_pipeline(
                    args,
                    progress_callback=lambda payload: self.queue.put(("progress", payload)),
                    log_callback=lambda message: self.queue.put(("log", message)),
                    cancel_event=self.generation_cancel_event,
                )
                latest = max(self._project_dirs(), key=lambda path: path.stat().st_mtime)
                self.queue.put(("done", latest))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("error", str(exc)))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _start_quote_series(self) -> None:
        if self.quote_series_worker and self.quote_series_worker.is_alive():
            messagebox.showinfo("crypolt studio", "Quote series generation is already running.")
            return

        anime = self.quote_series_anime_var.get().strip()
        if not anime:
            messagebox.showerror("crypolt studio", "Enter an anime title for the quote series.")
            return

        try:
            days = int(self.quote_series_days_var.get())
        except ValueError:
            messagebox.showerror("crypolt studio", "Number of days must be a number.")
            return

        if days < 1:
            messagebox.showerror("crypolt studio", "Number of days must be at least 1.")
            return

        ready, reason = self._preflight_ready("story")
        if not ready:
            self._append_output(f"[health] Preflight blocked quote series: {reason}")
            messagebox.showerror("crypolt studio", f"Quote series is blocked for now.\n\n{reason}\n\nPress 'Check Services' and try again.")
            return

        self.generation_cancel_event = threading.Event()
        self.quote_series_button.state(["disabled"])
        self._show_loader("quote_series", f"Generating quote series for {anime} ({days} days)...", cancellable=True)
        self._append_output(f"Starting quote series generation for {anime} ({days} days)")
        self._select_tab(self.quote_series_tab)

        def worker() -> None:
            try:
                series_dir = run_quote_series(
                    anime=anime,
                    days=days,
                    output_dir="output",
                    watermark=self.watermark_var.get().strip() or "crypolt",
                    music_mode=self.music_var.get(),
                    log_callback=lambda message: self.queue.put(("log", f"[quote-series] {message}")),
                    progress_callback=lambda data: self.queue.put(("quote_series_progress", data)),
                    cancel_event=self.generation_cancel_event,
                )
                self.queue.put(("quote_series_done", series_dir))
            except Exception as exc:  # noqa: BLE001
                self.queue.put(("quote_series_error", str(exc)))

        self.quote_series_worker = threading.Thread(target=worker, daemon=True)
        self.quote_series_worker.start()

    def _pump_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "progress":
                    data = payload
                    self.progressbar["value"] = data["completed"]
                    self.progress_var.set(f'{data["title"]}: {data["detail"]}')
                    self.step_var.set(f'Step {data["completed"]}/{data["total"]}')
                    self.eta_var.set(f'ETA: {data["eta"]}')
                    self._update_loader("generation", f'{data["title"]}: {data["detail"]}\nETA: {data["eta"]}')
                    self._append_output(f'[{data["completed"]}/{data["total"]}] {data["detail"]}')
                elif kind == "log":
                    self._append_output(f"[log] {payload}")
                elif kind == "done":
                    folder: Path = payload
                    self.generate_button.state(["!disabled"])
                    self._hide_loader("generation")
                    self.generation_cancel_event = None
                    self.progress_var.set("Generation completed successfully")
                    self.step_var.set("Final video, metadata and preview are ready")
                    self.eta_var.set("ETA: 0s")
                    self._append_output(f"Finished. Folder: {folder}")
                    self._append_output(f"Video: {folder / 'final.mp4'}")
                    self._load_projects()
                    for index, project in enumerate(self.projects):
                        if project == folder:
                            self.project_list.selection_clear(0, "end")
                            self.project_list.selection_set(index)
                            self.project_list.event_generate("<<ListboxSelect>>")
                            break
                    self.current_project = folder
                    self.last_result_var.set(folder.name)
                    self._select_tab(self.projects_tab)
                    self._load_video_preview(folder / "final.mp4")
                elif kind == "error":
                    self.generate_button.state(["!disabled"])
                    self._hide_loader("generation")
                    self.generation_cancel_event = None
                    error_text = str(payload)
                    cancelled = "cancelled" in error_text.lower()
                    self.progress_var.set("Generation failed")
                    self.step_var.set("The pipeline stopped before export")
                    self.eta_var.set("ETA: -")
                    self._append_output(f"Error: {error_text}")
                    if cancelled:
                        self.progress_var.set("Generation cancelled")
                        self.step_var.set("Rendering was stopped by user")
                    else:
                        friendly = error_text
                        if "download_failed:" in error_text:
                            friendly = "A file download failed after several retries. Check the network and try again."
                        messagebox.showerror("crypolt studio", friendly)
                elif kind == "quote_series_progress":
                    data = payload
                    self._update_loader("quote_series", f'Generating quote series\n{data["detail"]} ({data["current"]}/{data["total"]})')
                    self._append_output(f'[quote-series] {data["detail"]} ({data["current"]}/{data["total"]})')
                elif kind == "quote_series_done":
                    folder: Path = payload
                    self.quote_series_button.state(["!disabled"])
                    self._hide_loader("quote_series")
                    self.generation_cancel_event = None
                    self._append_output(f"[quote-series] Finished. Folder: {folder}")
                    self._load_projects()
                    self._set_text_widget(
                        self.quote_series_info,
                        f"Quote series completed successfully.\n\nFolder: {folder}\n\nOpen the folder to access day_01, day_02, ... and each generated final.mp4.",
                    )
                elif kind == "quote_series_error":
                    self.quote_series_button.state(["!disabled"])
                    self._hide_loader("quote_series")
                    cancelled = "cancelled" in str(payload).lower()
                    self.generation_cancel_event = None
                    self._append_output(f"[quote-series] Error: {payload}")
                    if cancelled:
                        self._set_text_widget(self.quote_series_info, "Quote series generation was cancelled.")
                    else:
                        friendly = "Could not generate the quote series right now. The app will try again cleanly on the next run."
                        if "download_failed:" in str(payload):
                            friendly = "A required file could not be downloaded after several retries. Check the network and try again."
                        self._set_text_widget(
                            self.quote_series_info,
                            "Quote series generation stopped before export.\n\n"
                            f"Details: {payload}\n\n"
                            "Tip: try again in a moment. If a public quote source is limited, the app will fall back automatically when possible.",
                        )
                        messagebox.showerror("crypolt studio", friendly)
                elif kind == "analytics_status":
                    data = payload
                    if data["request_id"] != self.analytics_request_id:
                        continue
                    self.analytics_status_var.set(str(data["message"]))
                    self._update_loader("analytics", str(data["message"]))
                    self._append_output(f'[analytics] {data["message"]}')
                elif kind == "analytics_done":
                    data = payload
                    if data["request_id"] != self.analytics_request_id:
                        continue
                    self.analytics_button.state(["!disabled"])
                    self._hide_loader("analytics")
                    self.analytics_status_var.set("Channel analytics completed")
                    self._append_output("[analytics] Channel analytics completed")
                    self._populate_analytics(data["result"])
                elif kind == "analytics_error":
                    data = payload
                    if data["request_id"] != self.analytics_request_id:
                        continue
                    self.analytics_button.state(["!disabled"])
                    self._hide_loader("analytics")
                    self.analytics_status_var.set("Channel analytics failed")
                    self._set_analytics_summary(f'Error while analyzing channel:\n{data["error"]}')
                    self._append_output(f'[analytics] Error: {data["error"]}')
                    messagebox.showerror("crypolt studio", "Could not load channel analytics right now. Please try again.")
                elif kind == "anime_preview_done":
                    data = payload
                    if data["request_id"] != self.preview_request_id:
                        continue
                    self.anime_preview_button.state(["!disabled"])
                    self._hide_loader("anime_preview")
                    self.anime_preview_status_var.set("Anime info loaded")
                    self._append_output("[anime-preview] Anime info loaded successfully")
                    self._populate_anime_preview(data["anime"])
                elif kind == "anime_preview_error":
                    data = payload
                    if data["request_id"] != self.preview_request_id:
                        continue
                    self.anime_preview_button.state(["!disabled"])
                    self._hide_loader("anime_preview")
                    self.anime_preview_status_var.set("Anime preview failed")
                    self._set_anime_synopsis(f'Error while loading anime:\n{data["error"]}')
                    self._append_output(f'[anime-preview] Error: {data["error"]}')
                    messagebox.showerror("crypolt studio", "Could not load anime info right now. Please try again.")
                elif kind == "popular_titles_done":
                    self._apply_popular_titles(payload)
                elif kind == "popular_titles_error":
                    self._append_output("[anime-list] Could not refresh titles from Jikan, using fallback list")
                elif kind == "service_health_done":
                    self._apply_service_health(payload)
                    self._append_output("[health] Service check completed")
                elif kind == "service_health_error":
                    self.runtime_status_var.set("Offline | check failed")
                    self.jikan_runtime_status_var.set("Offline | check failed")
                    self.animechan_runtime_status_var.set("Offline | check failed")
                    self.pixabay_runtime_status_var.set("Offline | check failed")
                    self._append_output(f"[health] Service check failed: {payload}")
        except Empty:
            pass
        self.root.after(150, self._pump_queue)

    def run(self) -> None:
        self.root.mainloop()


def run_gui() -> None:
    CrypoltGUI().run()
