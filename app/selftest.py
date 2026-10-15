"""End-to-end smoke test against the simulated camera.

Run:  python -m app.selftest
全链路自测：模拟相机 → 发现 → 连接 → 列表/缩略图 → 下载并校验文件。
"""
from __future__ import annotations

import os
import sys
import tempfile

from app import discovery
from app.client import CameraClient
from app.simulator import SimulatedCamera

PHOTO_COUNT = 12


def main() -> int:
    sim = SimulatedCamera(host="127.0.0.1", photo_count=PHOTO_COUNT)
    sim.start()
    print("[1/4] simulated camera started")

    name = discovery.probe_camera("127.0.0.1", timeout=2.0)
    assert name, "discovery probe failed"
    print(f"[2/4] discovery found: {name}")

    client = CameraClient("127.0.0.1", timeout=5.0)
    client.connect()
    client.open_session()
    photos = client.list_photos(thumbs=True)
    assert len(photos) == PHOTO_COUNT, f"expected {PHOTO_COUNT} photos, got {len(photos)}"
    assert all(p.thumb and p.thumb[:2] == b"\xff\xd8" for p in photos), "bad thumbnail data"
    print(f"[3/5] listed {len(photos)} photos with thumbnails")

    # partial object + EXIF parse / 局部读取 + EXIF 解析
    from app import exif as exifmod
    first = photos[0]
    chunk = client.get_partial_object(first.handle, 0, 65536)
    assert chunk[:2] == b"\xff\xd8", "partial object is not a JPEG header"
    meta = exifmod.parse_exif(chunk)
    assert meta.get("make") == "NIKON CORPORATION", f"unexpected EXIF: {meta}"
    assert "gps_lat" in meta, f"expected GPS in first photo, got: {meta}"
    print(f"[4/5] EXIF ok: {meta['fnumber']} {meta['shutter']} ISO {meta['iso']} "
          f"GPS {meta['gps_lat']},{meta['gps_lon']}")

    dest = os.path.join(tempfile.mkdtemp(prefix="nikon_selftest_"), first.filename)
    client.download(first.handle, dest)
    assert os.path.getsize(dest) == first.size, "downloaded size mismatch"
    with open(dest, "rb") as f:
        assert f.read(2) == b"\xff\xd8", "downloaded file is not a JPEG"
    client.close()
    sim.stop()
    print(f"[5/5] downloaded {first.filename} ({first.size} bytes) -> {dest}")
    print("SELFTEST PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
