"""
ascii-vision GUI
================
Dark-themed Tkinter launcher for ascii_vision.py.

Requires: tkinter (stdlib), opencv-python, numpy
Run with: python ascii_vision_gui.py
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox
from pathlib import Path


# ---------------------------------------------------------------------------
# Theme / Design tokens
# ---------------------------------------------------------------------------

COLORS = {
    # Backgrounds
    "bg_root":      "#0a0a0a",
    "bg_card":      "#111111",
    "bg_input":     "#1a1a1a",
    "bg_hover":     "#1e1e1e",
    "bg_separator": "#222222",

    # Accents
    "accent":       "#00e5ff",   # cyan
    "accent_dim":   "#00b8cc",
    "accent_glow":  "#003d47",
    "success":      "#00e676",
    "warning":      "#ffb300",
    "danger":       "#ff1744",

    # Text
    "text_primary":   "#f0f0f0",
    "text_secondary": "#888888",
    "text_muted":     "#444444",
    "text_accent":    "#00e5ff",
}

FONT_FAMILY = "Consolas" if platform.system() == "Windows" else "Monospace"
FONT_MONO   = (FONT_FAMILY, 10)
FONT_SMALL  = (FONT_FAMILY, 9)
FONT_LABEL  = (FONT_FAMILY, 10, "bold")
FONT_TITLE  = (FONT_FAMILY, 15, "bold")
FONT_BADGE  = (FONT_FAMILY, 8)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _script_dir() -> Path:
    return Path(__file__).resolve().parent


def _ascii_vision_path() -> Path:
    return _script_dir() / "ascii_vision.py"


def _python_executable() -> str:
    return sys.executable


def _build_command(
    video_path: str,
    width: int,
    use_color: bool,
    frame_skip: int,
    loop: bool,
    info_only: bool = False,
) -> list[str]:
    """Build the subprocess argv list for ascii_vision.py."""
    cmd = [_python_executable(), str(_ascii_vision_path()), video_path]
    if info_only:
        cmd.append("--info")
        return cmd
    cmd += ["--width", str(width)]
    cmd += ["--color"] if use_color else ["--no-color"]
    cmd += ["--skip", str(frame_skip)]
    if loop:
        cmd.append("--loop")
    return cmd


def _open_in_terminal(command: list[str]) -> None:
    """Launch *command* in a new visible terminal window (cross-platform)."""
    system = platform.system()

    if system == "Windows":
        # 'start' opens a new cmd window; /k keeps it open after the process ends
        joined = " ".join(f'"{c}"' if " " in c else c for c in command)
        subprocess.Popen(f'start cmd /k {joined}', shell=True)

    elif system == "Darwin":
        script = " ".join(f'\\"{c}\\"' if " " in c else c for c in command)
        apple_script = f'tell application "Terminal" to do script "{script}"'
        subprocess.Popen(["osascript", "-e", apple_script])

    else:  # Linux — try common emulators in order
        emulators = [
            ["gnome-terminal", "--"],
            ["xfce4-terminal", "-e"],
            ["konsole", "-e"],
            ["xterm", "-e"],
            ["lxterminal", "-e"],
            ["mate-terminal", "-e"],
        ]
        for emulator_prefix in emulators:
            binary = emulator_prefix[0]
            if shutil.which(binary):
                # gnome-terminal uses '--' separator; others use '-e'
                if binary == "gnome-terminal":
                    subprocess.Popen([binary, "--"] + command)
                else:
                    joined = " ".join(
                        f'"{c}"' if " " in c else c for c in command
                    )
                    subprocess.Popen([binary, "-e", joined])
                return
        messagebox.showerror(
            "Terminal not found",
            "Could not find a terminal emulator.\n"
            "Please install gnome-terminal, xterm, or konsole.",
        )


def _fetch_video_info(video_path: str) -> dict[str, str]:
    """
    Run ascii_vision.py --info and parse the output into a dict.
    Returns an empty dict on failure.
    """
    try:
        result = subprocess.run(
            _build_command(video_path, 120, False, 1, False, info_only=True),
            capture_output=True,
            text=True,
            timeout=10,
        )
        info: dict[str, str] = {}
        for line in result.stdout.splitlines():
            if ":" in line:
                parts = line.split(":", 1)
                key   = parts[0].strip().lstrip("│ ").strip()
                value = parts[1].strip()
                if key and value and key not in ("─",):
                    info[key] = value
        return info
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Custom widgets
# ---------------------------------------------------------------------------

class _Separator(tk.Frame):
    def __init__(self, parent, **kwargs):
        super().__init__(
            parent,
            height=1,
            bg=COLORS["bg_separator"],
            **kwargs,
        )


class _Label(tk.Label):
    """Pre-styled label."""
    def __init__(self, parent, text="", style="primary", **kwargs):
        color_map = {
            "primary":   COLORS["text_primary"],
            "secondary": COLORS["text_secondary"],
            "accent":    COLORS["text_accent"],
            "muted":     COLORS["text_muted"],
            "success":   COLORS["success"],
            "warning":   COLORS["warning"],
            "danger":    COLORS["danger"],
        }
        super().__init__(
            parent,
            text=text,
            fg=color_map.get(style, COLORS["text_primary"]),
            bg=kwargs.pop("bg", COLORS["bg_card"]),
            **kwargs,
        )


class _Button(tk.Frame):
    """
    Flat custom button with hover effect and optional left icon.
    Accepts an `on_click` callback.
    """

    def __init__(
        self,
        parent,
        text: str,
        on_click,
        icon: str = "",
        bg: str = COLORS["accent"],
        fg: str = "#000000",
        hover_bg: str = COLORS["accent_dim"],
        font=FONT_LABEL,
        padx: int = 20,
        pady: int = 10,
        **kwargs,
    ):
        super().__init__(parent, bg=parent["bg"], **kwargs)

        self._bg       = bg
        self._hover_bg = hover_bg
        self._fg       = fg
        self._callback = on_click

        label_text = f"{icon}  {text}" if icon else text
        self._label = tk.Label(
            self,
            text=label_text,
            bg=bg,
            fg=fg,
            font=font,
            padx=padx,
            pady=pady,
            cursor="hand2",
        )
        self._label.pack(fill="both", expand=True)

        self._label.bind("<Enter>",    self._on_enter)
        self._label.bind("<Leave>",    self._on_leave)
        self._label.bind("<Button-1>", self._on_click)

    def _on_enter(self, _event=None):
        self._label.config(bg=self._hover_bg)

    def _on_leave(self, _event=None):
        self._label.config(bg=self._bg)

    def _on_click(self, _event=None):
        self._callback()

    def set_state(self, enabled: bool) -> None:
        if enabled:
            self._label.config(
                bg=self._bg,
                fg=self._fg,
                cursor="hand2",
            )
            self._label.bind("<Button-1>", self._on_click)
        else:
            self._label.config(
                bg=COLORS["bg_separator"],
                fg=COLORS["text_muted"],
                cursor="",
            )
            self._label.unbind("<Button-1>")


class _ToggleButton(tk.Frame):
    """Two-state toggle (ON / OFF) rendered as a single pill."""

    def __init__(self, parent, label: str, variable: tk.BooleanVar, **kwargs):
        super().__init__(parent, bg=COLORS["bg_card"], **kwargs)
        self._var = variable

        self._lbl = tk.Label(
            self,
            text=label,
            bg=COLORS["bg_card"],
            fg=COLORS["text_secondary"],
            font=FONT_LABEL,
        )
        self._lbl.pack(side="left", padx=(0, 8))

        self._pill = tk.Label(
            self,
            text="  OFF  ",
            bg=COLORS["bg_input"],
            fg=COLORS["text_muted"],
            font=FONT_BADGE,
            padx=6,
            pady=3,
            cursor="hand2",
        )
        self._pill.pack(side="left")
        self._pill.bind("<Button-1>", self._toggle)
        self._refresh()

    def _toggle(self, _event=None):
        self._var.set(not self._var.get())
        self._refresh()

    def _refresh(self):
        if self._var.get():
            self._pill.config(
                text="  ON  ",
                bg=COLORS["accent_glow"],
                fg=COLORS["accent"],
            )
        else:
            self._pill.config(
                text="  OFF  ",
                bg=COLORS["bg_input"],
                fg=COLORS["text_muted"],
            )


class _SliderRow(tk.Frame):
    """Labeled slider with live value readout."""

    def __init__(
        self,
        parent,
        label: str,
        variable: tk.IntVar,
        from_: int,
        to: int,
        unit: str = "",
        **kwargs,
    ):
        super().__init__(parent, bg=COLORS["bg_card"], **kwargs)
        self._unit = unit

        _Label(self, text=label, style="secondary", font=FONT_LABEL).pack(
            side="left", padx=(0, 10)
        )

        self._value_lbl = _Label(
            self,
            text=f"{variable.get()}{unit}",
            style="accent",
            font=FONT_LABEL,
            width=6,
            anchor="e",
        )
        self._value_lbl.pack(side="right")

        self._slider = tk.Scale(
            self,
            variable=variable,
            from_=from_,
            to=to,
            orient="horizontal",
            showvalue=False,
            bg=COLORS["bg_card"],
            fg=COLORS["accent"],
            troughcolor=COLORS["bg_input"],
            activebackground=COLORS["accent"],
            highlightthickness=0,
            bd=0,
            command=self._on_change,
        )
        self._slider.pack(side="left", fill="x", expand=True, padx=8)

    def _on_change(self, value):
        self._value_lbl.config(text=f"{int(float(value))}{self._unit}")


# ---------------------------------------------------------------------------
# Main application window
# ---------------------------------------------------------------------------

class AsciiVisionApp(tk.Tk):

    def __init__(self):
        super().__init__()

        self.title("ascii-vision")
        self.resizable(False, False)
        self.configure(bg=COLORS["bg_root"])

        # Center the window
        self.geometry("480x680")
        self.update_idletasks()
        x = (self.winfo_screenwidth()  - 480) // 2
        y = (self.winfo_screenheight() - 680) // 2
        self.geometry(f"480x680+{x}+{y}")

        # State
        self._video_path:  str = ""
        self._width_var    = tk.IntVar(value=120)
        self._skip_var     = tk.IntVar(value=1)
        self._color_var    = tk.BooleanVar(value=False)
        self._loop_var     = tk.BooleanVar(value=False)

        self._build_ui()

    # ── UI construction ──────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root_pad = tk.Frame(self, bg=COLORS["bg_root"], padx=20, pady=20)
        root_pad.pack(fill="both", expand=True)

        self._build_header(root_pad)
        self._build_file_section(root_pad)
        self._build_info_section(root_pad)
        self._build_settings_section(root_pad)
        self._build_play_section(root_pad)
        self._build_status_bar(root_pad)

    # -- header

    def _build_header(self, parent: tk.Frame) -> None:
        frame = tk.Frame(parent, bg=COLORS["bg_root"])
        frame.pack(fill="x", pady=(0, 16))

        tk.Label(
            frame,
            text="░▒▓  ascii-vision  ▓▒░",
            bg=COLORS["bg_root"],
            fg=COLORS["accent"],
            font=FONT_TITLE,
        ).pack(side="left")

        tk.Label(
            frame,
            text="v1.0",
            bg=COLORS["bg_root"],
            fg=COLORS["text_muted"],
            font=FONT_BADGE,
        ).pack(side="right", anchor="s", pady=4)

        _Separator(parent, bg=COLORS["bg_separator"]).pack(fill="x", pady=(0, 16))

    # -- file picker

    def _build_file_section(self, parent: tk.Frame) -> None:
        card = self._make_card(parent, title="VIDEO FILE")

        # Drop zone / display
        self._file_display = tk.Label(
            card,
            text="No file selected",
            bg=COLORS["bg_input"],
            fg=COLORS["text_muted"],
            font=FONT_MONO,
            anchor="w",
            padx=12,
            pady=10,
            relief="flat",
        )
        self._file_display.pack(fill="x", pady=(0, 10))

        btn_row = tk.Frame(card, bg=COLORS["bg_card"])
        btn_row.pack(fill="x")

        _Button(
            btn_row,
            text="Browse",
            icon="📂",
            on_click=self._browse_file,
            bg=COLORS["bg_input"],
            fg=COLORS["text_primary"],
            hover_bg=COLORS["bg_hover"],
            font=FONT_LABEL,
            padx=14,
            pady=8,
        ).pack(side="left", padx=(0, 8))

        self._info_btn = _Button(
            btn_row,
            text="Show Info",
            icon="ℹ",
            on_click=self._show_info_terminal,
            bg=COLORS["bg_input"],
            fg=COLORS["text_primary"],
            hover_bg=COLORS["bg_hover"],
            font=FONT_LABEL,
            padx=14,
            pady=8,
        )
        self._info_btn.pack(side="left")
        self._info_btn.set_state(False)

    # -- video info panel

    def _build_info_section(self, parent: tk.Frame) -> None:
        self._info_card = self._make_card(parent, title="VIDEO INFO")

        self._info_rows: dict[str, tk.Label] = {}

        fields = [
            ("File",       "—"),
            ("Resolution", "—"),
            ("FPS",        "—"),
            ("Duration",   "—"),
        ]

        for field_key, default_val in fields:
            row = tk.Frame(self._info_card, bg=COLORS["bg_card"])
            row.pack(fill="x", pady=2)

            _Label(
                row,
                text=f"{field_key:<11}",
                style="secondary",
                font=FONT_MONO,
            ).pack(side="left")

            val_lbl = _Label(
                row,
                text=default_val,
                style="primary",
                font=FONT_MONO,
            )
            val_lbl.pack(side="left")
            self._info_rows[field_key] = val_lbl

    # -- settings panel

    def _build_settings_section(self, parent: tk.Frame) -> None:
        card = self._make_card(parent, title="SETTINGS")

        _SliderRow(
            card,
            label="Width  ",
            variable=self._width_var,
            from_=40,
            to=220,
            unit=" ch",
        ).pack(fill="x", pady=(0, 10))

        _SliderRow(
            card,
            label="Skip   ",
            variable=self._skip_var,
            from_=1,
            to=8,
            unit="×",
        ).pack(fill="x", pady=(0, 10))

        toggle_row = tk.Frame(card, bg=COLORS["bg_card"])
        toggle_row.pack(fill="x")

        _ToggleButton(
            toggle_row,
            label="Color (24-bit)",
            variable=self._color_var,
        ).pack(side="left", padx=(0, 24))

        _ToggleButton(
            toggle_row,
            label="Loop",
            variable=self._loop_var,
        ).pack(side="left")

    # -- play button

    def _build_play_section(self, parent: tk.Frame) -> None:
        tk.Frame(parent, bg=COLORS["bg_root"], height=12).pack()

        self._play_btn = _Button(
            parent,
            text="PLAY IN TERMINAL",
            icon="▶",
            on_click=self._play,
            bg=COLORS["accent"],
            fg="#000000",
            hover_bg=COLORS["accent_dim"],
            font=(FONT_FAMILY, 13, "bold"),
            padx=30,
            pady=14,
        )
        self._play_btn.pack(fill="x")
        self._play_btn.set_state(False)

    # -- status bar

    def _build_status_bar(self, parent: tk.Frame) -> None:
        tk.Frame(parent, bg=COLORS["bg_root"], height=12).pack()
        _Separator(parent, bg=COLORS["bg_separator"]).pack(fill="x", pady=(0, 8))

        self._status_var = tk.StringVar(value="Ready — select a video file to begin")
        tk.Label(
            parent,
            textvariable=self._status_var,
            bg=COLORS["bg_root"],
            fg=COLORS["text_muted"],
            font=FONT_SMALL,
            anchor="w",
        ).pack(fill="x")

    # ── Helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _make_card(parent: tk.Frame, title: str) -> tk.Frame:
        """Return a titled card frame packed into *parent*."""
        wrapper = tk.Frame(parent, bg=COLORS["bg_root"])
        wrapper.pack(fill="x", pady=(0, 12))

        header = tk.Frame(wrapper, bg=COLORS["bg_root"])
        header.pack(fill="x", pady=(0, 6))

        tk.Label(
            header,
            text=title,
            bg=COLORS["bg_root"],
            fg=COLORS["text_muted"],
            font=FONT_BADGE,
        ).pack(side="left")

        tk.Frame(header, bg=COLORS["bg_separator"], height=1).pack(
            side="left", fill="x", expand=True, padx=(8, 0), pady=6
        )

        card = tk.Frame(wrapper, bg=COLORS["bg_card"], padx=16, pady=14)
        card.pack(fill="x")
        return card

    def _set_status(self, message: str, color: str = COLORS["text_muted"]) -> None:
        self._status_var.set(message)

    def _update_info_panel(self, info: dict[str, str]) -> None:
        """Populate the info panel with data from *info*."""
        mapping = {
            "File":       ("File",       lambda d: d.get("File", "—")),
            "Resolution": ("Resolution", lambda d: d.get("Resolution", d.get("Resolusi", "—"))),
            "FPS":        ("FPS",        lambda d: d.get("FPS", "—")),
            "Duration":   ("Duration",   lambda d: d.get("Duration",  d.get("Durasi",   "—"))),
        }
        for display_key, (_, extractor) in mapping.items():
            value = extractor(info)
            lbl   = self._info_rows[display_key]
            lbl.config(text=value, fg=COLORS["text_primary"])

    def _clear_info_panel(self) -> None:
        for lbl in self._info_rows.values():
            lbl.config(text="—", fg=COLORS["text_muted"])

    # ── Event handlers ───────────────────────────────────────────────────────

    def _browse_file(self) -> None:
        file_types = [
            ("Video files", "*.mp4 *.avi *.mkv *.mov *.webm *.m4v *.flv *.wmv"),
            ("All files",   "*.*"),
        ]
        path = filedialog.askopenfilename(
            title="Select a video file",
            filetypes=file_types,
        )
        if not path:
            return

        self._video_path = path
        short_name       = Path(path).name

        # Update display
        self._file_display.config(
            text=short_name,
            fg=COLORS["text_primary"],
        )
        self._set_status(f"Loading info for  {short_name}…")
        self._clear_info_panel()
        self._play_btn.set_state(False)
        self._info_btn.set_state(False)

        # Fetch info in background so UI stays responsive
        threading.Thread(
            target=self._load_info_background,
            args=(path,),
            daemon=True,
        ).start()

    def _load_info_background(self, path: str) -> None:
        info = _fetch_video_info(path)
        # Schedule UI update back on the main thread
        self.after(0, self._on_info_loaded, info)

    def _on_info_loaded(self, info: dict[str, str]) -> None:
        if info:
            self._update_info_panel(info)
            self._set_status("File ready — configure settings and press Play")
        else:
            self._set_status("⚠  Could not read video info — check the file", COLORS["warning"])

        self._play_btn.set_state(True)
        self._info_btn.set_state(True)

    def _show_info_terminal(self) -> None:
        if not self._video_path:
            return
        cmd = _build_command(self._video_path, 120, False, 1, False, info_only=True)
        _open_in_terminal(cmd)
        self._set_status("Opened info window in terminal")

    def _play(self) -> None:
        if not self._video_path:
            messagebox.showwarning("No video", "Please select a video file first.")
            return

        if not _ascii_vision_path().exists():
            messagebox.showerror(
                "Script not found",
                f"ascii_vision.py not found in:\n{_script_dir()}\n\n"
                "Make sure both files are in the same folder.",
            )
            return

        cmd = _build_command(
            video_path  = self._video_path,
            width       = self._width_var.get(),
            use_color   = self._color_var.get(),
            frame_skip  = self._skip_var.get(),
            loop        = self._loop_var.get(),
        )

        _open_in_terminal(cmd)

        mode = "color" if self._color_var.get() else "grayscale"
        self._set_status(
            f"▶  Playing in terminal — {mode}, "
            f"width {self._width_var.get()}, "
            f"skip {self._skip_var.get()}×"
            + (" — looping" if self._loop_var.get() else "")
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = AsciiVisionApp()
    app.mainloop()
