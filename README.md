# 🎬 ascii-vision

> **Terminal ASCII Art Video Player** — watch any video as real-time ASCII art directly in your terminal, with optional 24-bit ANSI colour.

![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-4.x-5C3EE8?style=flat-square&logo=opencv&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)

---

## ✨ Features

- 🎨 **True-colour mode** — 24-bit ANSI colour rendering per character
- 🖤 **Grayscale mode** — fast, minimal, works on any terminal
- ⚡ **Frame skipping** — tune performance for your machine with `--skip`
- 🔁 **Loop playback** — repeat until `Ctrl+C`
- 📊 **Live progress bar** — frame counter and loop indicator
- 🧵 **Background decoder thread** — decoding never blocks rendering
- 🪟 **Cross-platform** — Windows, Linux, and macOS
- 🔍 **`--info` mode** — print video metadata without playing
- 💬 **Interactive fallback** — guided prompts if no arguments are provided

---

## 📸 Preview

```
▓▓▒▒░░  ▓█▓░  ░░▒▒▓▓▒▒░░ ▒▓█▓▒░  ░░▒▓█▓▒▒░░▓▒░
░▒▓██▓▒░▒▓█▓░░▒▓██▓▒░▒▓█▓▒░░▒▓██▓▒░░▒▓██▓▒░░▒▓
▒▓███▓▒░▒▓███▓░▒▓███▓▒░▒▓███▓░▒▓███▓▒░▒▓███▓▒░
[████████████████░░░░░░░░░░░░░░░░░░░░] 312/900 | Ctrl+C to quit
```

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-username/ascii-vision.git
cd ascii-vision
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

> **Windows users:** make sure you have a true-colour terminal such as [Windows Terminal](https://aka.ms/terminal) or VS Code's integrated terminal for `--color` mode.

### 3. Run

```bash
python ascii_vision.py video.mp4
```

---

## 📖 Usage

```
usage: ascii_vision.py [-h] [--width WIDTH] [--color | --no-color]
                        [--skip N] [--loop] [--info]
                        [video]
```

### Arguments

| Argument | Short | Description |
|---|---|---|
| `video` | — | Path to the video file (`mp4`, `avi`, `mkv`, …) |
| `--width` | `-w` | Output width in characters *(default: auto from terminal size)* |
| `--color` | `-c` | Enable 24-bit ANSI true colour |
| `--no-color` | — | Force grayscale mode *(default)* |
| `--skip N` | `-s` | Render every Nth frame — `--skip 2` halves the frame rate |
| `--loop` | `-l` | Loop the video until `Ctrl+C` |
| `--info` | `-i` | Print video metadata and exit without playing |
| `--help` | `-h` | Show help message |

### Examples

```bash
# Basic grayscale playback
python ascii_vision.py video.mp4

# True-colour, 100-char wide
python ascii_vision.py video.mp4 --color --width 100

# Fast mode: render every 2nd frame at 140 chars wide, loop forever
python ascii_vision.py video.mp4 --no-color --width 140 --skip 2 --loop

# Colour + frame skip for slower machines
python ascii_vision.py video.mp4 --color --skip 2 --width 80

# Show metadata only
python ascii_vision.py video.mp4 --info
```

---

## ⚙️ Performance Tips

| Scenario | Recommendation |
|---|---|
| Slow machine / large video | `--skip 2` or `--skip 3` + narrow `--width` |
| Fast machine, max quality | `--skip 1 --width 160` |
| Colour on slow machine | `--color --skip 2 --width 80` |
| Best grayscale quality | `--no-color --width 200` |

> Terminal font matters — monospace fonts like **Cascadia Code**, **Fira Code**, or **JetBrains Mono** produce sharper results.

---

## 🏗️ Architecture

The project is built with a clean OOP design, with each class owning a single responsibility:

```
ascii_vision.py
│
├── VideoInfo         — Immutable dataclass: fps, resolution, duration
├── AsciiConverter    — Frame → ASCII string (grayscale or 24-bit colour)
├── FrameDecoder      — Background thread: reads frames into a bounded queue
├── VideoPlayer       — Orchestrates decode → convert → render loop
└── CLI               — Argument parsing + interactive fallback
```

**Data flow:**

```
VideoCapture ──► FrameDecoder (thread) ──► Queue ──► VideoPlayer ──► stdout
                                                          │
                                                    AsciiConverter
```

---

## 📋 Requirements

- Python **3.9+**
- See [`requirements.txt`](requirements.txt) for Python packages

### Supported video formats

Any format supported by your local **OpenCV / FFmpeg** build:

| Format | Extension |
|---|---|
| MPEG-4 | `.mp4`, `.m4v` |
| AVI | `.avi` |
| Matroska | `.mkv` |
| QuickTime | `.mov` |
| WebM | `.webm` |
| And more… | depends on FFmpeg |

---

## 🪟 Windows Notes

- Run in **Windows Terminal** or **VS Code terminal** for ANSI support
- `--color` requires a true-colour terminal; legacy `cmd.exe` may not render colours correctly
- ANSI support is enabled automatically via `SetConsoleMode`

---

## 🐧 Linux / macOS Notes

- Works out of the box in any modern terminal emulator
- For best colour results use a terminal with 24-bit colour support (most do by default)

---

## 🤝 Contributing

Pull requests are welcome! Please open an issue first to discuss what you'd like to change.

1. Fork the repository
2. Create your feature branch: `git checkout -b feat/my-feature`
3. Commit your changes: `git commit -m 'feat: add my feature'`
4. Push to the branch: `git push origin feat/my-feature`
5. Open a Pull Request

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](LICENSE) for details.

---

<div align="center">
  Made with ♥ and a lot of <code>░▒▓█</code>
</div>
