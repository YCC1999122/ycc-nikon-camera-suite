"""Minimal EXIF reader for JPEG and NEF (TIFF-based) headers.

Works on partial file data (first ~256 KB is enough for IFD0/ExifIFD/GPS).
/ 轻量 EXIF 解析：支持 JPEG (APP1) 与 NEF（本质是 TIFF），
只需文件头部数据即可读出拍摄参数与 GPS，配合 GetPartialObject 使用。
"""
from __future__ import annotations

import struct

_TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8,
              11: 4, 12: 8}

_METERING = {0: "未知", 1: "平均测光", 2: "中央重点", 3: "点测光",
             4: "多区测光", 5: "矩阵测光", 6: "局部测光", 255: "其他"}
_PROGRAM = {0: "未定义", 1: "手动 M", 2: "程序自动 P", 3: "光圈优先 A",
            4: "快门优先 S", 5: "创意程序", 6: "运动程序", 7: "人像模式",
            8: "风景模式"}


def _find_tiff(data: bytes) -> tuple[bytes, int] | None:
    """Locate the TIFF header inside a JPEG, or accept raw TIFF/NEF. / 定位 TIFF 头"""
    if data[:4] in (b"II*\x00", b"MM\x00*"):
        return data, 0  # NEF / TIFF starts right away / NEF 直接就是 TIFF
    if data[:2] != b"\xff\xd8":
        return None
    off = 2  # scan JPEG markers for APP1(Exif) / 扫描 JPEG 标记段
    while off + 4 <= len(data):
        if data[off] != 0xFF:
            break
        marker = data[off + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            off += 2
            continue
        if marker == 0xDA:  # start of scan, metadata is over / 图像数据开始
            break
        (seglen,) = struct.unpack_from(">H", data, off + 2)
        if marker == 0xE1 and data[off + 4:off + 10] == b"Exif\x00\x00":
            return data, off + 10
        off += 2 + max(seglen, 2)
    return None


class _Tiff:
    """Bounded IFD reader tolerant of truncated data. / 容错截断数据的 IFD 读取器"""

    def __init__(self, data: bytes, base: int):
        if data[base:base + 2] == b"II":
            self.endian = "<"
        elif data[base:base + 2] == b"MM":
            self.endian = ">"
        else:
            raise ValueError("bad TIFF byte order")
        self.data = data
        self.base = base

    def u16(self, off: int) -> int:
        return struct.unpack_from(self.endian + "H", self.data, off)[0]

    def u32(self, off: int) -> int:
        return struct.unpack_from(self.endian + "I", self.data, off)[0]

    def ifd(self, ifd_off: int) -> dict[int, tuple[int, int, int]]:
        """Return {tag: (type, count, value_offset)}. / 读取一个 IFD 的条目表"""
        out: dict[int, tuple[int, int, int]] = {}
        start = self.base + ifd_off
        if start + 2 > len(self.data):
            return out
        try:
            count = self.u16(start)
            for i in range(count):
                entry = start + 2 + i * 12
                if entry + 12 > len(self.data):
                    break
                tag = self.u16(entry)
                typ = self.u16(entry + 2)
                num = self.u32(entry + 4)
                out[tag] = (typ, num, entry + 8)
        except struct.error:
            pass
        return out

    def raw(self, entry: tuple[int, int, int]):
        typ, num, valoff = entry
        size = _TYPE_SIZE.get(typ, 1) * num
        if size <= 4:
            buf = self.data[valoff:valoff + 4][:size]
        else:
            ptr = self.u32(valoff)
            buf = self.data[self.base + ptr:self.base + ptr + size]
        if len(buf) < size:
            raise struct.error("truncated value")
        return typ, num, buf

    def ascii(self, entry) -> str:
        try:
            _t, _n, buf = self.raw(entry)
            return buf.split(b"\x00")[0].decode("ascii", "replace").strip()
        except struct.error:
            return ""

    def shorts(self, entry) -> list[int]:
        try:
            typ, num, buf = self.raw(entry)
        except struct.error:
            return []
        if typ == 3:
            return list(struct.unpack_from(self.endian + f"{num}H", buf, 0))
        if typ == 4:
            return list(struct.unpack_from(self.endian + f"{num}I", buf, 0))
        return []

    def rationals(self, entry) -> list[float]:
        """Numeric value(s) as floats: RATIONAL(5), SRATIONAL(10), DOUBLE(12).
        / 数值统一转 float，兼容有理数与双精度（部分写入器用 DOUBLE）"""
        try:
            typ, num, buf = self.raw(entry)
        except struct.error:
            return []
        if typ == 12:
            try:
                return list(struct.unpack_from(self.endian + f"{num}d", buf, 0))
            except struct.error:
                return []
        if typ in (3, 4):
            return [float(v) for v in self.shorts(entry)]
        if typ not in (5, 10):
            return []
        out = []
        fmt = self.endian + ("i" if typ == 10 else "I") * 2
        for i in range(num):
            try:
                n, d = struct.unpack_from(fmt, buf, i * 8)
                out.append(n / d if d else 0.0)
            except struct.error:
                break
        return out


def _fmt_shutter(v: float) -> str:
    if v <= 0:
        return ""
    if v < 1:
        return f"1/{round(1 / v)} s"
    return f"{v:g} s"


def _gps_deg(vals: list[float], ref: str) -> float | None:
    if len(vals) < 3:
        return None
    deg = vals[0] + vals[1] / 60.0 + vals[2] / 3600.0
    if ref in ("S", "W"):
        deg = -deg
    return round(deg, 6)


def parse_exif(data: bytes) -> dict:
    """Parse shooting parameters + GPS from JPEG/NEF bytes.

    Returns display-ready strings plus gps_lat / gps_lon floats when present.
    / 解析拍摄参数与地理位置；返回可直接展示的字符串，GPS 为十进制度数"""
    found = _find_tiff(data)
    if not found:
        return {}
    try:
        t = _Tiff(*found)
    except ValueError:
        return {}
    out: dict = {}

    ifd0 = t.ifd(t.u32(t.base + 4))
    make = t.ascii(ifd0.get(0x010F, ())) if 0x010F in ifd0 else ""
    model = t.ascii(ifd0.get(0x0110, ())) if 0x0110 in ifd0 else ""
    if make:
        out["make"] = make
    if model:
        out["model"] = model

    # Exif sub-IFD / Exif 子目录
    if 0x8769 in ifd0:
        try:
            sub = t.ifd(t.u32(ifd0[0x8769][2]))
        except struct.error:
            sub = {}
        dt = t.ascii(sub[0x9003]) if 0x9003 in sub else ""
        if dt:
            out["datetime"] = dt
        v = t.rationals(sub[0x829D]) if 0x829D in sub else []
        if v:
            out["fnumber"] = f"f/{v[0]:g}"
        v = t.rationals(sub[0x829A]) if 0x829A in sub else []
        if v:
            out["shutter"] = _fmt_shutter(v[0])
        v = t.shorts(sub[0x8827]) if 0x8827 in sub else []
        if v:
            out["iso"] = str(v[0])
        v = t.rationals(sub[0x920A]) if 0x920A in sub else []
        if v:
            out["focal"] = f"{v[0]:g} mm"
        v = t.shorts(sub[0xA405]) if 0xA405 in sub else []
        if v:
            out["focal35"] = f"{v[0]} mm"
        v = t.rationals(sub[0x9204]) if 0x9204 in sub else []
        if v:
            out["bias"] = f"{v[0]:+.1f} EV"
        lens = t.ascii(sub[0xA434]) if 0xA434 in sub else ""
        if lens:
            out["lens"] = lens
        v = t.shorts(sub[0x9209]) if 0x9209 in sub else []
        if v:
            out["flash"] = "已闪光" if v[0] & 1 else "未闪光"
        v = t.shorts(sub[0xA403]) if 0xA403 in sub else []
        if v:
            out["wb"] = "自动白平衡" if v[0] == 0 else "手动白平衡"
        v = t.shorts(sub[0x9207]) if 0x9207 in sub else []
        if v:
            out["metering"] = _METERING.get(v[0], f"模式 {v[0]}")
        v = t.shorts(sub[0x8822]) if 0x8822 in sub else []
        if v:
            out["program"] = _PROGRAM.get(v[0], f"模式 {v[0]}")

    # GPS sub-IFD / GPS 子目录
    if 0x8825 in ifd0:
        try:
            gps = t.ifd(t.u32(ifd0[0x8825][2]))
        except struct.error:
            gps = {}
        lat = _gps_deg(t.rationals(gps[0x0002]) if 0x0002 in gps else [],
                       t.ascii(gps[0x0001]) if 0x0001 in gps else "")
        lon = _gps_deg(t.rationals(gps[0x0004]) if 0x0004 in gps else [],
                       t.ascii(gps[0x0003]) if 0x0003 in gps else "")
        if lat is not None and lon is not None:
            out["gps_lat"] = lat
            out["gps_lon"] = lon
    return out
