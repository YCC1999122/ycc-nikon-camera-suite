"""Offline-tolerant slippy-map widget (OpenStreetMap tiles) with a shooting-location pin.

Tiles are cached inside the project directory; when the network is unavailable the
widget falls back to a coordinate readout. Double-click opens the location in a browser.
/ 简易地图控件：加载 OSM 瓦片并标注拍摄位置；瓦片缓存在项目目录内，
离线时降级为坐标显示，双击可在浏览器中打开大图。
"""
from __future__ import annotations

import math
import os
import urllib.request

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from app.paths import project_root

PROJECT_ROOT = project_root()
CACHE_DIR = os.path.join(PROJECT_ROOT, "assets", "tile_cache")
TILE = 256
ZOOM = 15
UA = "NikonCameraSuite/1.1 (desktop photo manager)"


def _global_xy(lat: float, lon: float, z: int) -> tuple[float, float]:
    """Slippy-map global tile coordinates (fractional). / 经纬度转全局瓦片坐标"""
    n = 2 ** z
    fx = (lon + 180.0) / 360.0 * n
    r = math.radians(lat)
    fy = (1.0 - math.log(math.tan(r) + 1.0 / math.cos(r)) / math.pi) / 2.0 * n
    return fx, fy


class TileFetcher(QThread):
    """Download missing tiles in the background. / 后台下载缺失瓦片"""
    tile_done = Signal(int, int, str)  # tx, ty, local path ("" on failure)

    def __init__(self, tiles: list[tuple[int, int]], parent=None):
        super().__init__(parent)
        self._tiles = tiles

    def run(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        for tx, ty in self._tiles:
            path = os.path.join(CACHE_DIR, f"{ZOOM}_{tx}_{ty}.png")
            if not os.path.exists(path):
                url = f"https://tile.openstreetmap.org/{ZOOM}/{tx}/{ty}.png"
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=6) as resp:
                        payload = resp.read()
                    with open(path, "wb") as f:
                        f.write(payload)
                except Exception:  # noqa: BLE001 - offline just means no tile / 离线即无瓦片
                    path = ""
            self.tile_done.emit(tx, ty, path)


class MapWidget(QWidget):
    """3x3-tile map centered on the photo's GPS position. / 以拍摄点为中心的 3x3 瓦片地图"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(190)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("双击在浏览器中打开大地图")
        self._lat = 0.0
        self._lon = 0.0
        self._has = False
        self._tiles: dict[tuple[int, int], QPixmap | None] = {}
        self._pending = 0
        self._fetchers: list[TileFetcher] = []

    def set_location(self, lat: float, lon: float) -> None:
        self._lat, self._lon, self._has = lat, lon, True
        self._tiles.clear()
        fx, fy = _global_xy(lat, lon, ZOOM)
        cx, cy = int(fx), int(fy)
        want = [(cx + dx, cy + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)]
        self._pending = len(want)
        fetcher = TileFetcher(want, self)
        fetcher.tile_done.connect(self._on_tile)
        fetcher.finished.connect(lambda f=fetcher: self._drop(f))
        self._fetchers.append(fetcher)
        fetcher.start()
        self.update()

    def _drop(self, fetcher: TileFetcher) -> None:
        if fetcher in self._fetchers:
            self._fetchers.remove(fetcher)
        fetcher.deleteLater()

    def _on_tile(self, tx: int, ty: int, path: str) -> None:
        pix = QPixmap(path) if path else None
        if pix is not None and pix.isNull():
            pix = None
        self._tiles[(tx, ty)] = pix
        self._pending = max(0, self._pending - 1)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = self.rect()
        painter.fillRect(rect, QColor("#dbe4f0"))
        if not self._has:
            painter.setPen(QColor("#64748b"))
            painter.drawText(rect, Qt.AlignCenter, "选择带 GPS 的照片后显示拍摄地图")
            painter.end()
            return

        fx, fy = _global_xy(self._lat, self._lon, ZOOM)
        cx, cy = int(fx), int(fy)
        gx0, gy0 = (cx - 1) * TILE, (cy - 1) * TILE
        off_x = (3 * TILE - rect.width()) / 2
        off_y = (3 * TILE - rect.height()) / 2
        drew = 0
        for (tx, ty), pix in self._tiles.items():
            x = (tx - (cx - 1)) * TILE - off_x
            y = (ty - (cy - 1)) * TILE - off_y
            if pix:
                painter.drawPixmap(int(x), int(y), pix)
                drew += 1
            else:
                painter.fillRect(int(x), int(y), TILE, TILE, QColor("#e8eef8"))
        if drew == 0 and self._pending == 0:
            painter.setPen(QColor("#64748b"))
            painter.drawText(rect.adjusted(0, 0, 0, -28), Qt.AlignCenter,
                             "地图瓦片加载失败（可能无网络）\n双击可在浏览器中查看该位置")

        # location pin / 拍摄点标记
        mx = fx * TILE - gx0 - off_x
        my = fy * TILE - gy0 - off_y
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#ffffff"), 3))
        painter.setBrush(QColor("#ef4444"))
        painter.drawEllipse(int(mx) - 8, int(my) - 8, 16, 16)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(int(mx) - 3, int(my) - 3, 6, 6)

        # coordinate bar / 底部坐标条
        bar = QColor("#0f172a")
        bar.setAlpha(170)
        painter.fillRect(0, rect.height() - 24, rect.width(), 24, bar)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(rect.adjusted(8, 0, -8, 0),
                         Qt.AlignVCenter | Qt.AlignLeft,
                         f"{self._lat:.5f}, {self._lon:.5f} · 双击打开大地图")
        painter.end()

    def mouseDoubleClickEvent(self, event) -> None:
        if self._has:
            QDesktopServices.openUrl(QUrl(
                f"https://www.openstreetmap.org/?mlat={self._lat}&mlon={self._lon}"
                f"#map=16/{self._lat}/{self._lon}"))
        super().mouseDoubleClickEvent(event)
