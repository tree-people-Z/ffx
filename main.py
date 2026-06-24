import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt

from ui.main_window import MainWindow
from core.encoder_detect import find_ffmpeg
from core.settings import Settings


def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    style_path = Path(__file__).parent / "ui" / "style.qss"
    if style_path.exists():
        with open(style_path, encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    settings = Settings()
    settings.load()

    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle("FFmpeg 未找到")
        msg.setText("未在系统中找到 FFmpeg，请安装后重试。")
        msg.setInformativeText(
            "1. 从 https://ffmpeg.org/download.html 下载\n"
            "2. 将 ffmpeg.exe 和 ffprobe.exe 所在目录加入系统 PATH\n"
            "3. 重启本程序"
        )
        msg.exec()

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
