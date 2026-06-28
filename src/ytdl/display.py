"""Rich display utilities for CLI output."""

import re
from pathlib import Path
from typing import Optional

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text

from ytdl.core import FormatResult, VideoInfo, format_duration, format_filesize

console = Console()


def print_video_info(info: VideoInfo) -> None:
    """Display detailed video information in a rich panel."""
    title = Text(info.title, style="bold yellow", no_wrap=False)
    panel = Panel(
        _build_info_content(info),
        title=title,
        title_align="left",
        border_style="blue",
        padding=(1, 2),
    )
    console.print(panel)


def _build_info_content(info: VideoInfo) -> Table:
    """Build the info table content."""
    table = Table(show_header=False, box=box.SIMPLE, padding=(0, 2))
    table.add_column("Key", style="cyan", width=14)
    table.add_column("Value", style="white")

    table.add_row("URL", info.webpage_url or info.url)
    table.add_row("Channel", info.channel)
    table.add_row("Duration", info.duration_string)

    if info.upload_date and info.upload_date != "N/A":
        date_str = f"{info.upload_date[:4]}-{info.upload_date[4:6]}-{info.upload_date[6:]}"
        table.add_row("Uploaded", date_str)

    if info.view_count is not None:
        table.add_row("Views", f"{info.view_count:,}")

    if info.like_count is not None:
        table.add_row("Likes", f"{info.like_count:,}")

    if info.categories:
        table.add_row("Categories", ", ".join(info.categories))

    if info.filesize_approx:
        table.add_row("Size", format_filesize(info.filesize_approx))

    if info.resolution and info.resolution != "N/A":
        fps_str = f" @ {info.fps}fps" if info.fps else ""
        table.add_row("Resolution", f"{info.resolution}{fps_str}")

    table.add_row("Video Codec", info.vcodec)
    table.add_row("Audio Codec", info.acodec)
    table.add_row("Extractor", info.extractor)

    if info.description:
        desc = info.description[:300] + ("..." if len(info.description) > 300 else "")
        table.add_row("Description", Text(desc, style="dim italic", no_wrap=False))

    return table


def print_formats(info: VideoInfo) -> None:
    """Display available formats in a table."""
    if not info.formats:
        console.print("[yellow]No format information available.[/yellow]")
        return

    # Filter out storyboard and other non-downloadable formats
    real_formats = [f for f in info.formats if f.get("vcodec") != "none" or f.get("acodec") != "none"]

    # Also include format_note to show useful info
    table = Table(
        title=f"Available Formats — [bold yellow]{info.title}[/bold yellow]",
        box=box.ROUNDED,
        border_style="blue",
        header_style="bold cyan",
    )
    table.add_column("ID", style="yellow", width=8)
    table.add_column("Ext", width=6)
    table.add_column("Resolution", width=14)
    table.add_column("Size", width=10)
    table.add_column("Bitrate", width=10)
    table.add_column("Video Codec", width=12)
    table.add_column("Audio Codec", width=12)
    table.add_column("Note", width=20)

    for fmt in real_formats:
        fmt_id = fmt.get("format_id", "?")
        ext = fmt.get("ext", "?")
        res = fmt.get("resolution") or fmt.get("format_note", "") or "N/A"
        size = format_filesize(fmt.get("filesize") or fmt.get("filesize_approx"))
        tbr = f'{fmt.get("tbr", "?")}k' if fmt.get("tbr") else "?"
        vcodec = fmt.get("vcodec", "?") or "?"
        acodec = fmt.get("acodec", "?") or "?"
        note = fmt.get("format_note", "") or ""

        table.add_row(
            fmt_id,
            ext,
            str(res),
            size,
            tbr,
            vcodec,
            acodec,
            note,
        )

    console.print(table)


def print_search_results(results: list[VideoInfo]) -> None:
    """Display search results in a numbered table."""
    table = Table(
        title="Search Results",
        box=box.ROUNDED,
        border_style="green",
        header_style="bold green",
    )
    table.add_column("#", style="yellow", width=4)
    table.add_column("Title", width=60)
    table.add_column("Duration", width=10)
    table.add_column("Channel", width=25)

    for i, video in enumerate(results, 1):
        table.add_row(
            str(i),
            Text(video.title, no_wrap=False),
            video.duration_string,
            video.channel,
        )

    console.print(table)


def print_download_summary(title: str, filepath: Path) -> None:
    """Display download success message."""
    size = filepath.stat().st_size if filepath.exists() else 0
    console.print()
    console.print(
        Panel(
            f"[bold green]✓[/bold green] [bold]{title}[/bold]\n"
            f"  [dim]Saved to:[/dim] [cyan]{filepath}[/cyan]\n"
            f"  [dim]Size:[/dim] [cyan]{format_filesize(size)}[/cyan]",
            title="Download Complete",
            border_style="green",
            padding=(1, 2),
        )
    )


def print_error(message: str) -> None:
    """Display an error message."""
    console.print(f"[bold red]✗ Error:[/bold red] {message}")


def print_warning(message: str) -> None:
    """Display a warning message."""
    console.print(f"[bold yellow]⚠ Warning:[/bold yellow] {message}")


def print_success(message: str) -> None:
    """Display a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_info(message: str) -> None:
    """Display an info message."""
    console.print(f"[bold blue]ℹ[/bold blue] {message}")


def create_progress_bar(transient: bool = True) -> Progress:
    """Create a rich progress bar for downloads."""
    return Progress(
        TextColumn("[bold blue]{task.fields[name]}", justify="left"),
        BarColumn(bar_width=None),
        "[progress.percentage]{task.percentage:>3.1f}%",
        "•",
        DownloadColumn(),
        "•",
        TransferSpeedColumn(),
        "•",
        TimeRemainingColumn(),
        transient=transient,
        expand=True,
    )


def format_config_output(config: dict) -> Table:
    """Format configuration for display."""
    table = Table(
        title="Configuration",
        box=box.ROUNDED,
        border_style="blue",
        header_style="bold cyan",
    )
    table.add_column("Key", style="yellow", width=25)
    table.add_column("Value", style="white", width=60)

    for key, value in config.items():
        if key == "shortcuts":
            continue  # Display separately
        val_str = str(value) if value is not None else "[dim]not set[/dim]"
        if isinstance(value, bool):
            val_str = "[green]true[/green]" if value else "[red]false[/red]"
        table.add_row(key, val_str)

    return table


def print_shortcuts(shortcuts: dict[str, str]) -> None:
    """Display stored shortcuts."""
    if not shortcuts:
        console.print("[yellow]No shortcuts defined.[/yellow]")
        console.print("  Add one: [bold]ytdl shortcut add <name> <yt-dlp-flags>[/bold]")
        return

    table = Table(
        title="Custom Shortcuts",
        box=box.ROUNDED,
        border_style="magenta",
        header_style="bold magenta",
    )
    table.add_column("Name", style="yellow", width=15)
    table.add_column("Flags", style="white", width=80)

    for name, flags in sorted(shortcuts.items()):
        table.add_row(name, flags)

    console.print(table)
