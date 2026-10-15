"""PTP/IP protocol constants and packet codec (ISO 15740 over TCP/IP).

Only the read-only subset needed for photo transfer is implemented.
数据包格式: [length u32][type u32][payload]，length 包含头部 8 字节，全部小端序。
"""
from __future__ import annotations

import socket
import struct

PTPIP_PORT = 15740
PROTOCOL_VERSION = 0x00010000

# Packet types / 数据包类型
PKT_INIT_CMD_REQUEST = 0x01
PKT_INIT_CMD_ACK = 0x02
PKT_INIT_EVENT_REQUEST = 0x03
PKT_INIT_EVENT_ACK = 0x04
PKT_INIT_FAIL = 0x05
PKT_OP_REQUEST = 0x06
PKT_OP_RESPONSE = 0x07
PKT_EVENT = 0x08
PKT_START_DATA = 0x09
PKT_DATA = 0x0A
PKT_CANCEL = 0x0B
PKT_END_DATA = 0x0C
PKT_PING = 0x0D
PKT_PONG = 0x0E

# PTP operation codes / PTP 操作码
OP_GET_DEVICE_INFO = 0x1001
OP_OPEN_SESSION = 0x1002
OP_CLOSE_SESSION = 0x1003
OP_GET_STORAGE_IDS = 0x1004
OP_GET_OBJECT_HANDLES = 0x1007
OP_GET_OBJECT_INFO = 0x1008
OP_GET_OBJECT = 0x1009
OP_GET_THUMB = 0x100A
OP_GET_PARTIAL_OBJECT = 0x101B

# PTP response codes / PTP 响应码
RC_OK = 0x2001
RC_OPERATION_NOT_SUPPORTED = 0x2005
RC_INVALID_OBJECT_HANDLE = 0x2009
RC_SESSION_ALREADY_OPEN = 0x201E

# Data phase flags / 数据阶段标志
DP_NODATA = 0
DP_SENDDATA = 1
DP_GETDATA = 2

# Object formats / 对象格式
FMT_EXIF_JPEG = 0x3801

# Storage selectors / 存储选择器
STORAGE_ALL = 0xFFFFFFFF
DATA_CHUNK = 65536

_MAX_PACKET = 64 * 1024 * 1024


class ProtocolError(Exception):
    """Raised when a peer sends malformed or unexpected packets. / 对端发来异常数据包时抛出"""


def pack_packet(packet_type: int, payload: bytes = b"") -> bytes:
    return struct.pack("<II", 8 + len(payload), packet_type) + payload


def recv_exact(sock: socket.socket, size: int) -> bytes:
    buf = bytearray()
    while len(buf) < size:
        chunk = sock.recv(size - len(buf))
        if not chunk:
            raise ProtocolError("connection closed by peer")
        buf += chunk
    return bytes(buf)


def recv_packet(sock: socket.socket) -> tuple[int, bytes]:
    """Read one packet, return (packet_type, payload). / 读取一个完整数据包"""
    header = recv_exact(sock, 8)
    length, packet_type = struct.unpack("<II", header)
    if length < 8 or length > _MAX_PACKET:
        raise ProtocolError(f"bad packet length: {length}")
    return packet_type, recv_exact(sock, length - 8)


# ---- handshake / 握手 ----

def encode_name(text: str) -> bytes:
    """UTF-16LE null-terminated friendly name. / UTF-16LE 双字节结尾的名称"""
    return text.encode("utf-16-le") + b"\x00\x00"


def decode_name(data: bytes, offset: int = 0) -> tuple[str, int]:
    """Return (name, offset_after_null); scans on 2-byte alignment. / 按 2 字节对齐扫描结尾"""
    i = offset
    while i + 1 < len(data):
        if data[i] == 0 and data[i + 1] == 0:
            return data[offset:i].decode("utf-16-le", "replace"), i + 2
        i += 2
    raise ProtocolError("unterminated friendly name")


def build_init_cmd_request(guid: bytes, host_name: str) -> bytes:
    payload = guid + encode_name(host_name) + struct.pack("<I", PROTOCOL_VERSION)
    return pack_packet(PKT_INIT_CMD_REQUEST, payload)


def parse_init_cmd_request(payload: bytes) -> tuple[bytes, str, int]:
    guid = payload[:16]
    name, end = decode_name(payload, 16)
    (version,) = struct.unpack_from("<I", payload, end)
    return guid, name, version


def build_init_cmd_ack(conn_number: int, guid: bytes, name: str) -> bytes:
    payload = struct.pack("<I", conn_number) + guid + encode_name(name)
    payload += struct.pack("<I", PROTOCOL_VERSION)
    return pack_packet(PKT_INIT_CMD_ACK, payload)


def parse_init_cmd_ack(payload: bytes) -> tuple[int, bytes, str]:
    (conn_number,) = struct.unpack_from("<I", payload, 0)
    guid = payload[4:20]
    name, _ = decode_name(payload, 20)
    return conn_number, guid, name


def build_init_event_request(conn_number: int) -> bytes:
    return pack_packet(PKT_INIT_EVENT_REQUEST, struct.pack("<I", conn_number))


# ---- operations / 操作 ----

def build_op_request(dataphase: int, opcode: int, transid: int, params: tuple = ()) -> bytes:
    payload = struct.pack("<IHI", dataphase, opcode, transid)
    payload += b"".join(struct.pack("<I", p) for p in params)
    return pack_packet(PKT_OP_REQUEST, payload)


def parse_op_request(payload: bytes) -> tuple[int, int, int, list]:
    dataphase, opcode, transid = struct.unpack_from("<IHI", payload, 0)
    params = [struct.unpack_from("<I", payload, 10 + 4 * i)[0]
              for i in range((len(payload) - 10) // 4)]
    return dataphase, opcode, transid, params


def build_op_response(rcode: int, transid: int, params: tuple = ()) -> bytes:
    payload = struct.pack("<HI", rcode, transid)
    payload += b"".join(struct.pack("<I", p) for p in params)
    return pack_packet(PKT_OP_RESPONSE, payload)


def parse_op_response(payload: bytes) -> tuple[int, int, list]:
    rcode, transid = struct.unpack_from("<HI", payload, 0)
    params = [struct.unpack_from("<I", payload, 6 + 4 * i)[0]
              for i in range((len(payload) - 6) // 4)]
    return rcode, transid, params


# ---- data phase / 数据传输 ----

def build_start_data(transid: int, total: int) -> bytes:
    return pack_packet(PKT_START_DATA, struct.pack("<IQ", transid, total))


def parse_start_data(payload: bytes) -> tuple[int, int]:
    return struct.unpack_from("<IQ", payload, 0)


def build_data(transid: int, chunk: bytes, final: bool = False) -> bytes:
    packet_type = PKT_END_DATA if final else PKT_DATA
    return pack_packet(packet_type, struct.pack("<I", transid) + chunk)


def parse_data(payload: bytes) -> tuple[int, bytes]:
    (transid,) = struct.unpack_from("<I", payload, 0)
    return transid, payload[4:]


# ---- PTP strings & object info / PTP 字符串与对象信息 ----

def ptp_string(text: str) -> bytes:
    """PTP string: u8 char count (incl. null) + UTF-16LE chars. / 首字节为含结尾的字符数"""
    if not text:
        return b"\x00"
    return bytes([len(text) + 1]) + text.encode("utf-16-le") + b"\x00\x00"


def read_ptp_string(buf: bytes, offset: int) -> tuple[str, int]:
    count = buf[offset]
    if count == 0:
        return "", offset + 1
    start = offset + 1
    end = start + count * 2
    return buf[start:end - 2].decode("utf-16-le", "replace"), end


# ObjectInfo dataset fixed part: 15 fields, 52 bytes / 对象信息固定段 15 个字段共 52 字节
_OBJECT_INFO_FMT = "<IHHIHIIIIIIIHII"
_OBJECT_INFO_FIXED = struct.calcsize(_OBJECT_INFO_FMT)


def build_object_info(*, storage_id: int, obj_format: int, size: int,
                      thumb_format: int, thumb_size: int, thumb_w: int, thumb_h: int,
                      width: int, height: int, bit_depth: int, parent: int,
                      assoc_type: int, assoc_desc: int, seq: int,
                      filename: str, captured: str, modified: str,
                      keywords: str = "") -> bytes:
    fixed = struct.pack(
        _OBJECT_INFO_FMT,
        storage_id, obj_format, 0, size,
        thumb_format, thumb_size, thumb_w, thumb_h,
        width, height, bit_depth, parent,
        assoc_type, assoc_desc, seq,
    )
    return (fixed + ptp_string(filename) + ptp_string(captured)
            + ptp_string(modified) + ptp_string(keywords))


def parse_object_info(data: bytes) -> dict:
    (storage_id, obj_format, _prot, size,
     thumb_format, thumb_size, thumb_w, thumb_h,
     width, height, bit_depth, parent,
     assoc_type, assoc_desc, seq) = struct.unpack_from(_OBJECT_INFO_FMT, data, 0)
    off = _OBJECT_INFO_FIXED
    filename, off = read_ptp_string(data, off)
    captured, off = read_ptp_string(data, off)
    modified, off = read_ptp_string(data, off)
    keywords, off = read_ptp_string(data, off)
    return {
        "storage_id": storage_id, "format": obj_format, "size": size,
        "thumb_format": thumb_format, "thumb_size": thumb_size,
        "thumb_w": thumb_w, "thumb_h": thumb_h,
        "width": width, "height": height, "bit_depth": bit_depth,
        "parent": parent, "assoc_type": assoc_type, "assoc_desc": assoc_desc,
        "seq": seq, "filename": filename, "captured": captured,
        "modified": modified, "keywords": keywords,
    }


# ---- DeviceInfo dataset / 设备信息数据集 ----

def _skip_u16_array(data: bytes, offset: int) -> int:
    (count,) = struct.unpack_from("<I", data, offset)
    return offset + 4 + count * 2


def build_device_info(*, manufacturer: str, model: str,
                      version: str, serial: str) -> bytes:
    """Minimal DeviceInfo dataset for the simulator. / 模拟相机用的最小设备信息集"""
    ops = struct.pack("<I5H", 5, OP_OPEN_SESSION, OP_CLOSE_SESSION,
                      OP_GET_STORAGE_IDS, OP_GET_OBJECT_HANDLES, OP_GET_OBJECT_INFO)
    empty = struct.pack("<I", 0)
    out = struct.pack("<HIH", 100, 0xFFFFFFFF, 100) + ptp_string("nikon.co.jp")
    out += struct.pack("<H", 0)  # functional mode / 功能模式
    out += ops + empty + empty + empty + empty  # 5 capability arrays / 能力数组
    out += (ptp_string(manufacturer) + ptp_string(model)
            + ptp_string(version) + ptp_string(serial))
    return out


def parse_device_info(data: bytes) -> dict:
    """Extract vendor/model/firmware/serial from a DeviceInfo dataset.
    / 从设备信息数据集中提取厂商、型号、固件版本、序列号"""
    off = struct.calcsize("<HIH")
    _vendor_desc, off = read_ptp_string(data, off)
    off += 2  # functional mode
    for _ in range(5):  # operations/events/props/capture/image arrays
        off = _skip_u16_array(data, off)
    manufacturer, off = read_ptp_string(data, off)
    model, off = read_ptp_string(data, off)
    version, off = read_ptp_string(data, off)
    serial, off = read_ptp_string(data, off)
    return {"manufacturer": manufacturer, "model": model,
            "firmware": version, "serial": serial}
