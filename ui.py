"""Timelapser UI — premium workspace with refined, modern aesthetics."""

from __future__ import annotations

import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from . import APP_NAME, __version__
from .loader import PulseLoader
from .paths import default_output_dir, free_space_bytes
from .pipeline import (
    MODE_INTERVAL,
    MODE_REALTIME,
    MODE_SPEED,
    RESOLUTIONS,
    Recorder,
    RecordingConfig,
    suggest_filename,
)
from .preview import FramePainter, PreviewSession, fit_preview
from .sprites import load, sprite_size
from .theme import Color, Space, Type, init_typography, mix, tracked
from .widgets import (
    Button,
    Chip,
    Entry,
    IconButton,
    Page,
    Panel,
    Select,
    Segmented,
    Toggle,
    Well,
)
from .winenum import CaptureTarget, list_targets

SPEED_PRESETS = [2, 5, 10, 20, 30, 60, 120, 240]
HOTKEY = "f9"
PREVIEW_MS = 33
POLL_MS = 100

PAD = Space.XL
RAIL_W = 420


def _resource_path(*parts: str) -> str:
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


class TimelapserApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.recorder: Recorder | None = None
        self.preview = PreviewSession()
        self._painter = FramePainter()
        self.targets: list[CaptureTarget] = []
        self._hotkey_handle = None
        self._last_state = "idle"
        self._preview_photo = None
        self._painting = False
        self._overlay_visible = False
        self._paint_fps = 0.0
        self._paint_count = 0
        self._paint_t0 = 0.0
        self._record_started_at = 0.0
        self._timer_job = None
        self._loading_screen: tk.Toplevel | None = None

        root.title(APP_NAME)
        root.configure(bg=Color.BASE)
        self._size_window()
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._apply_icon()

        # Show loading screen immediately
        self._show_loading_screen()

        # Initialize UI in background
        root.after(50, self._initialize_app)

    # ---------------------------------------------------------------- chrome

    def _size_window(self) -> None:
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = min(1720, max(1360, screen_w - 64))
        height = min(1020, max(840, screen_h - 72))
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2 - 20)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min(1360, width), min(840, height))

    def _show_loading_screen(self) -> None:
        """Show a simple loading screen while the app initializes."""
        self._loading_screen = tk.Toplevel(self.root)
        self._loading_screen.overrideredirect(True)
        self._loading_screen.configure(bg=Color.BASE)

        # Center on screen
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        width = 400
        height = 200
        x = (screen_w - width) // 2
        y = (screen_h - height) // 2
        self._loading_screen.geometry(f"{width}x{height}+{x}+{y}")

        # Loading text
        self._loading_label = tk.Label(
            self._loading_screen,
            text="Loading Timelapser",
            fg=Color.TEXT,
            bg=Color.BASE,
            font=Type.H1,
        )
        self._loading_label.pack(pady=(60, 20))

        # Loading dots animation
        self._loading_dots = tk.Label(
            self._loading_screen,
            text="",
            fg=Color.TEXT_3,
            bg=Color.BASE,
            font=Type.BODY,
        )
        self._loading_dots.pack()

        # Animate dots
        self._loading_dot_count = 0
        self._animate_loading_dots()

        # Make it topmost
        try:
            self._loading_screen.wm_attributes("-topmost", True)
        except tk.TclError:
            pass

        # Update to show
        self._loading_screen.update()

    def _animate_loading_dots(self) -> None:
        """Animate loading dots."""
        if self._loading_screen is None:
            return
        self._loading_dot_count = (self._loading_dot_count + 1) % 4
        dots = "." * self._loading_dot_count
        self._loading_dots.configure(text=dots)
        if self._loading_screen.winfo_exists():
            self.root.after(300, self._animate_loading_dots)

    def _hide_loading_screen(self) -> None:
        """Hide the loading screen."""
        if self._loading_screen is not None:
            try:
                self._loading_screen.destroy()
            except tk.TclError:
                pass
            self._loading_screen = None

    def _initialize_app(self) -> None:
        """Initialize the main app UI."""
        try:
            self.page = Page(self.root)
            self._build()
            self._build_rail()

            self.refresh_targets()
            self._register_hotkey()
            self._poll()
            self._tick_preview()

            self.root.update_idletasks()
            self.page.render()

            # Hide loading screen
            self._hide_loading_screen()

            if os.environ.get("TL_TRACE_WINDOW"):
                self._trace_window()
            self.root.after(120, self._restart_preview)
        except Exception as e:
            # If initialization fails, hide loading screen and show error
            self._hide_loading_screen()
            messagebox.showerror(APP_NAME, f"Failed to initialize: {e}")
            self.root.destroy()

    def _trace_window(self) -> None:
        import traceback

        def on_unmap(_event=None):
            sys.stderr.write(f"UNMAP state={self.root.wm_state()}\n")
            traceback.print_stack(file=sys.stderr)
            sys.stderr.flush()

        self.root.bind("<Unmap>", on_unmap, add="+")

        def sample():
            sys.stderr.write(
                f"state={self.root.wm_state()} t={time.perf_counter():.1f}\n"
            )
            sys.stderr.flush()
            self.root.after(1000, sample)

        sample()

    def _apply_icon(self) -> None:
        ico = _resource_path("assets", "timelapser.ico")
        try:
            if os.path.isfile(ico):
                self.root.iconbitmap(ico)
        except Exception:
            pass

    # ---------------------------------------------------------------- layout

    def _build(self) -> None:
        root = self.root
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)

        # Main workspace split: preview left, controls right.
        self.page.root = root
        main = tk.Frame(root, bg=Color.BASE)
        main.pack(fill="both", expand=True)
        main.pack_propagate(True)

        # Rail on left, preview on right
        self._rail = Panel(main, self.page, radius=Space.RADIUS_LG, fill=Color.SURFACE, pad=PAD)
        self._rail.pack(side="left", fill="y", padx=(PAD, Space.SM), pady=PAD)
        rbody = self._rail.body

        left = Panel(main, self.page, radius=Space.RADIUS_LG, fill=Color.SURFACE, pad=PAD)
        left.pack(side="left", fill="both", expand=True, pady=PAD)
        lbody = left.body

        # Header with improved layout
        header = tk.Frame(lbody, bg=Color.SURFACE)
        header.pack(fill="x", pady=(0, Space.LG))

        title_box = tk.Frame(header, bg=Color.SURFACE)
        title_box.pack(side="left", padx=(Space.SM, 0))
        tk.Label(title_box, text=APP_NAME, fg=Color.TEXT, bg=Color.SURFACE, font=Type.H1, anchor="w").pack(anchor="w")
        tk.Label(title_box, text=tracked("SCREEN RECORDING & TIMELAPSE"), fg=Color.TEXT_4, bg=Color.SURFACE, font=Type.EYEBROW, anchor="w").pack(anchor="w", pady=(2, 0))
        self.source_label = tk.Label(title_box, text="No source selected", fg=Color.TEXT_3, bg=Color.SURFACE, font=Type.SMALL, anchor="w")
        self.source_label.pack(anchor="w", pady=(Space.XS, 0))

        meta = tk.Frame(header, bg=Color.SURFACE)
        meta.pack(side="right")
        self.encoder_chip = Chip(meta, self.page, "Encoder ready", tone="muted")
        self.encoder_chip.pack(side="right")
        self.state_chip = Chip(meta, self.page, "LIVE", tone="live", dot=True)
        self.state_chip.pack(side="right", padx=(Space.SM, 0))
        self.res_chip = self.encoder_chip
        self.fps_chip = self.state_chip

        # Preview area with subtle border
        preview_container = tk.Frame(lbody, bg=Color.SURFACE, highlightthickness=1, highlightbackground=Color.BORDER_SUBTLE)
        preview_container.pack(fill="both", expand=True)
        self.preview_shell = tk.Frame(preview_container, bg=Color.STAGE)
        self.preview_shell.pack(fill="both", expand=True, padx=1, pady=1)
        self.preview_shell.pack_propagate(True)
        self.well = Well(self.preview_shell, self.page, radius=Space.RADIUS)
        self.well.pack(fill="both", expand=True)

        self.overlay = tk.Frame(self.well, bg=Color.STAGE)
        self.overlay._glass_opaque = True
        self.overlay_label = tk.Label(self.overlay, text="Loading preview", bg=Color.STAGE, fg=Color.TEXT_2, font=Type.BODY)
        self.overlay_label.pack(pady=(0, Space.MD))
        self.loader = PulseLoader(self.overlay, color="#888888", accent=Color.ACCENT, bg=Color.STAGE, diameter=14, gap=12)
        self.loader.pack()

        # Bottom section with improved cards
        bottom = tk.Frame(lbody, bg=Color.SURFACE)
        bottom.pack(fill="x", pady=(Space.LG, 0))

        # Timing card with enhanced styling
        timing_card = tk.Frame(bottom, bg=Color.SURFACE_ALT, highlightthickness=1, highlightbackground=Color.BORDER)
        timing_card.pack(side="left", fill="both", expand=True)
        timing_inner = tk.Frame(timing_card, bg=Color.SURFACE_ALT)
        timing_inner.pack(fill="x", padx=Space.LG, pady=Space.MD)
        self.live_timer_var = tk.StringVar(value="00:00")
        self.live_status_var = tk.StringVar(value="Ready")
        tk.Label(timing_inner, text="Recording time", fg=Color.TEXT_4, bg=Color.SURFACE_ALT, font=Type.EYEBROW, anchor="w").pack(anchor="w")
        timer_row = tk.Frame(timing_inner, bg=Color.SURFACE_ALT)
        timer_row.pack(anchor="w", pady=(Space.XS, 0))
        self.record_dot = tk.Canvas(timer_row, width=10, height=10, highlightthickness=0, bd=0, bg=Color.SURFACE_ALT)
        self.record_dot.pack(side="left", padx=(0, Space.SM))
        self.record_dot.create_oval(2, 2, 8, 8, fill=Color.REC, outline="")
        tk.Label(timer_row, textvariable=self.live_timer_var, fg=Color.TEXT, bg=Color.SURFACE_ALT, font=Type.STAT, anchor="w").pack(side="left")
        tk.Label(timing_inner, textvariable=self.live_status_var, fg=Color.TEXT_4, bg=Color.SURFACE_ALT, font=Type.SMALL, anchor="w").pack(anchor="w", pady=(Space.XS, 0))

        # Activity card with enhanced styling
        activity = tk.Frame(bottom, bg=Color.SURFACE_ALT, highlightthickness=1, highlightbackground=Color.BORDER)
        activity.pack(side="left", fill="both", expand=True, padx=(Space.SM, 0))
        tk.Label(activity, text=tracked("ACTIVITY"), fg=Color.TEXT_4, bg=Color.SURFACE_ALT, font=Type.EYEBROW).pack(anchor="w", padx=Space.LG, pady=(Space.MD, 0))
        self.log_text = tk.Text(activity, height=4, width=1, bg=Color.SURFACE_ALT, fg=Color.TEXT_3, insertbackground=Color.TEXT, relief="flat", font=Type.CODE, wrap="word", state="disabled", highlightthickness=0, bd=0, spacing1=1)
        self.log_text.pack(fill="both", expand=True, padx=Space.LG, pady=(Space.SM, Space.MD))

    def _draw_brand(self) -> None:
        c = self.brand
        c.delete("all")
        # Draw a play-button icon using sprites
        play = load("UI_Flat_IconPlay01a.png", scale=2)
        if play:
            c.create_image(16, 16, image=play, anchor="center")
        else:
            c.create_oval(4, 4, 28, 28, fill=Color.SURFACE_ALT, outline="")
            c.create_arc(8, 8, 24, 24, start=0, extent=250, style="arc", outline=Color.ACCENT, width=2)
            c.create_oval(15, 15, 19, 19, fill=Color.TEXT_2, outline="")

    # ------------------------------------------------------------------ rail

    def _build_rail(self) -> None:
        body = self._rail.body

        # Source section with divider
        source_header = tk.Frame(body, bg=Color.SURFACE)
        source_header.pack(fill="x", pady=(0, Space.SM))
        tk.Label(source_header, text=tracked("SOURCE"), fg=Color.TEXT_4, bg=Color.SURFACE, font=Type.EYEBROW).pack(side="left")
        
        picker = tk.Frame(body, bg=Color.SURFACE)
        picker.pack(fill="x", pady=(0, Space.SM))
        self.target_var = tk.StringVar()
        self.target_select = Select(picker, self.page, self.target_var, command=lambda _v: self._on_target_change(), placeholder="No capturable windows")
        self.target_select.pack(side="left", fill="x", expand=True)
        IconButton(picker, self.page, "⟳", self.refresh_targets, size=32, tooltip="Rescan").pack(side="left", padx=(Space.SM, 0))

        toggles = tk.Frame(body, bg=Color.SURFACE)
        toggles.pack(fill="x", pady=(0, Space.LG))
        self.cursor_var = tk.BooleanVar(value=True)
        Toggle(toggles, self.page, "Cursor", self.cursor_var, command=self._restart_preview).pack(side="left")
        self.border_var = tk.BooleanVar(value=False)
        Toggle(toggles, self.page, "Border", self.border_var).pack(side="left", padx=(Space.MD, 0))

        # Divider
        divider1 = tk.Frame(body, bg=Color.BORDER, height=Space.DIVIDER)
        divider1.pack(fill="x", pady=(0, Space.LG))

        # Timelapse section
        tk.Label(body, text=tracked("TIMELAPSE"), fg=Color.TEXT_4, bg=Color.SURFACE, font=Type.EYEBROW).pack(anchor="w", pady=(0, Space.SM))
        self.mode_var = tk.StringVar(value=MODE_SPEED)
        Segmented(body, self.page, [(MODE_SPEED, "Speed"), (MODE_INTERVAL, "Interval"), (MODE_REALTIME, "Realtime")], self.mode_var, command=self._set_mode).pack(fill="x", pady=(0, Space.SM))

        self.mode_detail = tk.Frame(body, bg=Color.SURFACE)
        self.mode_detail.pack(fill="x", pady=(0, Space.SM))

        self.speed_var = tk.StringVar(value="20x")
        self.speed_row = tk.Frame(self.mode_detail, bg=Color.SURFACE)
        tk.Label(self.speed_row, text="Speed", fg=Color.TEXT_3, bg=Color.SURFACE, font=Type.BODY).pack(side="left")
        self.speed_select = Select(self.speed_row, self.page, self.speed_var, [f"{v}x" for v in SPEED_PRESETS], height=34, width=100, command=lambda _v: self._update_summary())
        self.speed_select.pack(side="right")

        self.interval_var = tk.StringVar(value="2.0")
        self.interval_row = tk.Frame(self.mode_detail, bg=Color.SURFACE)
        tk.Label(self.interval_row, text="Interval (s)", fg=Color.TEXT_3, bg=Color.SURFACE, font=Type.BODY).pack(side="left")
        ih = tk.Frame(self.interval_row, width=100, height=34, bg=Color.SURFACE)
        ih.pack(side="right")
        ih.pack_propagate(False)
        interval_field = Entry(ih, self.page, self.interval_var, pady=6)
        interval_field.pack(fill="both", expand=True)
        interval_field.entry.configure(justify="center")
        self.interval_var.trace_add("write", lambda *_: self._update_summary())

        self.summary_label = tk.Label(body, text="", fg=Color.TEXT_4, bg=Color.SURFACE, font=Type.SMALL, anchor="w", justify="left", wraplength=RAIL_W - PAD * 2 - 20)
        self.summary_label.pack(fill="x", pady=(0, Space.LG))

        # Divider
        divider2 = tk.Frame(body, bg=Color.BORDER, height=Space.DIVIDER)
        divider2.pack(fill="x", pady=(0, Space.LG))

        # Output section
        tk.Label(body, text=tracked("OUTPUT"), fg=Color.TEXT_4, bg=Color.SURFACE, font=Type.EYEBROW).pack(anchor="w", pady=(0, Space.SM))
        fps_row = tk.Frame(body, bg=Color.SURFACE)
        fps_row.pack(fill="x", pady=(0, Space.SM))
        tk.Label(fps_row, text="FPS", fg=Color.TEXT_3, bg=Color.SURFACE, font=Type.BODY).pack(side="left")
        self.fps_var = tk.StringVar(value="60")
        fh = tk.Frame(fps_row, width=140, height=34, bg=Color.SURFACE)
        fh.pack(side="right")
        fh.pack_propagate(False)
        Segmented(fh, self.page, [("30", "30"), ("60", "60")], self.fps_var, command=lambda _v: self._update_summary(), height=34).pack(fill="both", expand=True)

        res_row = tk.Frame(body, bg=Color.SURFACE)
        res_row.pack(fill="x", pady=(0, Space.SM))
        tk.Label(res_row, text="Resolution", fg=Color.TEXT_3, bg=Color.SURFACE, font=Type.BODY).pack(side="left")
        self.res_var = tk.StringVar(value=list(RESOLUTIONS)[0])
        Select(res_row, self.page, self.res_var, list(RESOLUTIONS), height=34, width=160, command=lambda _v: self._update_summary()).pack(side="right")

        self.cpu_var = tk.BooleanVar(value=False)
        Toggle(body, self.page, "Force CPU (x264)", self.cpu_var).pack(anchor="w", pady=(0, Space.SM))

        tk.Label(body, text="Save folder", fg=Color.TEXT_4, bg=Color.SURFACE, font=Type.LABEL, anchor="w").pack(anchor="w", pady=(0, Space.XS))
        folder_row = tk.Frame(body, bg=Color.SURFACE)
        folder_row.pack(fill="x", pady=(0, Space.SM))
        self.folder_var = tk.StringVar(value=default_output_dir())
        Entry(folder_row, self.page, self.folder_var).pack(side="left", fill="x", expand=True)
        IconButton(folder_row, self.page, "…", self._browse, size=32, tooltip="Choose folder").pack(side="left", padx=(Space.SM, 0))

        self.name_var = tk.StringVar()
        filename_row = tk.Frame(body, bg=Color.SURFACE)
        filename_row.pack(fill="x", pady=(0, Space.MD))
        tk.Label(filename_row, text="File name", fg=Color.TEXT_3, bg=Color.SURFACE, font=Type.BODY).pack(anchor="w", pady=(0, Space.XS))
        Entry(filename_row, self.page, self.name_var, placeholder="Editable file name").pack(fill="x")

        # Actions with enhanced spacing
        self.record_button = Button(body, self.page, "Start recording", self.toggle, variant="record", height=52, icon="dot")
        self.record_button.pack(fill="x", pady=(0, Space.SM))

        secondary = tk.Frame(body, bg=Color.SURFACE)
        secondary.pack(fill="x")
        Button(secondary, self.page, "Open folder", self._open_folder, variant="ghost", height=42, icon="folder").pack(side="left", fill="x", expand=True)
        Button(secondary, self.page, "Refresh", self._restart_preview, variant="ghost", height=42, icon="refresh").pack(side="left", fill="x", expand=True, padx=(Space.SM, 0))

        self.disk_var = tk.StringVar(value="")
        tk.Label(body, textvariable=self.disk_var, fg=Color.TEXT_4, bg=Color.SURFACE, font=Type.TINY, anchor="w").pack(fill="x", pady=(Space.SM + 2, 0))
        self._update_disk()

    def _update_disk(self) -> None:
        folder = self.folder_var.get().strip() or default_output_dir()
        free = free_space_bytes(folder)
        label = _format_size(free) if free > 0 else "unknown"
        self.disk_var.set(f"Saving to {folder}  ·  {label} free")
        self.root.after(5000, self._update_disk)

    # --------------------------------------------------------------- overlay

    def _show_overlay(self, text: str = "Loading preview") -> None:
        surface = getattr(self.well, "surface", Color.STAGE)
        self.overlay_label.configure(text=text, bg=surface)
        self.overlay.configure(bg=surface)
        self.loader.configure(bg=surface)
        if not self._overlay_visible:
            self.overlay.place(relx=0.5, rely=0.5, anchor="center")
            self.loader.start()
            self._overlay_visible = True

    def _hide_overlay(self) -> None:
        if self._overlay_visible:
            self.loader.stop()
            self.overlay.place_forget()
            self._overlay_visible = False

    # --------------------------------------------------------------- preview

    def _restart_preview(self) -> None:
        if os.environ.get("TL_NO_PREVIEW"):
            return
        if self.recorder is not None and self.recorder.is_active:
            return
        target = self._selected_target()
        self._show_overlay("Loading preview")
        self.preview.set_target(target, cursor=self.cursor_var.get())
        if target:
            self.source_label.configure(text=target.label[:64])
        else:
            self.source_label.configure(text="No source selected")
            self._hide_overlay()

    def _on_target_change(self) -> None:
        self._update_summary()
        self._restart_preview()

    def _tick_preview(self) -> None:
        started = time.perf_counter()
        if not self._painting:
            self._painting = True
            try:
                self._draw_preview()
            except Exception as exc:
                self.source_label.configure(text=f"Preview error: {exc}")
            finally:
                self._painting = False
        spent = (time.perf_counter() - started) * 1000.0
        self.root.after(max(1, int(PREVIEW_MS - spent)), self._tick_preview)

    def _draw_preview(self) -> None:
        recording = self.recorder is not None and self.recorder.is_active
        if recording:
            frame = self.recorder.latest_frame()
            if frame is not None:
                frame = frame.copy()
            self._hide_overlay()
        else:
            if self.preview.is_busy:
                self._show_overlay("Loading preview")
            frame = self.preview.latest()
            error = self.preview.error
            if error and frame is None:
                self._hide_overlay()
                self._stage_message(error)
                return
            if frame is not None:
                self._hide_overlay()

        well = self.well
        width = max(2, well.winfo_width())
        height = max(2, well.winfo_height())

        if frame is None:
            if not self._overlay_visible:
                self._stage_message("Live preview\n\nPick a window or monitor to begin")
            return

        # Use minimal padding so preview fills the well
        fitted = fit_preview(frame, max(2, width - 12), max(2, height - 12))
        photo = self._painter.to_photo(fitted)
        self._preview_photo = photo
        well.reset()
        well.create_image(width // 2, height // 2, image=photo, anchor="center")
        vh, vw = fitted.shape[:2]
        x0 = (width - vw) // 2
        y0 = (height - vh) // 2
        well.create_rectangle(x0 - 1, y0 - 1, x0 + vw, y0 + vh, outline=Color.BORDER, width=1)

        source_h, source_w = frame.shape[:2]
        self.res_chip.set(f"{source_w}×{source_h}", "accent")

        now = time.perf_counter()
        if self._paint_t0 == 0.0:
            self._paint_t0 = now
        self._paint_count += 1
        if now - self._paint_t0 >= 0.5:
            self._paint_fps = self._paint_count / (now - self._paint_t0)
            self._paint_count = 0
            self._paint_t0 = now
            self.fps_chip.set(f"{self._paint_fps:.0f} fps", "muted")

    def _stage_message(self, text: str) -> None:
        well = self.well
        width = max(2, well.winfo_width())
        height = max(2, well.winfo_height())
        well.reset()
        well.create_text(width // 2, height // 2, text=text, fill=Color.TEXT_4, font=Type.BODY, justify="center")

    # ------------------------------------------------------------- behaviour

    def refresh_targets(self) -> None:
        previous = self.target_var.get()
        self.targets = list_targets()
        labels = [str(target) for target in self.targets]
        self.target_select.set_values(labels)
        if previous in labels:
            self.target_var.set(previous)
        elif labels:
            self.target_var.set(labels[0])
        self._update_summary()
        self._restart_preview()

    def _selected_target(self) -> CaptureTarget | None:
        label = self.target_var.get()
        for target in self.targets:
            if str(target) == label:
                return target
        return None

    def _set_mode(self, mode: str | None = None) -> None:
        if mode is None:
            mode = self.mode_var.get()
        else:
            self.mode_var.set(mode)
        self.speed_row.pack_forget()
        self.interval_row.pack_forget()
        if mode == MODE_SPEED:
            self.speed_row.pack(fill="x")
        elif mode == MODE_INTERVAL:
            self.interval_row.pack(fill="x")
        self._update_summary()

    def _parse_speed(self) -> float:
        raw = self.speed_var.get().strip().lower().rstrip("x")
        try:
            return max(1.0, min(1000.0, float(raw)))
        except ValueError:
            return 20.0

    def _parse_interval(self) -> float:
        try:
            return max(0.05, min(3600.0, float(self.interval_var.get())))
        except ValueError:
            return 2.0

    def _output_fps(self) -> int:
        try:
            return int(self.fps_var.get())
        except ValueError:
            return 60

    def _build_config(self) -> RecordingConfig | None:
        target = self._selected_target()
        if target is None:
            messagebox.showerror(APP_NAME, "Select something to capture first.")
            return None
        folder = self.folder_var.get().strip() or default_output_dir()
        name = self.name_var.get().strip() or suggest_filename(target, self.mode_var.get())
        if not name.lower().endswith(".mp4"):
            name += ".mp4"
        return RecordingConfig(
            target=target,
            output_path=os.path.join(folder, name),
            mode=self.mode_var.get(),
            speed=self._parse_speed(),
            interval_s=self._parse_interval(),
            output_fps=self._output_fps(),
            resolution=RESOLUTIONS[self.res_var.get()],
            cursor_capture=self.cursor_var.get(),
            draw_border=self.border_var.get(),
            force_cpu=self.cpu_var.get(),
        )

    def _update_summary(self) -> None:
        target = self._selected_target()
        if target is None:
            self.summary_label.configure(text="")
            return
        config = RecordingConfig(
            target=target,
            output_path="",
            mode=self.mode_var.get(),
            speed=self._parse_speed(),
            interval_s=self._parse_interval(),
            output_fps=self._output_fps(),
            resolution=RESOLUTIONS[self.res_var.get()],
        )
        if config.mode == MODE_REALTIME:
            text = f"{config.describe()} · realtime, no speed-up"
        else:
            minute = 60.0 / config.effective_speed
            text = f"{config.describe()} · 10 min → {10 * minute:.0f}s"
        self.summary_label.configure(text=text)

    def _browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.folder_var.get() or default_output_dir())
        if folder:
            self.folder_var.set(os.path.normpath(folder))

    def _open_folder(self) -> None:
        folder = self.folder_var.get().strip() or default_output_dir()
        if os.path.isdir(folder):
            os.startfile(folder)
        else:
            messagebox.showinfo(APP_NAME, f"Folder does not exist yet:\n{folder}")

    def toggle(self) -> None:
        if self.recorder is not None and self.recorder.is_active:
            self._show_overlay("Finalising video")
            self.record_button.set_loading(True)
            self.recorder.stop()
            self.live_status_var.set("Stopping…")
            return

        config = self._build_config()
        if config is None:
            return

        free = free_space_bytes(os.path.dirname(config.output_path) or ".")
        if 0 <= free < 500 * 1024 * 1024:
            if not messagebox.askyesno(APP_NAME, f"Only {free / 1e6:.0f} MB free.\n\nRecord anyway?"):
                return

        self.preview.stop()
        self._show_overlay("Starting capture")
        self._clear_log()
        self.name_var.set(os.path.basename(config.output_path))
        self.recorder = Recorder(config)
        self.recorder.start()
        self._record_started_at = time.perf_counter()
        self._set_recording_ui(True)
        self.record_button.set_loading(True)
        self.live_status_var.set("Starting…")
        self._start_timer()

    def _set_recording_ui(self, recording: bool) -> None:
        if recording:
            self.record_button.set_variant("stop")
            self.record_button.set_icon("square")
            self.record_button.set_text("Stop recording")
            self.state_chip.set("REC", "rec", dot=True)
            self.state_chip.set_pulsing(True)
        else:
            self.record_button.set_variant("record")
            self.record_button.set_icon("dot")
            self.record_button.set_text("Start recording")
            self.record_button.set_loading(False)
            self.state_chip.set_pulsing(False)
            self.state_chip.set("LIVE", "live", dot=True)
            self._stop_timer()
            self.live_timer_var.set("00:00")
            self.live_status_var.set("Ready")

    def _poll(self) -> None:
        recorder = self.recorder
        if recorder is not None:
            while not recorder.logs.empty():
                self._append_log(recorder.logs.get())

            stats = recorder.snapshot()
            self._update_live_timer(stats.state)

            if stats.state == "recording":
                self._hide_overlay()
                self.record_button.set_loading(False)
            elif stats.state in ("starting", "stopping"):
                self._show_overlay("Starting capture" if stats.state == "starting" else "Finalising video")

            if stats.encoder_label:
                self.encoder_chip.set(stats.encoder_label, "info")

            if stats.state != self._last_state:
                self._on_state_change(stats)
                self._last_state = stats.state
            elif stats.state == "recording":
                self.live_status_var.set(f"Recording • {stats.resolution[0]}×{stats.resolution[1]} • {stats.encoder_label}")

        self.root.after(POLL_MS, self._poll)

    def _on_state_change(self, stats) -> None:
        if stats.state == "recording":
            self.live_status_var.set(f"Recording • {stats.resolution[0]}×{stats.resolution[1]} • {stats.encoder_label}")
            self._hide_overlay()
            self.record_button.set_loading(False)
        elif stats.state == "stopping":
            self.live_status_var.set("Finalising video…")
        elif stats.state == "finished":
            self._set_recording_ui(False)
            self._hide_overlay()
            self.live_status_var.set("Saved")
            self.name_var.set("")
            self._restart_preview()
        elif stats.state == "error":
            self._set_recording_ui(False)
            self._hide_overlay()
            self.live_status_var.set("Recording failed")
            messagebox.showerror(APP_NAME, stats.error or "Recording failed")
            self._restart_preview()

    def _append_log(self, message: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _start_timer(self) -> None:
        self._stop_timer()
        self._timer_tick()

    def _stop_timer(self) -> None:
        if self._timer_job is not None:
            try:
                self.root.after_cancel(self._timer_job)
            except Exception:
                pass
            self._timer_job = None

    def _timer_tick(self) -> None:
        self._timer_job = None
        if self.recorder is None or not self.recorder.is_active:
            self.live_timer_var.set("00:00")
            return
        elapsed = max(0.0, time.perf_counter() - self._record_started_at)
        self.live_timer_var.set(_format_duration_mmss(elapsed))
        self._timer_job = self.root.after(1000, self._timer_tick)

    def _update_live_timer(self, state: str) -> None:
        if state == "recording" and self.recorder is not None and self.recorder.is_active:
            self._timer_tick()

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _register_hotkey(self) -> None:
        if os.environ.get("TL_NO_HOTKEY"):
            return
        try:
            import keyboard
            self._hotkey_handle = keyboard.add_hotkey(HOTKEY, lambda: self.root.after(0, self.toggle))
        except Exception:
            self._append_log(f"Global {HOTKEY.upper()} hotkey unavailable")

    def _unregister_hotkey(self) -> None:
        if self._hotkey_handle is None:
            return
        try:
            import keyboard
            keyboard.remove_hotkey(self._hotkey_handle)
        except Exception:
            pass
        self._hotkey_handle = None

    def _on_close(self) -> None:
        if self.recorder is not None and self.recorder.is_active:
            if not messagebox.askyesno(APP_NAME, "A recording is in progress. Stop it and quit?"):
                return
            self.recorder.stop()
            self.live_status_var.set("Stopping…")
            self.root.after(400, self._on_close)
            return
        self.preview.stop()
        self.loader.stop()
        self._unregister_hotkey()
        self.root.destroy()


def _format_duration_mmss(seconds: float) -> str:
    seconds = max(0.0, seconds)
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_size(num_bytes: int) -> str:
    if num_bytes <= 0:
        return "—"
    for unit, limit in (("GB", 1e9), ("MB", 1e6), ("KB", 1e3)):
        if num_bytes >= limit:
            return f"{num_bytes / limit:.1f} {unit}"
    return f"{num_bytes} B"


def run() -> None:
    from .fonts import load_bundled_fonts
    load_bundled_fonts()
    root = tk.Tk()
    init_typography()
    TimelapserApp(root)
    root.mainloop()
