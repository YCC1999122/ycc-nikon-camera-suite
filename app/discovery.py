"""Locate PTP/IP cameras on the local network.

相机判定方式：对目标 15740 端口发起真实 PTP/IP 握手，
能完成握手并返回 FriendlyName 的才算相机，不依赖写死的型号字符串。
"""
from __future__ import annotations

import os
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from app import protocol as ptp

CAMERA_HOTSPOT_IP = "192.168.1.1"  # default IP when PC joins the camera hotspot / 相机热点默认地址


def local_ipv4() -> str:
    """Best-effort primary LAN IPv4 (no traffic is actually sent). / 取本机局域网 IP"""
    for target in (CAMERA_HOTSPOT_IP, "8.8.8.8"):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect((target, 80))
            return sock.getsockname()[0]
        except OSError:
            continue
        finally:
            sock.close()
    return "127.0.0.1"


def local_ipv4s() -> list[str]:
    """All private LAN IPv4 addresses of this PC (dual-homed friendly). / 本机所有局域网 IPv4"""
    host = socket.gethostname()
    addrs = {ai[4][0] for ai in socket.getaddrinfo(host, None, socket.AF_INET)}
    return sorted(a for a in addrs if a.startswith(("192.168.", "10.", "172.")))


def probe_port(ip: str, timeout: float = 0.5) -> bool:
    """TCP-only check of the PTP/IP port — does NOT consume the camera's one-shot
    wizard accept slot. / 仅探测端口开放，不发送 PTP 握手，避免占用相机向导的一次性连接槽位"""
    sock = socket.socket()
    sock.settimeout(timeout)
    try:
        sock.connect((ip, ptp.PTPIP_PORT))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def probe_camera(ip: str, timeout: float = 0.4) -> str | None:
    """Return the camera friendly name if a PTP/IP responder lives at ip. / 握手探测单台主机"""
    try:
        sock = socket.create_connection((ip, ptp.PTPIP_PORT), timeout=timeout)
        sock.settimeout(timeout)
        sock.sendall(ptp.build_init_cmd_request(os.urandom(16), "probe"))
        ptype, payload = ptp.recv_packet(sock)
        sock.close()
        if ptype == ptp.PKT_INIT_CMD_ACK:
            return ptp.parse_init_cmd_ack(payload)[2]
    except (OSError, ptp.ProtocolError):
        pass
    return None


def scan(hosts: list[str] | None = None, timeout: float = 1.0,
         workers: int = 128) -> list[tuple[str, str]]:
    """Scan every local subnet and return [(ip, camera_name)]. / 扫描所有本地网段"""
    if hosts is None:
        hosts = [CAMERA_HOTSPOT_IP, "127.0.0.1"]
        for local_ip in local_ipv4s():
            base = local_ip.rsplit(".", 1)[0]
            hosts += [f"{base}.{i}" for i in range(1, 255)]
        hosts = list(dict.fromkeys(hosts))
    found: list[tuple[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(probe_port, ip, timeout): ip for ip in hosts}
        for future in as_completed(futures):
            if future.result():
                found.append((futures[future], "PTP/IP 设备"))
    return sorted(found)
