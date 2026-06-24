import subprocess
import sys
import shutil
from pathlib import Path

ROOT = Path(__file__).parent


def main():
    dist = ROOT / "dist"
    if dist.exists():
        shutil.rmtree(dist)

    subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--windowed",
        "--onefile",
        "--name", "FFmpegVideoTranscoder",
        "--add-data", f"ui{Path.sep}style.qss;ui",
        "--icon", "icon.ico" if (ROOT / "icon.ico").exists() else "NUL",
        "--distpath", str(dist),
        str(ROOT / "main.py"),
    ], check=True)

    print(f"Build complete: {dist / 'FFmpegVideoTranscoder.exe'}")


if __name__ == "__main__":
    main()
