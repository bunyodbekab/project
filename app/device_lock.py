"""Device identity binding and USB unlock helpers."""

from __future__ import annotations

import glob
import os
import re
import string
import uuid
from datetime import datetime, timezone
from pathlib import Path


DEVICE_LOCK_KEY = "device_lock"
USB_PASSWORD_FILE = "password.txt"
USB_UNLOCK_PASSWORD = "192837456token"


def _decode_mount_token(token: str) -> str:
    """Decode escaped mount tokens from /proc/mounts (e.g. \040 for space)."""
    return (
        str(token or "")
        .replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _read_text_file(file_path: str) -> str:
    # Notepad/USB files can be saved with different encodings; try common ones.
    encodings = ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be", "cp1251", "cp866", "latin-1")
    for encoding in encodings:
        try:
            with open(file_path, "r", encoding=encoding) as file_obj:
                return file_obj.read().strip()
        except Exception:
            continue
    return ""


def _linux_mount_points() -> list[str]:
    mounts_text = _read_text_file("/proc/mounts")
    if not mounts_text:
        return []

    ignored_fs = {
        "proc",
        "sysfs",
        "tmpfs",
        "devtmpfs",
        "devpts",
        "cgroup",
        "cgroup2",
        "mqueue",
        "overlay",
        "squashfs",
        "tracefs",
        "debugfs",
        "securityfs",
        "pstore",
        "bpf",
        "fusectl",
        "configfs",
        "binfmt_misc",
        "nsfs",
        "rpc_pipefs",
        "autofs",
    }

    mount_points = []
    seen = set()
    for line in mounts_text.splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue

        device = str(parts[0])
        mount_point = _decode_mount_token(parts[1])
        fs_type = str(parts[2])

        if fs_type in ignored_fs:
            continue
        if mount_point == "/":
            continue
        if not mount_point.startswith("/"):
            continue
        if not os.path.isdir(mount_point):
            continue

        looks_like_usb_mount = mount_point.startswith(("/media/", "/run/media/", "/mnt/"))
        if not looks_like_usb_mount and not device.startswith("/dev/"):
            continue

        if mount_point in seen:
            continue
        seen.add(mount_point)
        mount_points.append(mount_point)

    return mount_points


def _password_candidates_in_dir(dir_path: str) -> list[str]:
    candidates = []
    target_name = USB_PASSWORD_FILE.lower()

    direct = str(Path(dir_path) / USB_PASSWORD_FILE)
    candidates.append(direct)

    try:
        for entry in os.listdir(dir_path):
            entry_name = str(entry or "")
            entry_lower = entry_name.lower()
            if entry_lower == target_name or entry_lower.startswith(f"{target_name}."):
                candidates.append(str(Path(dir_path) / entry_name))
    except Exception:
        pass

    return candidates


def _read_first_non_empty(paths: list[str]) -> str:
    for file_path in paths:
        value = _read_text_file(file_path)
        if value:
            return value
    return ""


def _cpu_serial_from_cpuinfo() -> str:
    cpuinfo = _read_text_file("/proc/cpuinfo")
    if not cpuinfo:
        return ""

    for line in cpuinfo.splitlines():
        lower = line.lower()
        if not lower.startswith("serial"):
            continue
        parts = line.split(":", 1)
        if len(parts) == 2:
            return parts[1].strip()
    return ""


def get_processor_serial_id() -> str:
    serial_id = _cpu_serial_from_cpuinfo()
    if serial_id:
        return serial_id.lower()

    serial_id = _read_first_non_empty(
        [
            "/sys/devices/virtual/dmi/id/product_uuid",
            "/sys/devices/virtual/dmi/id/board_serial",
            "/etc/machine-id",
            "/var/lib/dbus/machine-id",
        ]
    )
    if serial_id:
        return serial_id.lower()

    node = uuid.getnode()
    if node:
        return f"uuid-{node:012x}"
    return ""


_MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


def _normalize_mac(value: str) -> str:
    raw = str(value or "").strip().lower().replace("-", ":")
    if not raw:
        return ""

    if _MAC_RE.fullmatch(raw):
        return raw

    compact = re.sub(r"[^0-9a-f]", "", raw)
    if len(compact) != 12:
        return ""
    mac = ":".join(compact[i : i + 2] for i in range(0, 12, 2))
    if _MAC_RE.fullmatch(mac):
        return mac
    return ""


def _collect_sysfs_mac_addresses() -> list[str]:
    if not os.path.isdir("/sys/class/net"):
        return []

    ignored_prefixes = ("lo", "docker", "veth", "br-", "virbr", "tun", "tap")
    macs = []
    for iface in os.listdir("/sys/class/net"):
        iface_name = str(iface or "").strip().lower()
        if not iface_name or iface_name.startswith(ignored_prefixes):
            continue

        address_path = f"/sys/class/net/{iface}/address"
        mac = _normalize_mac(_read_text_file(address_path))
        if not mac or mac == "00:00:00:00:00:00":
            continue
        macs.append(mac)
    return macs


def get_mac_addresses() -> list[str]:
    unique = set(_collect_sysfs_mac_addresses())

    if not unique:
        node = uuid.getnode()
        fallback = _normalize_mac(f"{node:012x}")
        if fallback and fallback != "00:00:00:00:00:00":
            unique.add(fallback)

    return sorted(unique)


def collect_device_identity() -> dict:
    return {
        "cpu_serial": get_processor_serial_id(),
        "mac_addresses": get_mac_addresses(),
    }


def _normalize_mac_list(raw_value) -> list[str]:
    if not isinstance(raw_value, list):
        return []

    normalized = []
    for item in raw_value:
        mac = _normalize_mac(str(item))
        if mac:
            normalized.append(mac)

    return sorted(set(normalized))


def evaluate_device_lock(config_data: dict | None) -> dict:
    config_data = config_data or {}
    current_identity = collect_device_identity()
    current_serial = str(current_identity.get("cpu_serial") or "").strip().lower()
    current_macs = _normalize_mac_list(current_identity.get("mac_addresses") or [])

    lock_data = config_data.get(DEVICE_LOCK_KEY)
    if not isinstance(lock_data, dict):
        return {
            "allowed": False,
            "reason": "missing_config",
            "current": current_identity,
        }

    expected_serial = str(lock_data.get("cpu_serial") or "").strip().lower()
    expected_macs = _normalize_mac_list(lock_data.get("mac_addresses") or [])
    if not expected_serial or not expected_macs:
        return {
            "allowed": False,
            "reason": "missing_config",
            "current": current_identity,
        }

    if not current_serial or not current_macs:
        return {
            "allowed": False,
            "reason": "identity_unavailable",
            "current": current_identity,
            "expected": {
                "cpu_serial": expected_serial,
                "mac_addresses": expected_macs,
            },
        }

    if current_serial != expected_serial:
        return {
            "allowed": False,
            "reason": "serial_mismatch",
            "current": current_identity,
            "expected": {
                "cpu_serial": expected_serial,
                "mac_addresses": expected_macs,
            },
        }

    if set(current_macs) != set(expected_macs):
        return {
            "allowed": False,
            "reason": "mac_mismatch",
            "current": current_identity,
            "expected": {
                "cpu_serial": expected_serial,
                "mac_addresses": expected_macs,
            },
        }

    return {
        "allowed": True,
        "reason": "ok",
        "current": current_identity,
        "expected": {
            "cpu_serial": expected_serial,
            "mac_addresses": expected_macs,
        },
    }


def bind_current_device_to_config(config_data: dict) -> dict:
    identity = collect_device_identity()
    cpu_serial = str(identity.get("cpu_serial") or "").strip().lower()
    mac_addresses = _normalize_mac_list(identity.get("mac_addresses") or [])

    if not cpu_serial or not mac_addresses:
        raise RuntimeError("Device identity is unavailable")

    lock_data = {
        "cpu_serial": cpu_serial,
        "mac_addresses": mac_addresses,
        "bound_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    config_data[DEVICE_LOCK_KEY] = lock_data
    return lock_data


def _find_password_files() -> list[str]:
    files = []

    env_path = os.environ.get("MOYKA_USB_PASSWORD_PATH")
    if env_path:
        if os.path.isdir(env_path):
            files.append(str(Path(env_path) / USB_PASSWORD_FILE))
        else:
            files.append(env_path)

    if os.name == "nt":
        for drive_letter in string.ascii_uppercase:
            root = f"{drive_letter}:\\"
            if not os.path.isdir(root):
                continue
            files.extend(_password_candidates_in_dir(root))
    else:
        patterns = [
            f"/media/*/{USB_PASSWORD_FILE}",
            f"/media/*/*/{USB_PASSWORD_FILE}",
            f"/run/media/*/{USB_PASSWORD_FILE}",
            f"/run/media/*/*/{USB_PASSWORD_FILE}",
            f"/mnt/*/{USB_PASSWORD_FILE}",
            f"/mnt/*/*/{USB_PASSWORD_FILE}",
            f"/aa/{USB_PASSWORD_FILE}",
            f"/aa/*/{USB_PASSWORD_FILE}",
            f"/Volumes/*/{USB_PASSWORD_FILE}",
        ]
        for pattern in patterns:
            files.extend(glob.glob(pattern))

        # Armbian/Linux: inspect actual mounted volumes and match case-insensitively.
        for mount_point in _linux_mount_points():
            files.extend(_password_candidates_in_dir(mount_point))

    unique_existing = []
    seen = set()
    for file_path in files:
        full = str(Path(file_path))
        if full in seen:
            continue
        seen.add(full)
        if os.path.isfile(full):
            unique_existing.append(full)

    return unique_existing


def usb_password_matches(expected_password: str = USB_UNLOCK_PASSWORD) -> tuple[bool, str]:
    expected = str(expected_password or "").strip()
    if not expected:
        return False, ""

    for password_path in _find_password_files():
        content = _read_text_file(password_path)
        if content == expected:
            return True, password_path
    return False, ""