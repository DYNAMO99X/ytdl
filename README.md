# ytdl — A Beautiful YouTube Downloader

> A powerful, user-friendly wrapper for **yt-dlp** with a beautiful CLI and an interactive TUI powered by Textual.

```
          __      ____
   __  __/ /_____/ / /
  / / / / __/ __  / / 
 / /_/ / /_/ /_/ / /  
 \__, /\__/\__,_/_/   
/____/                
```

## Features

| Feature | Description |
|---|---|
| 🎬 **Download Videos** | Best quality auto-merged to MP4 with a single command |
| 🎵 **Extract Audio** | MP3, FLAC, Opus, M4A, WAV and more, with quality control |
| 📋 **Playlist Support** | Full playlist download with item range selection |
| 🔍 **YouTube Search** | Search from CLI or TUI, browse results, pick and download |
| 📦 **Batch Downloads** | Process URLs from a text file |
| ⚡ **Custom Shortcuts** | Define your own command presets (e.g. `ytdl mp3 <url>`) |
| 🖥️ **Interactive TUI** | Full terminal UI with tabs, search, progress bars, and config |
| ⚙️ **Persistent Config** | Saves your preferences to `~/.config/ytdl/config.json` |
| 🚀 **Optimized** | Auto-configured to use Node.js for better YouTube extraction |

---

## Installation

### Prerequisites

- **Python 3.10+** — Runtime
- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — The download engine (already installed on your system)
- **[ffmpeg](https://ffmpeg.org/)** — For merging video/audio and audio conversion (already installed)
- **Node.js** — Recommended for YouTube extraction (already installed)

### Install ytdl

```bash
# Clone or cd into the project
cd ytdl

# Install dependencies
pip install -r requirements.txt

# Install ytdl in development mode
pip install -e .
```

### Verify

```bash
ytdl --version
# → ytdl v1.0.0
```

---

## Quick Start

```bash
# Download the best quality video (auto-merges to MP4)
ytdl download "https://youtube.com/watch?v=dQw4w9WgXcQ"

# Extract audio as MP3
ytdl audio "https://youtube.com/watch?v=dQw4w9WgXcQ"

# Search YouTube and pick what to download
ytdl search "rick astley never gonna give you up"

# View detailed video information
ytdl info "https://youtube.com/watch?v=dQw4w9WgXcQ"

# List all available formats
ytdl formats "https://youtube.com/watch?v=dQw4w9WgXcQ"

# Download a playlist
ytdl playlist "https://youtube.com/playlist?list=..."

# Launch the interactive TUI
ytdl tui

# Or just run `ytdl` with no arguments
ytdl
```

---

## CLI Reference

### `ytdl download <url>`

Download a video with best quality by default.

```bash
# Default (best quality)
ytdl download "https://youtube.com/watch?v=..."

# Pick a quality preset
ytdl download -q 1080 "https://youtube.com/watch?v=..."
ytdl download -q 720 "https://youtube.com/watch?v=..."
ytdl download -q 480 "https://youtube.com/watch?v=..."

# Custom format specification
ytdl download -f "bestvideo[height<=1080]+bestaudio/best[height<=1080]" <url>

# Download with subtitles and thumbnail
ytdl download -s -t "https://youtube.com/watch?v=..."

# Specify output directory
ytdl download -d ~/Videos "https://youtube.com/watch?v=..."

# Custom output template
ytdl download -o "%(channel)s/%(title)s.%(ext)s" <url>

# Rate limit (e.g. 5 MB/s)
ytdl download --limit-rate 5M "https://youtube.com/watch?v=..."

# Via a proxy
ytdl download --proxy "http://proxy:8080" <url>

# Extra yt-dlp flags
ytdl download -e "--write-description" "https://youtube.com/watch?v=..."
```

**Quality presets:**

| Preset | Format string |
|---|---|
| `best` | `bestvideo+bestaudio/best` |
| `2160` (4K) | `bestvideo[height<=2160]+bestaudio/best[height<=2160]` |
| `1440` (2K) | `bestvideo[height<=1440]+bestaudio/best[height<=1440]` |
| `1080` | `bestvideo[height<=1080]+bestaudio/best[height<=1080]` |
| `720` | `bestvideo[height<=720]+bestaudio/best[height<=720]` |
| `480` | `bestvideo[height<=480]+bestaudio/best[height<=480]` |
| `360` | `bestvideo[height<=360]+bestaudio/best[height<=360]` |

---

### `ytdl audio <url>`

Extract audio from a video.

```bash
# Default MP3 (best quality)
ytdl audio "https://youtube.com/watch?v=..."

# Choose format
ytdl audio -f flac "https://youtube.com/watch?v=..."
ytdl audio -f opus "https://youtube.com/watch?v=..."
ytdl audio -f m4a "https://youtube.com/watch?v=..."

# Adjust quality (0=best, 9=worst)
ytdl audio -q 5 "https://youtube.com/watch?v=..."

# Embed metadata and thumbnail
ytdl audio --embed-thumbnail "https://youtube.com/watch?v=..."
```

**Supported audio formats:** `mp3`, `m4a`, `opus`, `aac`, `flac`, `wav`

---

### `ytdl info <url>`

Display detailed video information in a beautiful Rich panel.

```bash
ytdl info "https://youtube.com/watch?v=..."

# JSON output for scripting
ytdl info -j "https://youtube.com/watch?v=..." | jq .
```

Shows: title, channel, duration, upload date, views, likes, categories, resolution, codecs, description, and more.

---

### `ytdl formats <url>`

List all available formats in a sortable table.

```bash
ytdl formats "https://youtube.com/watch?v=..."

# JSON output
ytdl formats -j "https://youtube.com/watch?v=..." | jq .
```

Each row shows: format ID, extension, resolution, file size, bitrate, video/audio codecs.

---

### `ytdl search <query>`

Search YouTube and select videos to download.

```bash
ytdl search "never gonna give you up"

# Limit results
ytdl search -n 5 "lofi hip hop"

# Auto-download after selection
ytdl search -d "chill jazz"

# Download as audio directly
ytdl search -a "podcast interview"

# With custom format
ytdl search -f "bestvideo[height<=1080]+bestaudio" "4k nature"

# Extra flags
ytdl search -e "--write-subs" "documentary"
```

---

### `ytdl playlist <url>`

Download an entire playlist.

```bash
# Download all videos
ytdl playlist "https://youtube.com/playlist?list=..."

# Specific range
ytdl playlist --items "1-5,7,10-" <url>

# Reverse order
ytdl playlist --reverse <url>

# Custom format
ytdl playlist -f "bestvideo[height<=1080]+bestaudio" <url>
```

---

### `ytdl batch <file>`

Download multiple URLs from a text file.

```bash
# File format (one URL per line, # for comments):
#   https://youtube.com/watch?v=abc123
#   https://youtube.com/watch?v=def456

ytdl batch urls.txt

# With custom format
ytdl batch -f "bestvideo+bestaudio" urls.txt
```

---

### `ytdl config`

Manage persistent configuration.

```bash
# Show current config
ytdl config show

# Open config file in editor
ytdl config show --edit

# Get a specific value
ytdl config get download_dir

# Set a value
ytdl config set download_dir ~/Music
ytdl config set audio_format flac
ytdl config set embed_metadata true
ytdl config set concurrent_fragments 10
ytdl config set proxy http://proxy:8080

# Reset to defaults
ytdl config reset

# Show config file path
ytdl config path
```

**Full config reference:**

| Key | Type | Default | Description |
|---|---|---|---|
| `download_dir` | string | `~/Downloads/ytdl` | Where to save downloads |
| `output_template` | string | `%(title)s [%(id)s].%(ext)s` | yt-dlp output template |
| `format` | string | `bestvideo+bestaudio/best` | Default video format |
| `audio_format` | string | `mp3` | Default audio format |
| `audio_quality` | int | `0` | Audio quality (0=best, 9=worst) |
| `subtitles` | bool | `false` | Download subtitles |
| `subtitles_lang` | string | `en` | Subtitle language |
| `thumbnails` | bool | `false` | Write thumbnail files |
| `embed_metadata` | bool | `true` | Embed metadata in file |
| `embed_thumbnail` | bool | `false` | Embed thumbnail in file |
| `concurrent_fragments` | int | `5` | Parallel fragment downloads |
| `retries` | int | `10` | Download retry count |
| `limit_rate` | string | `null` | Download speed limit (e.g. `5M`) |
| `proxy` | string | `null` | Proxy URL |
| `cookies_file` | string | `null` | Path to cookies file |

---

### `ytdl shortcut`

Create and manage custom command presets.

```bash
# Add a shortcut
ytdl shortcut add mp3 "--extract-audio --audio-format mp3 --audio-quality 0"
ytdl shortcut add 4k "-f 'bestvideo[height<=2160]+bestaudio/best[height<=2160]'"
ytdl shortcut add h264 "-f 'bestvideo[codec=h264]+bestaudio[codec=aac]/best'"

# List all shortcuts
ytdl shortcut list

# Run a shortcut
ytdl mp3 "https://youtube.com/watch?v=..."
ytdl 4k "https://youtube.com/watch?v=..."

# Run with extra flags
ytdl mp3 -e "--embed-thumbnail" "https://youtube.com/watch?v=..."

# Remove a shortcut
ytdl shortcut remove mp3

# Explicit run (useful if name conflicts)
ytdl shortcut run mp3 "https://youtube.com/watch?v=..."
```

**Note:** Shortcut names cannot conflict with built-in commands (`download`, `audio`, `playlist`, `info`, `formats`, `search`, `batch`, `config`, `shortcut`, `tui`).

---

### `ytdl tui`

Launch the interactive Terminal User Interface.

```bash
# Launch
ytdl tui

# Or just run `ytdl` with no arguments
ytdl
```

The TUI has four tabs:

| Tab | Features |
|---|---|
| **Search** | Search YouTube, browse results in a table, download video/audio, view details |
| **Downloads** | Track active and completed downloads |
| **Config** | Quick access to edit config file |
| **About** | Version info, paths, credits |

Keyboard shortcuts in the TUI:

| Key | Action |
|---|---|
| `F5` | Refresh current tab |
| `Ctrl+Q` | Quit |
| `↑/↓` | Navigate results |
| `Enter` | Select a result |
| `Tab` | Switch between tabs |

---

## Custom Shortcuts (Deep Dive)

Shortcuts are stored in your config file under `"shortcuts"`. They let you define named presets of yt-dlp flags that become first-class CLI commands.

### Example Use Cases

```bash
# Best quality audio as Opus
ytdl shortcut add opus "--extract-audio --audio-format opus --audio-quality 0"

# Download only 720p H.264 (for compatibility)
ytdl shortcut add h264-720 "-f 'bestvideo[height<=720][codec=h264]+bestaudio[codec=aac]/best'"

# Download with all metadata and thumbnails
ytdl shortcut add complete "--embed-metadata --embed-thumbnail --write-thumbnail --write-subs --sub-langs en"

# Download at 480p with a rate limit (for slow connections)
ytdl shortcut add slow "--limit-rate 1M -f 'bestvideo[height<=480]+bestaudio'"
```

Then use them:

```bash
ytdl opus "https://youtube.com/watch?v=..."
ytdl h264-720 "https://youtube.com/watch?v=..."
ytdl complete "https://youtube.com/watch?v=..."
ytdl slow "https://youtube.com/watch?v=..."
```

---

## Tips & Tricks

### Combine Shortcuts with Extra Flags

```bash
# Add thumbnail to your mp3 shortcut
ytdl mp3 -e "--embed-thumbnail" "https://youtube.com/watch?v=..."
```

### Use with `jq` for Scripting

```bash
# Get just the video title
ytdl info -j <url> | jq -r '.title'

# Get download URL for best audio
ytdl info -j <url> | jq -r '.url'
```

### Set a Default Download Directory

```bash
ytdl config set download_dir ~/Music/YouTube
```

### Organize by Channel

```bash
ytdl download -o "%(channel)s/%(title)s [%(id)s].%(ext)s" <url>
```

### Limit Bandwidth for Shared Connections

```bash
ytdl config set limit_rate 2M
```

### Proxy Support

```bash
ytdl config set proxy "socks5://127.0.0.1:1080"
```

---

## Requirements

| Dependency | Purpose |
|---|---|
| **yt-dlp** | Download engine (must be installed separately) |
| **Python 3.10+** | Runtime |
| **ffmpeg** | Video/audio merging and format conversion |
| **Node.js** | JavaScript runtime for YouTube extraction |

### Python Packages (installed automatically)

| Package | Purpose |
|---|---|
| `click>=8.0` | CLI framework |
| `rich>=13.0` | Beautiful terminal output |
| `textual>=8.0` | Interactive TUI framework |

---

## Project Structure

```
ytdl/
├── ytdl                      # Entry shell script
├── pyproject.toml            # Python package config
├── requirements.txt          # Dependencies
├── README.md                 # This file
├── .gitignore
└── src/
    └── ytdl/
        ├── __init__.py       # Package init, version
        ├── __main__.py       # python -m ytdl support
        ├── cli.py            # All CLI commands (Click-based)
        ├── tui.py            # Textual TUI application
        ├── core.py           # yt-dlp subprocess wrapper
        ├── display.py        # Rich formatting utilities
        ├── config.py         # JSON config file management
        └── shortcuts.py      # Custom shortcut system
```

---

## How It Works

ytdl is a **wrapper** around [yt-dlp](https://github.com/yt-dlp/yt-dlp), the best YouTube downloader available. It doesn't reinvent the wheel — it makes the wheel beautiful and easy to use.

- **CLI Commands** are built with `Click`, providing a clean, intuitive interface with helpful error messages.
- **Output Formatting** uses `Rich` to render tables, panels, and progress bars in the terminal.
- **Interactive TUI** is built with `Textual`, giving you a full-screen app with tabs, search, and real-time progress.
- **Configuration** is stored as JSON in `~/.config/ytdl/config.json` and can be edited manually or via commands.
- **Shortcuts** are dynamic Click commands registered at startup, allowing any set of yt-dlp flags to be invoked as a top-level subcommand.

---

## License

MIT — Use it, modify it, share it.
