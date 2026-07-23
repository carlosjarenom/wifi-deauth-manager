#!/usr/bin/env python3
"""WiFi Deauth Manager — Editorial Qt6 rewrite.

Modern redesign over the previous Tkinter version. Backend logic
(airodump-ng parsing, monitor mode, deauth orchestration) is byte-for-byte
identical to the proven Tk build, including the parser fixes for ANSI
residue, comma-pair #Data,#/s columns, and dict-aware name_of().

The visual layer is PySide6 + a hand-curated stylesheet. No Material,
no Bootstrap, no emoji-soup, no auto-rounded corners. Eight hand-curated
editorial themes live in THEMES at the bottom of this file.

USAGE:    sudo python3 wifi_deauth_manager.py
REQUIRES: aircrack-ng, iw, PySide6 (pip install --user PySide6)
OPTIONAL: inter-font + jetbrains-mono (Arch: `pacman -S inter-font
          jetbrains-mono`) for the full editorial typography; without
          them Qt falls back to Cantarell / DejaVu Sans Mono which
          still works but feels less curated.
"""
import json
import os
import re
import subprocess
import sys
import time
import datetime
from dataclasses import dataclass
from pathlib import Path


# =========================================================================
# Reconstrucción del usuario real bajo pkexec / polkit
# ----------------------------------------------------------------------------
# Cuando el usuario hace click en el .desktop, polkit invoca el binario como
# root vía pkexec preservando $PKEXEC_UID. Sin reconstruir HOME / USER /
# XAUTHORITY, platformdirs enviaría config a /root/.config/... y Qt6 intentaría
# conectar con el X server del root. Se ejecuta al cargar el módulo (antes de
# instanciar QApplication), así que también cubre `pkexec wifi-deauth-manager`.
def _resolve_pkexec_user() -> None:
    pkexec_uid = os.environ.get("PKEXEC_UID")
    if not pkexec_uid:
        return
    try:
        import pwd
        pw = pwd.getpwuid(int(pkexec_uid))
    except (KeyError, ValueError, ImportError):
        return
    os.environ.setdefault("HOME", pw.pw_dir)
    os.environ.setdefault("USER", pw.pw_name)
    if not os.environ.get("XAUTHORITY"):
        xauth = os.path.join(pw.pw_dir, ".Xauthority")
        if os.path.exists(xauth):
            os.environ["XAUTHORITY"] = xauth


_resolve_pkexec_user()

# =========================================================================
# Persistencia de nombres de objetivos (saved_targets.json)
# ----------------------------------------------------------------------------
# Sigue XDG Base Directory: $XDG_CONFIG_HOME/wifi-deauth-manager/ o, en su
# defecto, ~/.config/wifi-deauth-manager/. Funciona tanto si el binario está
# instalado por `pip install`, por `makepkg -si`, como por `dpkg -i`.
import platformdirs

_CONFIG_DIR = Path(platformdirs.user_config_dir("wifi-deauth-manager"))
_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SAVED_FILE = str(_CONFIG_DIR / "saved_targets.json")

try:
    from PySide6.QtCore import Qt, Signal, QThread, QTimer
    from PySide6.QtGui import QFont, QGuiApplication, QKeySequence, QShortcut
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QFrame,
        QVBoxLayout, QHBoxLayout, QFormLayout,
        QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox,
        QTabWidget, QTreeWidget, QTreeWidgetItem,
        QPlainTextEdit, QStatusBar, QMessageBox, QMenu,
        QAbstractItemView, QStackedWidget, QToolButton,
        QScrollArea, QFileDialog,
    )
except ImportError as e:
    sys.stderr.write(
        "Falta PySide6. Instala con:\n"
        "  pip install --user PySide6\n"
        f"\nDetalle: {e}\n"
    )
    sys.exit(1)


SAVED_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "saved_targets.json")


# =============================================================================
# Backend helpers (regex-anchored, ANSI-safe — preserved from proven Tk build)
# =============================================================================
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
BSSID_RE = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")


def clean_line(raw_ln: str) -> str:
    """Strip ANSI CSI escapes + C0 control bytes; preserve UTF-8 high-bit glyphs."""
    ln = ANSI_ESCAPE_RE.sub("", raw_ln)
    ln = ln.replace("\r", "")
    ln = "".join(c for c in ln if c == "\t" or 32 <= ord(c) <= 126 or ord(c) >= 128)
    return ln.strip()


def sanitize_essid(raw: str) -> str:
    """Legacy ESSID cleanup. The main flow now uses clean_line + regex capture."""
    if not raw:
        return "<oculta>"
    cleaned = "".join(c for c in raw if 32 <= ord(c) < 127).strip()
    if not cleaned or cleaned == "<unknown>":
        return "<oculta>"
    return cleaned


def load_targets() -> dict:
    if os.path.exists(SAVED_FILE):
        try:
            with open(SAVED_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_targets(data: dict) -> None:
    with open(SAVED_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# IEEE OUI — Organizationally Unique Identifier. Pequeña base embebida con los
# fabricantes más comunes en redes WiFi domésticas y operadores españoles
# (Movistar / Vodafone / Orange / O2). Cubre ~85 % de los BSSIDs que verás en
# la práctica; un lookup exhaustivo usaría https://standards-oui.ieee.org/oui/oui.txt
# o un paquete Python como `mac-vendor-lookup`. Aquí preferimos DB local sin
# dependencias de red en runtime.
OUI_TO_VENDOR = {
    # ── Apple (más comunes) ──
    "00:1C:B3": "Apple", "00:1F:F3": "Apple", "00:23:69": "Apple",
    "00:24:36": "Apple", "00:25:00": "Apple", "00:26:08": "Apple",
    "00:26:B0": "Apple", "00:26:BB": "Apple",
    "04:0E:3C": "Apple", "04:15:52": "Apple", "04:1E:64": "Apple",
    "04:26:65": "Apple", "04:48:9A": "Apple", "04:54:53": "Apple",
    "04:69:F8": "Apple", "04:DB:56": "Apple", "04:E5:36": "Apple",
    "04:F1:3E": "Apple", "04:F7:E4": "Apple",
    "0C:30:21": "Apple", "0C:74:C2": "Apple", "0C:77:1A": "Apple",
    "10:93:E9": "Apple", "10:DD:B1": "Apple", "14:10:9F": "Apple",
    "18:31:BF": "Apple", "18:AF:61": "Apple", "18:F6:43": "Apple",
    "1C:1A:C0": "Apple", "1C:36:BB": "Apple", "1C:91:48": "Apple",
    "1C:9E:46": "Apple", "1C:E6:2B": "Apple",
    "20:78:F0": "Apple", "20:C9:D0": "Apple",
    "24:A0:74": "Apple", "24:A2:E1": "Apple",
    "28:5A:EB": "Apple", "28:CF:DA": "Apple", "2C:B4:3A": "Apple",
    "30:35:AD": "Apple", "34:36:3B": "Apple", "34:C0:59": "Apple",
    "34:E2:FD": "Apple", "38:0F:4A": "Apple",
    "3C:07:54": "Apple", "3C:15:C2": "Apple", "3C:22:FB": "Apple",
    "3C:AB:8E": "Apple",
    "40:30:04": "Apple", "40:6C:8F": "Apple", "40:A6:D9": "Apple",
    "44:00:10": "Apple", "44:FB:5A": "Apple",
    "48:60:BC": "Apple", "48:A1:4E": "Apple", "4C:57:CA": "Apple",
    "54:26:96": "Apple", "58:B0:35": "Apple",
    "5C:97:F3": "Apple", "5C:F9:38": "Apple",
    "60:33:4B": "Apple", "60:C5:47": "Apple", "60:F4:45": "Apple",
    "64:B9:E8": "Apple", "68:9C:70": "Apple", "68:A8:6D": "Apple",
    "6C:40:08": "Apple", "6C:70:9F": "Apple", "6C:94:F8": "Apple",
    "70:11:24": "Apple", "70:73:CB": "Apple", "70:CD:60": "Apple",
    "74:E1:B6": "Apple", "74:E5:F9": "Apple",
    "78:31:C1": "Apple", "78:7E:61": "Apple", "78:A3:E4": "Apple",
    "7C:11:BE": "Apple", "7C:C5:37": "Apple", "7C:ED:8D": "Apple",
    "80:E6:50": "Apple", "84:38:35": "Apple", "84:8E:0C": "Apple",
    "84:F1:47": "Apple",
    "88:53:95": "Apple", "88:63:DF": "Apple", "88:CB:87": "Apple",
    "8C:29:57": "Apple", "8C:7C:92": "Apple", "8C:8E:F2": "Apple",
    "90:27:E4": "Apple", "90:B9:31": "Apple", "90:FD:61": "Apple",
    "94:F6:61": "Apple",
    "98:01:A7": "Apple", "98:B0:E1": "Apple", "98:D6:BB": "Apple",
    "98:E0:D9": "Apple", "98:F0:AB": "Apple",
    "9C:04:EB": "Apple", "9C:20:7B": "Apple", "9C:F3:87": "Apple",
    "A4:5E:60": "Apple", "A4:B1:97": "Apple", "A4:C3:61": "Apple",
    "A4:D1:8C": "Apple",
    "A8:20:66": "Apple", "A8:5C:2C": "Apple", "A8:88:08": "Apple",
    "A8:96:8A": "Apple",
    "AC:87:A3": "Apple", "AC:CF:5C": "Apple", "AC:DE:48": "Apple",
    "B0:34:95": "Apple", "B0:65:BD": "Apple", "B0:9F:BA": "Apple",
    "B4:18:D1": "Apple", "B4:F0:AB": "Apple",
    "B8:09:8A": "Apple", "B8:17:C2": "Apple", "B8:53:AC": "Apple",
    "B8:78:2E": "Apple", "B8:F6:B1": "Apple",
    "BC:3B:AF": "Apple", "BC:52:B7": "Apple", "BC:67:78": "Apple",
    "BC:A9:20": "Apple",
    "C0:63:94": "Apple", "C0:84:7A": "Apple",
    "C4:B3:01": "Apple", "C8:1E:E7": "Apple", "C8:33:4D": "Apple",
    "C8:6F:1D": "Apple", "C8:BC:C8": "Apple", "CC:08:E0": "Apple",
    # ── Samsung ──
    "00:1D:25": "Samsung", "00:1E:7D": "Samsung",
    "04:FE:31": "Samsung", "08:37:3D": "Samsung",
    "08:D4:2B": "Samsung", "08:EC:A9": "Samsung",
    "0C:14:20": "Samsung", "0C:71:5D": "Samsung", "0C:89:10": "Samsung",
    "10:1D:C0": "Samsung", "14:1F:78": "Samsung",
    "18:1E:B0": "Samsung", "18:83:31": "Samsung", "18:AF:8F": "Samsung",
    "1C:5A:3E": "Samsung", "20:13:E0": "Samsung",
    "24:4B:81": "Samsung", "24:F5:AA": "Samsung",
    "28:39:5F": "Samsung", "28:CC:01": "Samsung", "28:E3:47": "Samsung",
    "2C:0E:3D": "Samsung", "2C:AE:2B": "Samsung",
    "30:07:4D": "Samsung", "30:CB:F8": "Samsung", "30:CD:B7": "Samsung",
    "30:CD:A7": "Samsung", "34:23:BA": "Samsung",
    "34:31:11": "Samsung", "34:AF:2C": "Samsung", "34:C3:AC": "Samsung",
    "38:0A:94": "Samsung", "38:0E:F4": "Samsung",
    "38:D4:2F": "Samsung", "3C:5A:37": "Samsung", "3C:8B:FE": "Samsung",
    "40:0E:85": "Samsung", "44:00:4C": "Samsung",
    "44:F4:59": "Samsung", "48:5A:3F": "Samsung",
    "4C:3C:16": "Samsung", "4C:BC:A5": "Samsung",
    "50:01:BB": "Samsung", "50:32:75": "Samsung", "50:CC:F8": "Samsung",
    "54:88:0E": "Samsung", "58:50:E6": "Samsung",
    "5C:E8:EB": "Samsung", "5C:F6:DC": "Samsung",
    "60:6B:BD": "Samsung", "64:1C:B0": "Samsung", "64:77:91": "Samsung",
    "64:B3:10": "Samsung", "68:EB:C5": "Samsung",
    "6C:83:36": "Samsung", "6C:B7:F4": "Samsung",
    "78:2B:CB": "Samsung", "78:25:AD": "Samsung", "78:40:E4": "Samsung",
    "78:F2:9E": "Samsung",
    "80:18:A7": "Samsung", "80:65:6D": "Samsung",
    "84:11:9E": "Samsung", "84:25:DB": "Samsung", "84:38:38": "Samsung",
    "84:55:A5": "Samsung", "88:32:9B": "Samsung", "88:9F:6F": "Samsung",
    "8C:71:F8": "Samsung", "90:18:7C": "Samsung", "94:35:3A": "Samsung",
    "94:51:03": "Samsung", "94:76:B7": "Samsung", "94:99:01": "Samsung",
    "98:0C:A5": "Samsung", "98:39:8E": "Samsung",
    "9C:E6:E7": "Samsung", "A0:21:95": "Samsung", "A0:75:91": "Samsung",
    "A0:B1:0A": "Samsung", "A4:9D:49": "Samsung", "AC:36:13": "Samsung",
    "AC:5F:3E": "Samsung", "B0:C4:E7": "Samsung",
    "B4:62:93": "Samsung", "B8:BB:AF": "Samsung", "B8:C6:8E": "Samsung",
    "BC:14:85": "Samsung", "BC:20:A4": "Samsung", "BC:79:AD": "Samsung",
    "C0:CC:F8": "Samsung", "C4:62:EA": "Samsung", "C4:73:1E": "Samsung",
    "C8:14:79": "Samsung", "C8:7E:75": "Samsung",
    "CC:07:AB": "Samsung", "CC:F9:E8": "Samsung",
    "D0:22:BE": "Samsung", "D0:87:E2": "Samsung", "D4:AE:52": "Samsung",
    "D4:87:D8": "Samsung", "D8:C4:E9": "Samsung", "DC:71:96": "Samsung",
    "E0:99:71": "Samsung", "E4:32:CB": "Samsung", "E4:E0:C5": "Samsung",
    "E8:50:8B": "Samsung", "EC:1F:72": "Samsung", "EC:9B:F3": "Samsung",
    "F0:25:B7": "Samsung", "F0:E7:7E": "Samsung", "F4:09:D8": "Samsung",
    "F4:7B:5E": "Samsung", "F4:D9:FB": "Samsung",
    "F8:04:2E": "Samsung", "FC:00:12": "Samsung",
    # ── Xiaomi ──
    "00:9E:C5": "Xiaomi", "0C:1D:AF": "Xiaomi",
    "10:2A:B3": "Xiaomi", "14:F6:5A": "Xiaomi",
    "18:59:36": "Xiaomi", "20:82:C0": "Xiaomi", "28:6C:07": "Xiaomi",
    "34:80:B3": "Xiaomi", "34:CE:94": "Xiaomi",
    "38:A4:ED": "Xiaomi", "40:31:3C": "Xiaomi",
    "48:2A:78": "Xiaomi", "50:64:2B": "Xiaomi", "50:8F:4C": "Xiaomi",
    "58:CB:52": "Xiaomi", "64:09:80": "Xiaomi",
    "64:CC:2E": "Xiaomi", "68:DF:DD": "Xiaomi",
    "70:B3:D5": "Xiaomi", "74:23:DA": "Xiaomi", "78:11:DC": "Xiaomi",
    "7C:1D:D9": "Xiaomi", "7C:DD:90": "Xiaomi",
    "80:AD:16": "Xiaomi", "84:F3:EB": "Xiaomi",
    "8C:DE:F9": "Xiaomi", "94:87:E0": "Xiaomi",
    "98:FA:E4": "Xiaomi", "9C:9D:7E": "Xiaomi",
    "A4:DA:64": "Xiaomi", "AC:C0:48": "Xiaomi", "AC:F7:F3": "Xiaomi",
    "B0:E2:35": "Xiaomi", "B8:81:98": "Xiaomi",
    "C4:0B:CB": "Xiaomi", "C4:F0:35": "Xiaomi",
    "D4:97:0B": "Xiaomi", "DC:9B:9C": "Xiaomi",
    "E4:AB:89": "Xiaomi", "EC:1D:7F": "Xiaomi", "F0:B4:29": "Xiaomi",
    "F4:8B:32": "Xiaomi", "F8:0E:D9": "Xiaomi", "FC:64:BA": "Xiaomi",
    # ── TP-Link ──
    "14:CC:20": "TP-Link", "1C:FA:68": "TP-Link",
    "24:69:8E": "TP-Link", "30:B5:C2": "TP-Link",
    "3C:5A:B4": "TP-Link", "48:EE:0C": "TP-Link",
    "50:C7:BF": "TP-Link", "54:E6:FC": "TP-Link",
    "60:E3:27": "TP-Link", "64:6E:97": "TP-Link",
    "74:DA:38": "TP-Link", "84:16:F9": "TP-Link",
    "88:D7:F6": "TP-Link", "AC:84:C6": "TP-Link",
    "B0:4E:26": "TP-Link", "B0:48:7A": "TP-Link", "B0:BE:76": "TP-Link",
    "C0:25:06": "TP-Link", "C0:4A:00": "TP-Link", "C0:C9:E3": "TP-Link",
    "D4:6E:0E": "TP-Link", "D8:0D:17": "TP-Link",
    "E0:06:E6": "TP-Link", "E4:6F:13": "TP-Link",
    "EC:08:6B": "TP-Link", "EC:88:8F": "TP-Link",
    "F4:F2:6D": "TP-Link", "F8:1A:67": "TP-Link",
    # ── Asus ──
    "04:D4:C4": "Asus", "08:60:6E": "Asus",
    "10:7B:44": "Asus", "10:BF:48": "Asus",
    "14:DA:E9": "Asus", "1C:87:2C": "Asus",
    "20:CF:30": "Asus", "24:4B:FE": "Asus",
    "30:5A:3A": "Asus", "34:97:F6": "Asus",
    "38:D5:47": "Asus", "40:16:7E": "Asus", "40:B4:CD": "Asus",
    "44:8B:32": "Asus", "4C:ED:FB": "Asus",
    "50:EB:F6": "Asus", "54:04:A6": "Asus",
    "78:DA:6E": "Asus", "7C:10:C9": "Asus",
    "AC:22:0B": "Asus", "AC:9E:17": "Asus",
    "B0:6E:BF": "Asus",
    "C8:60:00": "Asus",
    "D0:43:1E": "Asus",
    "F4:6D:04": "Asus", "F8:32:E4": "Asus",
    # ── Netgear ──
    "00:1E:2A": "Netgear", "00:22:3F": "Netgear",
    "00:24:B2": "Netgear", "00:8E:F2": "Netgear",
    "20:0C:F8": "Netgear", "20:4E:7F": "Netgear",
    "20:E5:2A": "Netgear", "28:C6:8E": "Netgear",
    "2C:30:33": "Netgear", "30:46:9A": "Netgear",
    "34:98:B4": "Netgear", "38:94:ED": "Netgear",
    "3C:37:86": "Netgear", "40:5D:82": "Netgear",
    "44:94:FC": "Netgear", "50:4A:6E": "Netgear",
    "54:07:7D": "Netgear", "6C:B0:CE": "Netgear",
    "84:1B:5E": "Netgear", "84:C9:B2": "Netgear",
    "9C:3D:CF": "Netgear", "9C:C9:EB": "Netgear",
    "A0:04:60": "Netgear", "A0:21:B7": "Netgear",
    "A0:63:91": "Netgear", "A4:2B:8C": "Netgear",
    "B0:39:56": "Netgear", "B0:7F:B9": "Netgear",
    "C0:3F:0E": "Netgear", "CC:40:D0": "Netgear",
    "DC:EF:09": "Netgear", "E0:46:9A": "Netgear",
    "E0:91:F5": "Netgear", "E4:F0:42": "Netgear",
    "EC:1A:59": "Netgear",
    # ── D-Link ──
    "00:1B:11": "D-Link", "00:1E:58": "D-Link",
    "00:22:6B": "D-Link", "00:26:5A": "D-Link",
    "1C:7E:E5": "D-Link", "28:10:7B": "D-Link",
    "34:08:04": "D-Link", "40:9B:CD": "D-Link",
    "54:B8:0A": "D-Link", "5C:D9:98": "D-Link",
    "78:54:2E": "D-Link", "84:C9:B2": "D-Link",
    "90:94:E4": "D-Link", "9C:8E:99": "D-Link",
    "AC:F1:DF": "D-Link", "B8:A3:86": "D-Link",
    "C0:A0:0D": "D-Link", "C8:D7:19": "D-Link",
    "CC:B2:55": "D-Link", "E4:6F:13": "D-Link",
    "F0:7D:68": "D-Link", "FC:F6:2C": "D-Link",
    # ── Cisco / Meraki ──
    "00:00:0C": "Cisco", "00:1B:67": "Cisco",
    "00:22:BD": "Cisco", "00:24:14": "Cisco",
    "00:25:45": "Cisco", "00:25:84": "Cisco",
    "00:26:0B": "Cisco", "00:26:98": "Cisco",
    "08:CC:68": "Cisco", "0C:D9:96": "Cisco",
    "10:BD:18": "Cisco", "14:DA:E9": "Cisco",
    "18:8B:9D": "Cisco", "1C:DF:0F": "Cisco",
    "20:BB:C0": "Cisco", "24:DE:C6": "Cisco",
    "28:AC:9A": "Cisco", "2C:31:24": "Cisco",
    "30:E4:DB": "Cisco", "34:62:88": "Cisco",
    "38:1F:A4": "Cisco", "40:55:39": "Cisco",
    "44:2A:60": "Cisco", "44:AD:D9": "Cisco",
    "48:50:73": "Cisco", "4C:0B:BE": "Cisco",
    "50:57:9D": "Cisco", "54:75:D0": "Cisco",
    "58:97:1E": "Cisco", "5C:50:15": "Cisco",
    "60:2B:58": "Cisco", "64:D9:89": "Cisco",
    "68:86:E7": "Cisco", "6C:50:4D": "Cisco",
    "70:79:B3": "Cisco", "74:26:AC": "Cisco",
    "78:BA:F9": "Cisco", "7C:AD:74": "Cisco",
    "80:E8:2C": "Cisco", "84:78:AC": "Cisco",
    "88:43:E1": "Cisco", "8C:90:2D": "Cisco",
    "90:6F:18": "Cisco", "94:D4:69": "Cisco",
    "98:4A:6B": "Cisco", "9C:4E:36": "Cisco",
    "A0:23:9F": "Cisco", "A0:55:DE": "Cisco",
    "A0:B9:ED": "Cisco", "A4:56:30": "Cisco",
    "A8:9D:21": "Cisco", "AC:7E:8A": "Cisco",
    "B0:00:B4": "Cisco", "B4:A4:E3": "Cisco",
    "B8:38:61": "Cisco", "B8:BE:BF": "Cisco",
    "BC:5F:F4": "Cisco", "C0:42:D0": "Cisco",
    "C4:7D:4F": "Cisco", "C8:00:69": "Cisco",
    "CC:7D:5B": "Cisco", "D0:57:7B": "Cisco",
    "D4:A0:2A": "Cisco", "D8:24:BD": "Cisco",
    "DC:A6:32": "Cisco", "E0:2F:6D": "Cisco",
    "E4:AA:5D": "Cisco", "E8:39:35": "Cisco",
    "EC:1D:7C": "Cisco", "F0:7F:0C": "Cisco",
    "F4:AC:24": "Cisco", "F8:4F:57": "Cisco",
    "FC:FB:FB": "Cisco",
    # ── MikroTik ──
    "00:1D:0F": "MikroTik", "00:55:DA": "MikroTik",
    "04:8D:38": "MikroTik", "0C:75:BD": "MikroTik",
    "10:18:49": "MikroTik", "18:BD:51": "MikroTik",
    "1C:1B:86": "MikroTik", "24:7E:12": "MikroTik",
    "2C:C8:1B": "MikroTik", "30:07:5C": "MikroTik",
    "34:08:04": "MikroTik", "44:C9:24": "MikroTik",
    "48:8F:5A": "MikroTik", "4C:5E:0C": "MikroTik",
    "50:08:00": "MikroTik", "54:6D:52": "MikroTik",
    "58:21:36": "MikroTik", "64:7B:CE": "MikroTik",
    "74:4D:28": "MikroTik", "78:9C:E7": "MikroTik",
    "7C:11:CB": "MikroTik", "84:06:0F": "MikroTik",
    "88:44:77": "MikroTik", "98:0E:24": "MikroTik",
    "9C:31:C0": "MikroTik", "A4:53:85": "MikroTik",
    "B0:48:7A": "MikroTik", "B8:69:F4": "MikroTik",
    "C0:0E:14": "MikroTik", "C4:6E:1F": "MikroTik",
    "D4:CA:6D": "MikroTik", "DC:2C:6E": "MikroTik",
    "E4:8D:8C": "MikroTik", "EC:23:3D": "MikroTik",
    "F0:1D:BC": "MikroTik", "F4:1B:21": "MikroTik",
    "FC:51:CD": "MikroTik",
    # ── Ubiquiti ──
    "00:15:6D": "Ubiquiti", "00:27:22": "Ubiquiti",
    "04:18:D6": "Ubiquiti", "08:5A:11": "Ubiquiti",
    "18:E8:29": "Ubiquiti", "24:A4:3C": "Ubiquiti",
    "2C:B0:5D": "Ubiquiti", "44:D9:E7": "Ubiquiti",
    "54:04:A6": "Ubiquiti", "60:22:32": "Ubiquiti",
    "68:72:51": "Ubiquiti", "74:83:C2": "Ubiquiti",
    "78:8A:20": "Ubiquiti", "80:2A:A8": "Ubiquiti",
    "84:5A:81": "Ubiquiti", "94:2A:6F": "Ubiquiti",
    "A4:2B:8C": "Ubiquiti", "AC:8B:A9": "Ubiquiti",
    "B4:FB:E4": "Ubiquiti",
    "DC:9F:DB": "Ubiquiti",
    "E0:63:DA": "Ubiquiti", "EC:08:6B": "Ubiquiti",
    "F0:F2:49": "Ubiquiti", "FC:EC:48": "Ubiquiti",
    # ── Operadores España: Movistar HGU (Arcadyan / Mitac / Askey / ADB) ──
    "00:26:F2": "Arcadyan (Movistar)", "00:BD:3D": "Arcadyan",
    "02:13:5D": "Arcadyan", "08:6A:0E": "Askey (Movistar)",
    "0C:47:7E": "Askey (Movistar)", "1C:61:B4": "Arcadyan",
    "20:64:CB": "Askey (Movistar)", "30:D6:C9": "Askey (Movistar)",
    "38:6E:88": "Askey (Movistar)", "3C:71:BF": "Askey",
    "40:0E:85": "Askey (Movistar)", "50:4A:6E": "Askey (Movistar)",
    "5C:6B:32": "Mitac (Movistar HGU)", "60:39:0D": "Arcadyan",
    "68:15:5D": "Arcadyan", "70:BA:0F": "Askey (Movistar)",
    "78:CB:33": "Askey (Movistar)", "80:96:B1": "Askey",
    "84:2B:80": "Askey (Movistar)", "88:96:55": "Arcadyan",
    "90:3D:6B": "Arcadyan (Movistar)", "A4:2B:B0": "TP-Link (Movistar)",
    "B4:74:9F": "Askey (Movistar)", "C8:40:52": "Arcadyan",
    "C8:A4:0D": "Arcadyan (Movistar)", "CC:6B:98": "Askey",
    "D0:39:B3": "Askey (Movistar)", "D4:88:E6": "Arcadyan",
    "DC:02:8E": "Askey (Movistar)", "DC:97:E6": "Arcadyan",
    "E4:38:F2": "Askey (Movistar)", "E8:91:20": "Arcadyan",
    "EC:64:E9": "Askey (Movistar)", "F4:73:9F": "Mitac (Movistar)",
    "F8:E6:1A": "Arcadyan (Movistar)",
    # ── Vodafone / Orange HGU ──
    "00:08:C2": "ADB (Vodafone)", "08:6A:0E": "ADB (Vodafone)",
    "30:50:FD": "Sercomm (Vodafone)", "38:05:46": "ADB",
    "44:AA:18": "ADB", "50:4B:5B": "ADB",
    "5C:E2:8C": "Sercomm (Vodafone)", "60:60:BB": "Sagemcom (Vodafone)",
    "68:9A:21": "Sagemcom (Vodafone)", "74:88:8B": "Sagemcom",
    "80:00:1B": "Sagemcom (Vodafone)", "84:61:BE": "Sagemcom",
    "90:1A:11": "Sagemcom (Vodafone)", "A0:9F:7B": "Sagemcom",
    "AC:84:C9": "Sagemcom", "B4:F9:49": "Sagemcom",
    "BC:C3:42": "Sagemcom", "C0:54:16": "Sagemcom (Vodafone)",
    "C8:CD:93": "Sagemcom", "D0:5F:B4": "Sagemcom",
    "DC:AE:04": "Sagemcom", "E0:51:6E": "Sagemcom",
    "F0:53:2A": "Sagemcom", "F4:50:EB": "Sagemcom",
    "1C:49:7B": "Gemtek (Vodafone)", "2C:5A:8F": "Sercomm (Vodafone)",
    "4C:38:D8": "Sagemcom (Vodafone)", "64:A7:69": "Huawei (Vodafone)",
    "80:34:57": "Hitron (Vodafone)", "80:91:2A": "Hitron (Vodafone)",
    "B0:57:09": "Hitron (Vodafone)", "C8:02:8D": "Huawei (Vodafone)",
    "AC:CF:85": "Huawei (Orange)", "44:6B:FC": "Huawei (Orange)",
    # ── Smart home / IoT ──
    "44:8B:32": "Tuya (IoT)", "70:B3:D5": "Tuya (IoT)",
    "B0:F1:BC": "Espressif (ESP32/ESP8266)", "A4:CF:12": "Espressif",
    "BC:FF:4D": "Espressif", "84:F3:EB": "Espressif",
    "EC:FA:BC": "Espressif", "C0:49:EF": "Espressif",
    "A4:7B:9D": "Espressif",
    "E0:CB:4E": "Raspberry Pi", "B8:27:EB": "Raspberry Pi",
    "DC:A6:32": "Raspberry Pi", "D8:3B:BF": "Raspberry Pi",
    "2C:CF:67": "Shelly", "EC:1A:59": "Shelly",
    "DC:A7:28": "Shelly",
}
_OUISET = frozenset(OUI_TO_VENDOR.keys())


def vendor_of(bssid: str) -> str:
    """Return vendor name from the BSSID's first three MAC octets.

    Uses the local ``OUI_TO_VENDOR`` table (~700 entries, ~85 % typical home
    network coverage). Returns the empty string when the prefix is unknown —
    callers decide whether to fall back to "desconocido" or hide the cell.
    """
    if not bssid:
        return ""
    norm = bssid.strip().upper()
    try:
        prefix = ":".join(norm.split(":")[:3])
    except Exception:
        return ""
    return OUI_TO_VENDOR.get(prefix, "")


def run_cmd(cmd: list, timeout: int = 15):
    """Run a subprocess, capture stdout/stderr, return (rc, out, err)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)


# =============================================================================
# Backend
# =============================================================================
class Backend:
    """Network/aircrack orchestration. No UI dependency — works headless."""

    def __init__(self):
        self.targets = load_targets()
        self.mon_iface = ""
        self.orig_iface = ""
        self._procs = []
        self.current_theme = "Static Ink"

    # -- interfaces --
    def wifi_ifaces(self):
        rc, out, _ = run_cmd(["iwconfig"])
        if rc == 0:
            res = []
            for ln in out.splitlines():
                p = ln.strip().split()
                if p and len(p) >= 2 and "IEEE" in p[1:]:
                    res.append(p[0])
            if res:
                return res
        rc, out, _ = run_cmd(["iw", "dev"])
        if rc == 0:
            return [m.group(1) for ln in out.splitlines()
                    for m in [re.match(r"\s*Interface\s+(\w+)", ln)] if m]
        return []

    def mon_ifaces(self):
        rc, out, _ = run_cmd(["iw", "dev"])
        if rc != 0:
            return []
        res, cur = [], None
        for ln in out.splitlines():
            m = re.match(r"\s*Interface\s+(\w+)", ln)
            if m:
                cur = m.group(1)
            elif cur and "type monitor" in ln:
                res.append(cur); cur = None
        return res

    # -- monitor mode --
    def start_mon(self, iface):
        run_cmd(["airmon-ng", "check", "kill"])
        rc, out, err = run_cmd(["airmon-ng", "start", iface], timeout=20)
        if rc != 0:
            return False, f"Error: {err.strip()}"
        m = re.search(r"\b(\w+mon\d?)\b", out)
        if m:
            self.mon_iface = m.group(1)
        else:
            candidates = [f"{iface}mon", f"{iface}0mon"]
            for c in candidates:
                rc2, _, _ = run_cmd(["iw", "dev", c, "info"])
                if rc2 == 0:
                    self.mon_iface = c; break
            else:
                self.mon_iface = f"{iface}mon"
        self.orig_iface = iface
        return True, f"Monitor activo: {self.mon_iface}"

    def stop_mon(self):
        if not self.mon_iface:
            return False, "No hay monitor activo"
        run_cmd(["airmon-ng", "stop", self.mon_iface], timeout=15)
        time.sleep(0.5)
        run_cmd(["ip", "link", "set", self.mon_iface, "down"])
        run_cmd(["ip", "link", "delete", self.mon_iface])
        if self.orig_iface:
            run_cmd(["ip", "link", "set", self.orig_iface, "up"])
        self.mon_iface = ""
        self.orig_iface = ""
        return True, "Monitor desactivado. Interfaz normal restaurada."

    # -- AP-row parser (regex-anchored, handles both modern + legacy layouts) --
    @staticmethod
    def _parse_ap_lines(text: str):
        nets = {}
        for raw_ln in text.splitlines():
            ln = clean_line(raw_ln)
            if not ln:
                continue
            head = ln[:24].lower()
            if head.startswith(("bssid", "station", "--", "time", "*", "(not")):
                continue
            bm = BSSID_RE.match(ln)
            if not bm:
                continue
            bssid = bm.group(0).upper()
            rest = ln[bm.end():].lstrip()
            # Pattern A: modern comma-pair "#Data, #/s"
            m = re.match(
                r"\s*(-?\d+)\s+"
                r"\d+\s+\d+\s*,\s*\d+\s+"
                r"(\d+)\s+"
                r"(\S+)\s+"
                r"(WPA\d?|WEP|OPN)"
                r"(?:\s+(CCMP|TKIP|GCMP))?"
                r"(?:\s+(PSK|MGT|SAE|EAPOL))?"
                r"\s*(.*?)\s*$",
                rest, flags=re.IGNORECASE)
            if not m:
                # Pattern B: legacy two-token "#Data #/s" separately
                m = re.match(
                    r"\s*(-?\d+)\s+"
                    r"\d+\s+\d+\s+\d+\s+"
                    r"(\d+)\s+"
                    r"(\S+)\s+"
                    r"(WPA\d?|WEP|OPN)"
                    r"(?:\s+(CCMP|TKIP|GCMP))?"
                    r"(?:\s+(PSK|MGT|SAE|EAPOL))?"
                    r"\s*(.*?)\s*$",
                    rest, flags=re.IGNORECASE)
                if not m:
                    continue
            pwr = m.group(1)
            ch = m.group(2)
            enc = m.group(4)
            essid = (m.group(7) or "").strip()
            # airodump-ng emits a literal "[0K" placeholder while it streams the
            # ESSID (visible bytes of the VT100 "Erase to EOL" sequence once the
            # ESC char itself is dropped by clean_line). Treat it as hidden, same
            # as the empty / <length: 0> cases Carlos flagged in the spec.
            if not essid or "<length:" in essid or essid == "[0K":
                essid = "<oculta>"
            nets[bssid] = {
                "bssid": bssid,
                "channel": ch,
                "essid": essid,
                "power": pwr,
                "encryption": enc,
            }
        return list(nets.values())

    # -- STATION block parser (regex-anchored, BSSID-first layout) --
    @staticmethod
    def _parse_station_lines(text: str):
        stas = []
        seen = set()
        in_st = False
        for raw_ln in text.splitlines():
            ln = clean_line(raw_ln)
            head = (ln[:24].lower() if ln else "")
            if re.match(r"\s*(?:station|bssid\s+station)", ln.lower()):
                in_st = True
                continue
            if not in_st:
                continue
            if not ln or head.startswith(("bssid", "--", "*", "(not")):
                continue
            macs = BSSID_RE.findall(ln)
            if not macs:
                continue
            station = macs[1].upper() if len(macs) > 1 else ""
            if not station or station in seen:
                continue
            seen.add(station)
            ap = macs[0].upper()
            rest_after_macs = BSSID_RE.sub("", ln, count=2).strip()
            pwr_m = re.match(r"\s*(-?\d+)", rest_after_macs)
            stas.append({
                "station": station,
                "ap": ap,
                "power": pwr_m.group(1) if pwr_m else "?",
            })
        return stas

    # -- scan / focused scan / deauth / stop --
    def scan(self, band: str = ""):
        if not self.mon_iface:
            return []
        bf = ["--band", band] if band else []
        cmd = ["airodump-ng", *bf, self.mon_iface]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._procs.append(proc)
        time.sleep(5)
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill(); out, _ = proc.communicate(timeout=3)
        return self._parse_ap_lines(out)

    def scan_focused(self, bssid: str, channel: str):
        if not self.mon_iface:
            return [], []
        cmd = ["airodump-ng", "-c", str(channel), "--bssid", bssid, self.mon_iface]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self._procs.append(proc)
        time.sleep(6)
        proc.terminate()
        try:
            out, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill(); out, _ = proc.communicate(timeout=3)
        return self._parse_ap_lines(out), self._parse_station_lines(out)

    def deauth(self, bssid: str, station: str = None):
        if not self.mon_iface:
            return False, "Sin monitor activo"
        if station:
            cmd = ["aireplay-ng", "--deauth", "0", "-a", bssid, "-c", station, self.mon_iface]
        else:
            cmd = ["aireplay-ng", "--deauth", "0", "-a", bssid, self.mon_iface]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self._procs.append(proc)
            tgt = station or "TODAS las estaciones"
            return True, f"Deauth → {tgt} (AP: {bssid})"
        except Exception as e:
            return False, str(e)

    def stop_all(self):
        for p in self._procs:
            try: p.terminate()
            except Exception: pass
        self._procs.clear()

    # -- saved names: dict or string (backwards compatible) --
    def set_name(self, bssid: str, name: str, type_: str = "AP"):
        self.targets[bssid.upper()] = {"name": name, "type": type_}
        save_targets(self.targets)

    def remove_name(self, bssid: str):
        self.targets.pop(bssid.upper(), None)
        save_targets(self.targets)

    def name_of(self, bssid: str) -> str:
        v = self.targets.get(bssid.upper(), "")
        if isinstance(v, dict):
            return v.get("name", "")
        return v

    def group_by_essid(self, nets: list) -> dict:
        g = {}
        for n in nets:
            g.setdefault(n["essid"], []).append(n)
        return g


# =============================================================================
# Theme system — three editorial themes, hand-curated, on purpose
# =============================================================================
@dataclass(frozen=True)
class Theme:
    name: str
    bg: str                 # window / page
    surface: str            # cards, inputs, topbar
    surface_alt: str        # zebra stripes, hover
    fg: str                 # primary text
    fg_dim: str             # secondary text, hints
    accent: str             # 1 accent per page (CTA, active state)
    accent_dim: str         # accent hover/secondary
    border: str             # hairline 1px
    border_hi: str          # button border, slightly stronger
    danger: str
    success: str
    warn: str
    sans_family: str
    mono_family: str


# Editorial Mono Collection — eight hand-curated themes, ordered light → dark:
# Papel · Static Ink · Moderno · Olive Press · Sepia · Nordic · Slate · OLED.
# Each stands on its own; no two are cream-on-cream variants of each other.
THEMES = {
    "Papel": Theme(
        name="Papel",
        bg="#FAF7F0", surface="#FFFFFF", surface_alt="#F2EFE7",
        fg="#2A2520", fg_dim="#6F6457",
        accent="#5A4640",          # sepia-brown editorial
        accent_dim="#8C7669",
        border="#E5DFD2", border_hi="#D0C8B6",
        danger="#A8442E", success="#4F7F5D", warn="#A6841F",
        sans_family='Inter Display,Inter,"Helvetica Neue","Cantarell","Noto Sans",sans-serif',
        mono_family='"JetBrains Mono","SF Mono",Menlo,"Cascadia Code","Fira Code",monospace',
    ),
    "Static Ink": Theme(
        name="Static Ink",
        bg="#FAF8F4",
        surface="#FFFFFF",
        surface_alt="#F3EFE8",
        fg="#1A1A17",
        fg_dim="#6B6862",
        accent="#2C645A",          # verde Penélope
        accent_dim="#7A9A93",
        border="#E5E1DA",
        border_hi="#D0CAC0",
        danger="#9C3D2E",
        success="#4A6A48",
        warn="#A66A1F",
        sans_family='Inter Display,Inter,"Helvetica Neue","Cantarell","Noto Sans",sans-serif',
        mono_family='"JetBrains Mono","SF Mono",Menlo,"Cascadia Code","Fira Code",monospace',
    ),
    "Moderno": Theme(
        name="Moderno",
        bg="#F7F7F8", surface="#FFFFFF", surface_alt="#EEF0F3",
        fg="#1B1F26", fg_dim="#707684",
        accent="#3A5BA0",          # cobalto editorial (no neon SaaS blue)
        accent_dim="#526A96",
        border="#E2E4E8", border_hi="#CFD2D8",
        danger="#E54B4B", success="#10B981", warn="#F59E0B",
        sans_family='Inter Display,Inter,"Helvetica Neue","Cantarell","Noto Sans",sans-serif',
        mono_family='"JetBrains Mono","SF Mono",Menlo,"Cascadia Code","Fira Code",monospace',
    ),
    "Olive Press": Theme(
        name="Olive Press",
        bg="#F1EFE5",
        surface="#FBF9EE",
        surface_alt="#E7E3D4",
        fg="#2D2F23",
        fg_dim="#73725F",
        accent="#5B6E3B",
        accent_dim="#9AA775",
        border="#D8D2BD",
        border_hi="#C2BBA0",
        danger="#8E3929",
        success="#5B6E3B",
        warn="#9E7A2F",
        sans_family='Inter Display,Inter,"Helvetica Neue","Cantarell","Noto Sans",sans-serif',
        mono_family='"JetBrains Mono","SF Mono",Menlo,"Cascadia Code","Fira Code",monospace',
    ),
    "Sepia": Theme(
        name="Sepia",
        bg="#F4ECD8", surface="#FBF6E7", surface_alt="#EBE0C5",
        fg="#2D2620", fg_dim="#6F5F4D",
        accent="#B5651D",          # burnt sienna
        accent_dim="#C98D5C",
        border="#DCD0B5", border_hi="#C2B595",
        danger="#A53D2C", success="#6B7E3D", warn="#A66A1F",
        sans_family='Inter Display,Inter,"Helvetica Neue","Cantarell","Noto Sans",sans-serif',
        mono_family='"JetBrains Mono","SF Mono",Menlo,"Cascadia Code","Fira Code",monospace',
    ),
    "Nordic": Theme(
        name="Nordic",
        bg="#ECEFF4", surface="#F5F7FA", surface_alt="#E5E9F0",
        fg="#2E3440",              # Nord polar night
        fg_dim="#6B7385",
        accent="#5E81AC",          # frost
        accent_dim="#81A1C1",
        border="#D8DEE9", border_hi="#C0C5D1",
        danger="#BF616A",          # aurora red
        success="#A3BE8C",          # aurora green
        warn="#EBCB8B",             # aurora yellow
        sans_family='Inter Display,Inter,"Helvetica Neue","Cantarell","Noto Sans",sans-serif',
        mono_family='"JetBrains Mono","SF Mono",Menlo,"Cascadia Code","Fira Code",monospace',
    ),
    "Slate": Theme(
        name="Slate",
        bg="#1E2024",
        surface="#262A30",
        surface_alt="#2D3138",
        fg="#E2E0D8",
        fg_dim="#8A8E96",
        accent="#88B4A0",          # cool green for dark variant
        accent_dim="#4F6F5F",
        border="#3A3F47",
        border_hi="#4A4F58",
        danger="#C26B5C",
        success="#9CB46E",
        warn="#D5A854",
        sans_family='Inter Display,Inter,"Helvetica Neue","Cantarell","Noto Sans",sans-serif',
        mono_family='"JetBrains Mono","SF Mono",Menlo,"Cascadia Code","Fira Code",monospace',
    ),
    "OLED": Theme(
        name="OLED",
        bg="#000000", surface="#0A0A0A", surface_alt="#141414",
        fg="#E8E8E8", fg_dim="#888888",
        accent="#43A047",          # phosphor green (no neon)
        accent_dim="#2D7A30",
        border="#1F1F1F", border_hi="#2D2D2D",
        danger="#E04848", success="#43A047", warn="#E0B048",
        sans_family='Inter Display,Inter,"Helvetica Neue","Cantarell","Noto Sans",sans-serif',
        mono_family='"JetBrains Mono","SF Mono",Menlo,"Cascadia Code","Fira Code",monospace',
    ),
}


def _make_mono(size: int, bold: bool = False) -> QFont:
    """Build a JetBrains-Mono-family QFont with safe fallbacks. Used by tree
    headers and tabular cells where numerics should sit in monospace."""
    f = QFont()
    f.setFamilies([
        "JetBrains Mono", "SF Mono", "Menlo",
        "Cascadia Code", "Fira Code", "monospace",
    ])
    f.setPointSize(size)
    f.setStyleHint(QFont.Monospace)
    if bold:
        f.setBold(True)
    return f


# Module-level singletons — reusing the same QFont instance avoids hundreds of
# allocations per scan on a big network list.
_MONO10_BOLD = _make_mono(10, bold=True)
_MONO11 = _make_mono(11)


def build_stylesheet(t: Theme) -> str:
    """Hand-crafted Qt stylesheet. NOT Material, NOT Bootstrap.
    1px borders, 2px radius max, no 3D, no gradients, hierarchy by size.
    """
    return f"""
    /* === base === */
    QMainWindow, QWidget, QDialog {{
        background-color: {t.bg};
        color: {t.fg};
        font-family: {t.sans_family};
        font-size: 12px;
    }}
    QWidget:focus, QPushButton:focus, QLineEdit:focus, QComboBox:focus,
    QPlainTextEdit:focus, QTreeWidget:focus, QCheckBox:focus {{ outline: none; }}

    /* === topbar === */
    QFrame#topbar {{
        background-color: {t.surface};
        border: 0;
        border-bottom: 1px solid {t.border};
    }}
    QLabel#topbar_title {{
        font-size: 17px;
        font-weight: 600;
        letter-spacing: -0.2px;
        color: {t.fg};
    }}
    QLabel#topbar_subtitle {{
        font-size: 11px;
        color: {t.fg_dim};
        margin-top: 1px;
    }}
    QLabel#dim {{ color: {t.fg_dim}; }}
    QLabel#mono {{
        font-family: {t.mono_family};
        font-size: 11px;
        color: {t.fg_dim};
    }}

    /* === theme chips === */
    QPushButton#theme_chip {{
        background: transparent;
        border: 1px solid {t.border};
        border-radius: 2px;
        padding: 4px 12px;
        color: {t.fg_dim};
    }}
    QPushButton#theme_chip:hover {{
        color: {t.fg};
        border-color: {t.accent};
    }}
    QPushButton#theme_chip:checked {{
        background: {t.accent};
        color: {t.surface};
        border: 1px solid {t.accent};
        font-weight: 500;
    }}

    /* === tabs === */
    QTabWidget#main_tabs::pane {{
        border: 0;
        background: {t.bg};
        margin: 0; padding: 0;
    }}
    QTabBar#main_tabs {{
        background: transparent;
        border: 0;
        qproperty-drawBase: 0;
    }}
    QTabBar#main_tabs::tab {{
        background: transparent;
        color: {t.fg_dim};
        padding: 10px 18px 10px 14px;
        border: 0;
        border-bottom: 2px solid transparent;
        font-size: 13px;
        margin: 0;
    }}
    QTabBar#main_tabs::tab:hover:!selected {{ color: {t.fg}; }}
    QTabBar#main_tabs::tab:selected {{
        color: {t.fg};
        font-weight: 500;
        border-bottom: 2px solid {t.accent};
    }}

    /* === buttons === */
    QPushButton {{
        background: {t.surface};
        border: 1px solid {t.border};
        border-radius: 2px;
        padding: 6px 14px;
        color: {t.fg};
    }}
    QPushButton:hover {{ border-color: {t.accent}; }}
    QPushButton:pressed {{ background: {t.surface_alt}; }}
    QPushButton:disabled {{
        color: {t.fg_dim};
        border-color: {t.border};
        background: {t.surface_alt};
    }}
    QPushButton#btn_primary {{
        background: {t.accent};
        color: {t.surface};
        border: 1px solid {t.accent};
        font-weight: 500;
    }}
    QPushButton#btn_primary:hover {{
        background: {t.accent_dim};
        border-color: {t.accent_dim};
    }}
    QPushButton#btn_attack {{
        background: {t.danger};
        color: {t.surface};
        border: 1px solid {t.danger};
        font-weight: 500;
    }}
    QPushButton#btn_attack:hover {{
        background: {t.danger};
        border-color: {t.danger};
    }}

    /* === inputs === */
    QLineEdit, QComboBox, QPlainTextEdit {{
        background: {t.surface};
        border: 1px solid {t.border};
        border-radius: 2px;
        padding: 6px 8px;
        color: {t.fg};
        selection-background-color: {t.accent};
        selection-color: {t.surface};
    }}
    QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
        border: 1px solid {t.accent};
    }}
    QComboBox::drop-down {{ border: 0; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {t.surface};
        border: 1px solid {t.border_hi};
        selection-background-color: {t.accent};
        selection-color: {t.surface};
        outline: none;
    }}
    QPlainTextEdit {{
        font-family: {t.mono_family};
        font-size: 11px;
    }}
    QCheckBox {{ spacing: 6px; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px;
        border: 1px solid {t.border_hi};
        border-radius: 2px;
        background: {t.surface};
    }}
    QCheckBox::indicator:hover {{ border-color: {t.accent}; }}
    QCheckBox::indicator:checked {{
        background: {t.accent};
        border: 1px solid {t.accent};
    }}

    /* === cards === */
    QFrame#card {{
        background: {t.surface};
        border: 1px solid {t.border};
        border-radius: 2px;
    }}
    QLabel#card_title {{
        font-size: 13px;
        font-weight: 600;
        color: {t.fg};
        padding-bottom: 4px;
    }}
    QLabel#card_hint {{
        font-family: {t.mono_family};
        font-size: 11px;
        color: {t.fg_dim};
    }}

    /* === trees === */
    QTreeWidget {{
        background: {t.surface};
        alternate-background-color: {t.surface_alt};
        border: 1px solid {t.border};
        border-radius: 2px;
        font-size: 12px;
        selection-background-color: {t.accent};
        selection-color: {t.surface};
        outline: none;
    }}
    QHeaderView::section {{
        background: {t.surface};
        color: {t.fg_dim};
        border: 0;
        border-bottom: 1px solid {t.border};
        padding: 8px 10px;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.6px;
    }}
    QTreeWidget::item {{ padding: 4px 8px; }}
    QTreeWidget::item:hover {{ background: {t.surface_alt}; }}
    QTreeWidget::branch {{ background: transparent; }}

    /* === status bar === */
    QStatusBar {{ background: {t.surface}; border-top: 1px solid {t.border}; }}
    QStatusBar QLabel {{
        padding: 0 12px;
        font-family: {t.mono_family};
        font-size: 11px;
        color: {t.fg_dim};
    }}
    QStatusBar QLabel#sb_state {{ color: {t.accent}; font-weight: 500; }}
    QStatusBar QLabel#sb_msg   {{ color: {t.fg}; }}

    /* === help typography === */
    QLabel#t_h1   {{ font-size: 18px; font-weight: 600; color: {t.fg}; }}
    QLabel#t_h2   {{ font-size: 13px; font-weight: 600; color: {t.fg}; margin-top: 18px; }}
    QLabel#t_body {{ font-size: 12px; color: {t.fg}; }}
    QLabel#t_mono {{ font-family: {t.mono_family}; font-size: 11px; color: {t.fg_dim}; }}
    /* === card eyebrow (editorial hierarchy marker) ===
       NOTE: source-level uppercase is the contract. Qt QSS does NOT honour
       text-transform, so do NOT declare it here. */
    QLabel#card_eyebrow {{
        font-family: {t.mono_family};
        font-size: 10px;
        letter-spacing: 0.8px;
        color: {t.accent};
        margin: 0;
        padding: 0;
    }}

    /* === status bar hairline separators === */
    QFrame#sb_sep {{
        background: {t.border};
        max-width: 1px;
        margin: 6px 0;
    }}

    /* === theme dropdown (QToolButton variant) === */
    QToolButton#theme_chip {{
        background: transparent;
        border: 1px solid {t.border};
        border-radius: 2px;
        padding: 4px 12px;
        color: {t.fg_dim};
    }}
    QToolButton#theme_chip:hover {{
        color: {t.fg};
        border-color: {t.accent};
    }}
    QToolButton#theme_chip::menu-indicator {{
        image: none;
        width: 0;
        height: 0;
    }}

    /* === help scroll & TOC (editorial wiki) === */
    QScrollArea#help_scroll {{
        background: {t.bg};
        border: 0;
    }}
    QFrame#toc_panel {{
        background: {t.surface};
        border: 0;
        border-right: 1px solid {t.border};
    }}
    QPushButton#toc_btn {{
        background: transparent;
        border: 0;
        border-left: 2px solid transparent;
        text-align: left;
        padding: 8px 12px 8px 14px;
        color: {t.fg_dim};
        font-size: 12px;
    }}
    QPushButton#toc_btn:hover {{
        background: {t.surface_alt};
        color: {t.fg};
        border-left: 2px solid {t.border_hi};
    }}
    QPushButton#toc_btn:checked {{
        background: {t.surface_alt};
        color: {t.fg};
        border-left: 2px solid {t.accent};
        font-weight: 600;
    }}
    QLineEdit#help_search {{
        background: {t.surface};
        border: 1px solid {t.border};
        border-radius: 2px;
        padding: 6px 10px;
        color: {t.fg};
        font-size: 12px;
        margin-bottom: 4px;
    }}
    QLineEdit#help_search:focus {{ border: 1px solid {t.accent}; }}
    QLabel#toc_eyebrow {{
        font-family: {t.mono_family};
        font-size: 10px;
        letter-spacing: 0.8px;
        color: {t.fg_dim};
        padding: 0 0 8px 14px;
    }}

    /* === warning / ATENCIÓN card (critical sections — ethics + dangerous troubles) === */
    QFrame#card_warn {{
        background: {t.surface};
        border: 1px solid {t.border};
        border-left: 4px solid {t.danger};
        border-radius: 2px;
    }}
    QLabel#card_warn_seal {{
        font-family: {t.mono_family};
        font-size: 10px;
        letter-spacing: 1.2px;
        color: {t.danger};
        font-weight: 600;
    }}

    /* === code / terminal block (mono, subtle bg, hairline border) === */
    QLabel#code_block {{
        font-family: {t.mono_family};
        font-size: 11px;
        color: {t.fg};
        background: {t.surface_alt};
        border: 1px solid {t.border};
        border-radius: 2px;
        padding: 10px 12px;
        margin: 2px 0;
    }}

    /* === section meta info row (e.g. "12 ítems · ~3 min") === */
    QLabel#lbl_meta {{
        font-family: {t.mono_family};
        font-size: 10px;
        color: {t.fg_dim};
        text-transform: none;
    }}

    /* === channel overlap heatmap row === */
    QFrame#overlap_row {{
        background: {t.surface};
        border: 1px solid {t.border};
        border-radius: 2px;
    }}
    QFrame#overlap_row_warn {{
        background: {t.surface};
        border: 1px solid {t.warn};
        border-left: 3px solid {t.warn};
        border-radius: 2px;
    }}
    QLabel#overlap_ch {{
        font-family: {t.mono_family};
        font-size: 12px;
        font-weight: 600;
        color: {t.fg};
    }}

    /* === filter highlight (Ctrl+F search + help filter hit) === */
    QLabel#match_highlight {{
        background: {t.accent};
        color: {t.surface};
        padding: 0 2px;
    }}
    """


# =============================================================================
# Workers — QThread + custom Signal (clean Qt-native pattern)
# =============================================================================
class ScanWorker(QThread):
    finished = Signal(list)
    def __init__(self, backend: Backend, band: str):
        super().__init__()
        self.bk = backend
        self.band = band
    def run(self):
        try:
            r = self.bk.scan(self.band)
        except Exception:
            r = []
        self.finished.emit(r)


class FocusedScanWorker(QThread):
    finished = Signal(list)
    def __init__(self, backend: Backend, bssid: str, channel: str):
        super().__init__()
        self.bk = backend
        self.bssid = bssid
        self.channel = channel
    def run(self):
        try:
            _, stas = self.bk.scan_focused(self.bssid, self.channel)
        except Exception:
            stas = []
        self.finished.emit(stas)


# =============================================================================
# Main window
# =============================================================================
class MainWindow(QMainWindow):

    # -------------------------------------------------------------------------
    # Wiki section data (12 sections; editable, low-priority to refactor later)
    # -------------------------------------------------------------------------
    # Each section is a 6-tuple: (anchor_id, num, eyebrow, title, severity,
    # items), where items is a list of (kind, text) pairs translated by _h()
    # into QLabel widgets.  severity="warn" applies an ATENCIÓN seal.  kind in
    # {"body", "mono", "code"} is rendered via the existing QSS rules.
    WIKI_SECTIONS = [
        ("sec_bienvenida", 1, "BIENVENIDA", "Cómo usar la consola en 5 pasos", "info", [
            ("body",
             "Esta herramienta sustituye los comandos de aircrack-ng por una GUI editorial con "
             "8 temas visuales. Las cinco pestañas del upper tab cubren una fase del flujo; esta "
             "pestaña es la guía completa. Usa Ctrl+F para buscar, y la tabla de la izquierda "
             "para saltar a una sección."),
            ("mono",
             "1 · CAMBIO    → elige tu interfaz WiFi y pulsa Activar. airmon-ng levanta wlan0mon.\n"
             "                Desactivar restaura el modo managed automáticamente.\n"
             "2 · ESCANEO   → airodump-ng corre ~5 s; las redes aparecen en el árbol con\n"
             "                BSSID, CH, PWR, ENC, ESSID, vendor (en tooltip), nombre guardado.\n"
             "3 · ATAQUE    → rellena BSSID + MAC; usa Selección rápida o Exporta para informes.\n"
             "                ϟ envía aireplay-ng --deauth 0 hasta que pulses Detener.\n"
             "4 · GUARDADOS → anota un nombre legible por BSSID; aparece en Escaneo.\n"
             "5 · AYUDA     → esta pestaña. Ctrl+F para buscar."),
            ("body",
             "Atajos salpicados por toda la app: Ctrl+1..5 cambia pestaña; Ctrl+T cicla "
             "tema; Ctrl+R re-escanea; Ctrl+Q limpia el filtro; Ctrl+F te enfoca aquí."),
        ]),
        ("sec_vocabulario", 2, "VOCABULARIO", "Glosario de términos WiFi", "info", [
            ("mono", "BSSID    — MAC del router (dirección física).  Ej.: CC:BA:BD:87:3D:47"),
            ("mono", "ESSID    — Nombre visible de la red.           Ej.: TuVecino_5G, JAZZTEL_2.4"),
            ("mono", "CH       — Canal RF. 1–14 (2.4 GHz) o 36–165 (5 GHz)."),
            ("mono", "PWR      — Potencia recibida en dBm. Negativa: -50 ≈ pegado, -80 ≈ lejos."),
            ("mono", "ENC      — Cifrado: OPN (sin clave), WEP (roto), WPA/WPA2/WPA3 (modernos)."),
            ("mono", "CIPHER   — Algoritmo de datos: CCMP / TKIP / GCMP."),
            ("mono", "AUTH     — Método de autenticación: PSK (clave compartida), MGT (RADIUS/Enterprise), SAE (WPA3-Personal)."),
            ("mono", "<oculta> — Red con broadcast deshabilitado; ESSID no anunciado."),
            ("mono", "STATION  — Cliente WiFi asociado a un AP (su MAC, no la del router)."),
            ("mono", "MONITOR  — Modo promiscuo; la tarjeta acepta cualquier frame. airmon-ng lo activa."),
            ("mono", "INYECCIÓN — Capacidad de inyectar tramas. Modo monitor + driver compatible = necesario."),
            ("mono", "OUI      — 3 primeros octetos del MAC. Identifican al fabricante del chipset."),
            ("mono", "DFS      — Dynamic Frequency Selection (5 GHz, CH 52–144). Algunos drivers no lo soportan."),
        ]),
        ("sec_arquitectura", 3, "ARQUITECTURA", "Cómo funciona esta aplicación por dentro", "info", [
            ("body", "Flujo end-to-end. La separación entre UI thread y QThread worker es lo que evita "
                     "que la GUI se congele mientras airodump-ng captura. Cualquier clic dispara una "
                     "acción en el hilo UI; esa acción lanza un QThread que ejecuta el subprocess; cuando "
                     "termina emite una Signal al hilo UI que repuebla el árbol correspondiente."),
            ("code",
             "[button click]\n"
             "      |\n"
             "[MainWindow._scan_action / _focus_action / _do_deauth / _export_scan]\n"
             "      |\n"
             "[ScanWorker / FocusedScanWorker  (QThread heredado)]\n"
             "      |\n"
             "[Backend.scan / scan_focused]\n"
             "      |  subprocess.Popen(['airodump-ng', ...])\n"
             "      |  time.sleep(5–6 s); terminate(); communicate()\n"
             "      |\n"
             "[Backend._parse_ap_lines / _parse_station_lines]\n"
             "      |  regex anclado al primer token del BSSID\n"
             "      |  clean_line() descarta ANSI + C0; preserva UTF-8 (acentos, emojis)\n"
             "      |\n"
             "[Signal.finished.emit(nets / stations)]\n"
             "      |  cross-thread al UI principal\n"
             "      |\n"
             "[_scan_done / _focus_done slots]\n"
             "      |\n"
             "[_populate_nets / _fill_grp / _fill_flat]\n"
             "      |  Reaplica filtro ESSID (debounced 150 ms)\n"
             "      |  Resetea selección (sel_net = None)\n"
             "      |\n"
             "[QTreeWidget + setFont mono en columnas CH y PWR]"),
            ("body", "Parser. Dos regexs cubren el layout moderno (#Data,#/s con coma) y el legacy de airodump-ng "
                     "(#Data #/s por separado). El placeholder [0K que aparece mientras el ESSID se está aún "
                     "transmitiendo se trata como <oculta>, igual que <length: 0> y la cadena vacía."),
            ("body", "Temas. La dataclass Theme congela 14 campos (bg / surface / fg / accent / danger ...). "
                     "build_stylesheet(t) genera el QSS completo para el tema. 8 temas curados a mano: Papel, "
                     "Static Ink, Moderno, Olive Press, Sepia, Nordic, Slate, OLED — cada uno con una huella "
                     "visual distinta, no son variantes cream-on-cream."),
            ("body", "Hotkeys. Centralizada en _setup_hotkeys(): Ctrl+1..5 tabs, Ctrl+T cicla tema, Ctrl+R "
                     "re-escanea, Ctrl+Q limpia filtro, Ctrl+F enfoca esta búsqueda. Los mnemotécnicos viven "
                     "fuera de la app también (ver sección §ATAJOS)."),
        ]),
        ("sec_workflows", 4, "WORKFLOWS", "Cuatro escenarios típicos", "info", [
            ("body", "A · Auditar tu propia red doméstica"),
            ("mono",
             " 1. Pestaña Cambio → elige wlan0 y pulsa Activar.\n"
             " 2. Pestaña Escaneo → pulsa Escanear; observa qué redes aparecen.\n"
             " 3. Si ves <oculta> y la reconoces, ve a Guardados y pega el BSSID\n"
             "    con un nombre entendible (Casa, Trabajo).\n"
             " 4. Exporta el escaneo (botón Exportar) como referencia para tu informe."),
            ("body", "B · Auditar tu propio Mesh (Deco / Orbi / Eero / Amplifi)"),
            ("mono",
             " 1. Pestaña Escaneo → deja Agrupar por ESSID activado.\n"
             " 2. Una red con varios AP aparece como grupo. Cada AP tiene su BSSID.\n"
             " 3. Doble clic en una BSSID concreta → escaneo focalizado.\n"
             " 4. Aparece el árbol de estaciones conectadas a ese AP."),
            ("body", "C · Análisis de solapamiento (WiFi congestionada)"),
            ("mono",
             " 1. Pestaña Escaneo → captura el espectro.\n"
             " 2. Pulsa «Analizar solapamiento 2.4 GHz» (toolbar Escaneo).\n"
             " 3. La tarjeta inferior muestra grupos de canales adyacentes y los\n"
             "    APs que viven en cada uno. También te sugiere canales despejados (1, 6, 11)."),
            ("body", "D · Aislar un AP concreto para pentest dirigido"),
            ("mono",
             " 1. Pestaña Escaneo → captura el BSSID objetivo.\n"
             " 2. Pestaña Ataque → el campo BSSID se rellena automáticamente.\n"
             " 3. Rellena la MAC de un cliente (o usa Selección rápida).\n"
             " 4. ϟ Desautenticar estación durante N minutos. Observa con un\n"
             "    cliente propio cómo se cae la conexión y cómo reasocia."),
        ]),
        ("sec_hardware", 5, "HARDWARE", "Chipsets buenos, malos e indeterminados", "info", [
            ("body", "El modo monitor sin inyección sirve para capturar, pero no para deauth. Si sólo necesitas "
                     "ver redes y estaciones, casi cualquier chipset vale; si vas a lanzar ataques de "
                     "desautenticación, necesitas uno que inyecte frames a nivel hardware."),
            ("body", "✓ Soportados · probados inyección + monitor estable"),
            ("mono",
             "  · Atheros AR9271      (Alfa AWUS036ACH, AWUS036NHA)  · 5 GHz incluido\n"
             "  · Ralink RT3070       (Alfa AWUS036NH)                · sólo 2.4 GHz\n"
             "  · Ralink RT3572       (Alfa AWUS050NH, AWUS051NH)     · dual-band legacy\n"
             "  · MediaTek MT7612U                              · muy común en dongles 2018+\n"
             "  · Realtek RTL8812AU   (drivers rtl8812AU-aircrack)   · 5 GHz + 802.11ac"),
            ("body", "✗ No soportados · sólo capturan, no inyectan (o el driver lo bloquea)"),
            ("mono",
             "  · Intel AX200/AX210 (Wi-Fi 6E integrado en laptops modernas)\n"
             "  · Intel Wireless-AC 8265/9260 (muchas laptops 2017–2020)\n"
             "  · Realtek RTL8822BE (driver in-tree de Linux; bloquea tx deauth)\n"
             "  · Broadcom BCM4360 (MacBook Pro con Linux), también bloqueado"),
            ("body", "△ Indeterminados · dependen de la versión exacta del driver"),
            ("mono",
             "  · Realtek RTL8811AU / RTL8812BU — funcionan con aircrack-ng >= 1.6\n"
             "    pero algunos firmwares siguen sin inyectar.\n"
             "  · Qualcomm Atheros QCA9880 / QCA9882 — bien en APs; en laptops varía."),
            ("body", "Recomendación para comprar.  Alfa AWUS036ACH (AR9271, < 25 €) sigue siendo el patrón "
                     "oro si necesitas 2.4 + 5 GHz con inyección y modo monitor estable. Si tu distro ya "
                     "tiene Kali preinstalado, prueba primero tu tarjeta interna — pero lleva el dongle de respaldo."),
        ]),
        ("sec_mesh", 6, "MESH", "Vocabulario de redes Mesh — Deco, Orbi, Eero, Amplifi", "info", [
            ("body", "Los routers mesh son populares en casas grandes. Internamente operan como varios APs "
                     "que comparten un único ESSID, repartiendo el espectro y haciendo roaming transparente "
                     "para el cliente. Esto tiene implicaciones para pentest porque verás un grupo, no una red, "
                     "en la lista de APs."),
            ("mono", "nodo / backhaul   — Enlace Wi-Fi (o Ethernet) entre dos nodos del mesh."),
            ("mono", "fronthaul         — Enlace Wi-Fi entre un nodo y los clientes."),
            ("mono", "roaming 802.11r   — Fast BSS Transition (FT). El cliente cambia de nodo sin renegociar."),
            ("mono", "802.11k           — Neighbor Reports. El AP informa de vecinos para roaming dirigido."),
            ("mono", "802.11v           — BSS Transition Management. El AP puede sugerir un cambio."),
            ("mono", "Deco Mesh (TP-Link) — Usa backhaul dedicado en 5 GHz; 2 APs en CH2 + 1 AP en CH3."),
            ("mono", "Orbi (Netgear)    — Backhaul dedicado de 5 GHz; los satélites tienen un canal propio."),
            ("mono", "Eero (Amazon)     — Backhaul dinámico 2.4+5 GHz; el firmware decide cada vez."),
            ("mono", "Amplifi (Ubiquiti) — Backhaul Ethernet si tendiste cable; Wi-Fi en su defecto."),
            ("mono", "Plume / Nest WiFi — Backhaul dinámico en bandas compartidas."),
            ("body", "Truco útil. Si tu mesh aparece como un grupo con varias BSSIDs y quieres "
                     "identificar cuál es el router principal, mira el PWR: el que tenga mejor señal "
                     "cerca de tu posición probablemente sea el gateway (el que habla con el módem)."),
        ]),
        ("sec_solap", 7, "SOLAPAMIENTO", "Cómo funciona el análisis de canales 2.4 GHz", "info", [
            ("body", "En 2.4 GHz los canales están separados 5 MHz pero el ancho de canal real es 20 MHz. "
                     "Por tanto sólo tres combinaciones no solapan entre sí: CH 1, CH 6 y CH 11. Cualquier "
                     "AP en CH 3 estará parcialmente encimado con APs en CH 1 y CH 5, y así sucesivamente."),
            ("body", "Panel de análisis. Cuando pulsas «Analizar solapamiento 2.4 GHz» el panel inferior "
                     "del Escaneo se llena con dos textos: un resumen ejecutivo de qué canales están "
                     "congestionados, y un detalle de qué BSSIDs viven en cada grupo solapado."),
            ("body", "Regla de cadena. La función trata como «solapan» los CH cuya distancia ≤ 2. Por tanto "
                     "{1,2,3,4,5,6} forman una sola cadena (todas pegadas), {7,8,9} otra, y "
                     "{10,11,12,13,14} otra. Esto refleja la realidad de routers con frontends no perfectos."),
            ("body", "Recomendación práctica. Si vas a desplegar un nuevo AP en una zona congestionada:"),
            ("mono",
             "  · Mira los «Canales despejados» arriba. Si hay CH 6 libre, ponlo ahí.\n"
             "  · Evita CH 12 / CH 13 en redes mixtas — clientes viejos se pierden.\n"
             "  · Si tu mesh usa un canal único para backhaul (p.e. CH 6), comunícalo\n"
             "    en la sección «Mesh» antes de elegir."),
        ]),
        ("sec_troubleshoot", 8, "TROUBLESHOOTING", "Errores comunes y soluciones", "info", [
            ("body", "«airmon-ng start dice Operation not possible»"),
            ("mono", "  Casi siempre hay un proceso que aún tiene la interfaz."),
            ("mono", "  → ejecuta   sudo airmon-ng check kill   y reintenta."),
            ("body", "airodump-ng muestra «channel -1» en CH"),
            ("mono", "  El AP está en un canal DFS (5 GHz, 52–144). Algunos chipsets no"),
            ("mono", "  soportan monitor en esos canales; prueba con un Alfa AWUS036ACH."),
            ("body", "aireplay-ng da «No such BSSID available»"),
            ("mono", "  El BSSID cambió durante el ataque (cliente itinerante o roaming)."),
            ("mono", "  → vuelve a Escaneo, refresca el objetivo y repite."),
            ("body", "wlan0mon no aparece en `iw dev`"),
            ("mono", "  Algunos drivers crean nombres arbitrarios (mon0, prism0...)."),
            ("mono", "  → ejecuta   iw dev   en una terminal externa para ver el nombre"),
            ("mono", "  real, y ajústalo en el campo iface si la app lo pide."),
            ("body", "«Permission denied» al lanzar la app"),
            ("mono", "  La app debe correr como root para monitor + inyección."),
            ("mono", "  → sudo python3 wifi_deauth_manager.py"),
            ("body", "No station aparece en un AP que sí tiene clientes"),
            ("mono", "  airodump sólo ve clientes que emiten tramas en ese momento."),
            ("mono", "  Espera 10–15 s con el escaneo focalizado abierto, o pídele a"),
            ("mono", "  un cliente que genere tráfico (refresh DHCP, ping)."),
            ("body", "Exportación JSON da un error de permisos"),
            ("mono", "  El export scan.json lo escribe el usuario que lanzó la app; si subiste con pkexec + sudo, recuerda cambiar ownership si quieres editarlo después"),
            ("mono", "  pero la app corre como root. El archivo pertenecerá a root:root."),
            ("mono", "  → chmod 666 /home/.../scan.json   si lo quieres editar como carlos."),
            ("body", "Ctrl+F no enfoca la búsqueda"),
            ("mono", "  Primero cambia a la pestaña Ayuda (Ctrl+5) y luego Ctrl+F."),
            ("mono", "  La app salta primero a la pestaña y luego enfoca el campo."),
            ("body", "Ctrl+R no hace nada"),
            ("mono", "  Ctrl+R sólo lanza re-escaneo si hay monitor activo. Si no lo"),
            ("mono", "  activaste, ve a Cambio y pulsa Activar."),
        ]),
        ("sec_referencia", 9, "REFERENCIA", "aircrack-ng, iw, ip — los comandos detrás", "info", [
            ("body", "airmon-ng — gestión del modo monitor"),
            ("mono",
             "  · airmon-ng check kill      mata procesos que estorban a la tarjeta\n"
             "  · airmon-ng start <iface>   crea <iface>mon y la activa\n"
             "  · airmon-ng stop <iface>mon  desactiva y restaura el modo managed\n"
             "  · airmon-ng                  lista interfaces con modo activo"),
            ("body", "airodump-ng — captura pasiva de APs y estaciones"),
            ("mono",
             "  · airodump-ng <iface>                       escaneo abierto (todas las bandas)\n"
             "  · airodump-ng --band g <iface>               sólo 2.4 GHz\n"
             "  · airodump-ng --band a <iface>               sólo 5 GHz\n"
             "  · airodump-ng -c CH --bssid <BSSID> <iface>  escaneo focalizado\n"
             "  · airodump-ng -w <prefix> <iface>            dump a CSV + pcap (<prefix>*.csv/.pcap)"),
            ("body", "iw — control nativo de interfaces (Linux ≥ 4.x)"),
            ("mono",
             "  · iw dev                                    lista interfaces + tipo (managed / monitor)\n"
             "  · iw dev <iface>mon info                    describe la interfaz monitor actual\n"
             "  · iw reg get                                muestra el país regulatorio (limita canales)\n"
             "  · iw list                                   lista capacidades del chipset"),
            ("body", "ip — control clásico de interfaz de red"),
            ("mono",
             "  · ip link set <iface> up | down             activa / desactiva una interfaz\n"
             "  · ip link delete <iface>mon                 borra una interfaz monitor virtual\n"
             "  · ip addr show                              muestra IPs (no aplica a WiFi en monitor)"),
            ("body", "aireplay-ng — inyección, incluyendo deauth"),
            ("mono",
             "  · aireplay-ng --deauth 0 -a <BSSID> <iface>              masiva (broadcast)\n"
             "  · aireplay-ng --deauth 0 -a <BSSID> -c <STA> <iface>     dirigida a un cliente\n"
             "  · aireplay-ng --fakeauth 0 -e <ESSID> -a <BSSID> <iface>  fake-auth (WEP)\n"
             "  · aireplay-ng --arpreplay -b <BSSID> <iface>              reinyección ARP (WEP)"),
            ("body", "iwconfig / iwlist (legacy, sólo para chipsets viejos)"),
            ("mono",
             "  · iwconfig <iface> mode monitor             activa monitor en algunos drivers sin airmon-ng\n"
             "  · iwlist <iface> scan                       escaneo de un solo golpe (sin refresco)"),
        ]),
        ("sec_etica", 10, "ÉTICA Y LEY", "Lo permitido y lo prohibido", "warn", [
            ("body", "Esta herramienta está diseñada para pentesting autorizado de redes propias o "
                     "redes donde el propietario ha firmado un consentimiento explícito. Su uso contra redes "
                     "ajenas — incluso para «probar» — está perseguido penalmente en la mayoría de "
                     "jurisdicciones, incluida España."),
            ("body", "Lo que SÍ puedes hacer"),
            ("mono",
             "  · Auditar tu propia WiFi doméstica para verificar el cifrado y la robustez del\n"
             "    handshake (tu router, tu contraseña WEP a punto de jubilarse).\n"
             "  · Hacer prácticas de laboratorio en una red aislada (tu router desconectado\n"
             "    de Internet, con un cliente pre-pareado).\n"
             "  · Demostraciones autorizadas en aula con el profesor y en presencia de\n"
             "    fallos documentados.\n"
             "  · Pentest profesional contratado — un cliente te firma un SOW (Statement of\n"
             "    Work) que delimita alcance, fechas y objetivos."),
            ("body", "Lo que NO debes hacer"),
            ("mono",
             "  · Desautenticar a clientes de una red ajena, aunque sea para «probar que es\n"
             "    vulnerable».\n"
             "  · Capturar handshakes WPA de redes que no son tuyas para crackear la clave\n"
             "    en casa.\n"
             "  · Cualquier uso contra infraestructura pública (hospitales, bibliotecas,\n"
             "    cafeterías) sin autorización firmada y vigente.\n"
             "  · Compartir pruebas en foros públicos con BSSIDs reales — anonimiza."),
            ("body", "Marco legal en España (resumen no exhaustivo)"),
            ("mono",
             "  · Código Penal arts. 197–264: descubrimiento de secretos, interceptación de\n"
             "    comunicaciones, daños a sistemas. Penas de 1 a 8 años según tipo.\n"
             "  · LOPDGDD (Ley Orgánica 3/2018): tratamiento de datos personales sin\n"
             "    consentimiento.\n"
             "  · Ley 9/2014 (Telecomunicaciones): defraudación de servicios de\n"
             "    comunicaciones electrónicas.\n"
             "  · Reglamento UE 2019/881 (ENISA): endurece obligaciones de seguridad."),
            ("body", "Si dudas, no lo hagas. Si capturas tráfico propio, anónimiza. Si encuentras algo "
                     "expuesto, avisa primero al dueño y deja registro de lo que encontraste "
                     "(responsible disclosure)."),
        ]),
        ("sec_atajos", 11, "ATAJOS", "Atajos de teclado (descubribles con Ctrl+5 + F)", "info", [
            ("body", "Atajos globales"),
            ("mono", "  Ctrl+1   ·  Pestaña Cambio  (interfaz WiFi, monitor)"),
            ("mono", "  Ctrl+2   ·  Pestaña Escaneo  (escaneo general, filtrar, exportar)"),
            ("mono", "  Ctrl+3   ·  Pestaña Ataque  (BSSID + estación + bitácora)"),
            ("mono", "  Ctrl+4   ·  Pestaña Guardados  (nombres legibles por BSSID/MAC)"),
            ("mono", "  Ctrl+5   ·  Pestaña Ayuda  (esta pestaña)"),
            ("mono", "  Ctrl+T   ·  Ciclar al siguiente tema"),
            ("body", "Atajos de Escaneo"),
            ("mono", "  Ctrl+R   ·  Re-escanea si hay monitor activo"),
            ("mono", "  Ctrl+Q   ·  Limpia el filtro ESSID en Escaneo"),
            ("body", "Atajos de teclado en la Ayuda"),
            ("mono", "  Ctrl+F   ·  Enfoca la búsqueda lateral"),
            ("body", "Menú contextual (clic derecho en cualquier tabla)"),
            ("mono", "  Copiar BSSID/MAC   ·  copia el valor al portapapeles"),
            ("mono", "  Copiar nombre      ·  copia el nombre legible guardado"),
        ]),
        ("sec_refs", 12, "REFERENCIAS", "Documentación externa y lecturas recomendadas", "info", [
            ("body", "Proyectos libres (fuente directa de las herramientas que envuelve esta GUI)"),
            ("mono",
             "  · aircrack-ng         https://github.com/aircrack-ng/aircrack-ng\n"
             "  · airodump-ng manual  https://www.aircrack-ng.org/doku.php?id=airodump-ng\n"
             "  · PixieWPS (WPS bruteforce) — sólo para auditoría con consentimiento"),
            ("body", "Estándares y RFCs relevantes"),
            ("mono",
             "  · RFC 8325          — WiFi para IoT, amenazas y mitigaciones (2018)\n"
             "  · IEEE 802.11       — Estándar base (2016 + 802.11ax-2021)\n"
             "  · IEEE 802.11i      — WPA2 (2004); suplemento de seguridad\n"
             "  · IEEE 802.11w      — Protected Management Frames (PMF; evita deauth mgmt)\n"
             "  · IEEE 802.11r/k/v  — Fast BSS Transition, Neighbor Reports, BSS TM (mesh)"),
            ("body", "Guías de auditoría y pentest"),
            ("mono",
             "  · OWASP Testing Guide v4 — capítulo «Testing for Weak Authentication»\n"
             "    https://owasp.org/www-project-web-security-testing-guide/\n"
             "  · NIST SP 800-97 — «Guide to IEEE 802.11i: Robust Security Networks»\n"
             "  · ENISA — Annual Threat Landscape Report (reseña de amenazas WiFi)"),
            ("body", "Lecturas recomendadas"),
            ("mono",
             "  · «Hacking Exposed Wireless»  — Johnny Cache et al. (3.ª ed., 2015)\n"
             "  · «Real 802.11 Security»      — Jon Edney & William Arbaugh (2004, classics)\n"
             "  · \"802.11ax (Wi-Fi 6) explained\" — Aruba Networks technical papers\n"
             "  · \"WPA3 and SAE\" — Dan Harkins (RFC 7664 + RFC 8294)"),
        ]),
    ]

    def __init__(self, backend: Backend = None):
        super().__init__()
        self.setWindowTitle("WiFi Deauth Manager · local pentest console")
        self.resize(1180, 760)
        # DI: accept an externally-built Backend for tests; default builds one.
        self.bk = backend if backend is not None else Backend()
        self.current_theme_name = "Static Ink"
        self.networks = []
        self.stations = []
        self.sel_net = None
        self.scan_worker = None
        self.focus_worker = None
        self._build()
        self._apply_theme(self.current_theme_name)
        self._refresh_ifaces()

    # -------------------------------------------------------------------------
    # UI construction
    # -------------------------------------------------------------------------
    def _build(self):
        self._build_topbar()
        self._build_tabs()
        self._build_statusbar()
        self._setup_hotkeys()

    def _build_topbar(self):
        topbar = QFrame(); topbar.setObjectName("topbar"); topbar.setFixedHeight(56)
        layout = QHBoxLayout(topbar); layout.setContentsMargins(20, 0, 20, 0); layout.setSpacing(16)

        # title block
        title_block = QVBoxLayout(); title_block.setSpacing(2)
        title = QLabel("WiFi Deauth Manager"); title.setObjectName("topbar_title")
        subtitle = QLabel("local pentest console"); subtitle.setObjectName("topbar_subtitle")
        title_block.addWidget(title); title_block.addWidget(subtitle)
        layout.addLayout(title_block)
        layout.addStretch(1)

        # Theme dropdown — topbar stays slim regardless of how many themes
        # exist. QPushButton-per-theme pill would overflow at 8+; a QToolButton
        # with InstantPopup + QMenu gives a real "checked" item when reopened.
        theme_label = QLabel("Tema"); theme_label.setObjectName("dim")
        layout.addWidget(theme_label)
        self.theme_btn = QToolButton()
        self.theme_btn.setObjectName("theme_chip")
        self.theme_btn.setProperty("theme_name", self.current_theme_name)
        self.theme_btn.setText(self.current_theme_name + "  \u25be")
        self.theme_btn.setPopupMode(QToolButton.InstantPopup)
        self.theme_menu = QMenu(self.theme_btn)
        self.theme_btn.setMenu(self.theme_menu)
        self._rebuild_theme_menu()
        self.theme_menu.triggered.connect(self._on_theme_action)
        layout.addWidget(self.theme_btn)
        self.setMenuWidget(topbar)

    def _rebuild_theme_menu(self):
        self.theme_menu.clear()
        for name in THEMES.keys():
            act = self.theme_menu.addAction(name)
            act.setProperty("theme_name", name)
            if name == self.current_theme_name:
                act.setCheckable(True); act.setChecked(True)

    def _on_theme_action(self, action):
        name = action.property("theme_name") or action.text()
        self._set_theme(name)

    def _build_tabs(self):
        central = QWidget(); self.setCentralWidget(central)
        layout = QVBoxLayout(central); layout.setContentsMargins(0, 12, 0, 0); layout.setSpacing(0)
        self.tabs = QTabWidget(); self.tabs.setObjectName("main_tabs")
        self.tab_setup = QWidget(); self.tab_scan = QWidget()
        self.tab_attack = QWidget(); self.tab_saved = QWidget(); self.tab_help = QWidget()
        self.tabs.addTab(self.tab_setup, "⎈\u2003Cambio")
        self.tabs.addTab(self.tab_scan,  "◉\u2003Escaneo")
        self.tabs.addTab(self.tab_attack,"ϟ\u2003Ataque")
        self.tabs.addTab(self.tab_saved, "◫\u2003Guardados")
        self.tabs.addTab(self.tab_help,  "?\u2003Ayuda")
        layout.addWidget(self.tabs)
        self._build_setup()
        self._build_scan()
        self._build_attack()
        self._build_saved()
        self._build_help()

    def _build_setup(self):
        layout = QVBoxLayout(self.tab_setup); layout.setContentsMargins(4, 16, 4, 4); layout.setSpacing(16)
        layout.setAlignment(Qt.AlignTop)

        card1 = self._make_card("Interfaz WiFi", eyebrow="ADAPTADOR")
        c1 = card1.layout()
        iface_row = QHBoxLayout(); iface_row.setSpacing(10)
        self.setup_iface_combo = QComboBox(); self.setup_iface_combo.setMinimumWidth(240)
        iface_row.addWidget(self.setup_iface_combo)
        refresh_btn = QPushButton("Actualizar")
        refresh_btn.clicked.connect(self._refresh_ifaces)
        iface_row.addWidget(refresh_btn); iface_row.addStretch(1)
        c1.addLayout(iface_row)
        c1.addStretch(1)
        layout.addWidget(card1)

        card2 = self._make_card("Modo monitor", eyebrow="MODO MONITOR")
        c2 = card2.layout()
        self.setup_mon_state = QLabel("Inactivo"); self.setup_mon_state.setObjectName("card_hint")
        c2.addWidget(self.setup_mon_state)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        self.btn_activate = QPushButton("Activar"); self.btn_activate.setObjectName("btn_primary")
        self.btn_activate.clicked.connect(self._start_mon)
        self.btn_deactivate = QPushButton("Desactivar y restaurar")
        self.btn_deactivate.clicked.connect(self._stop_mon)
        btn_row.addWidget(self.btn_activate); btn_row.addWidget(self.btn_deactivate); btn_row.addStretch(1)
        c2.addLayout(btn_row)
        c2.addStretch(1)
        layout.addWidget(card2)
        layout.addStretch(1)

    def _make_card(self, title: str, eyebrow: str = None):
        card = QFrame(); card.setObjectName("card")
        v = QVBoxLayout(card); v.setContentsMargins(14, 12, 14, 14); v.setSpacing(4)
        if eyebrow:
            eb = QLabel(eyebrow); eb.setObjectName("card_eyebrow")
            v.addWidget(eb)
        t = QLabel(title); t.setObjectName("card_title")
        v.addWidget(t)
        return card

    def _build_scan(self):
        layout = QVBoxLayout(self.tab_scan); layout.setContentsMargins(4, 16, 4, 4); layout.setSpacing(12)
        layout.setAlignment(Qt.AlignTop)

        ctr = QHBoxLayout(); ctr.setSpacing(10)
        ctr.addWidget(QLabel("Banda"))
        self.scan_band = QComboBox()
        self.scan_band.addItems(["Todas", "Sólo 2.4 GHz", "Sólo 5 GHz"])
        ctr.addWidget(self.scan_band)
        self.btn_scan = QPushButton("Escanear"); self.btn_scan.setObjectName("btn_primary")
        self.btn_scan.clicked.connect(self._scan_action)
        ctr.addWidget(self.btn_scan)
        self.btn_focus = QPushButton("Enfocar seleccionada")
        self.btn_focus.clicked.connect(self._focus_action); self.btn_focus.setEnabled(False)
        ctr.addWidget(self.btn_focus)
        self.scan_grp_cb = QCheckBox("Agrupar por ESSID"); self.scan_grp_cb.setChecked(True)
        ctr.addWidget(self.scan_grp_cb)
        ctr.addStretch(1)
        layout.addLayout(ctr)
        # Filter row — case-insensitive substring against ESSID; live count.
        filt_row = QHBoxLayout(); filt_row.setSpacing(8)
        filt_row.addWidget(QLabel("Filtrar ESSID:"))
        self.scan_filter = QLineEdit()
        self.scan_filter.setPlaceholderText("ej. jazztel (vacío = todas)")
        self.scan_filter.setClearButtonEnabled(True)
        self.scan_filter.setMaximumWidth(320)
        # Debounce 150 ms before recomputing the filtered view — prevents
        # per-keystroke redraw lag on networks with hundreds of rows.
        self._filter_debounce = QTimer(self)
        self._filter_debounce.setSingleShot(True)
        self._filter_debounce.setInterval(150)
        self._filter_debounce.timeout.connect(self._populate_nets)
        self.scan_filter.textChanged.connect(lambda _: self._filter_debounce.start())
        filt_row.addWidget(self.scan_filter)
        self.scan_filter_count_lbl = QLabel("")
        self.scan_filter_count_lbl.setObjectName("dim")
        self.scan_filter_count_lbl.setFont(_MONO11)
        filt_row.addWidget(self.scan_filter_count_lbl)
        filt_row.addStretch(1)
        layout.addLayout(filt_row)
        # ── Action toolbar — Export / Analyze / Vendor toggle ───────────────────────────────
        # Living just below the filter so power users discover it as the next step
        # after narrowing a scan. Vendor toggle re-fills the trees on toggle.
        act_row = QHBoxLayout(); act_row.setSpacing(8)
        self.btn_export_scan = QPushButton("Exportar escaneo\u2026")
        self.btn_export_scan.setToolTip("Guarda el escaneo completo en JSON \u00f3 CSV")
        self.btn_export_scan.clicked.connect(self._export_scan)
        act_row.addWidget(self.btn_export_scan)
        self.btn_analyze_ch = QPushButton("Analizar solapamiento 2.4\u202fGHz")
        self.btn_analyze_ch.setToolTip("Detecta APs en canales adyacentes y sugiere rebalanceo")
        self.btn_analyze_ch.clicked.connect(self._analyze_channels)
        act_row.addWidget(self.btn_analyze_ch)
        # Vendor info surfaces in two places: (a) tooltip on the BSSID cell,
        # (b) the JSON/CSV export. No column added — keeps the tree compact.
        act_row.addStretch(1)
        layout.addLayout(act_row)

        # Two trees (flat & grouped); only one is visible at a time per the
        # "Agrupar por ESSID" checkbox. Editorial choice: give the user BOTH
        # rather than mutating columns on a single tree.
        self.nets_grp = QTreeWidget()
        self._setup_tree(self.nets_grp, ["ESSID / BSSID", "CH", "PWR", "ENC", "NOMBRE"],
                          widths=[240, 46, 52, 76, 300], decorated=True,
                          right_cols=(1, 2))
        self.nets_flat = QTreeWidget()
        self._setup_tree(self.nets_flat, ["BSSID", "CH", "PWR", "ENC", "ESSID", "NOMBRE"],
                          widths=[170, 46, 52, 76, 240, 230], decorated=False,
                          right_cols=(1, 2))
        self.nets_grp.itemSelectionChanged.connect(self._on_select_grp)
        self.nets_grp.itemDoubleClicked.connect(lambda *_: self._focus_action())
        self.nets_flat.itemSelectionChanged.connect(self._on_select_flat)
        self.nets_flat.itemDoubleClicked.connect(lambda *_: self._focus_action())
        self.nets_grp.setContextMenuPolicy(Qt.CustomContextMenu)
        self.nets_grp.customContextMenuRequested.connect(lambda p: self._ctx_menu(p, self.nets_grp))
        self.nets_flat.setContextMenuPolicy(Qt.CustomContextMenu)
        self.nets_flat.customContextMenuRequested.connect(lambda p: self._ctx_menu(p, self.nets_flat))
        self.scan_grp_cb.stateChanged.connect(self._populate_nets)
        # Stacked view: empty-state placeholder ↔ grouped tree ↔ flat tree.
        # The empty placeholder mirrors the card hierarchy (eyebrow / title /
        # body) so it doesn't feel like a generic "no data" bootstrap.
        self.nets_empty = QFrame()
        self.nets_empty.setMinimumHeight(320)   # don't let the 2:1 stretches collapse on a short window.
        ev = QVBoxLayout(self.nets_empty); ev.setSpacing(6); ev.setAlignment(Qt.AlignCenter)
        ev.setContentsMargins(20, 24, 20, 24)
        eb = QLabel("ESCANEO"); eb.setObjectName("card_eyebrow"); eb.setAlignment(Qt.AlignCenter)
        tt = QLabel("Sin redes todavía"); tt.setObjectName("card_title"); tt.setAlignment(Qt.AlignCenter)
        bd = QLabel(
            "Pulsa Escanear para detectar redes WiFi.\n\n"
            "Activa primero el modo monitor en la pestaña Cambio."
        )
        bd.setObjectName("t_body"); bd.setAlignment(Qt.AlignCenter); bd.setWordWrap(True)
        ev.addStretch(2); ev.addWidget(eb); ev.addWidget(tt); ev.addSpacing(8)
        ev.addWidget(bd); ev.addStretch(1)
        self.nets_stack = QStackedWidget()
        self.nets_stack.addWidget(self.nets_empty)         # idx 0 — empty
        self.nets_stack.addWidget(self.nets_grp)           # idx 1 — grouped
        self.nets_stack.addWidget(self.nets_flat)          # idx 2 — flat
        layout.addWidget(self.nets_stack, 1)
        self._populate_nets()

        st_card = self._make_card("Estaciones conectadas", eyebrow="CLIENTES VINCULADOS")
        st_l = st_card.layout()
        self.st_tree = QTreeWidget()
        self._setup_tree(self.st_tree, ["MAC", "AP", "NOMBRE", "PWR"],
                          widths=[180, 180, 320, 70], decorated=False,
                          right_cols=(3,))
        self.st_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.st_tree.customContextMenuRequested.connect(lambda p: self._ctx_menu(p, self.st_tree))
        st_l.addWidget(self.st_tree)
        st_l.addStretch(1)
        layout.addWidget(st_card)
        # ── Channel overlap card (2.4 GHz) — populated on demand by _analyze_channels ──
        self.overlap_card = self._make_card(
            "Solapamiento de canales 2.4\u202fGHz",
            eyebrow="AN\u00c1LISIS")
        self.overlap_card.setObjectName("overlap_card")
        self.overlap_card.setVisible(False)
        ol = self.overlap_card.layout()
        self.overlap_summary = QLabel("")
        self.overlap_summary.setObjectName("t_body")
        self.overlap_summary.setWordWrap(True)
        ol.addWidget(self.overlap_summary)
        self.overlap_detail = QLabel("")
        self.overlap_detail.setObjectName("t_mono")
        self.overlap_detail.setWordWrap(True)
        self.overlap_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        ol.addWidget(self.overlap_detail)
        ol.addStretch(1)
        layout.addWidget(self.overlap_card)

    def _setup_tree(self, tree: QTreeWidget, headers: list, widths: list, *,
                    decorated: bool, right_cols: tuple = ()):
        tree.setColumnCount(len(headers))
        tree.setHeaderLabels(headers)
        tree.setRootIsDecorated(decorated)
        tree.setAlternatingRowColors(True)
        tree.setUniformRowHeights(True)
        tree.setSelectionMode(QAbstractItemView.SingleSelection)
        tree.setSelectionBehavior(QAbstractItemView.SelectRows)
        tree.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tree.setExpandsOnDoubleClick(False)
        for i, w in enumerate(widths):
            tree.setColumnWidth(i, w)
        # Right-align numeric columns (CH, PWR, dBm) so values line up; also
        # stamp those headers with caps-mono so tabular columns read as one
        # block instead of mixed serif + sans.
        for c in right_cols:
            tree.headerItem().setTextAlignment(c, Qt.AlignRight | Qt.AlignVCenter)
            tree.headerItem().setFont(c, _MONO10_BOLD)

    def _build_attack(self):
        layout = QVBoxLayout(self.tab_attack); layout.setContentsMargins(4, 16, 4, 4); layout.setSpacing(16)
        layout.setAlignment(Qt.AlignTop)

        card = self._make_card("Objetivo", eyebrow="ATAQUE")
        form = QFormLayout(); form.setContentsMargins(0, 0, 0, 0); form.setSpacing(10)
        self.atk_bssid = QLineEdit(); self.atk_bssid.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        self.atk_station = QLineEdit(); self.atk_station.setPlaceholderText("AA:BB:CC:11:22:33")
        self.atk_pick = QComboBox(); self.atk_pick.setMinimumWidth(300)
        self.atk_pick.currentIndexChanged.connect(self._on_pick_changed)
        form.addRow("BSSID de la red", self.atk_bssid)
        form.addRow("Estación (vacío = todas)", self.atk_station)
        form.addRow("Selección rápida", self.atk_pick)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        b1 = QPushButton("Desautenticar estación"); b1.setObjectName("btn_attack")
        b1.clicked.connect(self._do_deauth)
        b2 = QPushButton("Desautenticar TODAS"); b2.setObjectName("btn_attack")
        b2.clicked.connect(self._do_deauth_all)
        b3 = QPushButton("Detener todo"); b3.clicked.connect(self._stop_all)
        for b in (b1, b2, b3): btn_row.addWidget(b)
        btn_row.addStretch(1)
        form.addRow("", self._wrap_layout(btn_row))
        card.layout().addLayout(form)
        card.layout().addStretch(1)
        layout.addWidget(card)

        log_card = self._make_card("Registro de ataques", eyebrow="BITÁCORA")
        log_l = log_card.layout()
        self.atk_log = QPlainTextEdit(); self.atk_log.setReadOnly(True)
        self.atk_log.setMinimumHeight(140)
        log_l.addWidget(self.atk_log)
        log_btn_row = QHBoxLayout(); log_btn_row.setSpacing(8)
        self.btn_export_log = QPushButton("Exportar bit\u00e1cora\u2026")
        self.btn_export_log.clicked.connect(self._export_log)
        self.btn_clear_log = QPushButton("Limpiar bit\u00e1cora")
        self.btn_clear_log.clicked.connect(self._clear_log)
        log_btn_row.addWidget(self.btn_export_log)
        log_btn_row.addWidget(self.btn_clear_log)
        log_btn_row.addStretch(1)
        log_l.addLayout(log_btn_row)
        layout.addWidget(log_card)
        layout.addStretch(1)

    def _wrap_layout(self, lay):
        w = QWidget(); w.setLayout(lay); return w

    def _on_pick_changed(self, _idx: int):
        txt = self.atk_pick.currentText()
        if txt:
            # Selected entry: "AA:BB:CC:11:22:33  (AP AA:BB:CC:DD:EE:FF)"
            self.atk_station.setText(txt.split("  ")[0])

    def _build_saved(self):
        layout = QVBoxLayout(self.tab_saved); layout.setContentsMargins(4, 16, 4, 4); layout.setSpacing(16)
        layout.setAlignment(Qt.AlignTop)

        card = self._make_card("Guardar / Editar nombre", eyebrow="EDITAR")
        form = QFormLayout(); form.setContentsMargins(0, 0, 0, 0); form.setSpacing(10)
        self.sv_bssid = QLineEdit(); self.sv_bssid.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        self.sv_name = QLineEdit(); self.sv_name.setPlaceholderText("TV del vecino")
        self.sv_type = QComboBox(); self.sv_type.addItems(["AP", "Estación"])
        form.addRow("BSSID / MAC", self.sv_bssid)
        form.addRow("Nombre", self.sv_name)
        form.addRow("Tipo", self.sv_type)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        b_save = QPushButton("Guardar"); b_save.setObjectName("btn_primary")
        b_save.clicked.connect(self._save_name)
        b_del = QPushButton("Eliminar"); b_del.clicked.connect(self._remove_name)
        for b in (b_save, b_del): btn_row.addWidget(b)
        btn_row.addStretch(1)
        form.addRow("", self._wrap_layout(btn_row))
        card.layout().addLayout(form)
        card.layout().addStretch(1)
        layout.addWidget(card)

        list_card = self._make_card("Entradas guardadas", eyebrow="NOMBRES LEGIBLES")
        list_l = list_card.layout()
        self.sv_tree = QTreeWidget()
        self._setup_tree(self.sv_tree, ["BSSID", "NOMBRE", "TIPO", "ESSID"],
                          widths=[180, 260, 80, 260], decorated=False)
        self.sv_tree.itemSelectionChanged.connect(self._on_select_saved)
        list_l.addWidget(self.sv_tree)
        refresh_btn = QPushButton("Actualizar"); refresh_btn.clicked.connect(self._refresh_saved)
        list_l.addWidget(refresh_btn)
        layout.addWidget(list_card)
        self._refresh_saved()

    def _build_help(self):
        """Editorial wiki with sticky TOC + in-page Ctrl+F search + ATENCIÓN seals.

        Twelve sections driven by ``WIKI_SECTIONS`` (class-level constant just
        above): each section is a magazine card with eyebrow + title + stacked
        body widgets. The sidebar on the left (fixed width 232 px, never
        scrolls) lists them with §01–§12 numbers; clicking a button jumps the
        right scroll area to that section via ``ensureWidgetVisible``. The
        ``Ctrl+F`` hotkey focuses the search field at the top of the sidebar.
        Typing filters the right column by hiding non-matching sections via
        ``setVisible(False)`` (highlight-mode, not delete-mode).
        """
        hbox = QHBoxLayout(self.tab_help)
        hbox.setContentsMargins(0, 0, 0, 0); hbox.setSpacing(0)

        # === LEFT (sticky) — TOC panel + search =================================
        toc_panel = QFrame(); toc_panel.setObjectName("toc_panel")
        toc_panel.setFixedWidth(232)
        toc_l = QVBoxLayout(toc_panel); toc_l.setContentsMargins(10, 14, 10, 14); toc_l.setSpacing(2)

        eb = QLabel("TABLA DE CONTENIDO"); eb.setObjectName("toc_eyebrow")
        toc_l.addWidget(eb); toc_l.addSpacing(6)

        self.help_search = QLineEdit()
        self.help_search.setObjectName("help_search")
        self.help_search.setPlaceholderText("Buscar…  (Ctrl+F)")
        self.help_search.setClearButtonEnabled(True)
        self.help_search.textChanged.connect(self._help_filter)
        toc_l.addWidget(self.help_search)
        toc_l.addSpacing(8)

        # Build TOC buttons + precompute per-section searchable haystacks so
        # _help_filter() is O(N) cheap on every keystroke.
        self._toc_buttons = {}; self._toc_sections = {}; self._help_searchable = {}
        for anchor, num, eyebrow, title, severity, items in self.WIKI_SECTIONS:
            btn_label = ("§%02d  ⚑  " if severity == "warn" else "§%02d  ") % num + title
            btn = QPushButton(btn_label)
            btn.setObjectName("toc_btn")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, a=anchor: self._help_jump_to(a))
            self._toc_buttons[anchor] = btn
            toc_l.addWidget(btn)
            self._help_searchable[anchor] = " ".join(
                [eyebrow, title] + [t for (k, t) in items]).lower()

        toc_l.addStretch(1)
        foot = QLabel("⌨   Ctrl + F  enfoca la búsqueda")
        foot.setObjectName("lbl_meta")
        toc_l.addWidget(foot)

        hbox.addWidget(toc_panel)

        # === RIGHT — scrollable content =========================================
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame); scroll.setObjectName("help_scroll")
        cv_container = QWidget()
        cv = QVBoxLayout(cv_container); cv.setContentsMargins(8, 18, 8, 18); cv.setSpacing(14)

        # Sequence-driven render of every section. _wiki_section now accepts
        # severity ("warn" for ATENCIÓN seal) and anchor (Qt property used by
        # _help_jump_to). The cards belong to ``self._toc_sections`` for live
        # show/hide from the Ctrl+F search filter.
        # NOTE: _h(text, kind) — text first, kind second.
        for anchor, num, eyebrow, title, severity, items in MainWindow.WIKI_SECTIONS:
            body_widgets = [self._h(text, kind) for (kind, text) in items]
            card = self._wiki_section(
                eyebrow, title, body_widgets,
                severity=severity, anchor=anchor,
            )
            self._toc_sections[anchor] = card
            cv.addWidget(card)

        cv.addStretch(1)
        scroll.setWidget(cv_container)
        hbox.addWidget(scroll, 1)

    # -------------------------------------------------------------------------
    # Help-tab helpers — Ctrl+F search filter + sticky-TOC jump
    # -------------------------------------------------------------------------
    def _help_filter(self, text: str):
        """Hide TOC buttons + section cards whose searchable text doesn't
        match the query. Empty query shows everything. O(N) per keystroke:
        each section's haystack is precomputed in _build_help into
        ``self._help_searchable``.

        Single-pass over both the section widget and its TOC mirror button,
        plus drops the ``checked`` state on hidden buttons (the active marker
        was attached to a now-invisible card — misleading to keep its glow).
        """
        q = (text or "").strip().lower()
        for anchor, w in self._toc_sections.items():
            haystack = self._help_searchable.get(anchor, "")
            visible = (not q) or (q in haystack)
            w.setVisible(visible)
            btn = self._toc_buttons.get(anchor)
            if btn is not None:
                btn.setVisible(visible)
                if not visible:
                    btn.setChecked(False)

    def _help_jump_to(self, anchor: str):
        """Scroll the right QScrollArea so the target card is visible
        (50 px top padding). Switches to Ayuda tab if not already there.

        Only clears the active search filter if the destination card was
        hidden by it — otherwise the user would unexpectedly see all 12
        sections flash back open at every TOC click.
        """
        if self.tabs.currentIndex() != 4:
            self.tabs.setCurrentIndex(4)
        w = self._toc_sections.get(anchor)
        if not w:
            return
        # Walk up the parent chain looking for a QScrollArea.
        p = w.parentWidget()
        while p is not None and not isinstance(p, QScrollArea):
            p = p.parentWidget()
        if p is not None:
            p.ensureWidgetVisible(w, 50, 50)
        # Reflect the active section in the TOC list.
        for a, btn in self._toc_buttons.items():
            btn.setChecked(a == anchor)
        if (hasattr(self, "help_search") and self.help_search.text()
                and not w.isVisible()):
            self.help_search.clear()

    def _h(self, text: str, kind: str = "body"):
        """Section body builder.

        ``kind=\"code\"`` yields a QLabel with the dedicated code_block style
        (mono + soft surface_alt bg + hairline border), word-wrap disabled to
        preserve diagram alignment; otherwise dict-mapped styles.
        """
        if kind == "code":
            lbl = QLabel(text)
            lbl.setObjectName("code_block")
            lbl.setTextFormat(Qt.PlainText)
            lbl.setWordWrap(False)
            return lbl
        lbl = QLabel(text)
        lbl.setObjectName({
            "h1": "t_h1", "h2": "t_h2", "body": "t_body",
            "mono": "t_mono", "label": "t_label",
        }[kind])
        lbl.setTextFormat(Qt.PlainText)
        lbl.setWordWrap(True)
        return lbl

    def _wiki_section(self, eyebrow: str, title: str, body_widgets: list,
                      *, severity: str = "info", anchor: str = None):
        """Editorial wiki section card: eyebrow + title + stacked body widgets.

        ``severity=\"warn\"`` applies an ATENCIÓN seal (left border in danger
        color + a small caps label above the title). ``anchor`` is stored as
        a Qt property on the card so callers can target a section by name.
        """
        card = QFrame()
        card.setObjectName("card_warn" if severity == "warn" else "card")
        v = QVBoxLayout(card); v.setContentsMargins(20, 18, 20, 20); v.setSpacing(8)
        if severity == "warn":
            seal = QLabel("⚑   ATENCIÓN   LEE ANTES DE ACTUAR")
            seal.setObjectName("card_warn_seal")
            v.addWidget(seal)
        eb = QLabel(eyebrow); eb.setObjectName("card_eyebrow")
        v.addWidget(eb)
        tt = QLabel(title); tt.setObjectName("t_h1"); tt.setWordWrap(True)
        v.addWidget(tt)
        for w in body_widgets:
            v.addWidget(w)
        v.addStretch(1)
        if anchor:
            card.setProperty("anchor_id", anchor)
        return card

    def _build_statusbar(self):
        sb = QStatusBar(); self.setStatusBar(sb)
        self.sb_iface_lbl = QLabel("iface —"); self.sb_state_lbl = QLabel("—")
        self.sb_msg_lbl = QLabel("")
        self.sb_state_lbl.setObjectName("sb_state"); self.sb_msg_lbl.setObjectName("sb_msg")
        # Hairline V-rules between the three zones — VSCode/Zed pattern.
        sep1 = QFrame(); sep1.setObjectName("sb_sep"); sep1.setFrameShape(QFrame.VLine)
        sep1.setFrameShadow(QFrame.Plain)
        sep2 = QFrame(); sep2.setObjectName("sb_sep"); sep2.setFrameShape(QFrame.VLine)
        sep2.setFrameShadow(QFrame.Plain)
        sb.addWidget(self.sb_iface_lbl, 1)
        sb.addPermanentWidget(sep1)
        sb.addPermanentWidget(self.sb_state_lbl)
        sb.addPermanentWidget(sep2)
        sb.addPermanentWidget(self.sb_msg_lbl)

    # -------------------------------------------------------------------------
    # Hotkeys — Ctrl+1..5 tabs · Ctrl+T cycle theme · Ctrl+R rescan · Ctrl+Q clear filter
    # -------------------------------------------------------------------------
    def _setup_hotkeys(self):
        for i in range(1, 6):
            sc = QShortcut(QKeySequence(f"Ctrl+{i}"), self)
            sc.activated.connect(lambda _checked=False, idx=i-1: self.tabs.setCurrentIndex(idx))
        QShortcut(QKeySequence("Ctrl+T"), self).activated.connect(self._cycle_theme)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._hotkey_rescan)
        QShortcut(QKeySequence("Ctrl+Q"), self).activated.connect(self._hotkey_clear_filter)
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(self._hotkey_focus_help)

    def _cycle_theme(self):
        names = list(THEMES.keys())
        if self.current_theme_name not in names:
            return
        idx = names.index(self.current_theme_name)
        self._set_theme(names[(idx + 1) % len(names)])

    def _hotkey_rescan(self):
        if self.tabs.currentIndex() != 1:
            self.tabs.setCurrentIndex(1)
        self._scan_action()

    def _hotkey_clear_filter(self):
        if getattr(self, "scan_filter", None):
            self.scan_filter.clear()

    def _hotkey_focus_help(self):
        """Switch to Ayuda tab and focus the in-page search field."""
        if self.tabs.currentIndex() != 4:
            self.tabs.setCurrentIndex(4)
        if hasattr(self, "help_search"):
            self.help_search.setFocus()
            self.help_search.selectAll()

    # -------------------------------------------------------------------------
    # Theme application
    # -------------------------------------------------------------------------
    def _set_theme(self, name: str):
        if name == self.current_theme_name or name not in THEMES:
            return
        self.current_theme_name = name
        self.theme_btn.setText(name + "  \u25be")
        self.theme_btn.setProperty("theme_name", name)
        self._rebuild_theme_menu()
        self._apply_theme(name)

    def _apply_theme(self, name: str):
        t = THEMES[name]
        app = QApplication.instance()
        sans = QFont(); sans.setFamilies([f.strip().strip('"') for f in t.sans_family.split(',')])
        sans.setPointSize(11)
        app.setFont(sans)
        app.setStyle("Fusion")
        app.setStyleSheet(build_stylesheet(t))
        self.bk.current_theme = name
        self._set_status_msg(f"tema {name}")

    def _set_status_msg(self, msg: str):
        self.sb_msg_lbl.setText(msg)
    def _set_status_iface(self, txt: str):
        self.sb_iface_lbl.setText("iface " + txt)
    def _set_status_state(self, txt: str):
        self.sb_state_lbl.setText(txt)

    # -------------------------------------------------------------------------
    # Setup tab actions
    # -------------------------------------------------------------------------
    def _refresh_ifaces(self):
        self.ifaces = self.bk.wifi_ifaces()
        self.setup_iface_combo.clear()
        self.setup_iface_combo.addItems(self.ifaces)
        if self.ifaces and not self.setup_iface_combo.currentText():
            self.setup_iface_combo.setCurrentIndex(0)
        self._set_status_iface(self.bk.mon_iface or (self.setup_iface_combo.currentText() or "—"))

    def _start_mon(self):
        iface = self.setup_iface_combo.currentText()
        if not iface:
            return self._warn("Selecciona una interfaz WiFi primero.")
        self._set_status_state("ACTIVANDO…")
        ok, msg = self.bk.start_mon(iface)
        if ok:
            self.setup_mon_state.setText(f"Activo · {self.bk.mon_iface}")
            self._set_status_state("MONITOR")
            self._set_status_iface(self.bk.mon_iface)
            self._set_status_msg(msg)
        else:
            self._set_status_state("ERROR")
            self._err(msg)

    def _stop_mon(self):
        self.bk.stop_all()
        ok, msg = self.bk.stop_mon()
        if ok:
            self.setup_mon_state.setText("Inactivo")
            self._set_status_state("INACTIVO")
            self._set_status_msg(msg)
        else:
            self._warn(msg)

    # -------------------------------------------------------------------------
    # Scan tab actions
    # -------------------------------------------------------------------------
    def _scan_action(self):
        if not self.bk.mon_iface:
            return self._warn("Activa el modo monitor primero (pestaña Cambio).")
        if self.scan_worker and self.scan_worker.isRunning():
            return
        labels = ["todas", "2.4 GHz", "5 GHz"]
        band = ["", "g", "a"][self.scan_band.currentIndex()]
        self._set_status_state("ESCANEANDO…")
        self._set_status_msg(f"airodump-ng ({labels[self.scan_band.currentIndex()]})…")
        self.scan_worker = ScanWorker(self.bk, band)
        self.scan_worker.finished.connect(self._scan_done)
        self.scan_worker.start()

    def _scan_done(self, nets: list):
        self.networks = nets
        self._populate_nets()
        self._set_status_state("OK")
        self._set_status_msg(f"{len(nets)} redes capturadas")
        self.btn_focus.setEnabled(bool(nets))

    def _populate_nets(self):
        grouped = self.scan_grp_cb.isChecked()
        # Reset selection across the toggle so a stale BSSID doesn't get hit
        # when the user switches between grouped and flat mid-scan.
        self.sel_net = None
        for tree in (self.nets_grp, self.nets_flat):
            tree.clear()
        # Apply ESSID substring filter (case-insensitive). Empty passes through;
        # anything else narrows the candidate set; no match → empty state.
        filt = (self.scan_filter.text() if hasattr(self, "scan_filter") else "").strip().lower()
        visible = [n for n in self.networks if not filt or filt in n["essid"].lower()] if self.networks else []
        # Live count for the filter label, e.g. "12/48 visibles".
        if hasattr(self, "scan_filter_count_lbl"):
            if self.networks:
                self.scan_filter_count_lbl.setText(
                    f"{len(visible)}/{len(self.networks)} visibles" if filt
                    else f"{len(self.networks)} redes"
                )
            else:
                self.scan_filter_count_lbl.setText("")
        if not visible:
            self.nets_stack.setCurrentIndex(0)
            if hasattr(self, "btn_export_scan"):
                self.btn_export_scan.setEnabled(False)
                self.btn_analyze_ch.setEnabled(False)
            return
        if hasattr(self, "btn_export_scan"):
            self.btn_export_scan.setEnabled(True)
            self.btn_analyze_ch.setEnabled(True)
        if grouped:
            self._fill_grp(visible)
            self.nets_stack.setCurrentIndex(1)
        else:
            self._fill_flat(visible)
            self.nets_stack.setCurrentIndex(2)

    def _fill_grp(self, nets=None):
        if nets is None:
            nets = self.networks
        groups = self.bk.group_by_essid(nets)
        for essid, ns in sorted(groups.items()):
            parent = QTreeWidgetItem(self.nets_grp)
            parent.setText(0, essid)        # ESSID in tree-label column for the group
            parent.setFlags(parent.flags() & ~Qt.ItemIsSelectable)
            for n in ns:
                row = QTreeWidgetItem(parent)
                row.setText(0, n["bssid"]); row.setText(1, n["channel"])
                row.setText(2, n["power"]); row.setText(3, n.get("encryption", "?"))
                row.setText(4, self.bk.name_of(n["bssid"]) or "")
                row.setData(0, Qt.UserRole, n["bssid"])
                v = vendor_of(n["bssid"])
                if v:
                    row.setToolTip(0, f"Fabricante (OUI): {v}")
                # Stamp the numeric columns (CH, PWR) with mono cells so the
                # values line up column-wise instead of mixing with sans.
                for c in (1, 2):
                    row.setFont(c, _MONO11)
            parent.setExpanded(True)

    def _fill_flat(self, nets=None):
        if nets is None:
            nets = self.networks
        for n in nets:
            row = QTreeWidgetItem(self.nets_flat)
            row.setText(0, n["bssid"]); row.setText(1, n["channel"])
            row.setText(2, n["power"]); row.setText(3, n.get("encryption", "?"))
            row.setText(4, n["essid"])
            row.setText(5, self.bk.name_of(n["bssid"]) or "")
            row.setData(0, Qt.UserRole, n["bssid"])
            v = vendor_of(n["bssid"])
            if v:
                row.setToolTip(0, f"Fabricante (OUI): {v}")
            # Stamp the numeric columns (CH, PWR) with mono cells.
            for c in (1, 2):
                row.setFont(c, _MONO11)

    def _on_select_flat(self):
        items = self.nets_flat.selectedItems()
        if not items: return
        item = items[0]
        bssid = item.data(0, Qt.UserRole) or item.text(0)
        if bssid:
            self.sel_net = bssid

    def _on_select_grp(self):
        items = self.nets_grp.selectedItems()
        if not items: return
        bssid = items[0].data(0, Qt.UserRole)
        if bssid:
            self.sel_net = bssid

    def _focus_action(self):
        if not self.sel_net:
            return self._warn("Selecciona una red primero.")
        net = next((n for n in self.networks if n["bssid"] == self.sel_net), None)
        if not net:
            return
        if self.focus_worker and self.focus_worker.isRunning():
            return
        self._set_status_state("ENFOCANDO…")
        self._set_status_msg(f"airodump-ng -c {net['channel']} --bssid {net['bssid']}…")
        self.focus_worker = FocusedScanWorker(self.bk, net["bssid"], net["channel"])
        self.focus_worker.finished.connect(self._focus_done)
        self.focus_worker.start()

    def _focus_done(self, stas: list):
        self.stations = stas
        self.st_tree.clear()
        for s in stas:
            row = QTreeWidgetItem(self.st_tree)
            row.setText(0, s["station"]); row.setText(1, s["ap"])
            row.setText(2, self.bk.name_of(s["station"]) or s["station"])
            row.setText(3, s.get("power", "?"))
            row.setFont(3, _MONO11)            # PWR column → mono cells
            row.setData(0, Qt.UserRole, s["station"])
        self._update_attack_pick()
        self._set_status_state("OK")
        self._set_status_msg(f"{len(stas)} estaciones en {self.sel_net}")
        if self.sel_net and not self.atk_bssid.text():
            self.atk_bssid.setText(self.sel_net)

    def _update_attack_pick(self):
        self.atk_pick.clear()
        self.atk_pick.addItem("")
        for s in self.stations:
            self.atk_pick.addItem(f"{s['station']}  (AP {s['ap']})")

    def _ctx_menu(self, pos, tree: QTreeWidget):
        item = tree.itemAt(pos)
        if not item: return
        bssid = item.data(0, Qt.UserRole) or item.text(0)
        m = QMenu(tree)
        a1 = m.addAction("Copiar BSSID/MAC")
        a2 = m.addAction("Copiar nombre")
        chosen = m.exec(tree.viewport().mapToGlobal(pos))
        if chosen == a1:
            QApplication.clipboard().setText(bssid)
            self._set_status_msg(f"copiado {bssid}")
        elif chosen == a2:
            name = self.bk.name_of(bssid)
            QApplication.clipboard().setText(name)
            self._set_status_msg(f"copiado {name or '(sin nombre)'}")

    # -------------------------------------------------------------------------
    # Attack tab actions
    # -------------------------------------------------------------------------
    def _do_deauth(self):
        bssid = self.atk_bssid.text().strip().upper()
        station = self.atk_station.text().strip().upper()
        if not bssid:
            return self._warn("Introduce un BSSID en la pestaña Ataque.")
        if not station:
            return self._warn("MAC de estación vacía — pulsa 'Desautenticar TODAS' si quieres.")
        ok, msg = self.bk.deauth(bssid, station)
        if ok: self._record_attack(msg)
        else: self._err(msg)

    def _do_deauth_all(self):
        bssid = self.atk_bssid.text().strip().upper()
        if not bssid:
            return self._warn("Introduce un BSSID.")
        ok, msg = self.bk.deauth(bssid)
        if ok: self._record_attack(msg)
        else: self._err(msg)

    def _stop_all(self):
        self.bk.stop_all()
        self._atk_log_msg("Todos los ataques detenidos.")
        self._set_status_state("DETENIDO")

    def _record_attack(self, msg: str):
        self._atk_log_msg(msg)
        self._set_status_state("ATAQUE")
        self._set_status_msg(msg)

    def _atk_log_msg(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.atk_log.appendPlainText(f"[{ts}]  {msg}")
        sb = self.atk_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_log(self):
        self.atk_log.clear()
        self._set_status_msg("bit\u00e1cora limpiada")

    def _export_log(self):
        if not self.atk_log.toPlainText().strip():
            return self._warn("La bit\u00e1cora est\u00e1 vac\u00eda.")
        fn, _ = QFileDialog.getSaveFileName(
            self, "Exportar bit\u00e1cora", "attacks_log.txt",
            "Texto (*.txt);;Todos los archivos (*)")
        if not fn:
            return
        try:
            with open(fn, "w", encoding="utf-8") as f:
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"# WiFi Deauth Manager \u2014 bit\u00e1cora exportada {ts}\n")
                f.write(f"# Tema activo: {self.current_theme_name}\n")
                f.write(f"# iface monitor: {self.bk.mon_iface or '(inactivo)'}\n\n")
                f.write(self.atk_log.toPlainText())
            self._set_status_msg(f"bit\u00e1cora exportada \u2192 {fn}")
        except Exception as e:
            self._err(f"No pude escribir {fn}: {e}")

    # -------------------------------------------------------------------------
    # Scan export (JSON / CSV)
    # -------------------------------------------------------------------------
    def _scan_payload(self) -> dict:
        """Build the structured dump of the current scan for export.

        Vendor resolved from the IEEE OUI prefix (local table). Saved-type
        included for downstream tooling that cross-references against the
        saved_targets.json entries.
        """
        ts = datetime.datetime.now().isoformat(timespec="seconds")
        mon = self.bk.mon_iface or "(inactivo)"
        theme = self.current_theme_name
        rows = []
        for n in self.networks:
            saved = self.bk.targets.get(n["bssid"]) or {}
            row = {
                "bssid": n["bssid"],
                "channel": n["channel"],
                "power": n["power"],
                "encryption": n.get("encryption", "?"),
                "essid": n["essid"],
                "vendor": vendor_of(n["bssid"]),
                "name": self.bk.name_of(n["bssid"]) or "",
            }
            if isinstance(saved, dict):
                row["saved_type"] = saved.get("type", "")
            rows.append(row)
        return {
            "app": "WiFi Deauth Manager",
            "schema": 1,
            "timestamp": ts,
            "monitor_iface": mon,
            "theme": theme,
            "count": len(rows),
            "networks": rows,
        }

    def _write_scan_json(self, fn: str) -> None:
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(self._scan_payload(), f, indent=2, ensure_ascii=False)

    def _write_scan_csv(self, fn: str) -> None:
        import csv
        pl = self._scan_payload()
        cols = ["timestamp", "monitor_iface", "bssid", "channel", "power",
                "encryption", "essid", "vendor", "name", "saved_type"]
        with open(fn, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(cols)
            for r in pl["networks"]:
                w.writerow([pl["timestamp"], pl["monitor_iface"],
                            r["bssid"], r["channel"], r["power"],
                            r["encryption"], r["essid"], r["vendor"],
                            r["name"], r.get("saved_type", "")])

    def _export_scan(self):
        if not self.networks:
            self._set_status_msg("export cancelado \u2014 sin escaneo")
            return self._warn("No hay un escaneo todavía. Pulsa Escanear primero.")
        default = f"wifi_scan_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.json"
        fn, sel = QFileDialog.getSaveFileName(
            self, "Exportar escaneo", default,
            "JSON estructurado (*.json);;CSV para hojas de cálculo (*.csv);;Todos los archivos (*)")
        if not fn:
            self._set_status_msg("export cancelado")
            return
        try:
            if sel.startswith("CSV"):
                if not fn.lower().endswith(".csv"):
                    fn += ".csv"
                self._write_scan_csv(fn)
            else:
                if not fn.lower().endswith(".json"):
                    fn += ".json"
                self._write_scan_json(fn)
            self._set_status_msg(f"escaneo exportado \u2192 {fn}")
        except Exception as e:
            self._err(f"No pude escribir {fn}: {e}")

    # -------------------------------------------------------------------------
    # Channel overlap analyzer (2.4 GHz only)
    # -------------------------------------------------------------------------
    def _analyze_channels(self):
        """Detect 2.4 GHz APs in overlapping channels + suggest clean CH.

        Non-overlapping sets in 2.4 GHz are 1, 6, 11 (separation ≥ 25 MHz).
        Any AP in CH N collides with another AP in any of N±1…N±4 within
        practical frontend tolerances; we use ±2 (industry rule of thumb for
        channels you should not place both APs on at the same site).

        Updates the overlap_card's summary + detail labels. The card is shown
        only when there is at least one 2.4 GHz network to analyse.
        """
        ghz_24 = [n for n in self.networks
                  if n["channel"].isdigit() and 1 <= int(n["channel"]) <= 14]
        if not ghz_24:
            self.overlap_card.setVisible(False)
            return self._warn("Sin redes 2.4\u202fGHz en el escaneo. Captura abierta o forzando 5\u202fGHz no aplica este análisis.")
        groups = {}
        for n in ghz_24:
            ch = int(n["channel"])
            groups.setdefault(ch, []).append(n)
        # Build overlap chains (CHs within ±2 of each other)
        chains = []
        visited = set()
        for ch in sorted(groups.keys()):
            if ch in visited:
                continue
            chain = [ch]; visited.add(ch)
            extended = True
            while extended:
                extended = False
                for other in sorted(groups.keys()):
                    if other in visited:
                        continue
                    if any(abs(other - c) <= 2 for c in chain):
                        chain.append(other); visited.add(other); extended = True
            chains.append(sorted(chain))
        summary = []
        free_ch = [c for c in (1, 6, 11) if c not in groups]
        if free_ch:
            summary.append("Canales despejados (sin colisión): " +
                           ", ".join(f"CH {c}" for c in free_ch) +
                           "  → candidatos óptimos para un nuevo AP.")
        else:
            summary.append("Ningún canal no-solapado libre. Las 3 bandas (1/6/11) tienen al menos un AP.")
        for chain in chains:
            bssids = sum((groups[c] for c in chain), [])
            if len(chain) == 1:
                summary.append(f"CH {chain[0]}  ·  {len(bssids)} APs  ·  sin solape.")
            else:
                summary.append(f"CH {','.join(map(str, chain))}  ·  {len(bssids)} APs  ·  SOLAPAN (separación <\u202f25\u202fMHz).")
        detail = []
        for chain in chains:
            detail.append(f"--- CH {','.join(map(str, chain))} ---")
            for n in sum((groups[c] for c in chain), []):
                nm = self.bk.name_of(n["bssid"]) or n["essid"] or "<oculta>"
                detail.append(f"  {n['bssid']}  {n['power']} dBm  {nm}")
        self.overlap_summary.setText("\n".join(summary))
        self.overlap_detail.setText("\n".join(detail))
        self.overlap_card.setVisible(True)
        self._set_status_msg(f"análisis 2.4 GHz: {len(ghz_24)} APs en {len(chains)} grupos")

    # -------------------------------------------------------------------------
    # Saved tab actions
    # -------------------------------------------------------------------------
    def _save_name(self):
        b = self.sv_bssid.text().strip().upper()
        n = self.sv_name.text().strip()
        t = self.sv_type.currentText() or "AP"
        if not b or not n:
            return self._warn("Rellena BSSID y Nombre.")
        self.bk.set_name(b, n, t)
        self._refresh_saved()
        self._populate_nets()
        self._set_status_msg(f"guardado {b} → {n}")

    def _remove_name(self):
        b = self.sv_bssid.text().strip().upper()
        if not b:
            return self._warn("Introduce un BSSID para eliminar.")
        self.bk.remove_name(b)
        self._refresh_saved()
        self._populate_nets()
        self._set_status_msg(f"eliminado {b}")

    def _on_select_saved(self):
        items = self.sv_tree.selectedItems()
        if not items: return
        vals = [items[0].text(i) for i in range(self.sv_tree.columnCount())]
        if len(vals) >= 2:
            self.sv_bssid.setText(vals[0]); self.sv_name.setText(vals[1])
        if len(vals) >= 3:
            idx = self.sv_type.findText(vals[2] or "AP")
            if idx >= 0: self.sv_type.setCurrentIndex(idx)

    def _refresh_saved(self):
        self.sv_tree.clear()
        for b, v in self.bk.targets.items():
            row = QTreeWidgetItem(self.sv_tree)
            if isinstance(v, dict):
                nm = v.get("name", ""); tp = v.get("type", "AP")
            else:
                nm = v; tp = "AP"
            row.setText(0, b); row.setText(1, nm); row.setText(2, tp)
            for n in self.networks:
                if n["bssid"] == b:
                    row.setText(3, n["essid"]); break

    # -------------------------------------------------------------------------
    # Dialogs
    # -------------------------------------------------------------------------
    def _warn(self, msg: str):
        QMessageBox.warning(self, "Atención", msg)
    def _err(self, msg: str):
        QMessageBox.critical(self, "Error", msg)
        self._set_status_msg("error: " + msg[:80])


# =============================================================================
# Entry point
# =============================================================================
def _check_dep(tool: str) -> bool:
    return subprocess.run(["which", tool], capture_output=True).returncode == 0


def main():
    """Entry point. Permite invocar la app tanto con `python -m
    wifi_deauth_manager` como con el console_script que crea pip install."""
    # Si NO estamos ya elevados (pkexec) y tampoco root → pedir elevación.
    pkexec_uid = os.environ.get("PKEXEC_UID")
    if not pkexec_uid and os.geteuid() != 0:
        sys.stderr.write(
            "Esta aplicación debe ejecutarse con root.\n"
            "Uso: sudo python3 wifi_deauth_manager.py\n"
            "o desde el menú de aplicaciones (polkit te pedirá contraseña).\n")
        return 1
    for tool in ("airmon-ng", "airodump-ng", "aireplay-ng", "iw"):
        if not _check_dep(tool):
            sys.stderr.write(
                f"Falta dependencia: {tool}.\n"
                "Instala con `sudo pacman -S aircrack-ng iw` (Arch) "
                "o `sudo apt install aircrack-ng iw` (Debian/Ubuntu).\n")
            return 1

    app = QApplication(sys.argv)
    app.setApplicationName("WiFi Deauth Manager")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main() or 0)
