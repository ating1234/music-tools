from pathlib import Path
import subprocess


def download_youtube_mp3(url: str, target_dir: Path) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    output_template = target_dir / "youtube.%(ext)s"
    command = [
        "yt-dlp",
        "--no-progress",
        "--no-playlist",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "0",
        "-o",
        str(output_template),
        url,
    ]
    subprocess.run(command, check=True, capture_output=True, text=True, stdin=subprocess.DEVNULL)

    mp3_files = sorted(target_dir.glob("*.mp3"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not mp3_files:
        raise RuntimeError("yt-dlp completed but no MP3 output was found")
    return mp3_files[0]
