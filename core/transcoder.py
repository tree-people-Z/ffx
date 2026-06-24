import os
import re
import time
import platform

from PySide6.QtCore import QObject, QProcess, Signal

TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+\.?\d*)")

if platform.system() == "Windows":
    import ctypes
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
    PROCESS_SUSPEND_RESUME = 0x0800

    def _suspend_process(pid):
        try:
            h = _kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
            if h:
                _ntdll.NtSuspendProcess(h)
                _kernel32.CloseHandle(h)
        except Exception:
            pass

    def _resume_process(pid):
        try:
            h = _kernel32.OpenProcess(PROCESS_SUSPEND_RESUME, False, pid)
            if h:
                _ntdll.NtResumeProcess(h)
                _kernel32.CloseHandle(h)
        except Exception:
            pass
elif platform.system() in ("Linux", "Darwin"):
    import signal

    def _suspend_process(pid):
        try:
            os.kill(pid, signal.SIGSTOP)
        except (ProcessLookupError, PermissionError):
            pass

    def _resume_process(pid):
        try:
            os.kill(pid, signal.SIGCONT)
        except (ProcessLookupError, PermissionError):
            pass
else:
    def _suspend_process(pid):
        pass

    def _resume_process(pid):
        pass


class TranscodeWorker(QObject):
    progress = Signal(str, float)
    finished = Signal(str, bool)
    log_line = Signal(str, str)

    def __init__(self, input_path, output_path, params, probe_result):
        super().__init__()
        self.input_path = input_path
        self.output_path = output_path
        self.params = params
        self.total_duration = 0
        if probe_result:
            self.total_duration = probe_result.get("duration", 0)
        self.process = QProcess()
        self._last_progress_emit = 0.0
        self._progress_throttle = 0.15
        self._setup_process()

    def _setup_process(self):
        self.process.setProcessChannelMode(QProcess.SeparateChannels)
        self.process.readyReadStandardError.connect(self._on_stderr)
        self.process.finished.connect(self._on_finished)

    def _build_cmd(self):
        cmd = ["ffmpeg", "-y", "-i", self.input_path]

        vc = self.params.get("video_codec", "libx265")
        vp = self.params.get("video_params", {})

        cmd += ["-c:v", vc]
        for k, v in vp.items():
            cmd += [f"-{k}", str(v)]

        ac = self.params.get("audio_codec", "aac")
        ap = self.params.get("audio_params", {})
        cmd += ["-c:a", ac]
        for k, v in ap.items():
            cmd += [f"-{k}", str(v)]

        resolution = self.params.get("resolution")
        if resolution and resolution not in ("保持原始", "0x0", ""):
            cmd += ["-vf", f"scale={resolution.replace('×', ':')}"]

        container = self.params.get("container", "mp4")
        if container == "mp4":
            cmd += ["-movflags", "+faststart"]

        cmd += [self.output_path]
        return cmd

    def start(self):
        cmd = self._build_cmd()
        self.process.start(cmd[0], cmd[1:])

    def cancel(self):
        self.process.kill()

    def pause(self):
        pid = self.process.processId()
        if pid > 0:
            _suspend_process(pid)

    def resume(self):
        pid = self.process.processId()
        if pid > 0:
            _resume_process(pid)

    def _on_stderr(self):
        data = self.process.readAllStandardError().data().decode("utf-8", errors="replace")
        self.log_line.emit(self.input_path, data)
        self._parse_progress(data)

    def _parse_progress(self, text):
        m = TIME_RE.search(text)
        if m:
            h, m_, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            current = h * 3600 + m_ * 60 + s
            if self.total_duration > 0:
                pct = min(99.9, current / self.total_duration * 100)
                now = time.monotonic()
                if now - self._last_progress_emit >= self._progress_throttle:
                    self._last_progress_emit = now
                    self.progress.emit(self.input_path, pct)

    def _on_finished(self, exit_code, exit_status):
        success = exit_code == 0 and exit_status == QProcess.NormalExit
        self.finished.emit(self.input_path, success)
