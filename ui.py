import os

from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ai_engine import AIEngine
from command_runner import reassemble_command, run_ffmpeg
from media_utils import probe_file, get_media_summary
from paths import MODEL_PATH as _MODEL_PATH

# ── Dark theme ──────────────────────────────────────────────────────

_DARK_THEME = """
QMainWindow, QWidget#central {
    background-color: #1a1a2e;
}

QLabel {
    color: #ddd;
    font-size: 13px;
}

QLabel#fileInfo {
    color: #8892a0;
    font-size: 12px;
    padding: 2px 0;
}

QLabel#status {
    color: #8892a0;
    font-size: 13px;
    padding: 4px 0;
}

QLineEdit {
    background-color: #0f3460;
    border: 2px solid #2a2a4a;
    border-radius: 8px;
    color: #eee;
    font-size: 14px;
    padding: 10px 14px;
    selection-background-color: #533483;
}
QLineEdit:focus {
    border-color: #e94560;
}
QLineEdit::placeholder {
    color: #556680;
}

QPushButton#convertBtn {
    background-color: #e94560;
    border: none;
    border-radius: 8px;
    color: #fff;
    font-size: 14px;
    font-weight: bold;
    padding: 10px 24px;
    min-width: 90px;
}
QPushButton#convertBtn:hover {
    background-color: #d63851;
}
QPushButton#convertBtn:pressed {
    background-color: #c02e45;
}
QPushButton#convertBtn:disabled {
    background-color: #3a3a5a;
    color: #666;
}

QPushButton#clearBtn {
    background-color: transparent;
    border: 2px solid #2a2a4a;
    border-radius: 8px;
    color: #8892a0;
    font-size: 13px;
    padding: 10px 16px;
}
QPushButton#clearBtn:hover {
    border-color: #8892a0;
    color: #ccc;
}

QPushButton#openFolderBtn {
    background-color: transparent;
    border: 2px solid #4ecca3;
    border-radius: 8px;
    color: #4ecca3;
    font-size: 13px;
    padding: 6px 16px;
}
QPushButton#openFolderBtn:hover {
    background-color: #4ecca320;
}

QPushButton#advancedToggle {
    background-color: transparent;
    border: none;
    color: #556680;
    font-size: 12px;
    padding: 4px 0;
    text-align: left;
}
QPushButton#advancedToggle:hover {
    color: #8892a0;
}

QTextEdit#advancedView {
    background-color: #0d1b2a;
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    color: #8892a0;
    font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
    font-size: 11px;
    padding: 8px;
    selection-background-color: #533483;
}

QProgressBar {
    background-color: #16213e;
    border: none;
    border-radius: 4px;
    max-height: 8px;
}
QProgressBar::chunk {
    background-color: #e94560;
    border-radius: 4px;
}
"""


# ── Worker threads ──────────────────────────────────────────────────


class ModelLoadWorker(QThread):
    finished = Signal(object)

    def run(self):
        try:
            engine = AIEngine(_MODEL_PATH)
            self.finished.emit(engine)
        except Exception as e:
            self.finished.emit(e)


class BatchProbeWorker(QThread):
    """Probe multiple files sequentially, emitting per-file results."""
    file_probed = Signal(int, dict, str)   # (index, probe_data, summary)
    file_error = Signal(int, str)          # (index, error_message)
    all_done = Signal()

    def __init__(self, file_paths: list[str]):
        super().__init__()
        self.file_paths = file_paths

    def run(self):
        for i, path in enumerate(self.file_paths):
            try:
                data = probe_file(path)
                summary = get_media_summary(data)
                self.file_probed.emit(i, data, summary)
            except Exception as e:
                self.file_error.emit(i, str(e))
        self.all_done.emit()


class BatchConvertWorker(QThread):
    """Process multiple files sequentially with the same prompt."""
    file_started = Signal(int, int)          # (index, total)
    file_command_resolved = Signal(int, str)  # (index, resolved_command)
    file_progress = Signal(int, float)        # (index, percent 0-100)
    file_finished = Signal(int, str)          # (index, output_path)
    file_clarification = Signal(int, str)     # (index, question)
    file_error = Signal(int, str)             # (index, error_message)
    all_done = Signal(int, int, int)          # (total, succeeded, failed)

    def __init__(self, engine, file_records: list[dict], user_prompt: str):
        super().__init__()
        self.engine = engine
        self.file_records = file_records
        self.user_prompt = user_prompt

    def run(self):
        total = len(self.file_records)
        succeeded = 0
        failed = 0

        for i, rec in enumerate(self.file_records):
            self.file_started.emit(i, total)
            try:
                file_path = rec["path"]
                probe_data = rec["probe_data"]
                summary = rec["summary"]

                ext = os.path.splitext(file_path)[1]
                input_token = f"<INPUT_1>{ext}"
                input_files = {"<INPUT_1>": file_path}
                output_dir = os.path.dirname(file_path)

                ai_output = self.engine.generate_command(
                    summary, input_token, self.user_prompt
                )

                if ai_output["is_ambiguous"]:
                    self.file_clarification.emit(
                        i, ai_output["clarification_question"]
                    )
                    failed += 1
                    continue

                resolved_cmd, output_path = reassemble_command(
                    ai_output, input_files, output_dir
                )
                self.file_command_resolved.emit(i, resolved_cmd)

                duration = None
                fmt = probe_data.get("format", {})
                if fmt.get("duration"):
                    duration = float(fmt["duration"])

                run_ffmpeg(
                    resolved_cmd,
                    duration=duration,
                    progress_callback=lambda pct, idx=i: self.file_progress.emit(
                        idx, pct
                    ),
                )

                self.file_finished.emit(i, output_path)
                succeeded += 1

            except Exception as e:
                self.file_error.emit(i, str(e))
                failed += 1

        self.all_done.emit(total, succeeded, failed)


# ── Drop zone widget ────────────────────────────────────────────────


class DropZone(QLabel):
    files_dropped = Signal(list)

    _IDLE_STYLE = """
        QLabel {
            background-color: #16213e;
            border: 2px dashed #2a2a4a;
            border-radius: 16px;
            color: #556680;
            font-size: 15px;
            padding: 44px 20px;
        }
    """
    _HOVER_STYLE = """
        QLabel {
            background-color: #1a2744;
            border: 2px dashed #e94560;
            border-radius: 16px;
            color: #e94560;
            font-size: 15px;
            padding: 44px 20px;
        }
    """
    _HAS_FILE_STYLE = """
        QLabel {
            background-color: #16213e;
            border: 2px solid #2a2a4a;
            border-radius: 16px;
            color: #ddd;
            font-size: 14px;
            padding: 20px 20px;
        }
    """

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("Drop media files here")
        self.setStyleSheet(self._IDLE_STYLE)
        self.setAcceptDrops(True)
        self.setMinimumHeight(120)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(self._HOVER_STYLE)

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._IDLE_STYLE)

    def dropEvent(self, event):
        self.setStyleSheet(self._IDLE_STYLE)
        urls = event.mimeData().urls()
        if urls:
            paths = [u.toLocalFile() for u in urls if u.isLocalFile()]
            if paths:
                self.files_dropped.emit(paths)

    def show_files(self, file_records: list[dict]):
        """Display a summary of all dropped files."""
        count = len(file_records)
        if count == 1:
            rec = file_records[0]
            name = os.path.basename(rec["path"])
            summary = rec.get("summary") or "Analyzing..."
            self.setText(f"{name}\n{summary}")
        else:
            names = [os.path.basename(r["path"]) for r in file_records]
            display = names[:3]
            text = "\n".join(display)
            if count > 3:
                text += f"\n... and {count - 3} more"
            probed = sum(1 for r in file_records if r.get("summary"))
            if probed < count:
                text += f"\n\nAnalyzing files ({probed}/{count})..."
            else:
                text += f"\n\n{count} files ready"
            self.setText(text)
        self.setStyleSheet(self._HAS_FILE_STYLE)

    def reset(self):
        self.setText("Drop media files here")
        self.setStyleSheet(self._IDLE_STYLE)


# ── Main window ─────────────────────────────────────────────────────


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AI-ncoder")
        self.setMinimumSize(640, 460)

        # State
        self._engine: AIEngine | None = None
        self._files: list[dict] = []
        self._convertible: list[dict] = []  # snapshot of probed files during conversion
        self._worker = None

        # ── Layout ──
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Title
        title = QLabel("AI-ncoder")
        title.setStyleSheet(
            "font-size: 22px; font-weight: bold; color: #eee; padding: 0 0 4px 0;"
        )
        layout.addWidget(title)

        subtitle = QLabel("AI-powered media conversion — entirely offline")
        subtitle.setStyleSheet(
            "font-size: 12px; color: #556680; padding: 0 0 8px 0;"
        )
        layout.addWidget(subtitle)

        # Drop zone
        self._drop_zone = DropZone()
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        layout.addWidget(self._drop_zone)

        # Prompt row
        prompt_row = QHBoxLayout()
        prompt_row.setSpacing(8)

        self._prompt_input = QLineEdit()
        self._prompt_input.setPlaceholderText(
            'What do you want to do? e.g. "Extract audio as mp3"'
        )
        self._prompt_input.returnPressed.connect(self._on_convert)
        prompt_row.addWidget(self._prompt_input)

        self._convert_btn = QPushButton("Convert")
        self._convert_btn.setObjectName("convertBtn")
        self._convert_btn.setEnabled(False)
        self._convert_btn.clicked.connect(self._on_convert)
        prompt_row.addWidget(self._convert_btn)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setObjectName("clearBtn")
        self._clear_btn.clicked.connect(self._on_clear)
        prompt_row.addWidget(self._clear_btn)

        layout.addLayout(prompt_row)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        # Status row
        status_row = QHBoxLayout()
        self._status = QLabel("")
        self._status.setObjectName("status")
        self._status.setWordWrap(True)
        status_row.addWidget(self._status, 1)

        self._open_folder_btn = QPushButton("Open Folder")
        self._open_folder_btn.setObjectName("openFolderBtn")
        self._open_folder_btn.clicked.connect(self._on_open_folder)
        self._open_folder_btn.hide()
        status_row.addWidget(self._open_folder_btn)

        layout.addLayout(status_row)

        # Advanced View
        self._advanced_toggle = QPushButton("Show Command")
        self._advanced_toggle.setObjectName("advancedToggle")
        self._advanced_toggle.setCheckable(True)
        self._advanced_toggle.setChecked(False)
        self._advanced_toggle.clicked.connect(self._on_toggle_advanced)
        layout.addWidget(self._advanced_toggle)

        self._advanced_view = QTextEdit()
        self._advanced_view.setObjectName("advancedView")
        self._advanced_view.setReadOnly(True)
        self._advanced_view.setMaximumHeight(100)
        self._advanced_view.hide()
        layout.addWidget(self._advanced_view)

        layout.addStretch()

        # ── Load model in background ──
        self._set_status("Loading AI model...", "loading")
        self._progress_bar.setRange(0, 0)
        self._progress_bar.show()
        self._model_loader = ModelLoadWorker()
        self._model_loader.finished.connect(self._on_model_loaded)
        self._model_loader.start()

    # ── Status helper ───────────────────────────────────────────────

    def _set_status(self, text: str, kind: str = "default"):
        colors = {
            "default": "#8892a0",
            "loading": "#8892a0",
            "success": "#4ecca3",
            "error": "#e94560",
        }
        color = colors.get(kind, colors["default"])
        self._status.setStyleSheet(
            f"color: {color}; font-size: 13px; padding: 4px 0;"
        )
        self._status.setText(text)

    # ── Slots ───────────────────────────────────────────────────────

    def _on_model_loaded(self, result):
        self._progress_bar.hide()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        if isinstance(result, Exception):
            self._set_status(f"Model load error: {result}", "error")
            return
        self._engine = result
        self._set_status("Ready — drop files to get started.", "default")
        self._update_convert_enabled()

    # ── File drop & probe ──

    def _on_files_dropped(self, paths: list[str]):
        self._files = []
        self._open_folder_btn.hide()
        self._advanced_view.clear()

        for path in paths:
            self._files.append({
                "path": os.path.abspath(path),
                "probe_data": None,
                "summary": None,
                "output_path": None,
                "status": "pending_probe",
                "error_msg": None,
            })

        self._drop_zone.show_files(self._files)
        count = len(self._files)
        self._set_status(
            f"Analyzing {'file' if count == 1 else f'{count} files'}...",
            "loading",
        )
        self._update_convert_enabled()

        worker = BatchProbeWorker([rec["path"] for rec in self._files])
        worker.file_probed.connect(self._on_file_probed)
        worker.file_error.connect(self._on_probe_error)
        worker.all_done.connect(self._on_all_probed)
        self._worker = worker
        worker.start()

    def _on_file_probed(self, index: int, data: dict, summary: str):
        self._files[index]["probe_data"] = data
        self._files[index]["summary"] = summary
        self._files[index]["status"] = "probed"
        self._drop_zone.show_files(self._files)

    def _on_probe_error(self, index: int, msg: str):
        self._files[index]["status"] = "error"
        self._files[index]["error_msg"] = f"Unsupported: {msg}"
        self._drop_zone.show_files(self._files)

    def _on_all_probed(self):
        probed = sum(1 for r in self._files if r["status"] == "probed")
        errored = sum(1 for r in self._files if r["status"] == "error")
        if probed == 0:
            self._set_status("No supported files found.", "error")
        elif errored > 0:
            self._set_status(
                f"{probed} file{'s' if probed != 1 else ''} ready, "
                f"{errored} unsupported — enter a prompt and click Convert.",
                "default",
            )
        else:
            self._set_status(
                "Ready — enter a prompt and click Convert.", "default"
            )
        self._update_convert_enabled()

    # ── Conversion ──

    def _on_convert(self):
        prompt = self._prompt_input.text().strip()
        if not prompt or not self._can_convert():
            return

        self._convert_btn.setEnabled(False)
        self._drop_zone.setAcceptDrops(False)
        self._open_folder_btn.hide()
        self._advanced_view.clear()

        self._convertible = [r for r in self._files if r["status"] == "probed"]

        self._progress_bar.setRange(0, 0)
        self._progress_bar.show()

        worker = BatchConvertWorker(self._engine, self._convertible, prompt)
        worker.file_started.connect(self._on_batch_file_started)
        worker.file_command_resolved.connect(
            self._on_batch_file_command_resolved
        )
        worker.file_progress.connect(self._on_batch_file_progress)
        worker.file_finished.connect(self._on_batch_file_finished)
        worker.file_clarification.connect(self._on_batch_file_clarification)
        worker.file_error.connect(self._on_batch_file_error)
        worker.all_done.connect(self._on_batch_all_done)
        self._worker = worker
        worker.start()

    def _on_batch_file_started(self, index: int, total: int):
        self._progress_bar.setRange(0, 0)  # indeterminate during AI
        if total == 1:
            self._set_status("Generating command...", "loading")
        else:
            self._set_status(
                f"File {index + 1} of {total}: Generating command...",
                "loading",
            )

    def _on_batch_file_command_resolved(self, index: int, command: str):
        total = len(self._convertible)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        if total == 1:
            self._set_status("Converting...", "loading")
        else:
            self._set_status(
                f"File {index + 1} of {total}: Converting...", "loading"
            )
        self._advanced_view.setPlainText(command)

    def _on_batch_file_progress(self, index: int, pct: float):
        total = len(self._convertible)
        self._progress_bar.setValue(int(pct))
        if total == 1:
            self._set_status(f"Converting... {pct:.0f}%", "loading")
        else:
            self._set_status(
                f"File {index + 1} of {total}: Converting... {pct:.0f}%",
                "loading",
            )

    def _on_batch_file_finished(self, index: int, output_path: str):
        if index < len(self._convertible):
            self._convertible[index]["output_path"] = output_path
            self._convertible[index]["status"] = "done"

    def _on_batch_file_error(self, index: int, msg: str):
        if index < len(self._convertible):
            self._convertible[index]["status"] = "error"
            self._convertible[index]["error_msg"] = msg

    def _on_batch_file_clarification(self, index: int, question: str):
        if index < len(self._convertible):
            self._convertible[index]["status"] = "error"
            self._convertible[index]["error_msg"] = (
                f"Clarification needed: {question}"
            )

    def _on_batch_all_done(self, total: int, succeeded: int, failed: int):
        self._progress_bar.setValue(100)
        self._drop_zone.setAcceptDrops(True)

        if total == 1:
            if succeeded == 1:
                # Find the output path
                output = next(
                    (r["output_path"] for r in self._files if r.get("output_path")),
                    None,
                )
                if output:
                    self._set_status(
                        f"Done! Output: {os.path.basename(output)}", "success"
                    )
                else:
                    self._set_status("Done!", "success")
            else:
                err = next(
                    (r["error_msg"] for r in self._files if r.get("error_msg")),
                    "Unknown error",
                )
                self._set_status(f"Error: {err[:200]}", "error")
        else:
            if failed == 0:
                self._set_status(
                    f"Done! {succeeded} files converted successfully.",
                    "success",
                )
            else:
                self._set_status(
                    f"Done. {succeeded} succeeded, {failed} failed.",
                    "success" if succeeded > 0 else "error",
                )

        # Show errors in advanced view for failed files
        error_lines = [
            f"{os.path.basename(r['path'])}: {r['error_msg']}"
            for r in self._files
            if r.get("error_msg")
        ]
        if error_lines:
            self._advanced_view.setPlainText("\n\n".join(error_lines))
            if not self._advanced_toggle.isChecked():
                self._advanced_toggle.setChecked(True)
                self._advanced_view.show()

        self._open_folder_btn.show()
        self._update_convert_enabled()

    # ── Other slots ──

    def _on_open_folder(self):
        for rec in self._files:
            if rec.get("output_path"):
                folder = os.path.dirname(rec["output_path"])
                QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
                return

    def _on_toggle_advanced(self, checked: bool):
        self._advanced_view.setVisible(checked)
        self._advanced_toggle.setText(
            "Hide Command" if checked else "Show Command"
        )

    def _on_clear(self):
        self._files = []
        self._drop_zone.reset()
        self._prompt_input.clear()
        self._set_status(
            "Ready — drop files to get started."
            if self._engine
            else "Loading AI model...",
            "default" if self._engine else "loading",
        )
        self._progress_bar.hide()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._open_folder_btn.hide()
        self._advanced_view.clear()
        self._update_convert_enabled()

    # ── Helpers ──

    def _can_convert(self) -> bool:
        return (
            self._engine is not None
            and len(self._files) > 0
            and any(r["status"] == "probed" for r in self._files)
        )

    def _update_convert_enabled(self):
        self._convert_btn.setEnabled(self._can_convert())


def run_gui():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(_DARK_THEME)
    app.setFont(QFont(".AppleSystemUIFont", 13))
    window = MainWindow()
    window.show()
    app.exec()
