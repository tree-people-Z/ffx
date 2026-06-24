import subprocess
import json
from pathlib import Path

_cache: dict[str, dict] = {}


def find_ffprobe():
    candidates = ["ffprobe", "ffprobe.exe"]
    for c in candidates:
        try:
            result = subprocess.run([c, "-version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    extra_paths = [
        r"C:\ffmpeg\bin\ffprobe.exe",
        r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
    ]
    for p in extra_paths:
        if Path(p).exists():
            return str(Path(p))

    return None


def probe_file(file_path: str) -> dict:
    if file_path in _cache:
        return _cache[file_path]

    ffprobe = find_ffprobe()
    if not ffprobe:
        result = _probe_basic(file_path)
        _cache[file_path] = result
        return result

    try:
        proc = subprocess.run(
            [ffprobe, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", file_path],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            result = _probe_basic(file_path)
            _cache[file_path] = result
            return result

        data = json.loads(proc.stdout)
        info = _parse_ffprobe_output(data, file_path)
        _cache[file_path] = info
        return info
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError, ValueError):
        result = _probe_basic(file_path)
        _cache[file_path] = result
        return result


def _parse_ffprobe_output(data: dict, file_path: str) -> dict:
    streams = []
    for s in data.get("streams", []):
        streams.append({
            "index": s.get("index"),
            "codec_type": s.get("codec_type"),
            "codec_name": s.get("codec_name"),
            "width": s.get("width"),
            "height": s.get("height"),
            "bit_rate": int(s.get("bit_rate", 0) or 0),
            "frame_rate": _parse_frame_rate(s),
            "pix_fmt": s.get("pix_fmt"),
            "channels": s.get("channels"),
            "sample_rate": s.get("sample_rate"),
        })

    fmt = data.get("format", {})
    duration_str = fmt.get("duration", "0")
    try:
        duration = float(duration_str)
    except (ValueError, TypeError):
        duration = 0

    size_str = fmt.get("size", "0")
    try:
        size = int(size_str)
    except (ValueError, TypeError):
        size = 0

    return {
        "path": file_path,
        "duration": duration,
        "size": size,
        "streams": streams,
    }


def _parse_frame_rate(stream: dict) -> float:
    r = stream.get("r_frame_rate", "0/1")
    try:
        num, den = r.split("/")
        return float(num) / float(den) if float(den) != 0 else 0
    except (ValueError, ZeroDivisionError):
        return 0


def _probe_basic(file_path: str) -> dict:
    path = Path(file_path)
    size = path.stat().st_size if path.exists() else 0
    return {
        "path": file_path,
        "duration": 0,
        "size": size,
        "streams": [],
    }
