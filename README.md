# Nikon Camera Suite（尼康相机管理）

Windows 桌面软件，通过 WiFi 与尼康相机（PTP/IP 协议，Z fc / Z 系列等）通信，
提供照片浏览、筛选、下载与相机信息管理。界面基于 PySide6。

## 功能

- **设备连接**：局域网自动搜索相机（仅端口探测，不占用相机连接槽位），保存常用设备，支持备注与详情查看
- **照片浏览**：连接后后台为全部照片建立索引，几千张也可顺畅滚动；缩略图按可见区域懒加载；Ctrl+滚轮调整预览大小
- **筛选与排序**：按拍摄日期、格式（JPG / NEF RAW）、文件名搜索，支持按时间、文件名、大小排序
- **照片详情**：选中照片显示光圈、快门、ISO、焦距、镜头、白平衡等拍摄参数；有 GPS 时在内嵌地图标注拍摄位置（OpenStreetMap，双击可在浏览器打开）
- **照片下载**：后台队列下载，不阻塞浏览；选中下载时自动配对同名 RAW+JPG
- **相机信息**：读取型号、固件版本、序列号并展示
- **摄影助手**：常见场景参数建议与相机维护要点
- 浅色 / 深色主题切换

## 相机配对（首次使用，仅需一次）

尼康相机的「连接至 PC」向导需要完成一次官方配对才能保存配置文件：

1. 安装尼康官方免费的 **Wireless Transmitter Utility (WTU)**
2. 相机：网络菜单 → 连接至 PC → 新建配置文件 → 选择路由器 WiFi → 输入密码 → 停在等待界面
3. 在 WTU 中完成配对（仅一次，之后相机会记住该网络）

此后每次使用：相机重新进入「连接至 PC」→ 打开本软件 → 点「连接」。
注意：相机向导一次只接受一个连接，若连接被拒，重新进入向导后立刻点连接（软件会自动重试 60 秒）。

## 运行方式

### 方式一：打包好的 exe

见 Releases。解压后双击 `尼康相机管理.exe`，整个文件夹可整体迁移。

### 方式二：源码运行

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
.venv\Scripts\python.exe main.py
```

### 重新打包 exe

```powershell
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --distpath dist --workpath build pack_exe.spec
```

再将 `assets`、`devices.json`（可选）复制到 `dist` 目录。

## 项目结构

```
main.py            入口（直接打开主窗口）
app/
  protocol.py      PTP/IP (ISO 15740) 数据包编解码
  client.py        PTP 客户端：握手、会话、枚举、缩略图、局部读取、下载
  session.py       会话线程：索引 / 缩略图 / EXIF / 下载统一排队调度
  discovery.py     局域网相机发现（纯端口探测）
  exif.py          JPEG / NEF 的 EXIF 与 GPS 解析（读取文件头即可）
  mapwidget.py     OpenStreetMap 瓦片地图与拍摄点标注
  gui.py           主界面（侧导航 + 照片管理 + 摄影助手 + 日志面板）
  simulator.py     模拟相机（开发调试用，无需真机）
  selftest.py      端到端自测（python -m app.selftest）
pack_exe.spec      PyInstaller 打包配置
```

## 实现说明

- 相机默认监听 TCP 15740，使用 PTP/IP；扫描阶段只探测端口，避免占用相机的单次连接槽位
- 所有 PTP 操作串行在同一个会话队列，优先级：EXIF 查询 > 可见缩略图 > 下载 > 后台索引
- 拍摄参数与 GPS 通过 GetPartialObject(0x101B) 只读取文件头部数据解析，不需要下载整张照片

## 许可

仅供学习交流使用。Nikon、尼康及相关商标归尼康公司所有，本项目与尼康公司无关。
