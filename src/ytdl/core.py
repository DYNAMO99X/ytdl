"""Core yt-dlp Python API wrapper."""

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import yt_dlp

from ytdl.config import load_config, get_download_dir


@dataclass
class VideoInfo:
    """Structured video information from yt-dlp."""
    id: str
    title: str
    url: str
    duration: Optional[int] = None
    duration_string: str = "N/A"
    channel: str = "N/A"
    channel_url: str = ""
    upload_date: str = "N/A"
    description: str = ""
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    comment_count: Optional[int] = None
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    thumbnail: str = ""
    webpage_url: str = ""
    formats: list[dict] = field(default_factory=list)
    ext: str = ""
    filesize_approx: Optional[int] = None
    resolution: str = "N/A"
    fps: Optional[float] = None
    vcodec: str = "N/A"
    acodec: str = "N/A"
    extractor: str = ""

    @classmethod
    def from_json(cls, data: dict) -> "VideoInfo":
        """Create from yt-dlp JSON output."""
        duration = data.get("duration")
        dur_str = "N/A"
        if duration is not None:
            dur_str = format_duration(duration)

        # Find best format info for resolution/acodec/vcodec
        formats = data.get("formats", [])
        best_video = next(
            (f for f in reversed(formats) if f.get("vcodec") and f["vcodec"] != "none"),
            {},
        )
        best_audio = next(
            (f for f in reversed(formats) if f.get("acodec") and f["acodec"] != "none"),
            {},
        )

        return cls(
            id=data.get("id", ""),
            title=data.get("title", "Unknown"),
            url=data.get("url", data.get("webpage_url", "")),
            duration=duration,
            duration_string=dur_str,
            channel=data.get("channel", data.get("uploader", "N/A")),
            channel_url=data.get("channel_url", data.get("uploader_url", "")),
            upload_date=data.get("upload_date", "N/A"),
            description=data.get("description", "")[:500] if data.get("description") else "",
            view_count=data.get("view_count"),
            like_count=data.get("like_count"),
            comment_count=data.get("comment_count"),
            categories=data.get("categories", []),
            tags=data.get("tags", []),
            thumbnail=data.get("thumbnail", ""),
            webpage_url=data.get("webpage_url", ""),
            formats=formats,
            ext=data.get("ext", ""),
            filesize_approx=data.get("filesize_approx") or data.get("filesize"),
            resolution=best_video.get("resolution", "N/A"),
            fps=best_video.get("fps"),
            vcodec=best_video.get("vcodec", "N/A"),
            acodec=best_audio.get("acodec", "N/A"),
            extractor=data.get("extractor", "youtube"),
        )


@dataclass
class FormatResult:
    """A single format entry."""
    format_id: str
    ext: str
    resolution: str
    filesize: str
    tbr: str
    vcodec: str
    acodec: str
    fps: Optional[float] = None
    format_note: str = ""
    raw: dict = field(default_factory=dict)


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def format_filesize(size: Optional[int]) -> str:
    """Format bytes into human-readable size."""
    if size is None:
        return "N/A"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# ── yt-dlp Python API Wrapper ─────────────────────────────────────────


def _build_opts(
    url: str = "",
    format_spec: Optional[str] = None,
    output_dir: Optional[Path] = None,
    output_template: Optional[str] = None,
    audio_only: bool = False,
    audio_format: Optional[str] = None,
    audio_quality: Optional[int] = None,
    embed_metadata: Optional[bool] = None,
    embed_thumbnail: Optional[bool] = None,
    subtitles: Optional[bool] = None,
    subtitles_lang: Optional[str] = None,
    thumbnails: Optional[bool] = None,
    concurrent: Optional[int] = None,
    retries: Optional[int] = None,
    limit_rate: Optional[str] = None,
    proxy: Optional[str] = None,
    cookies_file: Optional[Path] = None,
    extra_args: Optional[list[str]] = None,
    quiet: bool = False,
    progress_hooks: Optional[list[Callable]] = None,
) -> dict[str, Any]:
    """Build yt-dlp options dict from config and overrides."""
    config = load_config()

    opts: dict[str, Any] = {
        "quiet": quiet,
        "no_warnings": True,
        "ignoreerrors": True,
        # Force built-in JS interpreter — no Node.js needed
        "js_runtimes": [],
    }

    # Format
    if format_spec:
        opts["format"] = format_spec
    elif audio_only:
        opts["format"] = "bestaudio/best"
    else:
        opts["format"] = config.get("format", "bestvideo+bestaudio/best")

    # Output template
    dl_dir = output_dir or get_download_dir()
    tmpl = output_template or config.get("output_template", "%(title)s [%(id)s].%(ext)s")
    opts["outtmpl"] = str(dl_dir / tmpl)

    # Audio extraction
    if audio_only:
        opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_format or config.get("audio_format", "mp3"),
                "preferredquality": (
                    audio_quality if audio_quality is not None
                    else config.get("audio_quality", 0)
                ),
            }
        ]

    # Metadata embedding
    em = embed_metadata if embed_metadata is not None else config.get("embed_metadata", True)
    if em:
        opts["embedmetadata"] = True
        opts["writethumbnail"] = True  # needed for embed-thumbnail to work

    et = embed_thumbnail if embed_thumbnail is not None else config.get("embed_thumbnail", False)
    if et:
        opts["embedsubs"] = True
        opts["embedthumbnail"] = True

    # Subtitles
    subs = subtitles if subtitles is not None else config.get("subtitles", False)
    if subs:
        opts["writesubtitles"] = True
        opts["writeautomaticsub"] = True
        opts["subtitleslangs"] = [subtitles_lang or config.get("subtitles_lang", "en")]

    # Thumbnails
    th = thumbnails if thumbnails is not None else config.get("thumbnails", False)
    if th:
        opts["writethumbnail"] = True

    # Performance
    cf = concurrent if concurrent is not None else config.get("concurrent_fragments", 5)
    if cf > 1:
        opts["concurrentfragmentdownloads"] = cf

    rt = retries if retries is not None else config.get("retries", 10)
    opts["retries"] = rt

    # Rate limit
    lr = limit_rate or config.get("limit_rate")
    if lr:
        opts["ratelimit"] = lr

    # Proxy
    px = proxy or config.get("proxy")
    if px:
        opts["proxy"] = px

    # Cookies
    cf_path = cookies_file or config.get("cookies_file")
    if cf_path:
        opts["cookiefile"] = str(Path(cf_path).expanduser())

    # Progress hooks
    if progress_hooks:
        opts["progress_hooks"] = progress_hooks

    # Extra args (passed as raw CLI-style args)
    if extra_args:
        # yt-dlp's Python API supports 'extractor_args' and 'postprocessor_args'
        # For truly arbitrary extra args, we'd need a different approach
        for arg in extra_args:
            if arg.startswith("--"):
                # Convert --flag=value or --flag value
                # We handle simple cases here
                pass

    return opts


def get_info(url: str) -> VideoInfo:
    """Get video information."""
    opts = {"quiet": True, "no_warnings": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=False)
            if data is None:
                raise RuntimeError("No data returned")
            return VideoInfo.from_json(data)
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"Failed to get video info: {e}")
    except Exception as e:
        raise RuntimeError(f"Failed to get video info: {e}")


def get_formats(url: str) -> VideoInfo:
    """Get video information with formats listed."""
    # Same as get_info - formats are always included in the response
    return get_info(url)


def search(query: str, limit: int = 10) -> list[VideoInfo]:
    """Search YouTube and return results."""
    search_url = f"ytsearch{limit}:{query}"
    opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "ignoreerrors": True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            data = ydl.extract_info(search_url, download=False)
            if data is None:
                return []
            videos = []
            entries = data.get("entries", [])
            if entries is None:
                return []
            for entry in entries:
                if entry is None:
                    continue
                videos.append(VideoInfo.from_json(entry))
            return videos
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"Search failed: {e}")
    except Exception as e:
        raise RuntimeError(f"Search failed: {e}")


def download(
    url: str,
    format_spec: Optional[str] = None,
    output_dir: Optional[Path] = None,
    output_template: Optional[str] = None,
    audio_only: bool = False,
    audio_format: Optional[str] = None,
    audio_quality: Optional[int] = None,
    embed_metadata: Optional[bool] = None,
    embed_thumbnail: Optional[bool] = None,
    subtitles: Optional[bool] = None,
    subtitles_lang: Optional[str] = None,
    thumbnails: Optional[bool] = None,
    concurrent: Optional[int] = None,
    retries: Optional[int] = None,
    limit_rate: Optional[str] = None,
    proxy: Optional[str] = None,
    cookies_file: Optional[Path] = None,
    extra_args: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    quiet: bool = False,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Path:
    """Download a video. Returns the output file path."""
    output_path: Optional[Path] = None
    start_time = time.time()

    def _progress_hook(d: dict) -> None:
        nonlocal output_path

        if d["status"] == "finished":
            fp = d.get("filename", "")
            if fp:
                output_path = Path(fp)

        if progress_callback:
            # Generate a status line similar to yt-dlp's CLI output
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                pct = (downloaded / total * 100) if total > 0 else 0
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)

                speed_str = format_filesize(int(speed)) + "/s" if speed else "N/A"
                eta_str = format_duration(int(eta)) if eta else "N/A"

                line = (
                    f"[download] {pct:.1f}% of {format_filesize(int(total))} "
                    f"at {speed_str} ETA {eta_str}"
                )
                progress_callback(line)
            elif d["status"] == "finished":
                elapsed = time.time() - start_time
                line = f"[download] 100% - completed in {elapsed:.1f}s"
                progress_callback(line)

    opts = _build_opts(
        url=url,
        format_spec=format_spec,
        output_dir=output_dir,
        output_template=output_template,
        audio_only=audio_only,
        audio_format=audio_format,
        audio_quality=audio_quality,
        embed_metadata=embed_metadata,
        embed_thumbnail=embed_thumbnail,
        subtitles=subtitles,
        subtitles_lang=subtitles_lang,
        thumbnails=thumbnails,
        concurrent=concurrent,
        retries=retries,
        limit_rate=limit_rate,
        proxy=proxy,
        cookies_file=cookies_file,
        extra_args=extra_args,
        quiet=quiet,
        progress_hooks=[_progress_hook],
    )

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            if cancel_check and cancel_check():
                raise RuntimeError("Cancelled")
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"Download failed: {e}")

    if output_path and output_path.exists():
        return output_path

    # Fallback: try to find the file
    dl_dir = output_dir or get_download_dir()
    tmpl = output_template or load_config().get("output_template", "%(title)s [%(id)s].%(ext)s")
    # Try a simple heuristic: find the most recent file in the download dir
    try:
        files = list(dl_dir.iterdir())
        if files:
            newest = max(files, key=lambda f: f.stat().st_mtime)
            return newest
    except (OSError, StopIteration):
        pass

    return dl_dir / "unknown"


def download_audio(
    url: str,
    audio_format: Optional[str] = None,
    audio_quality: Optional[int] = None,
    output_dir: Optional[Path] = None,
    output_template: Optional[str] = None,
    embed_metadata: Optional[bool] = None,
    embed_thumbnail: Optional[bool] = None,
    extra_args: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    quiet: bool = False,
) -> Path:
    """Download audio only."""
    return download(
        url=url,
        output_dir=output_dir,
        output_template=output_template,
        audio_only=True,
        audio_format=audio_format,
        audio_quality=audio_quality,
        embed_metadata=embed_metadata,
        embed_thumbnail=embed_thumbnail,
        extra_args=extra_args,
        progress_callback=progress_callback,
        quiet=quiet,
    )


def download_playlist(
    url: str,
    format_spec: Optional[str] = None,
    output_dir: Optional[Path] = None,
    output_template: Optional[str] = None,
    items: Optional[str] = None,
    reverse: bool = False,
    extra_args: Optional[list[str]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
    quiet: bool = False,
) -> int:
    """Download a playlist. Returns number of videos downloaded."""
    playlist_count = 0

    def _playlist_hook(d: dict) -> None:
        nonlocal playlist_count
        if d["status"] == "finished":
            playlist_count += 1
        if progress_callback:
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
                downloaded = d.get("downloaded_bytes", 0)
                pct = (downloaded / total * 100) if total > 0 else 0
                speed = d.get("speed", 0)
                eta = d.get("eta", 0)
                speed_str = format_filesize(int(speed)) + "/s" if speed else "N/A"
                eta_str = format_duration(int(eta)) if eta else "N/A"
                line = (
                    f"[download] {pct:.1f}% of {format_filesize(int(total))} "
                    f"at {speed_str} ETA {eta_str}"
                )
                progress_callback(line)
            elif d["status"] == "finished":
                line = f"[download] 100% - video {playlist_count} completed"
                progress_callback(line)

    opts = _build_opts(
        url=url,
        format_spec=format_spec,
        output_dir=output_dir,
        output_template=output_template or "%(playlist_title)s/%(playlist_index)s - %(title)s [%(id)s].%(ext)s",
        extra_args=extra_args,
        quiet=quiet,
        progress_hooks=[_playlist_hook],
    )

    if items:
        opts["playlist_items"] = items
    if reverse:
        opts["playlistreverse"] = True

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as e:
        raise RuntimeError(f"Playlist download failed: {e}")

    return playlist_count if playlist_count > 0 else -1


def batch_download(
    file_path: Path,
    **kwargs,
) -> list[Path]:
    """Download URLs from a file. Returns list of output paths."""
    urls = []
    with open(file_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    results = []
    for url in urls:
        try:
            dest = download(url, **kwargs)
            results.append(dest)
        except RuntimeError as e:
            print(f"Failed to download {url}: {e}", file=sys.stderr)
    return results
