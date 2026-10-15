"""Launcher GUI: one-click entry for the transfer app plus environment care.

启动工具：一键启动传输软件，附带环境检测与依赖修复；
所有子进程输出实时汇总到日志面板。
"""
from __future__ import annotations

import os
import subprocess
import sys
import time

from PySide6.QtCore import QProcess, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QPlainTextEdit,
    QPushButton, QVBoxLayout, QWidget,
)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_DIR = os.path.join(PROJECT_ROOT, ".venv")
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
# Prefer the project-local interpreter / 优先使用项目内解释器
PYTHON = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
PIP_MIRROR = "https://pypi.tuna.tsinghua.edu.cn/simple"
DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "downloads")


class EnvCheck(QThread):
    """Background environment probe. / 后台环境检测，避免卡住界面"""
    result = Signal(bool, str)

    def run(self):
        if not os.path.exists(VENV_PYTHON):
            self.result.emit(False, "未找到项目内 Python 环境（.venv），请点击「安装 / 修复依赖」")
            return
        try:
            proc = subprocess.run(
                [VENV_PYTHON, "-c", "import PySide6, PIL"],
                capture_output=True, timeout=30, cwd=PROJECT_ROOT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.result.emit(False, f"环境检测失败：{exc}")
            return
        if proc.returncode == 0:
            self.result.emit(True, "环境正常（.venv + PySide6 + Pillow）")
        else:
            self.result.emit(False, "依赖不完整，请点击「安装 / 修复依赖」")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("尼康照片传输 · 启动工具")
        self.resize(720, 620)
        self.proc_app: QProcess | None = None
        self.proc_job: QProcess | None = None  # one-shot tasks / 一次性任务（装依赖）
        self._build_ui()
        self._apply_style()
        self._log("启动工具就绪。首次使用请确认右上角环境状态为绿色。")
        QTimer.singleShot(100, self.check_env)

    # ---- UI construction / 界面搭建 ----

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("尼康照片传输 · 启动工具")
        title.setObjectName("title")
        self.lbl_env = QLabel("环境：未检测")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.lbl_env)
        root.addLayout(header)

        row1 = QHBoxLayout()
        self.btn_app = QPushButton("启动传输软件")
        self.btn_downloads = QPushButton("打开下载目录")
        self.btn_downloads.setObjectName("ghost")
        self.btn_env = QPushButton("重新检测环境")
        self.btn_env.setObjectName("ghost")
        self.btn_fix = QPushButton("安装 / 修复依赖")
        self.btn_fix.setObjectName("ghost")
        row1.addWidget(self.btn_app)
        row1.addWidget(self.btn_downloads)
        row1.addWidget(self.btn_env)
        row1.addWidget(self.btn_fix)
        row1.addStretch(1)
        root.addLayout(row1)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        root.addWidget(self.log_view, 1)

        self.btn_app.clicked.connect(self.start_app)
        self.btn_downloads.clicked.connect(self.open_downloads)
        self.btn_env.clicked.connect(self.check_env)
        self.btn_fix.clicked.connect(self.fix_deps)

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #f7f9fc; color: #1e293b; font-size: 13px; }
            QLabel#title { font-size: 17px; font-weight: 600; color: #0f172a; }
            QPushButton { background: #2563eb; color: #ffffff; border: none;
                          border-radius: 6px; padding: 10px 18px; }
            QPushButton:hover { background: #1d4ed8; }
            QPushButton:pressed { background: #1e40af; }
            QPushButton:disabled { background: #c3cfdf; color: #f1f5f9; }
            QPushButton#ghost { background: #ffffff; color: #2563eb; border: 1px solid #bfdbfe; }
            QPushButton#ghost:hover { background: #eff6ff; }
            QPushButton#ghost:disabled { color: #94a3b8; border-color: #e2e8f0; }
            QPlainTextEdit { background: #ffffff; color: #475569; border: 1px solid #dbe4f0;
                             border-radius: 8px; font-family: Consolas, monospace; font-size: 12px; }
        """)

    # ---- helpers / 辅助方法 ----

    def _log(self, msg: str):
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _drain(self, proc: QProcess):
        """Forward child process output into the log panel. / 子进程输出转发到日志面板"""
        text = bytes(proc.readAllStandardOutput()).decode("utf-8", "replace")
        for line in text.splitlines():
            if line.strip():
                self._log(line)

    def _start_process(self, attr: str, args: list, program: str = PYTHON,
                       on_finished=None) -> QProcess:
        proc = QProcess(self)
        proc.setProgram(program)
        proc.setArguments(args)
        proc.setWorkingDirectory(PROJECT_ROOT)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)  # merge stdout+stderr / 合并输出流
        proc.readyReadStandardOutput.connect(lambda p=proc: self._drain(p))
        if on_finished:
            proc.finished.connect(on_finished)
        setattr(self, attr, proc)
        proc.start()
        return proc

    @staticmethod
    def _running(proc: QProcess | None) -> bool:
        return proc is not None and proc.state() != QProcess.NotRunning

    # ---- actions / 操作 ----

    def start_app(self):
        if self._running(self.proc_app):
            self._log("传输软件已在运行中。")
            return
        self._log("正在启动传输软件…")
        proc = self._start_process("proc_app", ["-u", os.path.join(PROJECT_ROOT, "main.py")])
        proc.finished.connect(lambda code, _s: self._log(f"传输软件已退出（代码 {code}）。"))

    def open_downloads(self):
        os.makedirs(DOWNLOAD_DIR, exist_ok=True)
        os.startfile(DOWNLOAD_DIR)

    def check_env(self):
        self.lbl_env.setText("环境：检测中…")
        self.lbl_env.setStyleSheet("color: #d97706;")
        self.btn_env.setEnabled(False)
        thread = EnvCheck(self)
        thread.result.connect(self._on_env_result)
        thread.finished.connect(thread.deleteLater)
        self._env_thread = thread
        thread.start()

    def _on_env_result(self, ok: bool, msg: str):
        self.btn_env.setEnabled(True)
        self.lbl_env.setText("环境：正常" if ok else "环境：异常")
        self.lbl_env.setStyleSheet(f"color: {'#16a34a' if ok else '#dc2626'};")
        self._log(msg)

    def fix_deps(self):
        if self._running(self.proc_job):
            self._log("已有任务在运行，请稍候。")
            return
        self.btn_fix.setEnabled(False)
        if not os.path.exists(VENV_PYTHON):
            self._log("未找到 .venv，先创建项目内 Python 环境…")
            self._start_process(
                "proc_job", ["-m", "venv", VENV_DIR], program=sys.executable,
                on_finished=self._after_venv)
        else:
            self._pip_install()

    def _after_venv(self, code, _s):
        if code != 0:
            self.btn_fix.setEnabled(True)
            self._log(f"创建 .venv 失败（代码 {code}）。")
            return
        self._log(".venv 创建完成，开始安装依赖…")
        self._pip_install()

    def _pip_install(self):
        self._log("正在安装 / 修复依赖（清华镜像）…")
        args = ["-m", "pip", "install", "-r",
                os.path.join(PROJECT_ROOT, "requirements.txt"),
                "-i", PIP_MIRROR, "--timeout", "120"]
        self._start_process("proc_job", args, program=VENV_PYTHON,
                            on_finished=self._after_pip)

    def _after_pip(self, code, _s):
        self.btn_fix.setEnabled(True)
        self._log("依赖安装完成。" if code == 0 else f"依赖安装失败（代码 {code}）。")
        if code == 0:
            self.check_env()

    def closeEvent(self, event):
        for proc in (self.proc_app, self.proc_job):
            if self._running(proc):
                proc.kill()
                proc.waitForFinished(1500)
        event.accept()


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
