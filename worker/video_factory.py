"""Local YouTube video production helpers for AI House Studio.

This module creates original videos from researched scripts, licensed Pexels footage,
locally generated narration, captions, and FFmpeg editing. It never downloads YouTube
videos or reuses another creator's assets.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path
import httpx

PEXELS_API = "https://api.pexels.com/videos/search"
TIMEOUT = 45


class VideoFactoryError(RuntimeError):
    pass


def _pexels_key():
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        raise VideoFactoryError("PEXELS_API_KEY is not configured in worker/.env")
    return key


def _inside(root, path):
    root = Path(root).resolve()
    path = Path(path).expanduser().resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise VideoFactoryError("All production assets must stay inside the project workspace")
    return path


def search_pexels(query, per_page=5, orientation="landscape"):
    query = str(query or "").strip()
    if not query:
        raise VideoFactoryError("A visual search query is required")
    per_page = max(1, min(15, int(per_page)))
    if orientation not in ("landscape", "portrait", "square"):
        raise VideoFactoryError("orientation must be landscape, portrait, or square")
    response = httpx.get(
        PEXELS_API,
        headers={"Authorization": _pexels_key()},
        params={"query": query[:160], "per_page": per_page, "orientation": orientation},
        timeout=TIMEOUT,
    )
    if response.is_error:
        raise VideoFactoryError("Pexels search failed (" + str(response.status_code) + ")")
    payload = response.json()
    items = []
    for video in payload.get("videos", []):
        files = [f for f in video.get("video_files", []) if f.get("link")]
        if not files:
            continue
        # Prefer HD MP4 with a sensible frame size; avoid tiny previews.
        files.sort(key=lambda f: (f.get("file_type") == "video/mp4", int(f.get("width") or 0), int(f.get("height") or 0)), reverse=True)
        file = files[0]
        items.append({
            "id": video.get("id"),
            "duration": video.get("duration"),
            "width": file.get("width"),
            "height": file.get("height"),
            "url": file.get("link"),
            "photographer": video.get("user", {}).get("name", ""),
            "pexels_page": video.get("url", ""),
            "query": query,
        })
    return items


def download_clip(asset, project_dir, filename):
    root = Path(project_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    target = _inside(root, root / Path(filename).name)
    url = str(asset.get("url", ""))
    if not url.startswith("https://videos.pexels.com/"):
        raise VideoFactoryError("Only direct Pexels video asset URLs are accepted")
    with httpx.stream("GET", url, timeout=120, follow_redirects=True) as response:
        if response.is_error:
            raise VideoFactoryError("Pexels clip download failed (" + str(response.status_code) + ")")
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("video/") and "octet-stream" not in content_type:
            raise VideoFactoryError("Pexels returned a non-video asset")
        with target.open("wb") as out:
            for chunk in response.iter_bytes(1024 * 1024):
                out.write(chunk)
    if not target.is_file() or target.stat().st_size < 1024:
        target.unlink(missing_ok=True)
        raise VideoFactoryError("Downloaded video clip is empty or incomplete")
    return target


def create_voiceover(script, output_path, voice="en-US-AndrewNeural"):
    script = str(script or "").strip()
    if not script:
        raise VideoFactoryError("Narration script is empty")
    if not shutil.which("ffmpeg"):
        raise VideoFactoryError("FFmpeg must be installed and available on PATH")
    target = Path(output_path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [os.environ.get("AI_HOUSE_PYTHON", "python"), "-m", "edge_tts",
             "--voice", str(voice)[:80], "--text", script[:50000],
             "--write-media", str(target)],
            check=True, timeout=600, capture_output=True, text=True,
        )
    except FileNotFoundError as exc:
        raise VideoFactoryError("Install edge-tts with: pip install -r worker/requirements.txt") from exc
    except subprocess.CalledProcessError as exc:
        raise VideoFactoryError("Voice generation failed: " + (exc.stderr or "")[:500]) from exc
    if not target.is_file() or target.stat().st_size == 0:
        raise VideoFactoryError("Voice generation produced no audio file")
    return target


def render_video(project_dir, clips, narration_path, output_path, subtitles_path=None,
                 music_path=None, aspect="16:9"):
    root = Path(project_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    narration = _inside(root, narration_path)
    output = _inside(root, output_path)
    if not narration.is_file():
        raise VideoFactoryError("Narration audio file does not exist")
    if not clips or len(clips) > 80:
        raise VideoFactoryError("Provide between 1 and 80 scene clips")
    if aspect not in ("16:9", "9:16", "1:1"):
        raise VideoFactoryError("aspect must be 16:9, 9:16, or 1:1")
    if not shutil.which("ffmpeg"):
        raise VideoFactoryError("FFmpeg must be installed and available on PATH")
    width, height = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}[aspect]
    safe_clips = []
    for item in clips:
        path = _inside(root, item.get("path", ""))
        if not path.is_file():
            raise VideoFactoryError("Scene clip is missing: " + path.name)
        duration = float(item.get("duration", 6))
        if not 1 <= duration <= 60:
            raise VideoFactoryError("Scene duration must be between 1 and 60 seconds")
        safe_clips.append((path, duration))
    inputs = []
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for path, _ in safe_clips:
        cmd += ["-i", str(path)]
    narration_index = len(safe_clips)
    cmd += ["-i", str(narration)]
    music_index = None
    if music_path:
        music = _inside(root, music_path)
        if not music.is_file():
            raise VideoFactoryError("Background music file does not exist")
        music_index = narration_index + 1
        cmd += ["-i", str(music)]
    filters = []
    concat_inputs = []
    for index, (path, duration) in enumerate(safe_clips):
        filters.append(
            f"[{index}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,fps=30,trim=duration={duration},"
            f"setpts=PTS-STARTPTS,format=yuv420p[v{index}]"
        )
        concat_inputs.append(f"[v{index}]")
    filters.append("".join(concat_inputs) + f"concat=n={len(safe_clips)}:v=1:a=0[vbase]")
    video_label = "vbase"
    if subtitles_path:
        subtitles = _inside(root, subtitles_path)
        if not subtitles.is_file():
            raise VideoFactoryError("Subtitle file does not exist")
        # Escape characters for FFmpeg's filter parser; subprocess is not shell-based.
        sub = str(subtitles).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        filters.append(f"[vbase]subtitles='{sub}':force_style='FontName=Arial,FontSize=26,Outline=2,Shadow=1,Alignment=2,MarginV=55'[vsub]")
        video_label = "vsub"
    audio_label = f"{narration_index}:a"
    if music_index is not None:
        filters.append(f"[{narration_index}:a]volume=1.0[narr]")
        filters.append(f"[{music_index}:a]volume=0.12,aloop=loop=-1:size=2e+09[bed]")
        filters.append("[narr][bed]amix=inputs=2:duration=first:dropout_transition=2, loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
        audio_label = "aout"
    else:
        filters.append(f"[{narration_index}:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
        audio_label = "aout"
    cmd += ["-filter_complex", ";".join(filters), "-map", f"[{video_label}]", "-map", f"[{audio_label}]",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output)]
    try:
        subprocess.run(cmd, check=True, timeout=3600, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise VideoFactoryError("FFmpeg render failed: " + (exc.stderr or "")[-1200:]) from exc
    if not output.is_file() or output.stat().st_size == 0:
        raise VideoFactoryError("FFmpeg produced no video")
    return {"path": output.relative_to(root).as_posix(), "bytes": output.stat().st_size, "aspect": aspect, "scene_count": len(safe_clips)}


def write_credits(project_dir, assets, filename="asset_credits.json"):
    root = Path(project_dir).resolve()
    path = _inside(root, root / filename)
    clean = []
    for asset in assets:
        clean.append({key: str(asset.get(key, ""))[:500] for key in ("id", "photographer", "pexels_page", "query")})
    path.write_text(json.dumps({"provider": "Pexels", "assets": clean}, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
