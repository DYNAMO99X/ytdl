"""Core yt-dlp subprocess wrapper."""

import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

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


def _run_ytdlp(args: list[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """Run yt-dlp with given args and return result."""
    cmd = ["yt-dlp"] + args
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp timed out")
    except FileNotFoundError:
        raise RuntimeError(
            "yt-dlp not found. Please install it: https://github.com/yt-dlp/yt-dlp"
        )


def get_info(url: str) -> VideoInfo:
    """Get video information."""
    args = [
        "--dump-json",
        "--no-download",
        "--no-warnings",
        url,
    ]
    result = _run_ytdlp(args, timeout=60)
    if result.returncode != 0:
        error = result.stderr.strip() or "Unknown error"
        raise RuntimeError(f"Failed to get video info: {error}")

    try:
        data = json.loads(result.stdout.strip().splitlines()[0])
        return VideoInfo.from_json(data)
    except (json.JSONDecodeError, IndexError) as e:
        raise RuntimeError(f"Failed to parse video info: {e}")


def get_formats(url: str) -> VideoInfo:
    """Get video information with formats listed."""
    args = [
        "--dump-json",
        "--no-download",
        "--no-warnings",
        url,
    ]
    result = _run_ytdlp(args, timeout=60)
    if result.returncode != 0:
        error = result.stderr.strip() or "Unknown error"
        raise RuntimeError(f"Failed to get formats: {error}")

    try:
        data = json.loads(result.stdout.strip().splitlines()[0])
        return VideoInfo.from_json(data)
    except (json.JSONDecodeError, IndexError) as e:
        raise RuntimeError(f"Failed to parse formats: {e}")


def search(query: str, limit: int = 10) -> list[VideoInfo]:
    """Search YouTube and return results."""
    search_url = f"ytsearch{limit}:{query}"
    args = [
        "--dump-json",
        "--no-download",
        "--no-warnings",
        "--flat-playlist",
        search_url,
    ]
    result = _run_ytdlp(args, timeout=60)
    if result.returncode != 0:
        error = result.stderr.strip() or "Unknown error"
        raise RuntimeError(f"Search failed: {error}")

    videos = []
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        try:
            data = json.loads(line)
            videos.append(VideoInfo.from_json(data))
        except json.JSONDecodeError:
            continue
    return videos


def _build_download_args(
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
    quiet: bool = False,
) -> list[str]:
    """Build the argument list for yt-dlp download."""
    config = load_config()
    args = []

    # Always download the best quality available
    if format_spec:
        args.extend(["-f", format_spec])
    elif audio_only:
        args.extend(["-f", "bestaudio/best"])
    else:
        args.extend(["-f", config.get("format", "bestvideo+bestaudio/best")])

    # Output
    dl_dir = output_dir or get_download_dir()
    tmpl = output_template or config.get("output_template", "%(title)s [%(id)s].%(ext)s")
    args.extend(["-o", str(dl_dir / tmpl)])

    # Audio extraction
    if audio_only:
        args.append("-x")
        af = audio_format or config.get("audio_format", "mp3")
        args.extend(["--audio-format", af])
        aq = audio_quality if audio_quality is not None else config.get("audio_quality", 0)
        args.extend(["--audio-quality", str(aq)])

    # Metadata
    em = embed_metadata if embed_metadata is not None else config.get("embed_metadata", True)
    if em:
        args.append("--embed-metadata")

    et = embed_thumbnail if embed_thumbnail is not None else config.get("embed_thumbnail", False)
    if et:
        args.append("--embed-thumbnail")

    # Subtitles
    subs = subtitles if subtitles is not None else config.get("subtitles", False)
    if subs:
        args.append("--write-subs")
        args.append("--write-auto-subs")
        sl = subtitles_lang or config.get("subtitles_lang", "en")
        args.extend(["--sub-langs", sl])

    # Thumbnails
    th = thumbnails if thumbnails is not None else config.get("thumbnails", False)
    if th:
        args.append("--write-thumbnail")

    # Performance
    cf = concurrent if concurrent is not None else config.get("concurrent_fragments", 5)
    if cf > 1:
        args.extend(["--concurrent-fragments", str(cf)])

    rt = retries if retries is not None else config.get("retries", 10)
    args.extend(["--retries", str(rt)])

    # Rate limit
    lr = limit_rate or config.get("limit_rate")
    if lr:
        args.extend(["--limit-rate", lr])

    # Proxy
    px = proxy or config.get("proxy")
    if px:
        args.extend(["--proxy", px])

    # Cookies
    cf_path = cookies_file or config.get("cookies_file")
    if cf_path:
        args.extend(["--cookies", str(Path(cf_path).expanduser())])

    # Extra user-provided args
    if extra_args:
        args.extend(extra_args)

    if quiet:
        args.append("--quiet")

    # Add URL last
    args.append(url)

    return args


def download(
    url: str,
    format_spec: Optional[str] = None,
    output_dir: Optional[Path] = None,
    output_template: Optional[str] = None,
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
) -> Path:
    """Download a video. Returns the output file path."""
    args = _build_download_args(
        url=url,
        format_spec=format_spec,
        output_dir=output_dir,
        output_template=output_template,
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
    )

    # If we have a progress callback, stream output
    if progress_callback:
        cmd = ["yt-dlp"] + args
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        output_lines = []
        for line in process.stdout or []:
            line = line.rstrip()
            output_lines.append(line)
            progress_callback(line)

        process.wait()
        if process.returncode != 0:
            error = "\n".join(output_lines[-5:])
            raise RuntimeError(f"Download failed:\n{error}")

        # Try to extract the output file path from yt-dlp output
        dest_path = _extract_output_path(output_lines, url)
        return dest_path
    else:
        result = _run_ytdlp(args)
        if result.returncode != 0:
            error = result.stderr.strip() or "Unknown error"
            raise RuntimeError(f"Download failed: {error}")

        # Extract output file path
        stdout = result.stdout or ""
        dest_path = _extract_output_path(stdout.splitlines(), url)
        return dest_path


def _extract_output_path(lines: list[str], url: str) -> Path:
    """Extract the output file path from yt-dlp output."""
    # Look for "Destination:" or "[Merger] Merging..." or final output path
    for line in lines:
        if "Destination:" in line:
            path = line.split("Destination:")[-1].strip()
            if path:
                return Path(path)

    # Look for any line ending with .mp4, .mkv, .webm, .mp3, .m4a etc
    ext_pattern = re.compile(r'\.(mp4|mkv|webm|mp3|m4a|opus|flac|wav)$')
    for line in reversed(lines):
        parts = line.strip().split()
        for part in parts:
            if ext_pattern.search(part):
                return Path(part)

    # Fallback: return download dir with a generic name
    config = load_config()
    dl_dir = get_download_dir()
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
    args = _build_download_args(
        url=url,
        format_spec=format_spec,
        output_dir=output_dir,
        output_template=output_template or "%(playlist_title)s/%(playlist_index)s - %(title)s [%(id)s].%(ext)s",
        extra_args=extra_args,
        quiet=quiet,
    )

    if items:
        args.extend(["--playlist-items", items])
    if reverse:
        args.append("--playlist-reverse")

    if progress_callback:
        cmd = ["yt-dlp"] + args
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        count = 0
        for line in process.stdout or []:
            line = line.rstrip()
            progress_callback(line)
            if "[download] Downloading video" in line:
                count += 1
        process.wait()
        if process.returncode != 0:
            raise RuntimeError("Playlist download failed")
        return count if count > 0 else -1
    else:
        result = _run_ytdlp(args)
        if result.returncode != 0:
            raise RuntimeError(f"Playlist download failed: {result.stderr.strip()}")
        # Count downloaded videos
        count = 0
        for line in (result.stdout or "").splitlines():
            if "[download] Downloading video" in line:
                count += 1
        return count if count > 0 else -1


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
