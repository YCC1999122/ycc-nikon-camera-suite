"""Camera session worker: one QThread owns the PTP session and schedules all operations.

Priority order: user EXIF lookups > visible thumbnails > downloads > background indexing.
The camera exposes a single command channel, so everything is serialized here instead of
letting multiple threads fight over the socket.
/ 相机会话线程：独占 PTP 会话，统一调度所有操作。
优先级：EXIF 查询 > 可见缩略图 > 下载 > 后台索引。
相机只有一个命令通道，全部串行执行，避免多线程争抢 socket。
"""
from __future__ import annotations

import os
import queue
import threading
import time

from PySide6.QtCore import QThread, Signal

from app import exif as exifmod
from app.client import CameraClient, CameraError, PhotoInfo

_EXIF_BYTES = 256 * 1024  # EXIF/GPS live in the file header / EXIF 位于文件头部
_BATCH = 25  # index batch size / 索引批次大小


class CameraSession(QThread):
    log = Signal(str)
    failed = Signal(str)
    session_ready = Signal(str, dict)          # camera name, device info
    handles_total = Signal(int)                # total object handles on the camera
    index_batch = Signal(list, int)            # list[PhotoInfo], indexed count
    index_done = Signal()
    thumb_ready = Signal(int, bytes)           # handle, jpeg bytes (empty = none)
    exif_ready = Signal(int, dict)             # handle, parsed exif dict
    dl_progress = Signal(int, int, str)        # done, total, filename
    dl_done = Signal(int)                      # files finished

    def __init__(self, ip: str, parent=None):
        super().__init__(parent)
        self.ip = ip
        self.client = CameraClient(ip, timeout=15.0)
        self._stop = threading.Event()
        self._tasks: queue.Queue[tuple] = queue.Queue()   # ("exif", h) ("download", ...) ("stop",)
        self._want_thumbs: list[int] = []                  # visible handles, newest request wins
        self._want_lock = threading.Lock()
        self._thumb_skip: set[int] = set()                 # already fetched this session

    # ---- thread-safe API (GUI thread) / 供界面线程调用 ----

    def request_thumbs(self, handles: list[int]) -> None:
        """Replace the wanted-thumbnail set (stale scroll positions drop out).
        / 替换想要的缩略图集合，滚动过的旧请求自动作废"""
        with self._want_lock:
            self._want_thumbs = [h for h in handles if h not in self._thumb_skip]

    def request_exif(self, handle: int) -> None:
        self._tasks.put(("exif", handle))

    def enqueue_downloads(self, targets: list[tuple[int, str]], folder: str) -> None:
        """targets: (handle, filename) pairs. / 下载任务入队"""
        self._tasks.put(("download", targets, folder))

    def stop(self) -> None:
        self._stop.set()
        self._tasks.put(("stop",))

    # ---- worker loop / 工作循环 ----

    def run(self):
        try:
            if not self._connect_with_retry():
                return
            self.client.open_session()
            self.session_ready.emit(self.client.camera_name, self.client.fetch_device_info())
            handles = self.client.list_handles(newest_first=True)
            self.handles_total.emit(len(handles))
            self._main_loop(handles)
        except (CameraError, OSError) as exc:
            self.failed.emit(str(exc))
        finally:
            self.client.close()

    def _connect_with_retry(self) -> bool:
        for attempt in range(1, 21):
            if self._stop.is_set():
                return False
            try:
                self.client.connect()
                self.log.emit(f"已连接：{self.client.camera_name} ({self.ip})")
                return True
            except CameraError as exc:
                if attempt == 20:
                    self.failed.emit(
                        f"{exc}。相机向导一次只接受一个连接：请重新进入「连接至 PC」向导后立刻点「连接」。")
                    return False
                self.log.emit(f"第 {attempt} 次连接未成功，3 秒后自动重试…（请确认相机停在等待界面）")
                self._stop.wait(3)
        return False

    def _main_loop(self, handles: list[int]) -> None:
        idx = 0  # next handle to index / 待索引位置
        pending: list[PhotoInfo] = []
        downloads: tuple[list[tuple[int, str]], str, int] | None = None
        done_emitted = False
        indexed = 0

        while not self._stop.is_set():
            # 1. user-triggered tasks first (exif / download / stop) / 用户任务优先
            try:
                task = self._tasks.get_nowait()
            except queue.Empty:
                task = None
            if task:
                kind = task[0]
                if kind == "stop":
                    break
                if kind == "exif":
                    self._do_exif(task[1])
                    continue
                if kind == "download":
                    downloads = (list(task[1]), task[2], 0)
                    continue

            # 2. visible thumbnails / 可见区域缩略图
            handle = self._pop_thumb()
            if handle is not None:
                self._do_thumb(handle)
                continue

            # 3. one file of the active download / 下载队列逐个文件
            if downloads is not None:
                targets, folder, done = downloads
                if done >= len(targets):
                    self.dl_done.emit(done)
                    downloads = None
                    continue
                handle_, filename = targets[done]
                dest = os.path.join(folder, filename)
                try:
                    self.client.download(handle_, dest)
                    self.log.emit(f"下载 {filename} → {dest}")
                except CameraError as exc:
                    self.log.emit(f"[错误] 下载 {filename} 失败：{exc}")
                done += 1
                self.dl_progress.emit(done, len(targets), filename)
                downloads = (targets, folder, done)
                continue

            # 4. background indexing / 后台逐条建立索引
            if idx < len(handles):
                try:
                    info = self.client.get_object_info(handles[idx])
                    if info["assoc_type"] == 0:  # skip folder objects / 跳过目录
                        pending.append(PhotoInfo(
                            handle=handles[idx], filename=info["filename"],
                            size=info["size"], captured=info["captured"],
                            width=info["width"], height=info["height"],
                        ))
                except CameraError:
                    pass  # unreadable objects are skipped / 读不到的对象跳过
                idx += 1
                indexed = idx
                if len(pending) >= _BATCH:
                    self.index_batch.emit(pending, indexed)
                    pending = []
                continue
            if pending:
                self.index_batch.emit(pending, indexed)
                pending = []
            if not done_emitted:
                self.index_done.emit()
                done_emitted = True

            # 5. idle: block until a task arrives / 空闲时阻塞等任务
            try:
                task = self._tasks.get(timeout=0.3)
                self._tasks.put(task)  # re-queue, handled next iteration / 放回下一轮处理
                time.sleep(0.01)
            except queue.Empty:
                pass

    def _pop_thumb(self) -> int | None:
        with self._want_lock:
            while self._want_thumbs:
                handle = self._want_thumbs.pop(0)
                if handle not in self._thumb_skip:
                    self._thumb_skip.add(handle)
                    return handle
        return None

    def _do_thumb(self, handle: int) -> None:
        try:
            data = self.client.get_thumb(handle) or b""
            self.thumb_ready.emit(handle, data)
        except (CameraError, OSError):
            self.thumb_ready.emit(handle, b"")

    def _do_exif(self, handle: int) -> None:
        try:
            chunk = self.client.get_partial_object(handle, 0, _EXIF_BYTES)
            self.exif_ready.emit(handle, exifmod.parse_exif(chunk))
        except CameraError as exc:
            self.exif_ready.emit(handle, {"error": str(exc)})
