"""JSON persistence for saved cameras and app settings (project-local).
/ 已保存相机与应用设置的 JSON 持久化（全部存放在项目目录内）"""
from __future__ import annotations

import json
import os
import time

from app.paths import project_root

PROJECT_ROOT = project_root()
DEVICES_FILE = os.path.join(PROJECT_ROOT, "devices.json")
SETTINGS_FILE = os.path.join(PROJECT_ROOT, "settings.json")


def _read(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _write(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---- saved cameras / 已保存相机 ----

def load_devices() -> list[dict]:
    """Each: {ip, name, model, note, last_connected}. / 设备记录列表"""
    return _read(DEVICES_FILE, [])


def save_devices(devices: list[dict]) -> None:
    _write(DEVICES_FILE, devices)


def upsert_device(ip: str, name: str, model: str = "", note: str | None = None) -> None:
    devices = load_devices()
    for dev in devices:
        if dev["ip"] == ip:
            dev["name"] = name or dev["name"]
            dev["model"] = model or dev.get("model", "")
            if note is not None:
                dev["note"] = note
            dev["last_connected"] = time.strftime("%Y-%m-%d %H:%M")
            save_devices(devices)
            return
    devices.append({
        "ip": ip, "name": name or ip, "model": model,
        "note": note or "", "last_connected": time.strftime("%Y-%m-%d %H:%M"),
    })
    save_devices(devices)


def remove_device(ip: str) -> None:
    save_devices([d for d in load_devices() if d["ip"] != ip])


def set_note(ip: str, note: str) -> None:
    devices = load_devices()
    for dev in devices:
        if dev["ip"] == ip:
            dev["note"] = note
    save_devices(devices)


# ---- settings / 应用设置 ----

def get_setting(key: str, default=None):
    return _read(SETTINGS_FILE, {}).get(key, default)


def set_setting(key: str, value) -> None:
    data = _read(SETTINGS_FILE, {})
    data[key] = value
    _write(SETTINGS_FILE, data)
