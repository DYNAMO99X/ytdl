"""CLI commands for ytdl."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import click

from ytdl import __version__
from ytdl.config import DEFAULT_CONFIG, load_config, save_config, config_set, config_get, get_config_path, get_download_dir
from ytdl.core import (
    VideoInfo,
    batch_download,
    download,
    download_audio,
    download_playlist,
    format_filesize,
    get_formats,
    get_info,
    search,
)
from ytdl.display import (
    console,
    create_progress_bar,
    format_config_output,
    print_download_summary,
    print_error,
    print_info,
    print_shortcuts,
    print_success,
    print_video_info,
    print_formats,
    print_search_results,
    print_warning,
)
from ytdl.shortcuts import add_shortcut, get_shortcut_flags, list_shortcuts, remove_shortcut


class NaturalOrderGroup(click.Group):
    """Click group that preserves command order and supports dynamic commands."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._dynamic_commands = {}

    def list_commands(self, ctx):
        """Return commands in insertion order, builtins first, then shortcuts."""
        builtins = super().list_commands(ctx)
        shortcuts = sorted(self._dynamic_commands.keys())
        return builtins + shortcuts

    def get_command(self, ctx, name):
        """Try built-in command first, then dynamic shortcut, then fallback."""
        cmd = super().get_command(ctx, name)
        if cmd is not None:
            return cmd
        # Check if it's a shortcut
        flags = get_shortcut_flags(name)
        if flags:
            return self._make_shortcut_command(name, flags)
        return None

    def _make_shortcut_command(self, name: str, flags: str):
        """Create a dynamic Click command for a shortcut."""
        @click.command(name=name, help=f"Run shortcut '{name}' (flags: {flags})")
        @click.argument("url")
        @click.option("--extra", "-e", help="Extra yt-dlp flags to append")
        @click.option("--audio", "-x", is_flag=True, help="Extract audio")
        @click.option("--output-dir", "-d", help="Output directory")
        @click.pass_context
        def shortcut_cmd(ctx, url, extra, audio, output_dir):
            """Execute a custom shortcut."""
            # Build the download args
            extra_args = []
            if extra:
                extra_args = extra.split()

            shortcut_flags = flags.split()
            extra_args = shortcut_flags + extra_args

            try:
                with console.status(f"[bold green]Downloading via '{name}'...") as status:
                    dest = download(
                        url=url,
                        extra_args=extra_args,
                        output_dir=Path(output_dir) if output_dir else None,
                        quiet=False,
                    )
                print_download_summary(url, dest)
            except RuntimeError as e:
                print_error(str(e))
                sys.exit(1)

        return shortcut_cmd


def _register_shortcuts(group: NaturalOrderGroup):
    """Register all configured shortcuts as Click commands."""
    shortcuts = list_shortcuts()
    for name, flags in shortcuts.items():
        cmd = group._make_shortcut_command(name, flags)
        group._dynamic_commands[name] = cmd


@click.group(cls=NaturalOrderGroup, invoke_without_command=True)
@click.option("--version", "-V", is_flag=True, help="Show version and exit")
@click.pass_context
def cli(ctx, version):
    """ytdl — A beautiful YouTube downloader wrapper for yt-dlp.

    If no command is given, launches the interactive TUI.
    """
    if version:
        console.print(f"[bold]ytdl[/bold] v{__version__}")
        ctx.exit()

    if ctx.invoked_subcommand is None:
        # No command given — launch TUI
        ctx.invoke(tui_cmd)


# ── Download ──────────────────────────────────────────────────────────

@cli.command("download")
@click.argument("url")
@click.option("-f", "--format", "format_spec", help="Format code (e.g., 'bestvideo+bestaudio')")
@click.option("-o", "--output", "output_template", help="Output filename template")
@click.option("-d", "--output-dir", type=click.Path(), help="Download directory")
@click.option("-s", "--subtitles", is_flag=True, help="Download subtitles")
@click.option("-t", "--thumbnail", is_flag=True, help="Write thumbnail")
@click.option("-q", "--quality", type=click.Choice(["best", "2160", "1440", "1080", "720", "480", "360"]),
              help="Video quality preset")
@click.option("--embed-metadata/--no-embed-metadata", default=None, help="Embed metadata")
@click.option("--embed-thumbnail", is_flag=True, help="Embed thumbnail in file")
@click.option("--proxy", help="Proxy URL")
@click.option("--limit-rate", help="Download rate limit (e.g. '5M')")
@click.option("--extra", "-e", help="Extra yt-dlp flags")
def download_cmd(url, format_spec, output_template, output_dir, subtitles,
                 thumbnail, quality, embed_metadata, embed_thumbnail, proxy,
                 limit_rate, extra):
    """Download a video from YouTube.

    By default, downloads the best quality video+audio and merges to MP4.
    """
    # Resolve quality presets to format specs
    if quality and not format_spec:
        quality_map = {
            "best": "bestvideo+bestaudio/best",
            "2160": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
            "1440": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
            "1080": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720": "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "480": "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "360": "bestvideo[height<=360]+bestaudio/best[height<=360]",
        }
        format_spec = quality_map[quality]

    extra_args = extra.split() if extra else None

    try:
        with create_progress_bar(transient=False) as progress:
            progress.add_task("Downloading", total=None)
            dest = download(
                url=url,
                format_spec=format_spec,
                output_template=output_template,
                output_dir=Path(output_dir) if output_dir else None,
                subtitles=subtitles,
                thumbnails=thumbnail,
                embed_metadata=embed_metadata,
                embed_thumbnail=embed_thumbnail,
                proxy=proxy,
                limit_rate=limit_rate,
                extra_args=extra_args,
                quiet=True,
            )
        print_download_summary(url, dest)
    except RuntimeError as e:
        print_error(str(e))
        sys.exit(1)


# ── Audio ─────────────────────────────────────────────────────────────

@cli.command("audio")
@click.argument("url")
@click.option("-f", "--audio-format", type=click.Choice(["mp3", "m4a", "opus", "aac", "flac", "wav"]),
              help="Audio format (default: mp3)")
@click.option("-q", "--quality", type=int, default=None, help="Audio quality (0=best, 9=worst)")
@click.option("-o", "--output", "output_template", help="Output filename template")
@click.option("-d", "--output-dir", type=click.Path(), help="Download directory")
@click.option("--embed-metadata/--no-embed-metadata", default=None, help="Embed metadata")
@click.option("--embed-thumbnail", is_flag=True, help="Embed thumbnail in file")
@click.option("--extra", "-e", help="Extra yt-dlp flags")
def audio_cmd(url, audio_format, quality, output_template, output_dir,
              embed_metadata, embed_thumbnail, extra):
    """Extract audio from a video (default: MP3)."""
    extra_args = extra.split() if extra else None

    try:
        with create_progress_bar(transient=False) as progress:
            task = progress.add_task("Extracting audio", total=None)
            dest = download_audio(
                url=url,
                audio_format=audio_format,
                audio_quality=quality,
                output_template=output_template,
                output_dir=Path(output_dir) if output_dir else None,
                embed_metadata=embed_metadata,
                embed_thumbnail=embed_thumbnail,
                extra_args=extra_args,
                quiet=True,
            )
        print_download_summary(url, dest)
    except RuntimeError as e:
        print_error(str(e))
        sys.exit(1)


# ── Playlist ──────────────────────────────────────────────────────────

@cli.command("playlist")
@click.argument("url")
@click.option("-f", "--format", "format_spec", help="Format code")
@click.option("--items", help="Item range (e.g. '1-5,7,10-')")
@click.option("--reverse", is_flag=True, help="Download in reverse order")
@click.option("-o", "--output", "output_template", help="Output template")
@click.option("-d", "--output-dir", type=click.Path(), help="Download directory")
@click.option("--extra", "-e", help="Extra yt-dlp flags")
def playlist_cmd(url, format_spec, items, reverse, output_template, output_dir, extra):
    """Download an entire playlist."""
    extra_args = extra.split() if extra else None

    try:
        with console.status("[bold green]Downloading playlist..."):
            count = download_playlist(
                url=url,
                format_spec=format_spec,
                output_template=output_template,
                output_dir=Path(output_dir) if output_dir else None,
                items=items,
                reverse=reverse,
                extra_args=extra_args,
                quiet=True,
            )
        if count >= 0:
            print_success(f"Playlist download complete. {count} video(s) downloaded.")
        else:
            print_success("Playlist download complete.")
    except RuntimeError as e:
        print_error(str(e))
        sys.exit(1)


# ── Info ──────────────────────────────────────────────────────────────

@cli.command("info")
@click.argument("url")
@click.option("-j", "--json", "as_json", is_flag=True, help="Output as JSON")
def info_cmd(url, as_json):
    """Show detailed video information."""
    try:
        with console.status("[bold blue]Fetching video info..."):
            info = get_info(url)
        if as_json:
            import json
            console.print(json.dumps(info.__dict__, indent=2, default=str))
        else:
            print_video_info(info)
    except RuntimeError as e:
        print_error(str(e))
        sys.exit(1)


# ── Formats ───────────────────────────────────────────────────────────

@cli.command("formats")
@click.argument("url")
@click.option("-j", "--json", "as_json", is_flag=True, help="Output as JSON")
def formats_cmd(url, as_json):
    """List all available formats for a video."""
    try:
        with console.status("[bold blue]Fetching formats..."):
            info = get_formats(url)
        if as_json:
            import json
            console.print(json.dumps(info.formats, indent=2, default=str))
        else:
            print_formats(info)
    except RuntimeError as e:
        print_error(str(e))
        sys.exit(1)


# ── Search ────────────────────────────────────────────────────────────

@cli.command("search")
@click.argument("query", nargs=-1, required=True)
@click.option("-n", "--count", default=10, help="Number of results (max 50)")
@click.option("-d", "--download", "do_download", is_flag=True, help="Download after selecting")
@click.option("-a", "--audio", "audio_only", is_flag=True, help="Download as audio")
@click.option("-f", "--format", "format_spec", help="Format code")
@click.option("--extra", "-e", help="Extra yt-dlp flags")
def search_cmd(query, count, do_download, audio_only, format_spec, extra):
    """Search YouTube for videos."""
    query_str = " ".join(query)
    extra_args = extra.split() if extra else None

    try:
        with console.status("[bold green]Searching..."):
            results = search(query_str, limit=count)

        if not results:
            print_error("No results found.")
            sys.exit(1)

        print_search_results(results)

        # If --download flag is set, prompt for selection
        if do_download and results:
            click.echo()
            choice = click.prompt(
                "Enter number to download (or 0 to cancel)",
                type=click.IntRange(0, len(results)),
                default=0,
            )
            if choice > 0:
                selected = results[choice - 1]
                video_url = selected.webpage_url or f"https://www.youtube.com/watch?v={selected.id}"
                click.echo()
                print_info(f"Downloading: {selected.title}")

                if audio_only:
                    dest = download_audio(
                        url=video_url,
                        extra_args=extra_args,
                        quiet=False,
                    )
                else:
                    dest = download(
                        url=video_url,
                        format_spec=format_spec,
                        extra_args=extra_args,
                        quiet=False,
                    )
                print_download_summary(selected.title, dest)

    except RuntimeError as e:
        print_error(str(e))
        sys.exit(1)


# ── Batch ─────────────────────────────────────────────────────────────

@cli.command("batch")
@click.argument("file", type=click.Path(exists=True))
@click.option("-f", "--format", "format_spec", help="Format code")
@click.option("--extra", "-e", help="Extra yt-dlp flags")
def batch_cmd(file, format_spec, extra):
    """Download URLs from a text file (one URL per line, # for comments)."""
    extra_args = extra.split() if extra else None

    try:
        with console.status("[bold green]Processing batch file..."):
            results = batch_download(
                file_path=Path(file),
                format_spec=format_spec,
                extra_args=extra_args,
            )

        print_success(f"Batch complete. {len(results)} video(s) downloaded.")
        for path in results:
            console.print(f"  [cyan]{path}[/cyan]")

    except RuntimeError as e:
        print_error(str(e))
        sys.exit(1)


# ── Config ────────────────────────────────────────────────────────────

@cli.group("config")
def config_group():
    """Manage configuration."""
    pass


@config_group.command("show")
@click.option("--edit", is_flag=True, help="Open config in default editor")
def config_show(edit):
    """Show current configuration."""
    if edit:
        config_path = get_config_path()
        if not config_path.exists():
            save_config(load_config())
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "nano"))
        subprocess.call([editor, str(config_path)])
        return

    config = load_config()
    shortcuts = config.pop("shortcuts", {})
    table = format_config_output(config)
    console.print(table)

    if shortcuts:
        console.print()
        print_shortcuts(shortcuts)


@config_group.command("set")
@click.argument("key")
@click.argument("value")
def config_set_cmd(key, value):
    """Set a configuration value.

    Supported keys:
    \b
    download_dir      Download directory path
    output_template   Output filename template
    format            Default video format
    audio_format      Default audio format (mp3, m4a, opus, etc.)
    audio_quality     Audio quality (0=best, 9=worst)
    embed_metadata    true/false
    embed_thumbnail   true/false
    subtitles         true/false
    thumbnails        true/false
    concurrent_fragments  Number of concurrent fragments
    retries           Number of retries
    limit_rate        Rate limit (e.g. '5M')
    proxy             Proxy URL
    cookies_file      Path to cookies file
    """
    config_set(key, value)
    print_success(f"Set [bold]{key}[/bold] = [cyan]{value}[/cyan]")


@config_group.command("get")
@click.argument("key")
def config_get_cmd(key):
    """Get a configuration value."""
    value = config_get(key)
    if value is None:
        print_error(f"Key '{key}' not found in config")
        sys.exit(1)
    console.print(value)


@config_group.command("path")
def config_path_cmd():
    """Show the config file path."""
    console.print(str(get_config_path()))


@config_group.command("reset")
@click.confirmation_option(prompt="Reset all configuration to defaults?")
def config_reset():
    """Reset configuration to defaults."""
    save_config(DEFAULT_CONFIG.copy())
    print_success("Configuration reset to defaults.")


# ── Shortcut ──────────────────────────────────────────────────────────

@cli.group("shortcut")
def shortcut_group():
    """Manage custom shortcut commands."""
    pass


@shortcut_group.command("list")
def shortcut_list_cmd():
    """List all defined shortcuts."""
    shortcuts = list_shortcuts()
    print_shortcuts(shortcuts)


@shortcut_group.command("add", context_settings=dict(ignore_unknown_options=True))
@click.argument("name")
@click.argument("flags", nargs=-1, required=True)
def shortcut_add_cmd(name, flags):
    """Add a shortcut command.

    Put the flags in quotes so they're treated as one argument.

    Examples:

        ytdl shortcut add mp3 "--extract-audio --audio-format mp3"

        ytdl shortcut add 4k "-f bestvideo[height<=2160]+bestaudio/best[height<=2160]"
    """
    flags_str = " ".join(flags)
    try:
        add_shortcut(name, flags_str)
        print_success(f"Shortcut '[bold]{name}[/bold]' added: [dim]{flags_str}[/dim]")
        print_info(f"Use it with: [bold]ytdl {name} <url>[/bold]")
    except ValueError as e:
        print_error(str(e))
        sys.exit(1)


@shortcut_group.command("remove")
@click.argument("name")
def shortcut_remove_cmd(name):
    """Remove a shortcut."""
    if remove_shortcut(name):
        print_success(f"Shortcut '[bold]{name}[/bold]' removed.")
    else:
        print_error(f"Shortcut '[bold]{name}[/bold]' not found.")
        sys.exit(1)


@shortcut_group.command("run")
@click.argument("name")
@click.argument("url")
@click.option("--extra", "-e", help="Extra yt-dlp flags to append")
def shortcut_run_cmd(name, url, extra):
    """Run a shortcut on a URL explicitly."""
    flags = get_shortcut_flags(name)
    if flags is None:
        print_error(f"Shortcut '[bold]{name}[/bold]' not found.")
        print_info("Available shortcuts: " + ", ".join(list_shortcuts().keys()))
        sys.exit(1)

    extra_args = []
    if extra:
        extra_args = extra.split()

    all_args = flags.split() + extra_args

    try:
        with console.status(f"[bold green]Running shortcut '{name}'..."):
            dest = download(
                url=url,
                extra_args=all_args,
                quiet=False,
            )
        print_download_summary(url, dest)
    except RuntimeError as e:
        print_error(str(e))
        sys.exit(1)


# ── TUI ───────────────────────────────────────────────────────────────

@cli.command("tui")
def tui_cmd():
    """Launch the interactive Textual TUI."""
    try:
        from ytdl.tui import YtdlApp
        app = YtdlApp()
        app.run()
    except ImportError as e:
        print_error(f"Failed to start TUI: {e}")
        print_info("Make sure textual is installed: pip install textual")
        sys.exit(1)
    except Exception as e:
        print_error(f"TUI error: {e}")
        sys.exit(1)


# Register dynamic shortcut commands on startup
_register_shortcuts(cli)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
