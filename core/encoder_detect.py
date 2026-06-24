import subprocess
import re
from pathlib import Path

HW_PATTERNS = {
    "nvenc": ["h264_nvenc", "hevc_nvenc"],
    "qsv": ["h264_qsv", "hevc_qsv"],
    "amf": ["h264_amf", "hevc_amf"],
    "videotoolbox": ["h264_videotoolbox", "hevc_videotoolbox"],
}


def find_ffmpeg():
    candidates = ["ffmpeg", "ffmpeg.exe"]
    for c in candidates:
        try:
            result = subprocess.run([c, "-version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return c
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    extra_paths = [
        r"C:\ffmpeg\bin\ffmpeg.exe",
        r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
    ]
    for p in extra_paths:
        if Path(p).exists():
            return str(Path(p))

    return None


def detect_encoders():
    result = {}

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        return result

    try:
        proc = subprocess.run([ffmpeg, "-encoders"],
                              capture_output=True, text=True, timeout=15)
        output = proc.stdout + proc.stderr
    except (subprocess.TimeoutExpired, OSError):
        return result

    available = set()
    for line in output.splitlines():
        m = re.match(r"\s+(\S+)\s+(.*)", line)
        if m:
            codec = m.group(1).strip()
            available.add(codec)

    for vendor, codecs in HW_PATTERNS.items():
        for codec in codecs:
            if codec in available:
                result[codec] = f"{codec.upper().replace('_', ' ')} ({vendor.upper()})"

    for codec in ["libx264", "libx265", "libvpx-vp9", "libvpx", "libopus", "mpeg4"]:
        if codec in available:
            result[codec] = codec

    return result
