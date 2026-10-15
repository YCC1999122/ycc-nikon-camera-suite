"""PTP/IP initiator used by the desktop app to talk to the camera.

扮演 PTP/IP 发起方：握手、开会话、枚举照片、拉取缩略图与原图。
真机与模拟相机都走这同一份代码。
"""
from __future__ import annotations

import hashlib
import os
import socket
import struct
from dataclasses import dataclass

from app import protocol as ptp

# Stable client GUID so the camera sees the same identity on every run
# / 固定客户端 GUID，保证每次连接时相机看到的身份一致（配对档案关联用）
_GUID_SEED = "NikonTransferTool-StableClient-v1"


class CameraError(Exception):
    """Raised on protocol or connection failures. / 协议或连接失败时抛出"""


@dataclass
class PhotoInfo:
    handle: int
    filename: str
    size: int
    captured: str
    width: int
    height: int
    thumb: bytes | None = None


class CameraClient:
    def __init__(self, host: str, port: int = ptp.PTPIP_PORT,
                 timeout: float = 10.0, host_name: str = "NikonTransferPC"):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.host_name = host_name
        self.guid = hashlib.md5((_GUID_SEED + socket.gethostname()).encode()).digest()
        self.camera_name = ""
        self.conn_number = 0
        self._cmd: socket.socket | None = None
        self._evt: socket.socket | None = None
        self._transid = 0
        self._session = False
        self.last_consumed = 0  # pagination cursor from the last list_photos / 上次分页游标
        self.device_info: dict = {}  # filled by fetch_device_info / 设备信息缓存

    # ---- connection lifecycle / 连接生命周期 ----

    def connect(self) -> None:
        try:
            cmd = socket.create_connection((self.host, self.port), timeout=self.timeout)
        except OSError as exc:
            # wizard not ready / port closed → let callers retry uniformly
            # 向导未就绪或端口未开 → 统一转成 CameraError 交给上层重试
            raise CameraError(f"cannot reach camera at {self.host}:{self.port} ({exc})") from exc
        cmd.settimeout(self.timeout)
        cmd.sendall(ptp.build_init_cmd_request(self.guid, self.host_name))
        ptype, payload = ptp.recv_packet(cmd)
        if ptype == ptp.PKT_INIT_FAIL:
            cmd.close()
            raise CameraError("camera rejected the command connection")
        if ptype != ptp.PKT_INIT_CMD_ACK:
            cmd.close()
            raise CameraError(f"unexpected handshake packet 0x{ptype:02X}")
        self.conn_number, _cam_guid, self.camera_name = ptp.parse_init_cmd_ack(payload)
        self._cmd = cmd

        try:
            evt = socket.create_connection((self.host, self.port), timeout=self.timeout)
            evt.settimeout(self.timeout)
            evt.sendall(ptp.build_init_event_request(self.conn_number))
            ptype, _ = ptp.recv_packet(evt)
            if ptype != ptp.PKT_INIT_EVENT_ACK:
                evt.close()
                self._evt = None  # real cameras may refuse the event channel / 真机可能拒绝事件通道，容错继续
            else:
                self._evt = evt
        except OSError:
            self._evt = None

    def open_session(self) -> None:
        self._operation(ptp.OP_OPEN_SESSION, (1,), ptp.DP_NODATA)
        self._session = True

    def close(self) -> None:
        if self._session and self._cmd:
            try:
                self._operation(ptp.OP_CLOSE_SESSION, (), ptp.DP_NODATA)
            except (CameraError, OSError, ptp.ProtocolError):
                pass
            self._session = False
        for sock in (self._cmd, self._evt):
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
        self._cmd = self._evt = None

    # ---- public API / 对外接口 ----

    def fetch_device_info(self) -> dict:
        """Model / firmware / serial from the DeviceInfo dataset.
        / 读取相机型号、固件版本、序列号；失败时返回空字典"""
        if not self._session:
            self.open_session()
        try:
            _, data = self._operation(ptp.OP_GET_DEVICE_INFO, (), ptp.DP_GETDATA)
            self.device_info = ptp.parse_device_info(data)
        except (CameraError, ptp.ProtocolError, struct.error) as exc:
            self.device_info = {"error": str(exc)}
        return self.device_info

    def list_handles(self, newest_first: bool = False) -> list[int]:
        """All object handles across storages (one round trip per storage).
        / 枚举全部对象句柄（每个存储区一次往返），速度快，适合先拿到总数"""
        if not self._session:
            self.open_session()
        _, storage_data = self._operation(ptp.OP_GET_STORAGE_IDS, (), ptp.DP_GETDATA)
        (count,) = struct.unpack_from("<I", storage_data, 0)
        storage_ids = struct.unpack_from(f"<{count}I", storage_data, 4)
        handles: list[int] = []
        for sid in storage_ids:
            _, data = self._operation(ptp.OP_GET_OBJECT_HANDLES, (sid, 0, 0), ptp.DP_GETDATA)
            (n,) = struct.unpack_from("<I", data, 0)
            handles.extend(struct.unpack_from(f"<{n}I", data, 4))
        if newest_first:
            handles.reverse()  # latest handles first / 句柄升序对应旧照片，反转后最新在前
        return handles

    def get_object_info(self, handle: int) -> dict:
        """Metadata for one object. / 单个对象的元数据（文件名/时间/尺寸等）"""
        _, info_data = self._operation(ptp.OP_GET_OBJECT_INFO, (handle,), ptp.DP_GETDATA)
        return ptp.parse_object_info(info_data)

    def get_thumb(self, handle: int) -> bytes | None:
        """Thumbnail JPEG bytes, or None when the camera has none. / 缩略图，失败返回 None"""
        try:
            _, thumb = self._operation(ptp.OP_GET_THUMB, (handle,), ptp.DP_GETDATA)
            return thumb
        except CameraError:
            return None  # some cameras have no thumbs for RAW / RAW 可能无缩略图

    def get_partial_object(self, handle: int, offset: int = 0,
                           size: int = 262144) -> bytes:
        """Read a byte range of an object (EXIF sits at the start). / 读取对象局部数据（EXIF 在文件头）"""
        _, data = self._operation(ptp.OP_GET_PARTIAL_OBJECT,
                                  (handle, offset, size), ptp.DP_GETDATA)
        return data

    def list_photos(self, thumbs: bool = True, log=None, limit: int | None = None,
                    skip: int = 0, newest_first: bool = False) -> list[PhotoInfo]:
        handles = self.list_handles(newest_first=newest_first)

        photos: list[PhotoInfo] = []
        consumed = 0  # handles consumed in handle-space (incl. folders) / 含目录的句柄游标
        for handle in handles[skip:]:
            if limit is not None and len(photos) >= limit:
                break
            consumed += 1
            info = self.get_object_info(handle)
            if info["assoc_type"] != 0:
                continue  # folder objects are not photos / 跳过目录对象
            thumb = self.get_thumb(handle) if thumbs else None
            photos.append(PhotoInfo(
                handle=handle, filename=info["filename"], size=info["size"],
                captured=info["captured"], width=info["width"],
                height=info["height"], thumb=thumb,
            ))
            if log:
                log(f"读取照片信息: {info['filename']}")
        self.last_consumed = skip + consumed  # pagination cursor for load-more / 分页游标
        return photos

    def download(self, handle: int, dest_path: str) -> str:
        """Stream one photo to disk. / 流式下载单张照片"""
        with open(dest_path, "wb") as f:
            self._operation(ptp.OP_GET_OBJECT, (handle,), ptp.DP_GETDATA, data_sink=f.write)
        return dest_path

    # ---- internal / 内部实现 ----

    def _operation(self, opcode: int, params: tuple, dataphase: int,
                   data_sink=None) -> tuple[list, bytes]:
        if not self._cmd:
            raise CameraError("not connected")
        self._transid += 1
        transid = self._transid
        self._cmd.sendall(ptp.build_op_request(dataphase, opcode, transid, params))

        received = bytearray()
        while True:
            ptype, payload = ptp.recv_packet(self._cmd)
            if ptype == ptp.PKT_START_DATA:
                _tid, _total = ptp.parse_start_data(payload)
            elif ptype in (ptp.PKT_DATA, ptp.PKT_END_DATA):
                _tid, chunk = ptp.parse_data(payload)
                if data_sink:
                    data_sink(chunk)
                else:
                    received += chunk
            elif ptype == ptp.PKT_EVENT:
                continue  # ignore async events in this phase / 本阶段忽略异步事件
            elif ptype == ptp.PKT_OP_RESPONSE:
                rcode, _tid, rparams = ptp.parse_op_response(payload)
                if rcode == ptp.RC_SESSION_ALREADY_OPEN and opcode == ptp.OP_OPEN_SESSION:
                    rcode = ptp.RC_OK  # idempotent reconnect / 重连时幂等处理
                if rcode != ptp.RC_OK:
                    raise CameraError(f"op 0x{opcode:04X} failed, rc=0x{rcode:04X}")
                return rparams, bytes(received)
            else:
                raise CameraError(f"unexpected packet 0x{ptype:02X} during op 0x{opcode:04X}")
