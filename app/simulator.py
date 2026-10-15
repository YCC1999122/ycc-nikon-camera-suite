"""Simulated Nikon Wi-Fi camera (PTP/IP responder) for offline debugging.

Run standalone:  python -m app.simulator
模拟一台开了 Wi-Fi 热点的尼康相机，行为与真机一致，便于无真机调试全链路。
"""
from __future__ import annotations

import io
import socket
import struct
import threading
import time

from PIL import Image, ImageDraw

from app import protocol as ptp

SIM_NAME = "NIKON-SIM-D5300"
SIM_GUID = bytes.fromhex("4e494b4f4e2d53494d2d43414d2d3031")  # 16 bytes / 固定 GUID


def _make_photo(index: int) -> dict:
    """Generate one fake JPEG with distinct gradient/text + embedded EXIF.
    / 生成一张可区分的假照片，内嵌 EXIF（每 3 张带一次 GPS）"""
    width, height = 640, 480
    hue = (index * 37) % 255
    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):  # vertical gradient background / 竖直渐变背景
        draw.line([(0, y), (width, y)],
                  fill=(hue, (hue + y * 60 // height) % 255, 255 - hue))
    draw.rectangle([20, 20, 320, 92], outline=(255, 255, 255), width=3)
    captured = time.strftime("%Y%m%dT%H%M%S", time.localtime(time.time() - index * 3600))
    draw.text((34, 36), f"SIM DSC_{index + 1:04d}", fill=(255, 255, 255))
    draw.text((34, 62), captured, fill=(255, 255, 255))

    # embed EXIF: shooting params, GPS on every 3rd photo / 内嵌拍摄参数，每 3 张带 GPS
    exif = Image.Exif()
    exif[0x010F] = "NIKON CORPORATION"
    exif[0x0110] = SIM_NAME
    eifd = exif.get_ifd(0x8769)  # ExifIFD
    eifd[0x9003] = time.strftime("%Y:%m:%d %H:%M:%S",
                                 time.localtime(time.time() - index * 3600))
    eifd[0x829D] = round(1.8 + (index % 8) * 0.5, 1)        # FNumber
    eifd[0x829A] = 1.0 / (125 * (1 << index % 4))           # ExposureTime
    eifd[0x8827] = 100 * (1 << index % 4)                   # ISO
    eifd[0x920A] = float((23, 35, 50, 16)[index % 4])       # FocalLength
    eifd[0xA434] = "NIKKOR Z 28mm f/2.8 (SIM)"              # LensModel
    eifd[0x9207] = 5                                        # MeteringMode: matrix
    if index % 3 == 0:  # GPS around Beijing / GPS 落在北京附近
        g = exif.get_ifd(0x8825)
        g[1] = "N"
        g[2] = (39.0, float(50 + index % 9), 30.0)
        g[3] = "E"
        g[4] = (116.0, float(20 + index % 11), 30.0)

    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=85, exif=exif.tobytes())
    thumb_buf = io.BytesIO()
    img.resize((160, 120)).save(thumb_buf, "JPEG", quality=80)

    return {
        "handle": index + 1,
        "filename": f"DSC_{index + 1:04d}.JPG",
        "data": buf.getvalue(),
        "thumb": thumb_buf.getvalue(),
        "captured": captured,
        "width": width,
        "height": height,
    }


class SimulatedCamera:
    """Speaks the PTP/IP responder role; a drop-in stand-in for a real Nikon. / 扮演 PTP/IP 响应方"""

    def __init__(self, host: str = "0.0.0.0", port: int = ptp.PTPIP_PORT, photo_count: int = 12):
        self.host = host
        self.port = port
        self.photos = [_make_photo(i) for i in range(photo_count)]
        self._by_handle = {ph["handle"]: ph for ph in self.photos}
        self._server: socket.socket | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._next_conn = 1
        self.session_open = False

    def start(self) -> None:
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind((self.host, self.port))
        self._server.listen(8)
        self._server.settimeout(0.5)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        if self._server:
            self._server.close()

    def _accept_loop(self) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        try:
            while True:
                ptype, payload = ptp.recv_packet(conn)
                if ptype == ptp.PKT_INIT_CMD_REQUEST:
                    ptp.parse_init_cmd_request(payload)  # validate / 校验格式
                    with self._lock:
                        conn_id = self._next_conn
                        self._next_conn += 1
                    conn.sendall(ptp.build_init_cmd_ack(conn_id, SIM_GUID, SIM_NAME))
                elif ptype == ptp.PKT_INIT_EVENT_REQUEST:
                    conn.sendall(ptp.pack_packet(ptp.PKT_INIT_EVENT_ACK))
                elif ptype == ptp.PKT_OP_REQUEST:
                    self._handle_operation(conn, payload)
                elif ptype == ptp.PKT_PING:
                    conn.sendall(ptp.pack_packet(ptp.PKT_PONG))
        except (ptp.ProtocolError, ConnectionError, OSError):
            pass
        finally:
            conn.close()

    def _handle_operation(self, conn: socket.socket, payload: bytes) -> None:
        _dataphase, opcode, transid, params = ptp.parse_op_request(payload)

        if opcode == ptp.OP_OPEN_SESSION:
            self.session_open = True
            self._respond(conn, ptp.RC_OK, transid)
        elif opcode == ptp.OP_GET_DEVICE_INFO:
            self._send_data(conn, transid, ptp.build_device_info(
                manufacturer="NIKON CORPORATION", model=SIM_NAME,
                version="1.00", serial="0000001"))
            self._respond(conn, ptp.RC_OK, transid)
        elif opcode == ptp.OP_CLOSE_SESSION:
            self.session_open = False
            self._respond(conn, ptp.RC_OK, transid)
        elif opcode == ptp.OP_GET_STORAGE_IDS:
            self._send_data(conn, transid, struct.pack("<II", 1, 0x00010001))
            self._respond(conn, ptp.RC_OK, transid)
        elif opcode == ptp.OP_GET_OBJECT_HANDLES:
            handles = sorted(self._by_handle)
            data = struct.pack("<I", len(handles))
            data += b"".join(struct.pack("<I", h) for h in handles)
            self._send_data(conn, transid, data)
            self._respond(conn, ptp.RC_OK, transid)
        elif opcode == ptp.OP_GET_OBJECT_INFO:
            photo = self._by_handle.get(params[0] if params else -1)
            if not photo:
                self._respond(conn, ptp.RC_INVALID_OBJECT_HANDLE, transid)
                return
            self._send_data(conn, transid, self._build_object_info(photo))
            self._respond(conn, ptp.RC_OK, transid)
        elif opcode == ptp.OP_GET_PARTIAL_OBJECT:
            photo = self._by_handle.get(params[0] if params else -1)
            if not photo:
                self._respond(conn, ptp.RC_INVALID_OBJECT_HANDLE, transid)
                return
            offset = params[1] if len(params) > 1 else 0
            count = params[2] if len(params) > 2 else len(photo["data"])
            self._send_data(conn, transid, photo["data"][offset:offset + count])
            self._respond(conn, ptp.RC_OK, transid)
        elif opcode in (ptp.OP_GET_THUMB, ptp.OP_GET_OBJECT):
            photo = self._by_handle.get(params[0] if params else -1)
            if not photo:
                self._respond(conn, ptp.RC_INVALID_OBJECT_HANDLE, transid)
                return
            body = photo["thumb"] if opcode == ptp.OP_GET_THUMB else photo["data"]
            self._send_data(conn, transid, body)
            self._respond(conn, ptp.RC_OK, transid)
        else:
            self._respond(conn, ptp.RC_OPERATION_NOT_SUPPORTED, transid)

    @staticmethod
    def _respond(conn: socket.socket, rcode: int, transid: int) -> None:
        conn.sendall(ptp.build_op_response(rcode, transid))

    @staticmethod
    def _send_data(conn: socket.socket, transid: int, data: bytes) -> None:
        """StartData + chunked Data + EndData. / 分块发送以贴近真机行为"""
        conn.sendall(ptp.build_start_data(transid, len(data)))
        offset = 0
        while offset + ptp.DATA_CHUNK < len(data):
            conn.sendall(ptp.build_data(transid, data[offset:offset + ptp.DATA_CHUNK]))
            offset += ptp.DATA_CHUNK
        conn.sendall(ptp.build_data(transid, data[offset:], final=True))

    @staticmethod
    def _build_object_info(photo: dict) -> bytes:
        return ptp.build_object_info(
            storage_id=0x00010001,
            obj_format=ptp.FMT_EXIF_JPEG,
            size=len(photo["data"]),
            thumb_format=ptp.FMT_EXIF_JPEG,
            thumb_size=len(photo["thumb"]),
            thumb_w=160, thumb_h=120,
            width=photo["width"], height=photo["height"],
            bit_depth=24, parent=0, assoc_type=0, assoc_desc=0,
            seq=photo["handle"],
            filename=photo["filename"],
            captured=photo["captured"],
            modified=photo["captured"],
        )


def main() -> None:
    cam = SimulatedCamera(host="0.0.0.0")
    cam.start()
    print(f"Simulated camera '{SIM_NAME}' listening on port {ptp.PTPIP_PORT}. Ctrl+C to stop.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cam.stop()


if __name__ == "__main__":
    main()
