"""Main window: sidebar navigation + content pages + right-side log panel.
Pages: connect / gallery (with camera info card) / shooting guide / about.
/ 主窗口：左侧导航 + 内容页 + 右侧日志面板。页面：设备连接 / 照片管理（含相机信息卡）/ 摄影助手 / 关于"""
from __future__ import annotations

import os
import time
from collections import OrderedDict

from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QFileDialog,
                               QFrame, QGridLayout, QHBoxLayout, QInputDialog,
                               QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMainWindow, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea,
                               QSizePolicy, QSlider, QStackedWidget,
                               QTextBrowser, QVBoxLayout, QWidget)

from app import discovery, storage, theme
from app.client import PhotoInfo
from app.effects import (AnimatedProgressBar, HoverButton, ParticleField,
                         fade_in)
from app.mapwidget import MapWidget
from app.paths import project_root
from app.session import CameraSession

PROJECT_ROOT = project_root()
DOWNLOAD_DIR = os.path.join(PROJECT_ROOT, "downloads")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
APP_VERSION = "1.1.0"
_THUMB_CACHE_MAX = 3000  # in-memory thumbnail cap / 内存缩略图缓存上限

HELP_HTML = """
<h2 style="color:#2563eb;">使用说明</h2>
<h3>一、首次使用：相机配对（仅需一次）</h3>
<ol>
<li>下载并安装尼康官方免费软件 <b>Wireless Transmitter Utility (WTU)</b>（尼康下载中心可获取）。</li>
<li>相机：网络菜单 → <b>连接至 PC</b> → 网络设定 → <b>新建配置文件</b> → 搜索网络 → 选择路由器 WiFi → 输入密码 → 自动获取 IP → 停在等待界面。</li>
<li>电脑：打开 WTU → 选择相机 → 输入相机屏幕上的<b>验证码</b> → 配对完成。此后配置文件永久保存在相机中。</li>
</ol>
<h3>二、日常传输</h3>
<ol>
<li>相机：网络菜单 → 连接至 PC → <b>选择已保存的配置文件</b> → 等待连接。</li>
<li>本软件：在「设备连接」页搜索相机（或点已保存相机的「连接」）→ 连接成功后自动进入「照片管理」。</li>
<li>「下载选中」自动带上同名 RAW/JPG 配对文件；「下载全部」下载当前格式筛选可见部分。</li>
</ol>
<h3>三、常见问题</h3>
<ul>
<li><b>搜索不到？</b>确认电脑与相机在同一局域网，且相机已进入连接向导等待界面。</li>
<li><b>连接一直重试？</b>相机向导是一次性的，槽位被占后需在相机上重新进入连接向导；软件会自动重试 60 秒。</li>
<li><b>相机信息不显示？</b>连接成功后自动读取型号/固件/序列号，部分老机型可能不支持。</li>
</ul>
"""

GUIDE_DATA = [
    ("人像写真", "光圈 f/1.8–f/2.8 · 快门 ≥1/125s · ISO 自动",
     "开大光圈虚化背景；人眼侦测对焦；点测光对脸部；逆光记得曝光补偿 +0.7EV。"),
    ("风光建筑", "光圈 f/8–f/11 · 快门 安全或三脚架 · ISO 100",
     "小光圈保证全景深；上三脚架用低感；高反差场景开包围曝光后期合成。"),
    ("夜景弱光", "光圈 f/1.4–f/2.8（手持）或 f/8（三脚架）· 快门 1/60s 或长曝",
     "手持开高 ISO 保快门；三脚架低感长曝；长曝降噪建议开启。"),
    ("街头快拍", "光圈 f/5.6–f/8 · 快门 ≥1/250s · ISO 自动上限 3200",
     "超焦距估焦快速抓拍；静音快门不打扰；连拍抓决定性瞬间。"),
    ("运动生态", "快门 ≥1/1000s · AF-C 连续对焦 · 高速连拍",
     "高速快门凝固动作；广域对焦区域；适当提高 ISO 保证快门速度。"),
    ("微距静物", "光圈 f/8–f/11 · 手动对焦微调 · 防抖开启",
     "微距景深极浅，收小光圈；对焦包围可后期堆栈；注意补光。"),
]

MAINTENANCE_TIPS = [
    "定期用气流吹清洁镜头与卡口，传感器清洁交给专业渠道",
    "长期不用时取出电池并保持 50% 左右电量存放",
    "关注尼康官网固件更新，升级前备份设置并保证电量充足",
    "存储卡在相机内格式化，重要照片双备份（电脑 + 云/移动硬盘）",
    "避免高温潮湿环境，雨天拍摄后及时擦干并放入干燥箱",
]


def camera_image_path(model: str) -> str:
    """Pick a bundled camera illustration by model name. / 按型号匹配内置相机图"""
    key = (model or "").lower().replace(" ", "").replace("_", "")
    if "zfc" in key:
        return os.path.join(ASSETS_DIR, "camera_zfc.jpg")
    return os.path.join(ASSETS_DIR, "camera_generic.jpg")


class BgPage(QWidget):
    """Content page painting the theme background image + overlay.
    / 内容页基座：绘制主题背景图与统一遮罩，保证全局配色一致"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix: QPixmap | None = None
        self._overlay = QColor("#f4f8ff")
        self._overlay.setAlpha(215)
        self._content_layout: QVBoxLayout | None = None

    def set_theme(self, palette: dict, project_root: str) -> None:
        path = os.path.join(project_root, palette["bg_image"])
        self._pix = QPixmap(path) if os.path.exists(path) else None
        self._overlay = QColor(palette["overlay"])
        self._overlay.setAlpha(215)
        self.update()

    def set_content(self, widget: QWidget) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(widget)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        if self._pix and not self._pix.isNull():
            scaled = self._pix.scaled(self.size(), Qt.KeepAspectRatioByExpanding,
                                      Qt.SmoothTransformation)
            painter.drawPixmap(self.rect(), scaled)
        painter.fillRect(self.rect(), self._overlay)
        painter.end()


class PhotoGrid(QListWidget):
    """Thumbnail grid with Ctrl+wheel tile zoom. / 缩略图网格：Ctrl+滚轮调整预览大小"""
    zoom_step = Signal(int)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            self.zoom_step.emit(1 if event.angleDelta().y() > 0 else -1)
            event.accept()
            return
        super().wheelEvent(event)


class Worker(QThread):
    """Runs blocking network work off the GUI thread. / 网络操作放到工作线程避免卡界面"""
    log = Signal(str)
    failed = Signal(str)
    cameras_found = Signal(list)
    photos_ready = Signal(object, bool)
    progress = Signal(int, int, str)
    done = Signal(str)

    def __init__(self, job):
        super().__init__()
        self._job = job

    def run(self):
        try:
            self._job(self)
        except Exception as exc:  # noqa: BLE001 - surface all worker errors to the log
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("尼康相机管理")
        self.resize(1360, 820)
        self.session: CameraSession | None = None
        self.cam_info: dict = {}
        self.photos: list[PhotoInfo] = []
        self._by_handle: dict[int, PhotoInfo] = {}
        self._workers: list[Worker] = []
        self._thumbs: OrderedDict[int, QPixmap] = OrderedDict()
        self._exif_cache: dict[int, dict] = {}
        self._item_by_handle: dict[int, QListWidgetItem] = {}
        self._placeholders: dict[tuple[str, int], QPixmap] = {}
        self._total_handles = 0
        self._indexed = 0
        self._dates: set[str] = set()
        self._zoom = int(storage.get_setting("zoom", 168) or 168)
        self.theme_name = storage.get_setting("theme", "light")

        # debounce timers / 防抖定时器
        self._thumb_timer = QTimer(self, singleShot=True)
        self._thumb_timer.timeout.connect(self._request_visible_thumbs)
        self._refresh_timer = QTimer(self, singleShot=True)
        self._refresh_timer.timeout.connect(self._refresh_grid)
        self._date_timer = QTimer(self, singleShot=True)
        self._date_timer.timeout.connect(self._refresh_date_combo)

        self._build_menus()
        self._build_ui()
        self.apply_theme()
        self.refresh_device_list()
        self._log("就绪。在「设备连接」页搜索相机，首次使用请阅读 帮助 → 使用说明。")

    # ---- menus / 菜单栏 ----

    def _build_menus(self):
        bar = self.menuBar()
        m_file = bar.addMenu("文件(&F)")
        m_file.addAction("打开下载目录", self.on_open_downloads)
        m_file.addAction("选择保存位置…", self.on_browse)
        m_file.addSeparator()
        m_file.addAction("退出", self.close)
        m_help = bar.addMenu("帮助(&H)")
        m_help.addAction("使用说明", self.on_help)
        m_help.addAction("关于", lambda: self._nav_to(3))

    # ---- UI construction / 界面搭建 ----

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # sidebar / 左侧导航栏
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sb = QVBoxLayout(sidebar)
        sb.setContentsMargins(14, 22, 14, 16)
        sb.setSpacing(6)
        title = QLabel("尼康相机管理")
        title.setObjectName("appTitle")
        sub = QLabel("Nikon Camera Suite")
        sub.setObjectName("appSub")
        sb.addWidget(title)
        sb.addWidget(sub)
        self.status_label = QLabel("● 未连接")
        self.status_label.setObjectName("appSub")
        sb.addWidget(self.status_label)
        sb.addSpacing(18)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_buttons: list[QPushButton] = []
        for i, text in enumerate(["设备连接", "照片管理", "摄影助手", "关于软件"]):
            btn = QPushButton(text)
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, idx=i: self._nav_to(idx))
            self.nav_group.addButton(btn, i)
            self.nav_buttons.append(btn)
            sb.addWidget(btn)
        self.nav_buttons[0].setChecked(True)
        sb.addStretch(1)
        self.btn_theme = QPushButton("切换主题")
        self.btn_theme.setObjectName("nav")
        self.btn_theme.clicked.connect(self.toggle_theme)
        sb.addWidget(self.btn_theme)
        root.addWidget(sidebar)

        # center content pages / 中间内容页
        self.stack = QStackedWidget()
        self.page_connect = self._wrap_bg(self._build_connect_page())
        self.page_gallery = self._wrap_bg(self._build_gallery_page())
        self.page_guide = self._wrap_bg(self._build_guide_page())
        self.page_about = self._wrap_bg(self._build_about_page())
        for p in (self.page_connect, self.page_gallery, self.page_guide, self.page_about):
            self.stack.addWidget(p)
        root.addWidget(self.stack, 1)

        # right log panel / 右侧日志面板
        log_card = QFrame()
        log_card.setObjectName("card")
        log_card.setFixedWidth(300)
        lc = QVBoxLayout(log_card)
        lc.setContentsMargins(14, 14, 14, 14)
        head = QHBoxLayout()
        head.addWidget(self._section_label("运行日志"))
        head.addStretch(1)
        btn_clear = QPushButton("清空")
        btn_clear.setObjectName("mini")
        btn_clear.clicked.connect(lambda: self.log_view.clear())
        head.addWidget(btn_clear)
        lc.addLayout(head)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("logPanel")
        self.log_view.setReadOnly(True)
        lc.addWidget(self.log_view, 1)
        root.addWidget(log_card)

    def _wrap_bg(self, content: QWidget) -> BgPage:
        page = BgPage()
        page.set_content(content)
        return page

    @staticmethod
    def _section_label(text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("section")
        return lab

    def _nav_to(self, index: int):
        self.nav_buttons[index].setChecked(True)
        self.stack.setCurrentIndex(index)
        fade_in(self.stack.currentWidget())

    # ---- connect page / 设备连接页 ----

    def _build_connect_page(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 26, 32, 26)
        lay.setSpacing(14)

        hero = QLabel("连接你的尼康相机")
        hero.setObjectName("hero")
        subtitle = QLabel("相机进入「连接至 PC」向导后，搜索并连接即可开始管理（首次使用见 帮助 → 使用说明）")
        subtitle.setObjectName("subtitle")
        lay.addWidget(hero)
        lay.addWidget(subtitle)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(12)
        row1 = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setMinimumWidth(300)
        self.btn_scan = HoverButton("搜索相机")
        row1.addWidget(QLabel("发现的设备:"))
        row1.addWidget(self.combo, 1)
        row1.addWidget(self.btn_scan)
        cl.addLayout(row1)
        row2 = QHBoxLayout()
        row2.addStretch(1)
        self.btn_connect = HoverButton("连接")
        self.btn_connect.setMinimumWidth(140)
        row2.addWidget(self.btn_connect)
        cl.addLayout(row2)
        lay.addWidget(card)

        lay.addWidget(self._section_label("已保存的相机"))
        self.device_list = QListWidget()
        self.device_list.setObjectName("deviceList")
        self.device_list.setSpacing(8)
        lay.addWidget(self.device_list, 1)

        self.particles_connect = ParticleField(content, count=40)
        self.particles_connect.lower()  # behind content widgets / 置于内容下方
        self.particles_connect.setGeometry(0, 0, 600, 400)

        self.btn_scan.clicked.connect(self.on_scan)
        self.btn_connect.clicked.connect(self.on_connect)
        return content

    # ---- gallery page / 照片管理页 ----

    def _build_gallery_page(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(10)

        # camera info card / 相机信息卡
        info_card = QFrame()
        info_card.setObjectName("card")
        ic = QHBoxLayout(info_card)
        ic.setContentsMargins(18, 14, 18, 14)
        self.cam_img = QLabel()
        self.cam_img.setFixedSize(120, 90)
        self.cam_img.setScaledContents(False)
        self.cam_img.setAlignment(Qt.AlignCenter)
        ic.addWidget(self.cam_img)
        col = QVBoxLayout()
        self.cam_model = QLabel("未连接相机")
        self.cam_model.setObjectName("camModel")
        self.cam_detail = QLabel("连接后显示型号 / 固件 / 序列号")
        self.cam_detail.setObjectName("dim")
        col.addWidget(self.cam_model)
        col.addWidget(self.cam_detail)
        col.addStretch(1)
        ic.addLayout(col, 1)
        self.btn_back = QPushButton("断开连接")
        self.btn_back.setObjectName("ghost")
        ic.addWidget(self.btn_back, alignment=Qt.AlignTop)
        lay.addWidget(info_card)

        # toolbar: filters + zoom + downloads / 工具栏：筛选 + 缩放 + 下载
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.combo_fmt = QComboBox()
        self.combo_fmt.addItems(["全部格式", "仅 JPG", "仅 NEF (RAW)"])
        self.combo_fmt.setMinimumWidth(110)
        self.combo_date = QComboBox()
        self.combo_date.addItem("全部日期")
        self.combo_date.setMinimumWidth(130)
        self.combo_sort = QComboBox()
        self.combo_sort.addItems(["拍摄时间：新→旧", "拍摄时间：旧→新", "文件名", "文件大小"])
        self.combo_sort.setMinimumWidth(140)
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("搜索文件名…")
        self.edit_search.setMaximumWidth(170)
        row1.addWidget(self.combo_fmt)
        row1.addWidget(self.combo_date)
        row1.addWidget(self.combo_sort)
        row1.addWidget(self.edit_search)
        row1.addStretch(1)
        row1.addWidget(QLabel("预览大小"))
        self.slider_zoom = QSlider(Qt.Horizontal)
        self.slider_zoom.setRange(96, 320)
        self.slider_zoom.setSingleStep(16)
        self.slider_zoom.setValue(self._zoom)
        self.slider_zoom.setFixedWidth(130)
        row1.addWidget(self.slider_zoom)
        self.btn_dl_sel = HoverButton("下载选中")
        self.btn_dl_all = HoverButton("下载全部")
        row1.addWidget(self.btn_dl_sel)
        row1.addWidget(self.btn_dl_all)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        self.edit_folder = QLineEdit(DOWNLOAD_DIR)
        self.btn_browse = QPushButton("浏览…")
        self.btn_browse.setObjectName("ghost")
        row2.addWidget(QLabel("保存到:"))
        row2.addWidget(self.edit_folder, 1)
        row2.addWidget(self.btn_browse)
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("countLabel")
        row2.addWidget(self.lbl_count)
        lay.addLayout(row2)

        # body: grid + photo info panel / 主体：网格 + 右侧照片详情
        body = QHBoxLayout()
        body.setSpacing(10)
        self.list = PhotoGrid()
        self.list.setObjectName("photoGrid")
        self.list.setViewMode(QListView.IconMode)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setMovement(QListView.Static)
        self.list.setSelectionMode(QListView.ExtendedSelection)
        self.list.setSpacing(8)
        self.list.setUniformItemSizes(True)
        self._apply_zoom(self._zoom, save=False)
        body.addWidget(self.list, 1)
        body.addWidget(self._build_info_panel())
        lay.addLayout(body, 1)

        self.progress_bar = AnimatedProgressBar()
        self.progress_bar.setValue(0)
        lay.addWidget(self.progress_bar)

        self.btn_back.clicked.connect(self.on_disconnect)
        self.btn_browse.clicked.connect(self.on_browse)
        self.combo_fmt.currentIndexChanged.connect(lambda _i: self._refresh_grid())
        self.combo_date.currentIndexChanged.connect(lambda _i: self._refresh_grid())
        self.combo_sort.currentIndexChanged.connect(lambda _i: self._refresh_grid())
        self.edit_search.textChanged.connect(lambda _t: self._refresh_timer.start(300))
        self.slider_zoom.valueChanged.connect(self._apply_zoom)
        self.list.zoom_step.connect(self._on_zoom_step)
        self.btn_dl_sel.clicked.connect(lambda: self.on_download(True))
        self.btn_dl_all.clicked.connect(lambda: self.on_download(False))
        self.list.currentItemChanged.connect(self._on_select)
        self.list.verticalScrollBar().valueChanged.connect(
            lambda _v: self._thumb_timer.start(120))
        self.list.viewport().installEventFilter(self)
        return content

    def _build_info_panel(self) -> QFrame:
        """Right-side photo detail card: preview, EXIF params, GPS map.
        / 右侧照片详情卡：预览、拍摄参数、GPS 地图"""
        card = QFrame()
        card.setObjectName("card")
        card.setFixedWidth(300)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(8)

        v.addWidget(self._section_label("照片详情"))
        self.info_preview = QLabel("选择照片")
        self.info_preview.setObjectName("dim")
        self.info_preview.setFixedHeight(168)
        self.info_preview.setAlignment(Qt.AlignCenter)
        v.addWidget(self.info_preview)
        self.info_name = QLabel("未选择照片")
        self.info_name.setObjectName("infoName")
        self.info_name.setWordWrap(True)
        v.addWidget(self.info_name)
        self.info_basic = QLabel("点击左侧任意照片，此处显示拍摄参数")
        self.info_basic.setObjectName("dim")
        self.info_basic.setWordWrap(True)
        v.addWidget(self.info_basic)

        gridw = QWidget()
        g = QGridLayout(gridw)
        g.setContentsMargins(0, 4, 0, 4)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(5)
        self._exif_vals: dict[str, QLabel] = {}
        rows = [("datetime", "拍摄时间"), ("program", "曝光模式"), ("fnumber", "光圈"),
                ("shutter", "快门"), ("iso", "ISO"), ("focal", "焦距"),
                ("focal35", "等效焦距"), ("bias", "曝光补偿"), ("lens", "镜头"),
                ("metering", "测光"), ("wb", "白平衡"), ("flash", "闪光灯")]
        for r, (key, label) in enumerate(rows):
            k = QLabel(label)
            k.setObjectName("exifKey")
            val = QLabel("—")
            val.setObjectName("exifVal")
            val.setWordWrap(True)
            g.addWidget(k, r, 0)
            g.addWidget(val, r, 1)
            self._exif_vals[key] = val
        g.setColumnStretch(1, 1)
        v.addWidget(gridw)

        self.gps_head = self._section_label("拍摄位置")
        self.map = MapWidget()
        self.gps_note = QLabel("")
        self.gps_note.setObjectName("dim")
        self.gps_note.setWordWrap(True)
        v.addWidget(self.gps_head)
        v.addWidget(self.map)
        v.addWidget(self.gps_note)
        self._show_gps_block(False)
        v.addStretch(1)
        scroll.setWidget(inner)
        outer.addWidget(scroll)
        return card

    def _show_gps_block(self, show: bool) -> None:
        for w in (self.gps_head, self.map, self.gps_note):
            w.setVisible(show)

    # ---- guide page / 摄影助手页 ----

    def _build_guide_page(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 26, 32, 26)
        lay.setSpacing(12)
        hero = QLabel("摄影助手")
        hero.setObjectName("hero")
        sub = QLabel("常见拍摄场景的推荐参数与相机日常维护建议（以 Z fc 为参考，可按需调整）")
        sub.setObjectName("subtitle")
        lay.addWidget(hero)
        lay.addWidget(sub)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        grid = QVBoxLayout(inner)
        grid.setSpacing(10)
        for name, params, tips in GUIDE_DATA:
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(18, 14, 18, 14)
            cl.setSpacing(6)
            t = QLabel(name)
            t.setObjectName("deviceName")
            p = QLabel(params)
            p.setStyleSheet("color: #2563eb; font-weight: 600;")
            d = QLabel(tips)
            d.setObjectName("dim")
            d.setWordWrap(True)
            cl.addWidget(t)
            cl.addWidget(p)
            cl.addWidget(d)
            grid.addWidget(card)

        mcard = QFrame()
        mcard.setObjectName("card")
        ml = QVBoxLayout(mcard)
        ml.setContentsMargins(18, 14, 18, 14)
        ml.setSpacing(6)
        mt = QLabel("相机日常维护")
        mt.setObjectName("deviceName")
        ml.addWidget(mt)
        for tip in MAINTENANCE_TIPS:
            lab = QLabel("· " + tip)
            lab.setObjectName("dim")
            lab.setWordWrap(True)
            ml.addWidget(lab)
        grid.addWidget(mcard)
        grid.addStretch(1)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        return content

    # ---- about page / 关于页 ----

    def _build_about_page(self) -> QWidget:
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(32, 26, 32, 26)
        lay.setSpacing(12)
        hero = QLabel("关于软件")
        hero.setObjectName("hero")
        lay.addWidget(hero)
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(22, 18, 22, 18)
        cl.setSpacing(8)
        for text in [
            f"尼康相机管理 · 版本 {APP_VERSION}",
            "基于 PTP/IP（ISO 15740）协议与尼康 Wi-Fi 相机通信",
            "功能：设备搜索与记忆、相机信息读取、照片浏览与高速下载、RAW/JPG 配对、格式筛选",
            "扩展：摄影场景参数助手、相机日常维护指南",
            "技术栈：Python + PySide6，全部依赖与资源内置于项目目录，便于打包迁移",
        ]:
            lab = QLabel(text)
            lab.setWordWrap(True)
            cl.addWidget(lab)
        cl.addStretch(1)
        lay.addWidget(card)
        lay.addStretch(1)
        return content

    # ---- theme / 主题 ----

    def apply_theme(self):
        self.setStyleSheet(theme.stylesheet(self.theme_name))
        c = theme.palette(self.theme_name)
        self.particles_connect.setColor(QColor(c["accent"]))
        self.progress_bar.setColors(QColor(c["track"]), QColor(c["accent2"]),
                                    QColor(c["accent"]))
        for page in (self.page_connect, self.page_gallery, self.page_guide, self.page_about):
            page.set_theme(c, PROJECT_ROOT)
        self._render_status()

    def toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        storage.set_setting("theme", self.theme_name)
        self.apply_theme()
        self._log(f"已切换到{'深色' if self.theme_name == 'dark' else '浅色'}主题。")

    # ---- helpers / 辅助 ----

    def _log(self, msg: str):
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def _render_status(self):
        if self.session:
            self.status_label.setText(f"● 已连接 {self.session.client.camera_name}")
            self.status_label.setStyleSheet("color: #4ade80; font-weight: 600;")
        else:
            self.status_label.setText("● 未连接")
            self.status_label.setStyleSheet("")

    def _set_busy(self, busy: bool):
        # only the connect-page buttons lock; the gallery stays interactive / 只锁定连接页按钮
        for btn in (self.btn_scan, self.btn_connect):
            btn.setEnabled(not busy)

    def _start_worker(self, job) -> Worker:
        worker = Worker(job)
        self._workers.append(worker)
        worker.finished.connect(lambda wk=worker: self._workers.remove(wk))
        worker.log.connect(self._log)
        worker.failed.connect(lambda msg: (self._log(f"[错误] {msg}"), self._set_busy(False)))
        worker.done.connect(lambda _msg: self._set_busy(False))
        worker.finished.connect(worker.deleteLater)
        self._set_busy(True)
        worker.start()
        return worker

    def _placeholder(self, filename: str) -> QPixmap:
        """Colored tile with the file extension, used until the real thumb arrives.
        / 缩略图到达前的占位图（底色 + 扩展名）"""
        ext = filename.rpartition(".")[2].upper() or "IMG"
        key = (ext, self._zoom)
        pix = self._placeholders.get(key)
        if pix:
            return pix
        w, h = self._zoom, int(self._zoom * 0.75)
        pix = QPixmap(w, h)
        color = QColor("#93c5fd") if ext in ("JPG", "JPEG") else QColor("#c4b5fd")
        pix.fill(color)
        painter = QPainter(pix)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(pix.rect(), Qt.AlignCenter, ext)
        painter.end()
        self._placeholders[key] = pix
        return pix

    def _update_camera_card(self):
        """Fill the gallery info card from the active session. / 更新相机信息卡"""
        info = self.cam_info
        if not self.session:
            self.cam_model.setText("未连接相机")
            self.cam_detail.setText("连接后显示型号 / 固件 / 序列号")
            self.cam_img.clear()
            return
        model = info.get("model") or self.session.client.camera_name
        lines = []
        if info.get("manufacturer"):
            lines.append(info["manufacturer"])
        if info.get("firmware"):
            lines.append(f"固件 {info['firmware']}")
        if info.get("serial"):
            lines.append(f"序列号 {info['serial']}")
        lines.append(f"IP {self.session.ip}")
        if info.get("error"):
            lines.append("（设备详情读取失败，仅显示基本信息）")
        self.cam_model.setText(model or self.session.client.camera_name)
        self.cam_detail.setText("  ·  ".join(lines))
        pix = QPixmap(camera_image_path(model or self.session.client.camera_name))
        if not pix.isNull():
            self.cam_img.setPixmap(pix.scaled(120, 90, Qt.KeepAspectRatio,
                                              Qt.SmoothTransformation))

    # ---- saved camera list / 设备记忆 ----

    def refresh_device_list(self):
        self.device_list.clear()
        devices = storage.load_devices()
        if not devices:
            item = QListWidgetItem("暂无保存的相机 —— 连接成功后会自动记录到此处")
            item.setFlags(Qt.NoItemFlags)
            self.device_list.addItem(item)
            return
        for dev in devices:
            item = QListWidgetItem()
            card = self._device_card(dev)
            item.setSizeHint(card.sizeHint() + QSize(8, 8))
            self.device_list.addItem(item)
            self.device_list.setItemWidget(item, card)

    def _device_card(self, dev: dict) -> QWidget:
        card = QFrame()
        card.setObjectName("deviceCard")
        lay = QHBoxLayout(card)
        lay.setContentsMargins(14, 10, 14, 10)
        img = QLabel()
        img.setFixedSize(72, 54)
        pix = QPixmap(camera_image_path(dev.get("model") or dev.get("name", "")))
        if not pix.isNull():
            img.setPixmap(pix.scaled(72, 54, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        lay.addWidget(img)
        info = QVBoxLayout()
        name = QLabel(dev.get("name") or dev["ip"])
        name.setObjectName("deviceName")
        detail = f"{dev['ip']}  ·  {dev.get('model') or '未知型号'}  ·  上次连接 {dev.get('last_connected', '-')}"
        if dev.get("note"):
            detail += f"  ·  备注：{dev['note']}"
        sub = QLabel(detail)
        sub.setObjectName("dim")
        info.addWidget(name)
        info.addWidget(sub)
        lay.addLayout(info, 1)

        for text, slot in (("详情", lambda ip=dev["ip"]: self._show_device_detail(ip)),
                           ("备注", lambda ip=dev["ip"], old=dev.get("note", ""): self._edit_note(ip, old)),
                           ("删除", lambda ip=dev["ip"]: self._remove_device(ip)),
                           ("连接", lambda ip=dev["ip"]: self._connect_ip(ip))):
            btn = QPushButton(text)
            btn.setObjectName("mini")
            btn.clicked.connect(lambda _=False, s=slot: s())
            lay.addWidget(btn)
        return card

    def _show_device_detail(self, ip: str):
        dev = next((d for d in storage.load_devices() if d["ip"] == ip), None)
        if not dev:
            return
        live = ""
        if self.session and self.session.ip == ip and self.cam_info:
            i = self.cam_info
            live = (f"<hr><b>当前连接读取：</b><br>厂商：{i.get('manufacturer', '-')}"
                    f"<br>型号：{i.get('model', '-')}<br>固件：{i.get('firmware', '-')}"
                    f"<br>序列号：{i.get('serial', '-')}")
        dlg = QMessageBox(self)
        dlg.setWindowTitle("设备详情")
        dlg.setTextFormat(Qt.RichText)
        dlg.setText(f"<b>{dev.get('name') or ip}</b><br>IP：{ip}"
                    f"<br>型号：{dev.get('model') or '未知'}"
                    f"<br>备注：{dev.get('note') or '无'}"
                    f"<br>上次连接：{dev.get('last_connected', '-')}{live}")
        dlg.exec()

    def _edit_note(self, ip: str, old: str):
        note, ok = QInputDialog.getText(self, "设备备注", "为这台相机添加备注：", text=old)
        if ok:
            storage.set_note(ip, note.strip())
            self.refresh_device_list()

    def _remove_device(self, ip: str):
        storage.remove_device(ip)
        self.refresh_device_list()
        self._log(f"已删除保存的设备 {ip}")

    def _connect_ip(self, ip: str):
        for i in range(self.combo.count()):
            if self.combo.itemData(i) == ip:
                self.combo.setCurrentIndex(i)
                self.on_connect()
                return
        self.combo.addItem(f"已保存设备  ({ip})", ip)
        self.combo.setCurrentIndex(self.combo.count() - 1)
        self.on_connect()

    # ---- actions / 操作 ----

    def on_scan(self):
        def job(w: Worker):
            w.log.emit("正在扫描局域网内的相机…")
            found = discovery.scan()
            w.cameras_found.emit(found)
            w.done.emit("扫描完成")

        worker = self._start_worker(job)
        worker.cameras_found.connect(self._on_cameras_found)

    def _on_cameras_found(self, found: list):
        self.combo.clear()
        for ip, name in found:
            self.combo.addItem(f"{name}  ({ip})", ip)
        if found:
            self._log(f"发现 {len(found)} 台候选设备。请在相机上进入「连接至 PC」向导后点「连接」。")
        else:
            self._log("未发现设备。请确认相机已通过 Wi-Fi 连入同一网络并处于连接向导界面。")

    def on_connect(self):
        if self.session:
            self._log("已处于连接状态。")
            return
        ip = self.combo.currentData()
        if not ip:
            self._log("请先搜索并选择一台相机。")
            return
        self._reset_gallery_state()
        session = CameraSession(ip, self)
        session.log.connect(self._log)
        session.failed.connect(self._on_session_failed)
        session.session_ready.connect(self._on_session_ready)
        session.handles_total.connect(self._on_handles_total)
        session.index_batch.connect(self._on_index_batch)
        session.index_done.connect(self._on_index_done)
        session.thumb_ready.connect(self._on_thumb_ready)
        session.exif_ready.connect(self._on_exif_ready)
        session.dl_progress.connect(self._on_progress)
        session.dl_done.connect(self._on_dl_done)
        session.finished.connect(self._on_session_finished)
        self.session = session
        self._render_status()
        self._log("正在连接相机（自动重试 60 秒）…")
        session.start()

    def _reset_gallery_state(self):
        self.photos = []
        self._by_handle.clear()
        self._item_by_handle.clear()
        self._thumbs.clear()
        self._exif_cache.clear()
        self._dates.clear()
        self._total_handles = 0
        self._indexed = 0
        self.list.clear()
        self.combo_date.blockSignals(True)
        self.combo_date.clear()
        self.combo_date.addItem("全部日期")
        self.combo_date.blockSignals(False)
        self._update_count()

    def _on_session_ready(self, camera_name: str, info: dict):
        self.cam_info = info
        model = info.get("model") or camera_name
        if info.get("model"):
            self._log(f"设备信息：{info.get('manufacturer', '')} {info['model']} "
                      f"固件 {info.get('firmware', '-')}")
        storage.upsert_device(self.session.ip, camera_name, model=model)
        self.refresh_device_list()
        self._update_camera_card()
        self._nav_to(1)

    def _on_handles_total(self, total: int):
        self._total_handles = total
        self._log(f"相机内共 {total} 个对象，正在后台建立索引（可立即开始浏览，缩略图随滚动加载）…")
        self._update_count()

    def _on_index_batch(self, batch: list, indexed: int):
        self._indexed = indexed
        for photo in batch:
            self._by_handle[photo.handle] = photo
            self.photos.append(photo)
            date = self._date_of(photo)
            if date:
                self._dates.add(date)
        if self._default_view():
            for photo in batch:
                self._add_grid_item(photo)
        else:
            self._refresh_timer.start(600)
        self._date_timer.start(700)
        self._update_count()

    def _on_index_done(self):
        n_jpg = sum(1 for p in self.photos if p.filename.upper().endswith((".JPG", ".JPEG")))
        n_raw = sum(1 for p in self.photos if p.filename.upper().endswith((".NEF", ".NRW")))
        self._log(f"索引完成：共 {len(self.photos)} 张照片（JPG {n_jpg} / RAW {n_raw}）。"
                  "上下滚动浏览全部，Ctrl+滚轮可调整预览大小。")
        if not self._default_view():
            self._refresh_grid()
        self._date_timer.start(100)
        self._update_count()

    def _on_thumb_ready(self, handle: int, data: bytes):
        if not data:
            return
        img = QImage.fromData(data)
        if img.isNull():
            return
        pix = QPixmap.fromImage(img)
        self._thumbs[handle] = pix
        self._thumbs.move_to_end(handle)
        while len(self._thumbs) > _THUMB_CACHE_MAX:
            self._thumbs.popitem(last=False)
        item = self._item_by_handle.get(handle)
        if item:
            item.setIcon(QIcon(pix))
        current = self.list.currentItem()
        if current and current.data(Qt.UserRole) == handle:
            self._set_preview(handle)

    def _on_exif_ready(self, handle: int, meta: dict):
        self._exif_cache[handle] = meta
        current = self.list.currentItem()
        if current and current.data(Qt.UserRole) == handle:
            self._fill_exif(meta)

    def _on_session_failed(self, msg: str):
        self._log(f"[错误] {msg}")

    def _on_session_finished(self):
        if self.session:
            self.session.deleteLater()
            self.session = None
        self.cam_info = {}
        self._render_status()
        self._update_camera_card()

    def on_disconnect(self):
        session = self.session
        if session:
            self._log("正在断开连接…")
            session.stop()
            session.wait(5000)
            if session.isRunning():
                self._log("[提示] 断开超时，已强制结束会话线程")
                session.terminate()
                session.wait(1000)
            self._on_session_finished()
        self.photos = []
        self._by_handle.clear()
        self.list.clear()
        self._nav_to(0)
        self._log("已断开。下次连接前请在相机上重新进入连接向导。")

    # ---- gallery / 照片管理 ----

    @staticmethod
    def _fmt_match(photo: PhotoInfo, mode: str) -> bool:
        name = photo.filename.upper()
        if mode == "仅 JPG":
            return name.endswith((".JPG", ".JPEG"))
        if mode == "仅 NEF (RAW)":
            return name.endswith((".NEF", ".NRW"))
        return True

    @staticmethod
    def _date_of(photo: PhotoInfo) -> str:
        c = photo.captured  # PTP format YYYYMMDDTHHMMSS
        return f"{c[0:4]}-{c[4:6]}-{c[6:8]}" if len(c) >= 8 else ""

    @staticmethod
    def _fmt_captured(photo: PhotoInfo) -> str:
        c = photo.captured
        if len(c) >= 13:
            return f"{c[0:4]}-{c[4:6]}-{c[6:8]} {c[9:11]}:{c[11:13]}"
        return c or "未知时间"

    def _default_view(self) -> bool:
        return (self.combo_fmt.currentIndex() == 0
                and self.combo_date.currentIndex() == 0
                and self.combo_sort.currentIndex() == 0
                and not self.edit_search.text().strip())

    def _visible_photos(self) -> list[PhotoInfo]:
        mode = self.combo_fmt.currentText()
        date = self.combo_date.currentText()
        term = self.edit_search.text().strip().upper()
        out = []
        for p in self.photos:
            if not self._fmt_match(p, mode):
                continue
            if self.combo_date.currentIndex() > 0 and self._date_of(p) != date:
                continue
            if term and term not in p.filename.upper():
                continue
            out.append(p)
        idx = self.combo_sort.currentIndex()
        if idx == 1:
            out.sort(key=lambda p: (p.captured, p.filename))
        elif idx == 2:
            out.sort(key=lambda p: p.filename)
        elif idx == 3:
            out.sort(key=lambda p: -p.size)
        return out  # idx 0 keeps arrival order (newest first) / 默认即最新在前

    def _add_grid_item(self, photo: PhotoInfo) -> QListWidgetItem:
        pix = self._thumbs.get(photo.handle)
        icon = QIcon(pix) if pix else QIcon(self._placeholder(photo.filename))
        item = QListWidgetItem(icon, f"{photo.filename}\n{self._fmt_captured(photo)}")
        item.setData(Qt.UserRole, photo.handle)
        item.setToolTip(f"{photo.filename}\n{self._fmt_captured(photo)} · "
                        f"{photo.size / 1024:.0f} KB")
        self.list.addItem(item)
        self._item_by_handle[photo.handle] = item
        return item

    def _refresh_grid(self):
        self.list.clear()
        self._item_by_handle.clear()
        for photo in self._visible_photos():
            self._add_grid_item(photo)
        self._update_count()
        self._thumb_timer.start(150)

    def _update_count(self):
        if not self.session and not self.photos:
            self.lbl_count.setText("")
            return
        visible = self.list.count()
        if self._indexed < self._total_handles:
            self.lbl_count.setText(
                f"索引中 {self._indexed}/{self._total_handles} · 已发现照片 {len(self.photos)} 张")
        else:
            self.lbl_count.setText(f"共 {len(self.photos)} 张 · 当前显示 {visible} 张")

    def _refresh_date_combo(self):
        keep = self.combo_date.currentText()
        self.combo_date.blockSignals(True)
        self.combo_date.clear()
        self.combo_date.addItem("全部日期")
        for d in sorted(self._dates, reverse=True):
            self.combo_date.addItem(d)
        i = self.combo_date.findText(keep)
        self.combo_date.setCurrentIndex(i if i >= 0 else 0)
        self.combo_date.blockSignals(False)

    # zoom / 预览缩放

    def _apply_zoom(self, value: int, save: bool = True):
        self._zoom = value
        self.list.setIconSize(QSize(value, int(value * 0.75)))
        self.list.setGridSize(QSize(value + 28, int(value * 0.75) + 56))
        if save:
            storage.set_setting("zoom", value)
        self._placeholders.clear()
        self._thumb_timer.start(120)

    def _on_zoom_step(self, step: int):
        self.slider_zoom.setValue(self.slider_zoom.value() + step * 16)

    def eventFilter(self, obj, event):
        if obj is self.list.viewport() and event.type() == event.Type.Resize:
            self._thumb_timer.start(120)
        return super().eventFilter(obj, event)

    # lazy thumbnails / 缩略图按可见区域加载

    def _request_visible_thumbs(self):
        if not self.session or self.list.count() == 0:
            return
        grid = self.list.gridSize()
        vp = self.list.viewport().size()
        cols = max(1, vp.width() // grid.width())
        y0 = self.list.verticalScrollBar().value()
        first_row = max(0, y0 // grid.height())
        rows = vp.height() // grid.height() + 2
        start = max(0, (first_row - 1) * cols)
        end = min(self.list.count(), (first_row + rows + 1) * cols)
        handles = []
        for i in range(start, end):
            handle = self.list.item(i).data(Qt.UserRole)
            if handle not in self._thumbs:
                handles.append(handle)
        if handles:
            self.session.request_thumbs(handles)

    # selection & detail panel / 选中与详情面板

    def _on_select(self, current: QListWidgetItem | None, _prev):
        if not current:
            return
        handle = current.data(Qt.UserRole)
        photo = self._by_handle.get(handle)
        if not photo:
            return
        self.info_name.setText(photo.filename)
        self.info_basic.setText(
            f"{self._fmt_captured(photo)} · {photo.width}×{photo.height} · "
            f"{photo.size / 1024 / 1024:.1f} MB")
        self._set_preview(handle)
        meta = self._exif_cache.get(handle)
        if meta is not None:
            self._fill_exif(meta)
        else:
            for lab in self._exif_vals.values():
                lab.setText("…")
            self._show_gps_block(False)
            if self.session:
                self.session.request_exif(handle)

    def _set_preview(self, handle: int):
        pix = self._thumbs.get(handle)
        if pix:
            self.info_preview.setPixmap(pix.scaled(
                self.info_preview.width(), self.info_preview.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.info_preview.setText("缩略图加载中…")

    def _fill_exif(self, meta: dict):
        if meta.get("error"):
            for lab in self._exif_vals.values():
                lab.setText("—")
            self._show_gps_block(False)
            return
        for key, lab in self._exif_vals.items():
            lab.setText(str(meta.get(key) or "—"))
        lat, lon = meta.get("gps_lat"), meta.get("gps_lon")
        if lat is not None and lon is not None:
            self._show_gps_block(True)
            self.map.set_location(lat, lon)
            self.gps_note.setText(f"经纬度 {lat:.5f}, {lon:.5f} · 双击地图可在浏览器中查看")
        else:
            self._show_gps_block(False)

    # download / 下载

    def _with_pairs(self, photo: PhotoInfo) -> list[PhotoInfo]:
        base, _, ext = photo.filename.rpartition(".")
        base = base.upper()
        out = [photo]
        for other in self.photos:
            if other.handle == photo.handle:
                continue
            obase, _, oext = other.filename.rpartition(".")
            if obase.upper() == base and oext.upper() != ext.upper():
                out.append(other)
        return out

    def on_download(self, selected_only: bool):
        if not self.session:
            self._log("尚未连接相机。")
            return
        if selected_only:
            handles = {item.data(Qt.UserRole) for item in self.list.selectedItems()}
            selected = [p for p in self.photos if p.handle in handles]
            if not selected:
                self._log("请先在列表中选中要下载的照片。")
                return
            targets: list[PhotoInfo] = []
            seen: set[int] = set()
            for photo in selected:
                for mate in self._with_pairs(photo):
                    if mate.handle not in seen:
                        seen.add(mate.handle)
                        targets.append(mate)
            missing = [p.filename for p in selected if len(self._with_pairs(p)) == 1]
            if missing:
                self._log(f"提示：这些照片的同名配对文件不在索引中："
                          f"{', '.join(missing[:5])}{'…' if len(missing) > 5 else ''}")
        else:
            targets = self._visible_photos()
        if not targets:
            self._log("没有可下载的照片。")
            return
        folder = self.edit_folder.text().strip() or DOWNLOAD_DIR
        os.makedirs(folder, exist_ok=True)
        self._log(f"已加入下载队列：{len(targets)} 个文件（后台下载，可继续浏览与筛选）。")
        self.session.enqueue_downloads([(p.handle, p.filename) for p in targets], folder)

    def _on_progress(self, done: int, total: int, filename: str):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)
        self.progress_bar.setFormat(f"{done}/{total} · {filename}")

    def _on_dl_done(self, count: int):
        self._log(f"下载队列完成：{count} 个文件已保存。")

    # ---- menu actions / 菜单动作 ----

    def on_browse(self):
        folder = QFileDialog.getExistingDirectory(self, "选择保存位置", self.edit_folder.text())
        if folder:
            self.edit_folder.setText(folder)

    def on_open_downloads(self):
        folder = self.edit_folder.text().strip() or DOWNLOAD_DIR
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)

    def on_help(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("使用说明")
        dlg.resize(640, 560)
        lay = QVBoxLayout(dlg)
        view = QTextBrowser()
        view.setHtml(HELP_HTML)
        view.setOpenExternalLinks(True)
        lay.addWidget(view)
        btn = QPushButton("关闭")
        btn.setObjectName("ghost")
        btn.clicked.connect(dlg.accept)
        lay.addWidget(btn, alignment=Qt.AlignRight)
        dlg.exec()

    # ---- shutdown / 关闭 ----

    def closeEvent(self, event):
        for worker in list(self._workers):
            worker.wait(3000)
        try:
            if self.session:
                self.session.stop()
                self.session.wait(5000)
                if self.session.isRunning():
                    self.session.terminate()
                    self.session.wait(1000)
        finally:
            event.accept()
