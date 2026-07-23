#!/usr/bin/env python3
"""Tests for the rewritten airodump-ng parser in wifi_deauth_manager.

Synthetic samples model what airodump-ng writes to stdout when captured
via Popen() with encoding='utf-8', errors='ignore'. They include real
ANSI escape sequences emitted by airodump when it expects a TTY:

  \\x1b[H    cursor home
  \\x1b[2J   clear screen
  \\x1b[?25l hide cursor
  \\x1b[2K   clear current line (used on row rewrites)
  \\x1b[0K   clear from cursor to end of line (the "[0K" Carlos used to
             see as a fake ESSID for hidden networks)

Run from project root: python test_parser.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wifi_deauth_manager as wm


# --- Synthetic samples ------------------------------------------------------

# 6 APs covering: WPA2 visible, WPA2 hidden, OPN, ANSI [0K residue,
# WPA3 with SAE, hidden with "<length: 0>" placeholder.
AP_SAMPLE = (
    "BSSID              PWR  Beacons    #Data, #/s  CH   MB   ENC   CIPHER  AUTH  ESSID\n"
    "\x1b[2KAA:BB:CC:DD:EE:FF  -65      23        0, 0    6   54e  WPA2   CCMP    PSK   MiRed\n"
    "\x1b[2K11:22:33:44:55:66  -78      10        5, 2    11  54e  WPA2   CCMP    PSK   \n"
    "\x1b[2K22:33:44:55:66:77  -45       1        0, 0    1   54   OPN                    Vecino\n"
    "\x1b[2K\x1b[0K33:44:55:66:77:88  -55 1 0 0 6 54e WPA2 CCMP PSK HiddenTest\n"
    "\x1b[2K44:55:66:77:88:99  -90    100       20, 5    36  300  WPA3   GCMP    SAE   WiFi6_Lab\n"
    "\x1b[2K55:66:77:88:99:AA  -50    5           0, 0    6   54e  WPA2   CCMP    PSK   <length: 0>\n"
)

# Real airodump-ng STATION layout: BSSID first, STATION second.
# Two clients on the same AP; one with PWR Rate as 2 tokens ("54 -6"),
# one with single token ("54e").
STATION_SAMPLE = (
    "BSSID              STATION            PWR   Rate    Lost    Frames  ESSID\n"
    "\x1b[2KAA:BB:CC:DD:EE:FF          AA:BB:CC:11:22:33  -45   54 -6   0       10      MiRed\n"
    "\x1b[2KAA:BB:CC:DD:EE:FF          11:22:33:44:55:66  -60   54e-1   0        5      MiRed\n"
)

# A station that has not yet associated. Should be skipped (not a valid
# deauth target because there is no AP to disconnect it from).
NOT_ASSOC_SAMPLE = (
    "BSSID              STATION            PWR   Rate    Lost    Frames  ESSID\n"
    "\x1b[2K(not associated)               AA:BB:CC:11:22:33  -45   54 -6   0       10      \n"
)


# --- Tests ------------------------------------------------------------------

def test_ap_lines():
    nets = wm.Backend._parse_ap_lines(AP_SAMPLE)
    by_bssid = {n["bssid"]: n for n in nets}
    assert len(by_bssid) == 6, f"Expected 6 unique APs, got {len(by_bssid)}"

    # AP1: WPA2 / MiRed / CH 6 / PWR -65
    n = by_bssid["AA:BB:CC:DD:EE:FF"]
    assert n["power"] == "-65", f"PWR AP1: {n}"
    assert n["channel"] == "6", f"CH AP1: {n}"
    assert n["encryption"] == "WPA2", f"ENC AP1: {n}"
    assert n["essid"] == "MiRed", f"ESSID AP1: {n}"

    # AP2: WPA2 / hidden (empty after AUTH strip) / CH 11
    n = by_bssid["11:22:33:44:55:66"]
    assert n["essid"] == "<oculta>", f"Hidden AP2: {n}"
    assert n["channel"] == "11", f"CH AP2: {n}"
    assert n["power"] == "-78", f"PWR AP2: {n}"

    # AP3: OPN / Vecino / CH 1
    n = by_bssid["22:33:44:55:66:77"]
    assert n["encryption"] == "OPN", f"ENC AP3: {n}"
    assert n["essid"] == "Vecino", f"ESSID AP3: {n}"
    assert n["channel"] == "1", f"CH AP3: {n}"

    # AP4: had a mid-row \x1b[0K. ESSID should still parse cleanly to
    # "HiddenTest" and "[0K" must NOT leak through.
    n = by_bssid["33:44:55:66:77:88"]
    assert n["essid"] == "HiddenTest", f"ESSID AP4 (post-ANSI strip): {n}"
    for bad in ("[0K", "[", "?"):
        assert bad not in n["essid"], f"Residue '{bad}' leaked: {n}"
    # No comma-pair in this row, so we use the MB-token fallback.
    assert n["channel"] == "6", f"CH AP4 (fallback path): {n}"

    # AP5: WPA3 / GCMP / SAE / WiFi6_Lab / CH 36
    n = by_bssid["44:55:66:77:88:99"]
    assert n["encryption"] == "WPA3", f"ENC AP5: {n}"
    assert n["essid"] == "WiFi6_Lab", f"ESSID AP5: {n}"
    assert n["channel"] == "36", f"CH AP5: {n}"
    assert n["power"] == "-90", f"PWR AP5: {n}"

    # AP6: "<length: 0>" placeholder in ESSID column -> "<oculta>"
    n = by_bssid["55:66:77:88:99:AA"]
    assert n["essid"] == "<oculta>", f"ESSID AP6 (<length: 0>): {n}"

    # Global: no row should leak ANSI fragments or "?" placeholders.
    for n in nets:
        assert "[0K" not in n["essid"], f"ANSI leaked: {n}"
        assert n["power"] != "0" or n["bssid"].startswith("00:"), \
            f"PWR=0 unexpected: {n}"

    print("[OK] _parse_ap_lines: 6 cases (incl. hidden, OPN, WPA3, ANSI strip, fallback)")


def test_station_lines():
    stas = wm.Backend._parse_station_lines(STATION_SAMPLE)
    assert len(stas) == 2, f"Expected 2 stations, got {len(stas)}: {stas}"

    by_mac = {s["station"]: s for s in stas}
    s1 = by_mac["AA:BB:CC:11:22:33"]
    assert s1["ap"] == "AA:BB:CC:DD:EE:FF", f"AP for station AA:BB:CC:11:22:33: {s1}"

    s2 = by_mac["11:22:33:44:55:66"]
    assert s2["ap"] == "AA:BB:CC:DD:EE:FF", f"AP for station 11:22:33:44:55:66: {s2}"

    print("[OK] _parse_station_lines: 2 stations, Rate column width handled")


def test_not_associated():
    stas = wm.Backend._parse_station_lines(NOT_ASSOC_SAMPLE)
    assert stas == [], f"'(not associated)' must be skipped, got: {stas}"
    print("[OK] _parse_station_lines skips '(not associated)' sentinel")


def test_ap_lines_dedupe():
    """airodump emits the same BSSID twice when channel & ESSID list
    span multiple 'blocks'; the parser should keep only one entry."""
    sample = (
        "BSSID              PWR  Beacons    #Data, #/s  CH   MB   ENC   CIPHER  AUTH  ESSID\n"
        "\x1b[2KAA:BB:CC:DD:EE:FF  -65      23        0, 0    6   54e  WPA2   CCMP    PSK   MiRed\n"
        "\x1b[2KAA:BB:CC:DD:EE:FF  -67      50       50, 4    6   54e  WPA2   CCMP    PSK   MiRed\n"
    )
    nets = wm.Backend._parse_ap_lines(sample)
    assert len(nets) == 1, f"Expected 1 deduplicated AP, got {len(nets)}: {nets}"
    print("[OK] _parse_ap_lines dedupes by BSSID")


if __name__ == "__main__":
    test_ap_lines()
    test_station_lines()
    test_not_associated()
    test_ap_lines_dedupe()
    print("\nAll parser tests passed.")
