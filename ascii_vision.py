"""
ascii-vision — Terminal ASCII Art Video Player
==============================================
A cross-platform (Windows / Linux / macOS) ASCII video player built with
a clean object-oriented architecture.

Features:
  - OOP design: VideoInfo, AsciiConverter, FrameDecoder, VideoPlayer, CLI
  - --color / --no-color (ANSI 24-bit true color)
  - --width, --skip  (frame skip to speed up playback on slower machines)
  - --loop           (loop video until Ctrl+C)
  - --info           (print metadata only, no playback)
  - Background decoder thread with graceful shutdown
  - Accurate per-frame timing with busy-wait correction
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Callable

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 92-character brightness ramp (darkest → brightest)
ASCII_CHARSET = (
    " `.-':_,^=;><+!rc*/z?sLTv)J7(|Fi{C}fI31tlu"
    "[neoZ5Yxjya]2ESwqkP6h9d4VpOGbUAKXHm8RD#$Bg0MNWQ%&@"
)
_CHARSET_ARRAY = np.array(list(ASCII_CHARSET))

# ANSI escape sequences
_ANSI_CURSOR_HOME  = "\033[H"
_ANSI_CLEAR_SCREEN = "\033[2J"
_ANSI_HIDE_CURSOR  = "\033[?25l"
_ANSI_SHOW_CURSOR  = "\033[?25h"
_ANSI_RESET        = "\033[0m"

# UI palette
_COLOR_CYAN   = "\033[96m"
_COLOR_GREEN  = "\033[92m"
_COLOR_YELLOW = "\033[93m"
_COLOR_RED    = "\033[91m"
_COLOR_GRAY   = "\033[90m"
_COLOR_BOLD   = "\033[1m"

_PROGRESS_BAR_LENGTH = 40
_DEFAULT_QUEUE_SIZE  = 8
_DECODER_TIMEOUT_SEC = 2.0


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _enable_ansi_on_windows() -> None:
    """Enable ANSI escape code processing on Windows consoles."""
    if os.name != "nt":
        return
    try:
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7)
    except Exception:
        pass


def _terminal_width() -> int:
    """Return current terminal column count, falling back to 80."""
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VideoInfo:
    """Immutable snapshot of a video file's metadata."""

    fps: float
    total_frames: int
    width_px: int
    height_px: int
    duration_seconds: float

    @classmethod
    def from_capture(cls, capture: cv2.VideoCapture) -> "VideoInfo":
        raw_fps    = capture.get(cv2.CAP_PROP_FPS)
        safe_fps   = raw_fps if raw_fps > 0 else 30.0
        frames     = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        return cls(
            fps              = safe_fps,
            total_frames     = frames,
            width_px         = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height_px        = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            duration_seconds = frames / safe_fps,
        )

    def format_duration(self) -> str:
        total_seconds = int(self.duration_seconds)
        return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


# ---------------------------------------------------------------------------
# ASCII converter
# ---------------------------------------------------------------------------

class AsciiConverter:
    """Converts OpenCV BGR frames to ANSI terminal strings."""

    def __init__(self, output_width: int, use_color: bool) -> None:
        self.output_width = output_width
        self.use_color    = use_color
        self._charset_len = len(ASCII_CHARSET) - 1

    # -- public interface

    def convert(self, frame: np.ndarray) -> str:
        """Return an ASCII art string for *frame*."""
        if self.use_color:
            return self._convert_color(frame)
        return self._convert_grayscale(frame)

    # -- private helpers

    def _compute_output_height(self, frame: np.ndarray) -> int:
        src_h, src_w = frame.shape[:2]
        # Divide by 2 because terminal characters are ~2× taller than wide
        return max(1, int(src_h * self.output_width / src_w / 2))

    def _convert_grayscale(self, frame: np.ndarray) -> str:
        output_height = self._compute_output_height(frame)
        resized       = cv2.resize(frame, (self.output_width, output_height))
        gray          = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

        rows = []
        for pixel_row in gray:
            row_chars = "".join(
                ASCII_CHARSET[int(pixel / 255.0 * self._charset_len)]
                for pixel in pixel_row
            )
            rows.append(row_chars)
        return "\n".join(rows)

    def _convert_color(self, frame: np.ndarray) -> str:
        output_height = self._compute_output_height(frame)
        resized       = cv2.resize(frame, (self.output_width, output_height))
        rgb           = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        r_channel = rgb[:, :, 0].astype(np.float32)
        g_channel = rgb[:, :, 1].astype(np.float32)
        b_channel = rgb[:, :, 2].astype(np.float32)

        brightness    = 0.299 * r_channel + 0.587 * g_channel + 0.114 * b_channel
        char_indices  = np.clip(
            (brightness / 255.0 * self._charset_len).astype(np.int32),
            0, self._charset_len,
        )
        char_grid = _CHARSET_ARRAY[char_indices]

        rows = []
        for row_index in range(output_height):
            parts = []
            for col_index in range(self.output_width):
                rv  = int(rgb[row_index, col_index, 0])
                gv  = int(rgb[row_index, col_index, 1])
                bv  = int(rgb[row_index, col_index, 2])
                ch  = char_grid[row_index, col_index]
                parts.append(f"\033[38;2;{rv};{gv};{bv}m{ch}")
            parts.append(_ANSI_RESET)
            rows.append("".join(parts))
        return "\n".join(rows)


# ---------------------------------------------------------------------------
# Background frame decoder
# ---------------------------------------------------------------------------

class FrameDecoder:
    """
    Reads raw frames from a VideoCapture in a background thread and
    places them into a bounded queue for the render loop to consume.
    """

    SENTINEL = None  # signals end-of-stream

    def __init__(
        self,
        capture: cv2.VideoCapture,
        frame_skip: int,
        queue_size: int = _DEFAULT_QUEUE_SIZE,
    ) -> None:
        self._capture    = capture
        self._frame_skip = max(1, frame_skip)
        self._queue: Queue = Queue(maxsize=queue_size)
        self._stop_event   = threading.Event()
        self._thread       = threading.Thread(
            target=self._decode_loop, daemon=True
        )

    # -- lifecycle

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = _DECODER_TIMEOUT_SEC) -> None:
        self._stop_event.set()
        self._thread.join(timeout=timeout)

    # -- consumer interface

    def next_frame(self, timeout: float = _DECODER_TIMEOUT_SEC):
        """
        Block until a frame is available and return it.
        Returns *SENTINEL* on end-of-stream or *timeout*.
        Raises *KeyboardInterrupt* transparently.
        """
        try:
            return self._queue.get(timeout=timeout)
        except Empty:
            return FrameDecoder.SENTINEL

    # -- private

    def _decode_loop(self) -> None:
        frame_index = 0
        while not self._stop_event.is_set():
            success, raw_frame = self._capture.read()
            if not success:
                break

            # Drop frames according to skip ratio
            if self._frame_skip > 1 and frame_index % self._frame_skip != 0:
                frame_index += 1
                continue

            frame_index += 1
            self._enqueue(raw_frame)

        self._enqueue(FrameDecoder.SENTINEL)

    def _enqueue(self, item) -> None:
        """Put *item* into the queue, retrying until space is available or stopped."""
        while not self._stop_event.is_set():
            try:
                self._queue.put(item, timeout=0.05)
                return
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Video player
# ---------------------------------------------------------------------------

class VideoPlayer:
    """
    Orchestrates decoding, conversion, and rendering of an ASCII video.

    Parameters
    ----------
    video_path   : Path to the video file.
    output_width : Width of the ASCII output in terminal characters.
    use_color    : Enable 24-bit ANSI colour.
    frame_skip   : Render every Nth frame (1 = all frames).
    loop         : Loop the video until the user interrupts.
    """

    def __init__(
        self,
        video_path: str,
        output_width: int,
        use_color: bool = False,
        frame_skip: int = 1,
        loop: bool = False,
    ) -> None:
        self.video_path   = video_path
        self.output_width = output_width
        self.use_color    = use_color
        self.frame_skip   = frame_skip
        self.loop         = loop

    # -- public

    def play(self) -> None:
        """Start playback. Blocks until finished or Ctrl+C."""
        self._validate_file()
        _enable_ansi_on_windows()

        converter   = AsciiConverter(self.output_width, self.use_color)
        loop_number = 0

        while True:
            loop_number += 1
            capture = self._open_capture()
            info    = VideoInfo.from_capture(capture)

            if loop_number == 1:
                self._print_playback_header(info)
                time.sleep(2.0)

            self._run_playback_loop(capture, info, converter, loop_number)
            capture.release()

            if not self.loop:
                break

        self._restore_terminal()
        sys.stdout.write(f"\n\n{_COLOR_GREEN}[done]{_ANSI_RESET} Playback finished.\n")
        sys.stdout.flush()

    # -- private: setup / teardown

    def _validate_file(self) -> None:
        if not os.path.exists(self.video_path):
            sys.exit(
                f"{_COLOR_RED}[error]{_ANSI_RESET} "
                f"File not found: '{self.video_path}'"
            )

    def _open_capture(self) -> cv2.VideoCapture:
        capture = cv2.VideoCapture(self.video_path)
        if not capture.isOpened():
            sys.exit(f"{_COLOR_RED}[error]{_ANSI_RESET} Unable to open video file.")
        return capture

    @staticmethod
    def _restore_terminal() -> None:
        sys.stdout.write(_ANSI_SHOW_CURSOR)
        sys.stdout.write(_ANSI_RESET)
        sys.stdout.flush()

    # -- private: rendering

    def _run_playback_loop(
        self,
        capture: cv2.VideoCapture,
        info: VideoInfo,
        converter: AsciiConverter,
        loop_number: int,
    ) -> None:
        # Frame delay compensates for skip ratio so wall-clock speed is correct
        frame_delay  = (1.0 / info.fps) * self.frame_skip
        total_frames = max(1, info.total_frames // self.frame_skip)

        decoder = FrameDecoder(capture, self.frame_skip)
        decoder.start()

        sys.stdout.write(_ANSI_HIDE_CURSOR)
        sys.stdout.write(_ANSI_CLEAR_SCREEN)
        sys.stdout.flush()

        rendered_count = 0
        try:
            while True:
                tick = time.perf_counter()

                frame = decoder.next_frame()
                if frame is FrameDecoder.SENTINEL:
                    break

                rendered_count += 1
                ascii_art = converter.convert(frame)

                self._render_frame(ascii_art, rendered_count, total_frames, loop_number)

                elapsed    = time.perf_counter() - tick
                sleep_time = frame_delay - elapsed
                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            decoder.stop()
            self._restore_terminal()
            print(f"\n\n{_COLOR_YELLOW}[info]{_ANSI_RESET} Stopped by user.\n")
            sys.exit(0)
        finally:
            decoder.stop()

    def _render_frame(
        self,
        ascii_art: str,
        current_frame: int,
        total_frames: int,
        loop_number: int,
    ) -> None:
        progress = current_frame / total_frames
        filled   = int(_PROGRESS_BAR_LENGTH * progress)
        bar      = "█" * filled + "░" * (_PROGRESS_BAR_LENGTH - filled)
        loop_tag = f" | Loop #{loop_number}" if self.loop else ""

        sys.stdout.write(_ANSI_CURSOR_HOME)
        sys.stdout.write(ascii_art)
        sys.stdout.write(
            f"\n{_ANSI_RESET}{_COLOR_GRAY}"
            f"[{bar}] {current_frame}/{total_frames}"
            f"{loop_tag} | Ctrl+C to quit"
            f"{_ANSI_RESET}"
        )
        sys.stdout.flush()

    # -- private: info display

    def _print_playback_header(self, info: VideoInfo) -> None:
        color_label = (
            f"{_COLOR_GREEN}color (ANSI 24-bit){_ANSI_RESET}"
            if self.use_color
            else f"{_COLOR_GRAY}grayscale{_ANSI_RESET}"
        )
        _print_video_info(self.video_path, info)
        print(f"  Mode        : {color_label}")
        print(f"  Output width: {self.output_width} chars")
        print(f"  Frame skip  : every {self.frame_skip} frame(s)")
        print(f"  Loop        : {'yes' if self.loop else 'no'}")
        print(
            f"\n{_COLOR_YELLOW}"
            f"Starting in 2 seconds… Ctrl+C to abort."
            f"{_ANSI_RESET}\n"
        )


# ---------------------------------------------------------------------------
# Shared UI helper
# ---------------------------------------------------------------------------

def _print_video_info(video_path: str, info: VideoInfo) -> None:
    """Print a formatted metadata block to stdout."""
    separator = f"{_COLOR_CYAN}{'─' * 54}{_ANSI_RESET}"
    print(f"\n{separator}")
    print(f"  {_COLOR_BOLD}ascii-vision — Terminal ASCII Art Video Player{_ANSI_RESET}")
    print(separator)
    print(f"  {_COLOR_YELLOW}File      {_ANSI_RESET}: {os.path.basename(video_path)}")
    print(f"  {_COLOR_YELLOW}Resolution{_ANSI_RESET}: {info.width_px} × {info.height_px} px")
    print(f"  {_COLOR_YELLOW}FPS       {_ANSI_RESET}: {info.fps:.2f}")
    print(
        f"  {_COLOR_YELLOW}Duration  {_ANSI_RESET}: "
        f"{info.format_duration()} ({info.total_frames} frames)"
    )
    print(f"{separator}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

class CLI:
    """
    Handles argument parsing and wires everything together.
    Supports both full CLI mode and interactive (no-args) fallback.
    """

    _DESCRIPTION = "ascii-vision — Terminal ASCII Art Video Player"

    _EXAMPLES = """
examples:
  python ascii_vision.py video.mp4
  python ascii_vision.py video.mp4 --color --width 100
  python ascii_vision.py video.mp4 --no-color --width 140 --loop
  python ascii_vision.py video.mp4 --color --skip 2 --width 80
  python ascii_vision.py video.mp4 --info
"""

    def run(self) -> None:
        _enable_ansi_on_windows()
        args = self._build_parser().parse_args()

        if args.video is None:
            args = self._interactive_prompt(args)

        args.width = self._resolve_width(args)
        args.skip  = max(1, args.skip)

        if args.info:
            self._show_info_only(args.video)
            return

        VideoPlayer(
            video_path   = args.video,
            output_width = args.width,
            use_color    = args.color,
            frame_skip   = args.skip,
            loop         = args.loop,
        ).play()

    # -- private

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            prog             = "ascii_vision.py",
            description      = self._DESCRIPTION,
            formatter_class  = argparse.RawTextHelpFormatter,
            epilog           = self._EXAMPLES,
        )
        parser.add_argument(
            "video",
            nargs   = "?",
            default = None,
            help    = "Path to the video file (mp4, avi, mkv, …)",
        )
        parser.add_argument(
            "--width", "-w",
            type    = int,
            default = None,
            help    = "Output width in characters (default: auto from terminal size)",
        )
        color_group = parser.add_mutually_exclusive_group()
        color_group.add_argument(
            "--color", "-c",
            action  = "store_true",
            default = False,
            help    = "Enable 24-bit ANSI colour (requires a true-colour terminal)",
        )
        color_group.add_argument(
            "--no-color",
            action  = "store_true",
            default = False,
            help    = "Force grayscale mode (default)",
        )
        parser.add_argument(
            "--skip", "-s",
            type    = int,
            default = 1,
            metavar = "N",
            help    = "Render every Nth frame (e.g. --skip 2 halves the frame rate)",
        )
        parser.add_argument(
            "--loop", "-l",
            action  = "store_true",
            default = False,
            help    = "Loop the video until Ctrl+C",
        )
        parser.add_argument(
            "--info", "-i",
            action  = "store_true",
            default = False,
            help    = "Print video metadata and exit without playing",
        )
        return parser

    def _interactive_prompt(self, args: argparse.Namespace) -> argparse.Namespace:
        """Collect missing options interactively when no arguments were passed."""
        separator = f"{_COLOR_CYAN}{'─' * 54}{_ANSI_RESET}"
        print(f"\n{separator}")
        print(f"  {_COLOR_BOLD}ascii-vision — Interactive Mode{_ANSI_RESET}")
        print(separator)
        print(f"  For all options: {_COLOR_YELLOW}python ascii_vision.py --help{_ANSI_RESET}\n")

        args.video = input("  Video path: ").strip().strip('"')
        if not args.video:
            sys.exit(f"{_COLOR_RED}[error]{_ANSI_RESET} No path provided.")

        color_answer = input("  Enable color? (y/N): ").strip().lower()
        args.color   = color_answer == "y"

        default_width = self._resolve_width(args)
        width_answer  = input(
            f"  Output width (default {default_width}): "
        ).strip()
        try:
            args.width = int(width_answer) if width_answer else default_width
        except ValueError:
            args.width = default_width

        skip_answer = input("  Frame skip (default 1 = every frame): ").strip()
        try:
            args.skip = int(skip_answer) if skip_answer else 1
        except ValueError:
            args.skip = 1

        loop_answer = input("  Loop video? (y/N): ").strip().lower()
        args.loop   = loop_answer == "y"

        return args

    @staticmethod
    def _resolve_width(args: argparse.Namespace) -> int:
        if args.width is not None:
            return args.width
        columns = _terminal_width()
        # Colour mode is heavier; cap at a lower default to reduce rendering lag
        return min(columns, 100) if args.color else min(columns, 200)

    @staticmethod
    def _show_info_only(video_path: str) -> None:
        if not os.path.exists(video_path):
            sys.exit(
                f"{_COLOR_RED}[error]{_ANSI_RESET} "
                f"File not found: '{video_path}'"
            )
        capture = cv2.VideoCapture(video_path)
        info    = VideoInfo.from_capture(capture)
        capture.release()
        _print_video_info(video_path, info)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    CLI().run()
