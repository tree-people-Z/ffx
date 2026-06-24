from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QStackedWidget, QWidget, QLabel, QPushButton,
    QComboBox, QLineEdit, QSpinBox, QCheckBox,
    QRadioButton, QButtonGroup, QFileDialog,
    QListWidget, QFrame,
)

from core.settings import Settings


# ============================================================================
#  设置弹窗 — 侧边栏 + 内容页
# ============================================================================
class SettingsDialog(QDialog):
    settings_changed = Signal()

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("设置")
        self.setMinimumSize(560, 400)
        self.resize(600, 440)
        self._init_ui()
        self._load_settings()

    # ---- 布局构造 ----------------------------------------------------------

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(18, 14, 18, 16)

        # 内容区：左侧栏 + 右侧堆叠页
        content = QHBoxLayout()
        content.setSpacing(16)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("settingsSidebar")
        self.sidebar.setFixedWidth(110)
        for item in ("通用", "FFmpeg", "关于"):
            self.sidebar.addItem(item)
        self.sidebar.setCurrentRow(0)
        self.sidebar.currentRowChanged.connect(self._switch_page)
        content.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._page_general())
        self.stack.addWidget(self._page_ffmpeg())
        self.stack.addWidget(self._page_about())
        content.addWidget(self.stack, stretch=1)

        layout.addLayout(content, stretch=1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        save_btn = QPushButton("保存设置")
        save_btn.setObjectName("primaryBtn")
        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self._on_save)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _switch_page(self, idx):
        self.stack.setCurrentIndex(idx)

    # ---- 辅助：分区标题 + 分隔线 -------------------------------------------

    def _section(self, text):
        w = QWidget()
        w.setObjectName("settingsSectionWrap")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lbl = QLabel(text)
        lbl.setObjectName("settingsSection")
        lay.addWidget(lbl)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("settingsSep")
        lay.addWidget(sep)
        lay.addSpacing(4)
        return w

    # ======================================================================
    #  通用页
    # ======================================================================

    def _page_general(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._section("输出路径"))

        self.out_mode_group = QButtonGroup(self)
        self.out_same_dir = QRadioButton("同目录 + 后缀")
        self.out_custom_dir = QRadioButton("自定义目录")
        self.out_mode_group.addButton(self.out_same_dir, 0)
        self.out_mode_group.addButton(self.out_custom_dir, 1)
        layout.addWidget(self.out_same_dir)
        layout.addWidget(self.out_custom_dir)

        r1 = QHBoxLayout()
        r1.setSpacing(6)
        r1.addSpacing(24)
        r1.addWidget(QLabel("后缀"))
        self.suffix_input = QLineEdit("_converted")
        self.suffix_input.setFixedWidth(140)
        r1.addWidget(self.suffix_input)
        r1.addStretch()
        layout.addLayout(r1)

        r2 = QHBoxLayout()
        r2.setSpacing(6)
        r2.addSpacing(24)
        r2.addWidget(QLabel("目录"))
        self.custom_dir_input = QLineEdit()
        self.custom_dir_input.setPlaceholderText("选择输出目录...")
        r2.addWidget(self.custom_dir_input, stretch=1)
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self._browse_custom_dir)
        r2.addWidget(browse_btn)
        layout.addLayout(r2)

        layout.addWidget(self._section("性能"))

        f1 = QFormLayout()
        f1.setSpacing(8)
        f1.setContentsMargins(0, 0, 0, 0)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(1, 16)
        f1.addRow("并行转码数:", self.workers_spin)
        self.maximize_check = QCheckBox("启动时最大化窗口")
        f1.addRow("", self.maximize_check)
        layout.addLayout(f1)

        layout.addStretch()
        return w

    def _browse_custom_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.custom_dir_input.setText(d)

    # ======================================================================
    #  FFmpeg 页
    # ======================================================================

    def _page_ffmpeg(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(self._section("路径"))

        f1 = QFormLayout()
        f1.setSpacing(8)
        f1.setContentsMargins(0, 0, 0, 0)

        r1 = QHBoxLayout()
        self.ffmpeg_path = QLineEdit()
        self.ffmpeg_path.setPlaceholderText("自动检测")
        b1 = QPushButton("浏览")
        b1.clicked.connect(lambda: self._browse_exe("ffmpeg"))
        r1.addWidget(self.ffmpeg_path)
        r1.addWidget(b1)
        f1.addRow("ffmpeg:", r1)

        r2 = QHBoxLayout()
        self.ffprobe_path = QLineEdit()
        self.ffprobe_path.setPlaceholderText("自动检测")
        b2 = QPushButton("浏览")
        b2.clicked.connect(lambda: self._browse_exe("ffprobe"))
        r2.addWidget(self.ffprobe_path)
        r2.addWidget(b2)
        f1.addRow("ffprobe:", r2)

        layout.addLayout(f1)

        tip = QLabel("留空则自动在 PATH 及默认安装路径查找")
        tip.setObjectName("hintLabel")
        layout.addWidget(tip)

        layout.addWidget(self._section("硬件加速"))

        self.hw_check = QCheckBox("启用 NVENC / QSV / AMF 硬件编码器")
        layout.addWidget(self.hw_check)

        layout.addStretch()
        return w

    def _browse_exe(self, name):
        path, _ = QFileDialog.getOpenFileName(self, f"选择 {name}.exe", "", "可执行文件 (*.exe)")
        if path:
            if name == "ffmpeg":
                self.ffmpeg_path.setText(path)
            else:
                self.ffprobe_path.setText(path)

    # ======================================================================
    #  关于页
    # ======================================================================

    def _page_about(self):
        import sys
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addSpacing(8)

        title = QLabel("FFmpeg Video Transcoder")
        title.setObjectName("aboutTitle")
        layout.addWidget(title)

        ver = QLabel("版本 1.0.0")
        ver.setObjectName("aboutVersion")
        layout.addWidget(ver)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setObjectName("aboutSep")
        layout.addWidget(sep)

        info = QLabel(
            "基于 PySide6 + FFmpeg 的桌面视频转码工具\n\n"
            f"Python  {sys.version.split()[0]}\n"
            "FFmpeg  自动检测系统安装版本\n\n"
            "支持 H.264 / H.265 / VP9 编码\n"
            "支持 NVENC / QSV / AMF 硬件加速")
        info.setObjectName("aboutInfo")
        layout.addWidget(info)

        layout.addStretch()
        credit = QLabel("tree-people-Z  © 2026")
        credit.setObjectName("aboutCredit")
        layout.addWidget(credit)
        return w

    # ======================================================================
    #  读取 / 保存
    # ======================================================================

    def _load_settings(self):
        s = self.settings
        mode = s.get("general", "output_mode", "same_dir")
        if mode == "custom_dir":
            self.out_custom_dir.setChecked(True)
        else:
            self.out_same_dir.setChecked(True)
        self.suffix_input.setText(s.get("general", "suffix", "_converted"))
        self.custom_dir_input.setText(s.get("general", "custom_dir", ""))
        self.ffmpeg_path.setText(s.get("ffmpeg", "custom_ffmpeg_path", ""))
        self.ffprobe_path.setText(s.get("ffmpeg", "custom_ffprobe_path", ""))
        self.hw_check.setChecked(s.get("ffmpeg", "enable_hardware", True))
        self.maximize_check.setChecked(s.get("interface", "maximize_on_start", False))
        self.workers_spin.setValue(s.get("interface", "max_workers", 2))

    def _on_save(self):
        self.settings.set("general", "output_mode",
                          "custom_dir" if self.out_custom_dir.isChecked() else "same_dir")
        self.settings.set("general", "suffix", self.suffix_input.text().strip() or "_converted")
        self.settings.set("general", "custom_dir", self.custom_dir_input.text().strip())
        self.settings.set("ffmpeg", "custom_ffmpeg_path", self.ffmpeg_path.text().strip())
        self.settings.set("ffmpeg", "custom_ffprobe_path", self.ffprobe_path.text().strip())
        self.settings.set("ffmpeg", "enable_hardware", self.hw_check.isChecked())
        self.settings.set("interface", "maximize_on_start", self.maximize_check.isChecked())
        self.settings.set("interface", "max_workers", self.workers_spin.value())
        self.settings.save()
        self.settings_changed.emit()
        self.accept()
