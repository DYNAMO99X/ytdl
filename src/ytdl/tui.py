"""Textual-based TUI for ytdl."""

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from textual import work
from textual.css.query import NoMatches
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
)

from ytdl import __version__
from ytdl.config import config_set, get_config_path, load_config, save_config, get_download_dir
from ytdl.core import (
    VideoInfo,
    download,
    download_audio,
    format_filesize,
    get_info,
    search,
)


# ── Data Models ───────────────────────────────────────────────────────

@dataclass
class DownloadTask:
    """Represents a download in progress or completed."""
    id: str
    title: str
    url: str
    status: str = "queued"  # queued, downloading, completed, failed
    progress: float = 0.0
    speed: str = ""
    eta: str = ""
    filesize: str = ""
    filepath: Optional[Path] = None
    error: str = ""
    is_audio: bool = False
    start_time: float = field(default_factory=time.time)


# ── Progress Parser ───────────────────────────────────────────────────

PROGRESS_RE = re.compile(
    r'\[download\]\s+([\d.]+)%\s+of\s+~?([\d.]+[KMG]?i?B)'
    r'(?:\s+at\s+([\d.]+[KMG]?i?B/s))?'
    r'(?:\s+ETA\s+(\S+))?'
)

FFMPEG_RE = re.compile(r'\[ffmpeg\]')
DESTINATION_RE = re.compile(r'Destination:\s+(.+)')
MERGING_RE = re.compile(r'Merging formats into\s+"(.+)"')


def parse_progress_line(line: str) -> Optional[dict]:
    """Parse a yt-dlp progress line and return a dict with progress info."""
    m = PROGRESS_RE.search(line)
    if m:
        return {
            "percent": float(m.group(1)),
            "filesize": m.group(2) or "",
            "speed": m.group(3) or "",
            "eta": m.group(4) or "",
        }
    return None


def parse_destination_line(line: str) -> Optional[str]:
    """Extract file path from yt-dlp output."""
    m = DESTINATION_RE.search(line)
    if m:
        return m.group(1).strip()
    m = MERGING_RE.search(line)
    if m:
        return m.group(1).strip()
    return None


# ── Search Result Screen ──────────────────────────────────────────────

class SearchResultScreen(Screen):
    """Screen showing detailed info about a search result."""

    def __init__(self, video: VideoInfo, results_list: list[VideoInfo], idx: int):
        super().__init__()
        self.video = video
        self.results = results_list
        self.idx = idx

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static(f"[bold yellow]{self.video.title}[/bold yellow]", id="result-title"),
            Static(f"Channel: {self.video.channel}", id="result-channel"),
            Static(f"Duration: {self.video.duration_string}", id="result-duration"),
            Static(f"Views: {self.video.view_count:,}" if self.video.view_count else "", id="result-views"),
            Static(f"URL: {self.video.webpage_url or self.video.url}", id="result-url"),
            Static(f"Description:", classes="section-label"),
            Static(self.video.description[:500] if self.video.description else "No description", id="result-desc"),
            Horizontal(
                Button("Download Video", variant="primary", id="dl-video"),
                Button("Download Audio", variant="success", id="dl-audio"),
                Button("Back", variant="default", id="back"),
                classes="button-row",
            ),
            id="result-container",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "dl-video":
            self._start_download(audio=False)
        elif event.button.id == "dl-audio":
            self._start_download(audio=True)
        elif event.button.id == "back":
            self.dismiss()

    def _start_download(self, audio: bool = False):
        url = self.video.webpage_url or f"https://www.youtube.com/watch?v={self.video.id}"
        self.app.push_screen(DownloadScreen(url, title=self.video.title, audio_only=audio))


# ── Download Screen ──────────────────────────────────────────────────

class DownloadScreen(Screen):
    """Screen showing a single download progress."""

    def __init__(self, url: str, title: str = "", audio_only: bool = False):
        super().__init__()
        self.url = url
        self.video_title = title
        self.audio_only = audio_only
        self.dl_task = DownloadTask(id=url, title=title or url, url=url, is_audio=audio_only)
        self._cancelled = False

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static(f"[bold]Downloading:[/bold] {self.dl_task.title}", id="dl-title", shrink=True),
            ProgressBar(total=100, show_eta=True, id="dl-progress"),
            Horizontal(
                Static("", id="dl-speed"),
                Static("", id="dl-eta"),
                classes="dl-info-row",
            ),
            Static("", id="dl-status"),
            RichLog(id="dl-log", highlight=True, max_lines=20),
            Horizontal(
                Button("Cancel", variant="error", id="cancel"),
                Button("Back", variant="default", id="back"),
                classes="button-row",
            ),
            id="dl-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._start_download()

    def _start_download(self):
        self._run_download()

    @work(thread=True)
    def _run_download(self):
        """Run the download in a background thread."""
        config = load_config()

        self.post_message(self.ProgressMsg("download", 0, "", "Starting..."))

        try:
            last_percent = -1

            def _progress(line: str) -> None:
                nonlocal last_percent
                # Parse progress from generated line
                progress = parse_progress_line(line)
                if progress:
                    pct = progress["percent"]
                    if int(pct) != int(last_percent):
                        last_percent = pct
                        speed = progress.get("speed", "")
                        eta = progress.get("eta", "")
                        self.post_message(self.ProgressMsg("download", pct, speed, eta))
                # Parse destination
                dest = parse_destination_line(line)
                if dest:
                    self.dl_task.filepath = Path(dest)
                self.post_message(self.LogMsg(line))

            dest = download(
                url=self.url,
                audio_only=self.audio_only,
                progress_callback=_progress,
                cancel_check=lambda: self._cancelled,
                quiet=True,
            )

            if self._cancelled:
                self.post_message(self.ProgressMsg("cancelled", 0, "", "Cancelled"))
            else:
                self.dl_task.filepath = dest
                self.post_message(self.ProgressMsg("completed", 100, "", "Complete!"))

        except Exception as e:
            self.post_message(self.ProgressMsg("failed", 0, "", f"Error: {str(e)}"))
            self.post_message(self.LogMsg(f"[red]Error: {str(e)}[/red]"))

    class ProgressMsg(Message):
        def __init__(self, status: str, percent: float, speed: str, eta: str):
            super().__init__()
            self.status = status
            self.percent = percent
            self.speed = speed
            self.eta = eta

    class LogMsg(Message):
        def __init__(self, line: str):
            super().__init__()
            self.line = line

    def on_download_screen_progress_msg(self, event: ProgressMsg) -> None:
        """Handle progress update message."""
        status = event.status
        self.dl_task.status = status
        self.dl_task.progress = event.percent
        self.dl_task.speed = event.speed
        self.dl_task.eta = event.eta

        progress_bar = self.query_one("#dl-progress", ProgressBar)
        speed_w = self.query_one("#dl-speed", Static)
        eta_w = self.query_one("#dl-eta", Static)
        status_w = self.query_one("#dl-status", Static)

        if status == "download":
            progress_bar.progress = event.percent
            speed_w.update(f"Speed: {event.speed}" if event.speed else "")
            eta_w.update(f"ETA: {event.eta}" if event.eta else "")
            status_w.update(f"[blue]Downloading... {event.percent:.1f}%[/blue]")
        elif status == "completed":
            progress_bar.progress = 100
            speed_w.update("")
            eta_w.update("")
            status_w.update("[bold green]✓ Download Complete![/bold green]")
            self._update_downloads_list()
        elif status == "failed":
            status_w.update(f"[bold red]✗ {event.eta}[/bold red]")
        elif status == "cancelled":
            status_w.update("[bold yellow]✗ Cancelled[/bold yellow]")

    def _update_downloads_list(self):
        """Notify the main screen about completed download."""
        try:
            main_screen = self.app.get_screen("main")
            if main_screen and hasattr(main_screen, 'add_completed_download'):
                main_screen.add_completed_download(self.dl_task)
        except Exception:
            pass

    def on_download_screen_log_msg(self, event: LogMsg) -> None:
        """Handle log line message."""
        log = self.query_one("#dl-log", RichLog)
        log.write(event.line)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self._cancelled = True
            if self._process:
                self._process.kill()
            self.dl_task.status = "cancelled"
        elif event.button.id == "back":
            if self._process and self._process.poll() is None:
                self._cancelled = True
                self._process.kill()
            self.dismiss()


# ── Config Screen ─────────────────────────────────────────────────────

class ConfigScreen(Screen):
    """Screen for viewing and editing configuration."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("[bold]Configuration[/bold]", classes="section-title"),
            TabbedContent(id="config-tabs"),
            Horizontal(
                Button("Save", variant="primary", id="save-config"),
                Button("Reset", variant="error", id="reset-config"),
                Button("Back", variant="default", id="back"),
                classes="button-row",
            ),
            id="config-container",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._load_config_into_tabs()

    def _load_config_into_tabs(self):
        config = load_config()

        # Build tab content
        general_rows = []
        for key in ["download_dir", "output_template", "subtitles", "subtitles_lang", "thumbnails", "embed_metadata", "embed_thumbnail"]:
            val = config.get(key)
            general_rows.append(self._make_config_row(key, val))

        formats_rows = []
        for key in ["format", "audio_format", "audio_quality"]:
            val = config.get(key)
            formats_rows.append(self._make_config_row(key, val))

        advanced_rows = []
        for key in ["concurrent_fragments", "retries", "limit_rate", "proxy", "cookies_file"]:
            val = config.get(key)
            advanced_rows.append(self._make_config_row(key, val))

        # Clear existing tabs and mount new ones
        tabs = self.query_one("#config-tabs", TabbedContent)
        tabs.remove_children()
        tabs.mount(
            TabPane("General", id="config-general", *general_rows),
            TabPane("Formats", id="config-formats", *formats_rows),
            TabPane("Advanced", id="config-advanced", *advanced_rows),
        )

    def _make_config_row(self, key: str, value) -> Container:
        val_str = str(value) if value is not None else ""
        return Container(
            Static(f"  {key}:", classes="config-key"),
            Input(value=val_str, id=f"cfg-{key}", classes="config-input"),
            classes="config-row",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-config":
            self._save_config()
        elif event.button.id == "reset-config":
            from ytdl.config import DEFAULT_CONFIG
            save_config(DEFAULT_CONFIG.copy())
            self._load_config_into_tabs()
            self.notify("Config reset to defaults", severity="warning")
        elif event.button.id == "back":
            self.dismiss()

    def _save_config(self):
        """Read all input fields and save config."""
        config = load_config()
        # Only iterate keys that have corresponding Input widgets
        config_keys = [
            "download_dir", "output_template",
            "subtitles", "subtitles_lang", "thumbnails",
            "embed_metadata", "embed_thumbnail",
            "format", "audio_format", "audio_quality",
            "concurrent_fragments", "retries",
            "limit_rate", "proxy", "cookies_file",
        ]
        for key in config_keys:
            try:
                widget = self.query_one(f"#cfg-{key}", Input)
            except NoMatches:
                continue
            val = widget.value
            if val.lower() in ("true", "false"):
                config[key] = val.lower() == "true"
            elif val.isdigit():
                config[key] = int(val)
            elif val == "" or val == "None":
                config[key] = None
            else:
                config[key] = val

        save_config(config)
        self.notify("Configuration saved!", severity="information")


# ── About Screen ──────────────────────────────────────────────────────

class AboutScreen(Screen):
    """About screen."""

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("[bold yellow]ytdl[/bold yellow]", id="about-title"),
            Static(f"Version {__version__}", id="about-version"),
            Static("A beautiful YouTube downloader wrapper for yt-dlp"),
            Static(""),
            Static("Powered by:"),
            Static("  • yt-dlp - The best YouTube downloader"),
            Static("  • Textual - Modern TUI framework"),
            Static("  • Rich - Beautiful terminal formatting"),
            Static("  • Click - CLI framework"),
            Static(""),
            Static(f"Config: {get_config_path()}"),
            Static(f"Download dir: {get_download_dir()}"),
            Static(""),
            Button("Back", variant="default", id="back"),
            id="about-container",
        )
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "back":
            self.dismiss()


# ── Main Screen ───────────────────────────────────────────────────────

class MainScreen(Screen):
    """Main screen with tabbed interface."""

    BINDINGS = [
        ("ctrl+q", "quit", "Quit"),
        ("f5", "refresh_search", "Refresh"),
    ]

    def __init__(self):
        super().__init__()
        self.search_results: list[VideoInfo] = []
        self.completed_downloads: list[DownloadTask] = []

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(initial="tab-search"):
            with TabPane("Search", id="tab-search"):
                yield Horizontal(
                    Input(placeholder="Search YouTube...", id="search-input"),
                    Button("Search", variant="primary", id="search-btn"),
                    Button("Clear", variant="default", id="clear-btn"),
                    classes="search-row",
                )
                yield DataTable(id="search-results")
                yield Horizontal(
                    Button("Download Video", variant="primary", id="dl-video-btn", disabled=True),
                    Button("Download Audio", variant="success", id="dl-audio-btn", disabled=True),
                    Button("View Info", variant="default", id="info-btn", disabled=True),
                    classes="button-row",
                )
            with TabPane("Downloads", id="tab-downloads"):
                yield Static("[bold]Downloads[/bold]", classes="section-title")
                yield ListView(id="downloads-list")
                yield Horizontal(
                    Button("Clear Completed", variant="default", id="clear-completed"),
                    classes="button-row",
                )
            with TabPane("Config", id="tab-config"):
                yield Static("[bold]Configuration[/bold]", classes="section-title")
                yield Vertical(
                    Static(id="cfg-dl-dir"),
                    Static(id="cfg-output-tmpl"),
                    Static(id="cfg-format"),
                    Static(id="cfg-audio"),
                    id="config-summary",
                )
                yield Button("Open Config Editor", variant="primary", id="open-config-editor")
            with TabPane("About", id="tab-about"):
                yield Static("[bold yellow]ytdl[/bold yellow]", id="about-title")
                yield Static(f"Version {__version__}")
                yield Static("")
                yield Static("A beautiful YouTube downloader wrapper for yt-dlp")
                yield Static("")
                yield Static("[dim]Powered by:[/dim]")
                yield Static("  • yt-dlp")
                yield Static("  • Textual")
                yield Static("  • Rich")
                yield Static("  • Click")
                yield Static("")
                yield Static(f"[dim]Config:[/dim] {get_config_path()}")
                yield Static(f"[dim]Downloads:[/dim] {get_download_dir()}")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#search-results", DataTable)
        table.add_columns("#", "Title", "Duration", "Channel", "Views")
        table.cursor_type = "row"
        table.zebra_stripes = True
        self._refresh_config_summary()

    def _refresh_config_summary(self):
        """Update the config tab summary with current values."""
        config = load_config()
        try:
            self.query_one("#cfg-dl-dir", Static).update(
                f"[bold]Download dir:[/bold] {config['download_dir']}"
            )
            self.query_one("#cfg-output-tmpl", Static).update(
                f"[bold]Output template:[/bold] {config['output_template']}"
            )
            self.query_one("#cfg-format", Static).update(
                f"[bold]Default format:[/bold] {config.get('format', 'bestvideo+bestaudio/best')}"
            )
            audio_fmt = config.get("audio_format", "mp3")
            audio_q = config.get("audio_quality", 0)
            self.query_one("#cfg-audio", Static).update(
                f"[bold]Audio:[/bold] {audio_fmt} (quality {audio_q})"
            )
        except NoMatches:
            pass

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "search-input":
            self._do_search()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        if btn_id == "search-btn":
            self._do_search()
        elif btn_id == "clear-btn":
            self._clear_search()
        elif btn_id == "dl-video-btn":
            self._download_selected(audio=False)
        elif btn_id == "dl-audio-btn":
            self._download_selected(audio=True)
        elif btn_id == "info-btn":
            self._show_selected_info()
        elif btn_id == "clear-completed":
            self.completed_downloads.clear()
            self._refresh_downloads_list()
        elif btn_id == "open-config-editor":
            self.app.push_screen(ConfigScreen())

    def _do_search(self):
        input_w = self.query_one("#search-input", Input)
        query = input_w.value.strip()
        if not query:
            self.notify("Enter a search query", severity="warning")
            return

        self.notify(f"Searching for '{query}'...")
        self._run_search(query)

    @work(thread=True)
    def _run_search(self, query: str):
        """Run search in a background thread."""
        try:
            results = search(query, limit=20)
            self.post_message(self.SearchResultsMsg(results))
        except Exception as e:
            self.post_message(self.SearchErrorMsg(str(e)))

    class SearchResultsMsg(Message):
        def __init__(self, results: list[VideoInfo]):
            super().__init__()
            self.results = results

    class SearchErrorMsg(Message):
        def __init__(self, error: str):
            super().__init__()
            self.error = error

    def on_main_screen_search_results_msg(self, event: SearchResultsMsg) -> None:
        self.search_results = event.results
        table = self.query_one("#search-results", DataTable)
        table.clear()

        for i, video in enumerate(event.results, 1):
            views = f"{video.view_count:,}" if video.view_count else "N/A"
            table.add_row(
                str(i),
                video.title,
                video.duration_string,
                video.channel,
                views,
            )

        # Enable action buttons
        self.query_one("#dl-video-btn", Button).disabled = False
        self.query_one("#dl-audio-btn", Button).disabled = False
        self.query_one("#info-btn", Button).disabled = False

        self.notify(f"Found {len(event.results)} results", severity="information")

    def on_main_screen_search_error_msg(self, event: SearchErrorMsg) -> None:
        self.notify(f"Search failed: {event.error}", severity="error")

    def _clear_search(self):
        self.search_results = []
        self.query_one("#search-input", Input).value = ""
        self.query_one("#search-results", DataTable).clear()
        self.query_one("#dl-video-btn", Button).disabled = True
        self.query_one("#dl-audio-btn", Button).disabled = True
        self.query_one("#info-btn", Button).disabled = True

    def _get_selected_video(self) -> Optional[VideoInfo]:
        table = self.query_one("#search-results", DataTable)
        cursor = table.cursor_coordinate
        if cursor is None:
            return None
        row = cursor.row
        if 0 <= row < len(self.search_results):
            return self.search_results[row]
        return None

    def _download_selected(self, audio: bool = False):
        video = self._get_selected_video()
        if video is None:
            self.notify("Select a video first", severity="warning")
            return

        url = video.webpage_url or f"https://www.youtube.com/watch?v={video.id}"
        self.app.push_screen(DownloadScreen(url, title=video.title, audio_only=audio))

    def _show_selected_info(self):
        video = self._get_selected_video()
        if video is None:
            return
        self.app.push_screen(SearchResultScreen(video, self.search_results, 0))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Enable buttons when a row is selected."""
        if event.cursor_row is not None:
            self.query_one("#dl-video-btn", Button).disabled = False
            self.query_one("#dl-audio-btn", Button).disabled = False
            self.query_one("#info-btn", Button).disabled = False

    def add_completed_download(self, task: DownloadTask):
        """Called from DownloadScreen when download completes."""
        self.completed_downloads.append(task)
        self._refresh_downloads_list()

    def _refresh_downloads_list(self):
        list_view = self.query_one("#downloads-list", ListView)
        list_view.clear()

        # Show completed
        for dl in reversed(self.completed_downloads):
            status_icon = "[green]✓[/green]" if dl.status == "completed" else "[red]✗[/red]"
            title = dl.title[:60] + "..." if len(dl.title) > 60 else dl.title
            fp = f" at {dl.filepath}" if dl.filepath else ""
            item = ListItem(
                Static(f"{status_icon} {title}{fp}")
            )
            list_view.append(item)

    # ── Tab Navigation ──

    def action_refresh_search(self) -> None:
        """F5 - Refresh current tab."""
        tab_content = self.query_one(TabbedContent)
        active = tab_content.active
        if active == "tab-search":
            self._do_search()
        elif active == "tab-downloads":
            self._refresh_downloads_list()


# ── Main App ──────────────────────────────────────────────────────────

class YtdlApp(App):
    """Main ytdl TUI application."""

    TITLE = "ytdl - YouTube Downloader"
    SUB_TITLE = f"v{__version__}"

    CSS = """
    Screen {
        background: $surface;
    }

    MainScreen > TabbedContent {
        height: 1fr;
    }

    .search-row {
        height: 3;
        margin: 1 0;
    }

    #search-input {
        width: 1fr;
        margin-right: 1;
    }

    #search-btn, #clear-btn {
        width: 16;
    }

    #search-results {
        height: 1fr;
    }

    .button-row {
        height: 3;
        margin: 1 0;
        align: center middle;
    }

    .button-row Button {
        margin: 0 1;
    }

    .section-title {
        text-style: bold;
        padding: 1 0;
    }

    #dl-title {
        padding: 1 0;
    }

    #dl-progress {
        margin: 1 0;
    }

    .dl-info-row {
        height: 1;
    }

    #dl-speed, #dl-eta {
        width: 1fr;
    }

    #dl-log {
        height: 1fr;
        border: solid $primary;
        margin: 1 0;
    }

    #downloads-list {
        height: 1fr;
    }

    #about-title {
        text-style: bold;
    }

    TabPane {
        padding: 1 2;
    }

    #config-container {
        padding: 1 2;
        max-width: 80;
    }

    .config-row {
        height: 3;
        layout: horizontal;
    }

    .config-key {
        width: 24;
        padding: 0 1;
        text-style: bold;
    }

    .config-input {
        width: 1fr;
    }

    #config-summary {
        margin: 1 0;
        padding: 1;
        border: solid $primary;
    }
    """

    def on_mount(self) -> None:
        """Called when app is mounted."""
        self.push_screen(MainScreen())
