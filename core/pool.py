from PySide6.QtCore import QObject, Signal

from .transcoder import TranscodeWorker


class TranscodePool(QObject):
    progress_updated = Signal(str, float)
    file_started = Signal(str)
    file_finished = Signal(str, bool)
    all_finished = Signal()

    def __init__(self, max_workers=2):
        super().__init__()
        self.max_workers = max_workers
        self.queue = []
        self.active = []
        self.total_count = 0
        self.completed_count = 0
        self._paused = False
        self._cancelled = False

    def add_tasks(self, tasks):
        if not tasks:
            self.all_finished.emit()
            return
        self.queue = list(tasks)
        self.active = []
        self.total_count = len(tasks)
        self.completed_count = 0
        self._paused = False
        self._cancelled = False
        self._process_queue()

    def _process_queue(self):
        if self._cancelled:
            return
        while not self._paused and self.queue and len(self.active) < self.max_workers:
            task = self.queue.pop(0)
            worker = TranscodeWorker(*task)
            worker.progress.connect(self._on_worker_progress)
            worker.finished.connect(self._on_worker_finished)
            self.active.append(worker)
            self.file_started.emit(task[0])
            worker.start()

    def _on_worker_progress(self, file_path, progress_value):
        self.progress_updated.emit(file_path, progress_value)

    def _on_worker_finished(self, file_path, success):
        self.active = [w for w in self.active if w.input_path != file_path]
        self.completed_count += 1
        self.file_finished.emit(file_path, success)
        if self.completed_count >= self.total_count:
            self.all_finished.emit()
        else:
            self._process_queue()

    def pause(self):
        self._paused = True
        for w in self.active:
            w.pause()

    def resume(self):
        self._paused = False
        for w in self.active:
            w.resume()
        self._process_queue()

    def cancel_all(self):
        self._cancelled = True
        for w in self.active:
            w.cancel()
        self.active.clear()
        self.queue.clear()
