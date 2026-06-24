import os
from pathlib import Path

from PySide6.QtCore import Qt, QObject, QThread, Signal, QEvent, QPoint
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QShortcut, QKeySequence, QColor
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QSlider,
    QTableWidget, QTableWidgetItem, QProgressBar,
    QFileDialog, QMessageBox, QHeaderView,
    QMenu, QFrame,
)

from core.probe import probe_file
from core.pool import TranscodePool
from core.encoder_detect import detect_encoders
from core.settings import Settings
from ui.settings_dialog import SettingsDialog

# ── 文件状态颜色 ──────────────────────────────────────────────────────
C_PROBING = QColor("#999999")      # 分析中：灰色
C_READY = QColor("#E6E6E6")        # 就绪：白色
C_TRANSCODING = QColor("#529CCA")  # 转码中：蓝色
C_DONE = QColor("#5A9E6F")         # 完成：绿色
C_FAILED = QColor("#D97373")       # 失败：红色

SUPPORTED_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpg", ".mpeg", ".ts", ".mts"}
VIDEO_FILTER = "视频文件 (*.mp4 *.avi *.mkv *.mov *.wmv *.flv *.webm *.m4v *.mpg *.mpeg *.ts *.mts);;所有文件 (*)"

# ── 格式 → 兼容的视频编码器 ──────────────────────────────────────────
VIDEO_CODEC_MAP = {
    "mp4":  ["libx264", "libx265", "h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf"],
    "mkv":  ["libx264", "libx265", "h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf", "libvpx-vp9"],
    "mov":  ["libx264", "libx265", "h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv", "h264_amf", "hevc_amf"],
    "avi":  ["libx264", "mpeg4"],
    "webm": ["libvpx", "libvpx-vp9"],
}

# ── 格式 → 兼容的音频编码器 ──────────────────────────────────────────
AUDIO_CODEC_MAP = {
    "mp4":  ["aac", "libmp3lame", "copy"],
    "mkv":  ["aac", "libmp3lame", "libopus", "flac", "copy"],
    "mov":  ["aac", "libmp3lame", "copy"],
    "avi":  ["libmp3lame", "aac", "copy"],
    "webm": ["libopus", "libvorbis", "copy"],
}


# ── 后台线程：ffprobe 元信息分析 ─────────────────────────────────────
class ProbeWorker(QObject):
    finished = Signal(str, dict)

    def __init__(self, file_path):
        super().__init__()
        self.file_path = file_path

    def run(self):
        try:
            result = probe_file(self.file_path)
        except Exception as e:
            result = {"error": str(e)}
        self.finished.emit(self.file_path, result)


# ── 拖拽区 ──────────────────────────────────────────────────────────
class DropZone(QFrame):
    files_dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("cardDrop")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        self.label = QLabel("拖拽视频文件到此处，或点击选择")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size: 14px; background: transparent;")
        layout.addWidget(self.label)

    def _set_state(self, active):
        self.setProperty("dragOver", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_state(True)

    def dragLeaveEvent(self, event):
        self._set_state(False)

    def dropEvent(self, event: QDropEvent):
        self._set_state(False)
        supported = SUPPORTED_EXTENSIONS
        paths = []
        for u in event.mimeData().urls():
            if u.isLocalFile():
                p = u.toLocalFile()
                if Path(p).suffix.lower() in supported:
                    paths.append(p)
        if paths:
            self.files_dropped.emit(paths)

    def mousePressEvent(self, event):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "",
            VIDEO_FILTER)
        if paths:
            self.files_dropped.emit(paths)


# ============================================================================
#  主窗口 — 卡片分区布局
# ============================================================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FFmpeg Video Transcoder")
        self.setMinimumSize(720, 560)
        self.resize(840, 640)

        # 检测可用编码器（含硬件加速）
        self.available_encoders = detect_encoders()

        self.settings = Settings()
        self.settings.load()
        self.pool = None
        self._paused = False
        self.file_paths: dict[str, int] = {}
        self.file_status: dict[str, str] = {}

        self._init_ui()
        self._connect_all()
        self._apply_settings()

    # ======================================================================
    #  UI 构造
    # ======================================================================

    def _init_ui(self):
        c = QWidget()
        self.setCentralWidget(c)
        root = QVBoxLayout(c)
        root.setSpacing(0)
        root.setContentsMargins(32, 20, 32, 24)

        root.addWidget(self._make_title_bar())
        root.addSpacing(16)
        root.addWidget(self._make_drop_zone())
        root.addSpacing(12)
        root.addWidget(self._make_files_card(), stretch=1)
        root.addSpacing(12)
        root.addWidget(self._make_settings_card())
        root.addSpacing(16)
        root.addWidget(self._make_button_area())
        root.addSpacing(8)
        root.addWidget(self._make_progress_card())

        self.statusBar().showMessage("点击任意编码参数可查看说明")

    def _make_title_bar(self):
        """左上标题 + 右上设置按钮"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        title = QLabel("FFmpeg Video Transcoder")
        title.setObjectName("titleLabel")
        h.addWidget(title)
        h.addStretch()
        self.settings_btn = QPushButton("设置")
        self.settings_btn.setObjectName("settingsBtn")
        h.addWidget(self.settings_btn)
        return w

    def _make_drop_zone(self):
        self.drop_zone = DropZone()
        return self.drop_zone

    def _make_files_card(self):
        """源文件卡片 — 内嵌文件表格"""
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.file_table = QTableWidget(0, 4)
        self.file_table.setHorizontalHeaderLabels(["文件名", "大小", "编码", "分辨率"])
        self.file_table.setShowGrid(False)
        self.file_table.verticalHeader().setVisible(False)
        self.file_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.file_table.horizontalHeader().setStretchLastSection(True)
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.setColumnWidth(1, 70)
        self.file_table.setColumnWidth(2, 56)
        self.file_table.setColumnWidth(3, 84)
        self.file_table.setContextMenuPolicy(Qt.CustomContextMenu)
        layout.addWidget(self.file_table)

        return card

    def _make_settings_card(self):
        """输出设置卡片 — 所有 FFmpeg 编码参数，网格对齐"""
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        header = QLabel("输出设置")
        header.setObjectName("cardHeader")
        layout.addWidget(header)

        grid = QGridLayout()
        grid.setSpacing(8)

        # ── Row 0: 格式 + 编码器 ─────────────────────────────────────
        self.param_format = QComboBox()
        self.param_format.addItems(["mp4", "mkv", "mov", "avi", "webm"])
        self.param_format.setMinimumWidth(100)
        self.param_format.setProperty("hint", "mp4 兼容最广, webm 适合网页, mkv 适合无损")
        self._bind_hint(self.param_format)

        self.param_encoder = QComboBox()
        self.param_encoder.setMinimumWidth(150)
        self.param_encoder.setProperty("hint", "H.265 省空间, H.264 兼容广, NVENC 极速")
        self._bind_hint(self.param_encoder)

        grid.addWidget(QLabel("格式"), 0, 0)
        grid.addWidget(self.param_format, 0, 1)
        grid.addWidget(QLabel("编码器"), 0, 2)
        grid.addWidget(self.param_encoder, 0, 3)

        # ── Row 1: 分辨率 + 编码速度 ─────────────────────────────────
        self.param_res = QComboBox()
        self.param_res.addItems([
            "保持原始", "3840×2160", "2560×1440",
            "1920×1080", "1280×720", "852×480", "640×360"])
        self.param_res.setMinimumWidth(130)
        self.param_res.setProperty("hint", "缩小分辨率可加快编码，低于源分辨率时先缩后编")
        self._bind_hint(self.param_res)

        self.param_speed = QComboBox()
        self.param_speed.addItems(
            ["ultrafast", "superfast", "veryfast", "faster", "fast",
             "medium", "slow", "slower", "veryslow"])
        self.param_speed.setCurrentText("medium")
        self.param_speed.setMinimumWidth(110)
        self.param_speed.setProperty("hint", "ultrafast 最快体积大 → veryslow 最慢体积小")
        self._bind_hint(self.param_speed)

        grid.addWidget(QLabel("分辨率"), 1, 0)
        grid.addWidget(self.param_res, 1, 1)
        grid.addWidget(QLabel("编码速度"), 1, 2)
        grid.addWidget(self.param_speed, 1, 3)

        # ── Row 2: 画质 CRF 滑块 ─────────────────────────────────────
        self.param_crf = QSlider(Qt.Horizontal)
        self.param_crf.setRange(0, 51)
        self.param_crf.setValue(23)
        self.param_crf.setFixedWidth(160)
        self.param_crf.setProperty("hint", "0 = 无损, 51 = 最低质量, 建议 18-28（值越小画质越好体积越大）")

        self.param_crf_label = QLabel("23")
        self.param_crf_label.setObjectName("crfValue")
        self.param_crf_label.setFixedWidth(20)

        crf_row = QHBoxLayout()
        crf_row.setSpacing(8)
        crf_row.addWidget(self.param_crf)
        crf_row.addWidget(self.param_crf_label)
        crf_row.addStretch()

        grid.addWidget(QLabel("画质 (CRF)"), 2, 0)
        grid.addLayout(crf_row, 2, 1, 1, 3)

        # ── Row 3: 音频 + 比特率 ─────────────────────────────────────
        self.param_audio = QComboBox()
        self.param_audio.addItems(["aac", "libmp3lame", "libopus", "libvorbis", "flac", "copy"])
        self.param_audio.setMinimumWidth(120)
        self.param_audio.setProperty("hint", "AAC 通用推荐, Opus 更高效, Copy 不重新编码")
        self._bind_hint(self.param_audio)

        self.param_bitrate = QComboBox()
        self.param_bitrate.addItems(["96k", "128k", "192k", "256k", "320k"])
        self.param_bitrate.setCurrentText("128k")
        self.param_bitrate.setMinimumWidth(90)
        self.param_bitrate.setProperty("hint", "96k 对话, 128k 通用, 256k 高保真")
        self._bind_hint(self.param_bitrate)

        grid.addWidget(QLabel("音频"), 3, 0)
        grid.addWidget(self.param_audio, 3, 1)
        grid.addWidget(QLabel("比特率"), 3, 2)
        grid.addWidget(self.param_bitrate, 3, 3)

        # 最右列吃剩余空间，保證整体不过宽
        grid.setColumnStretch(4, 1)

        layout.addLayout(grid)
        return card

    def _make_button_area(self):
        """居中按钮 — 开始 / 暂停 / 取消"""
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)

        self.start_btn = QPushButton("开始转码")
        self.start_btn.setObjectName("primaryBtn")
        self.start_btn.setMinimumWidth(200)

        self.pause_btn = QPushButton("暂停")
        self.pause_btn.hide()

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.hide()

        h.addStretch()
        h.addWidget(self.start_btn)
        h.addWidget(self.pause_btn)
        h.addWidget(self.cancel_btn)
        h.addStretch()
        return w

    def _make_progress_card(self):
        """进度卡片（转码时才显示）"""
        self.progress_card = QFrame()
        self.progress_card.setObjectName("card")
        layout = QVBoxLayout(self.progress_card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        header = QLabel("进度")
        header.setObjectName("cardHeader")
        layout.addWidget(header)

        self.global_progress = QProgressBar()
        self.global_progress.setValue(0)
        layout.addWidget(self.global_progress)

        self.status_label = QLabel()
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

        self.progress_card.hide()
        return self.progress_card

    # ======================================================================
    #  信号连接
    # ======================================================================

    def _connect_all(self):
        self.drop_zone.files_dropped.connect(self.on_files_added)
        self.file_table.customContextMenuRequested.connect(self._table_menu)
        self.settings_btn.clicked.connect(self._open_settings)
        self.start_btn.clicked.connect(self.on_start)
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.cancel_btn.clicked.connect(self.on_cancel)

        self.param_crf.valueChanged.connect(self._on_param_crf_changed)
        self.param_format.currentTextChanged.connect(self._on_format_changed)

        # 滑块按下时显示画质提示
        self.param_crf.sliderPressed.connect(lambda: self._show_hint(self.param_crf))

        # 阻止鼠标滚轮误切换下拉框
        for cb in (self.param_format, self.param_encoder, self.param_res,
                   self.param_speed, self.param_audio, self.param_bitrate,
                   self.param_crf):
            cb.installEventFilter(self)

        QShortcut(QKeySequence("Ctrl+O"), self, self._add_files_dialog)
        QShortcut(QKeySequence("Delete"), self, self._remove_selected_files)
        QShortcut(QKeySequence("Ctrl+A"), self, self._select_all_files)

        self._on_format_changed(self.param_format.currentText())

    # ======================================================================
    #  文件管理
    # ======================================================================

    def on_files_added(self, paths):
        added = 0
        for path in paths:
            norm = os.path.normpath(path)
            if norm in self.file_paths:
                continue
            row = self.file_table.rowCount()
            self.file_table.insertRow(row)

            it = QTableWidgetItem(Path(norm).name)
            it.setData(Qt.UserRole, norm)
            it.setFlags(it.flags() & ~Qt.ItemIsEditable)
            it.setForeground(C_PROBING)
            self.file_table.setItem(row, 0, it)

            for col in range(1, 4):
                ph = QTableWidgetItem("—")
                ph.setFlags(ph.flags() & ~Qt.ItemIsEditable)
                ph.setForeground(QColor("#666666"))
                self.file_table.setItem(row, col, ph)

            self.file_paths[norm] = row
            self.file_status[norm] = "probing"
            self._probe_async(norm, row)
            added += 1

    def _probe_async(self, path, row):
        thread = QThread()
        worker = ProbeWorker(path)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda p, r: self._on_probe_result(p, r))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    def _on_probe_result(self, path, result):
        row = self.file_paths.get(os.path.normpath(path))
        if row is None:
            return
        if "error" in result:
            self._set_row_color(path, C_FAILED)
            self._set_status(path, "failed")
            return

        vs = None
        for s in result.get("streams", []):
            if s.get("codec_type") == "video":
                vs = s
                break

        self.file_table.item(row, 1).setText(_fmt_size(result.get("size", 0)))
        self.file_table.item(row, 1).setForeground(QColor("#E6E6E6"))

        codec = (vs.get("codec_name", "").upper() if vs else "") or "?"
        self.file_table.item(row, 2).setText(codec)
        self.file_table.item(row, 2).setForeground(QColor("#E6E6E6"))

        if vs and vs.get("width"):
            self.file_table.item(row, 3).setText(f"{vs['width']}×{vs['height']}")
        self.file_table.item(row, 3).setForeground(QColor("#E6E6E6"))

        self._set_row_color(path, C_READY)
        self._set_status(path, "ready")
        self.file_table.item(row, 0).setData(Qt.UserRole + 1, result)

    def _table_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("移除选中", self._remove_selected_files)
        menu.addAction("清空列表", self._clear_all_files)
        menu.exec(self.file_table.mapToGlobal(pos))

    def _remove_selected_files(self):
        rows = sorted({ix.row() for ix in self.file_table.selectedIndexes()}, reverse=True)
        for r in rows:
            it = self.file_table.item(r, 0)
            if it:
                p = it.data(Qt.UserRole)
                self.file_paths.pop(p, None)
                self.file_status.pop(p, None)
            self.file_table.removeRow(r)

    def _clear_all_files(self):
        self.file_table.setRowCount(0)
        self.file_paths.clear()
        self.file_status.clear()

    # ======================================================================
    #  格式切换 → 更新编码器列表
    # ======================================================================

    def _on_format_changed(self, fmt):
        """根据选择的格式，过滤可用的视频编码器"""
        self.param_encoder.blockSignals(True)
        self.param_encoder.clear()

        codecs = VIDEO_CODEC_MAP.get(fmt, ["libx264"])
        for codec in codecs:
            display = self.available_encoders.get(codec, codec)
            self.param_encoder.addItem(display, codec)

        # 默认选中 libx265 或 libx264
        for target in ("libx265", "hevc_nvenc", "hevc_qsv", "libx264"):
            idx = self.param_encoder.findData(target)
            if idx >= 0:
                self.param_encoder.setCurrentIndex(idx)
                break

        self.param_encoder.blockSignals(False)

        # 按格式过滤音频编码器
        audio_codecs = AUDIO_CODEC_MAP.get(fmt, ["aac"])
        self.param_audio.blockSignals(True)
        self.param_audio.clear()
        for ac in audio_codecs:
            self.param_audio.addItem(ac)
        self.param_audio.blockSignals(False)

    # ======================================================================
    #  转码
    # ======================================================================

    def on_start(self):
        if self.pool is not None or self.file_table.rowCount() == 0:
            return

        tasks = []
        for row in range(self.file_table.rowCount()):
            it = self.file_table.item(row, 0)
            if not it:
                continue
            p = it.data(Qt.UserRole)
            st = self.file_status.get(p, "")
            if st in ("probing", "failed", "done"):
                continue
            probe = it.data(Qt.UserRole + 1) or {}
            tasks.append((p, self._out_path(p), self._build_params(), probe))

        if not tasks:
            return

        n = self.settings.get("interface", "max_workers", 2)
        self.pool = TranscodePool(n)
        self.pool.progress_updated.connect(self._on_progress)
        self.pool.file_started.connect(self._on_file_start)
        self.pool.file_finished.connect(self._on_file_finish)
        self.pool.all_finished.connect(self._on_all_finished)

        self._enter_transcoding_mode()
        self.pool.add_tasks(tasks)

    def _out_path(self, src):
        """根据设置生成输出文件路径"""
        s = self.settings
        mode = s.get("general", "output_mode", "same_dir")
        suffix = s.get("general", "suffix", "_converted")
        ext = self.param_format.currentText()
        if mode == "custom_dir":
            od = s.get("general", "custom_dir", "") or str(Path(src).parent)
        else:
            od = str(Path(src).parent)
        return str(Path(od) / f"{Path(src).stem}{suffix}.{ext}")

    def _build_params(self):
        """从 UI 控件直接收集所有编码参数"""
        vc = self.param_encoder.currentData()
        if not vc:
            vc = self.param_encoder.currentText()

        crf_val = str(self.param_crf.value())
        res_text = self.param_res.currentText()
        resolution = res_text.split(" ")[0] if "×" in res_text else "保持原始"

        return {
            "video_codec": vc,
            "video_params": {"crf": crf_val, "preset": self.param_speed.currentText()},
            "audio_codec": self.param_audio.currentText(),
            "audio_params": {"b:a": self.param_bitrate.currentText()},
            "container": self.param_format.currentText(),
            "resolution": resolution,
        }

    def _enter_transcoding_mode(self):
        self.start_btn.hide()
        self.pause_btn.show()
        self.cancel_btn.show()
        self.drop_zone.setEnabled(False)
        self.global_progress.setValue(0)
        self.progress_card.show()
        self.status_label.setText("准备中...")

    def _exit_transcoding_mode(self):
        self.start_btn.show()
        self.pause_btn.hide()
        self.cancel_btn.hide()
        self.drop_zone.setEnabled(True)

    # ======================================================================
    #  进度回调
    # ======================================================================

    def _on_progress(self, path, pct):
        total = self.pool.total_count
        done = self.pool.completed_count
        self.global_progress.setValue(int((done + pct / 100) / total * 100) if total else 0)
        self.status_label.setText(f"{Path(path).name}  {pct:.0f}%  —  {done}/{total}")

    def _on_file_start(self, path):
        self._set_row_color(path, C_TRANSCODING)
        self._set_status(path, "transcoding")

    def _on_file_finish(self, path, ok):
        self._set_row_color(path, C_DONE if ok else C_FAILED)
        self._set_status(path, "done" if ok else "failed")
        if not ok:
            self.file_table.item(self.file_paths[path], 0).setText(Path(path).name + " ✗")
        total = self.pool.total_count
        self.global_progress.setValue(int(self.pool.completed_count / total * 100) if total else 0)

    def _on_all_finished(self):
        ok = sum(1 for s in self.file_status.values() if s == "done")
        ng = sum(1 for s in self.file_status.values() if s == "failed")
        parts = []
        if ok:
            parts.append(f"{ok} 成功")
        if ng:
            parts.append(f"{ng} 失败")
        self.status_label.setText("全部完成  —  " + "，".join(parts) if parts else "全部完成")
        self.global_progress.setValue(100)
        self._exit_transcoding_mode()
        self.pool = None

    # ======================================================================
    #  暂停 / 继续 / 取消
    # ======================================================================

    def _toggle_pause(self):
        if not self.pool:
            return
        if self._paused:
            self.pool.resume()
            self._paused = False
            self.pause_btn.setText("暂停")
        else:
            self.pool.pause()
            self._paused = True
            self.pause_btn.setText("继续")
            self.status_label.setText("已暂停")

    def on_cancel(self):
        if self.pool:
            self.pool.cancel_all()
            self.pool = None
        self._paused = False
        self._exit_transcoding_mode()
        self.progress_card.hide()
        self.global_progress.setValue(0)

    # ======================================================================
    #  设置
    # ======================================================================

    def _open_settings(self):
        dlg = SettingsDialog(self.settings, self)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec()

    def _on_settings_changed(self):
        self._apply_settings()
        self.settings.save()

    def _apply_settings(self):
        s = self.settings
        if s.get("interface", "maximize_on_start", False):
            self.showMaximized()

    def closeEvent(self, event):
        self.settings.save()
        super().closeEvent(event)

    # ======================================================================
    #  辅助方法
    # ======================================================================

    def _set_row_color(self, path, color: QColor):
        row = self.file_paths.get(os.path.normpath(path))
        if row is None:
            return
        it = self.file_table.item(row, 0)
        if it:
            it.setForeground(color)

    def _set_status(self, path, status):
        self.file_status[os.path.normpath(path)] = status

    def _add_files_dialog(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择视频文件", "",
            VIDEO_FILTER)
        if paths:
            self.on_files_added(paths)

    def _select_all_files(self):
        self.file_table.selectAll()

    # ── 事件过滤器：拦截下拉框滚轮误切换 ──────────────────────────
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and isinstance(obj, QComboBox):
            if not obj.view().isVisible():
                return True
        return super().eventFilter(obj, event)

    def _show_hint(self, widget):
        hint = widget.property("hint")
        if hint:
            self.statusBar().showMessage(hint)

    def _bind_hint(self, widget):
        widget.showPopup = lambda: self._popup_upward(widget)

    def _popup_upward(self, widget):
        self._show_hint(widget)
        menu = QMenu(self)
        for i in range(widget.count()):
            act = menu.addAction(widget.itemText(i))
            act.setData(i)
        menu.triggered.connect(lambda act: widget.setCurrentIndex(act.data()))
        g = widget.mapToGlobal(QPoint(0, 0))
        h = menu.sizeHint().height()
        menu.popup(QPoint(g.x(), g.y() - h))

    def _on_param_crf_changed(self, val):
        self.param_crf_label.setText(str(val))


# ── 工具函数 ──────────────────────────────────────────────────────────
def _fmt_size(n: int) -> str:
    if n <= 0:
        return "—"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.1f} MB"
