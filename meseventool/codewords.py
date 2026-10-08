"""
meseventool/codewords.py
========================
The ME7 emissions codeword block (CD*/CW* single-byte switches around file
offset 0x018194) is NOT one layout.  Its byte order depends on the Bosch
software build, which the ROM's version string names ("40/1/ME7.5/3/4019.20"
→ build 4019).  Writing a "universal" fixed address therefore clears the
wrong switch on many ECUs (review item A7).

This module holds the layouts that are backed by evidence and maps a ROM to
one of them.  A ROM whose build is not listed gets no layout, and every
codeword patch is then NOT_APPLICABLE: the tool never guesses.

Evidence (files.s4wiki.com ``defs/``, all with BASEOFFSET 0, plus the stock
bytes of ~290 corpus images; see ``docs/me7_stable_codeword_block.md``):

- ``me71``   8D0907551M / G XDFs.  Builds 40/1/ME7.1/5/6001, 6005, 6010, 6025
             (S4 B5, A6 C5 2.7T, early Allroad up to M).
- ``4b0``    Same addresses as ``me71`` for every codeword we touch; validated
             on 4B0906018CM tuned files.  Builds ME7.5 4012.xx and 4016.xx
             (4B0906018, 06B906018, 8E0909518, 8E0906018).
- ``06a``    06A906032HS / LP XDFs: an extra CDHSVSA at 0x0181A2 pushes
             CDKAT..CDLSVV one byte later and there is no CDLSHV.  Builds
             ME7.5 4013, 4018, 4019 and 4518 (field 3 == 120): 06A906032,
             8N0906018, 8L0906018.
- ``me711``  4Z7907551R / AA and 4D1907558 XDFs: the whole block two bytes
             earlier.  Builds ME7.1.1 6030, 6011, 8001, 8542 and the RS4
             6024 build (8D0907551K/Q, which is ME7.1 but shares the layout).

Known exceptions (bytes contradict the build rule) are excluded by part
number.  Unlisted: 42/1/ME7.1/5/60xx early 2.7T, 8D0907551F (its XDF is
shifted five), 06A906032 X505R/4220, 4B0906018R, 4D1907558D, 4D0907560BR,
every VR6/W12/Touareg build, and the Golf 5 R32 S1103A builds (code lives
at that offset).
"""

from __future__ import annotations

import re
from typing import Dict, Optional

LAYOUT_TAG_PREFIX = "cw_"

# Address of each codeword per layout (file offsets in a 1 MB image).
# Only codewords the catalogue touches, or that anchor the evidence, are listed.
LAYOUTS: Dict[str, Dict[str, int]] = {
    "me71": {
        "CDEHFM": 0x01819C, "CDHSVE": 0x0181A1, "CDKAT": 0x0181A2, "CDKVS": 0x0181A3,
        "CDLSH": 0x0181AA, "CDLSHV": 0x0181AB, "CDLSV": 0x0181AC, "CDNWS": 0x0181AF,
        "CDSLS": 0x0181B0, "CDTANKL": 0x0181B1, "CDTES": 0x0181B2, "CWKONLS": 0x0181BB,
    },
    "06a": {
        "CDEHFM": 0x01819C, "CDHSVE": 0x0181A1, "CDHSVSA": 0x0181A2, "CDKAT": 0x0181A3,
        "CDKVS": 0x0181A4, "CDLSH": 0x0181AB, "CDLSV": 0x0181AC, "CDNWS": 0x0181AF,
        "CDSLS": 0x0181B0, "CDTANKL": 0x0181B1, "CDTES": 0x0181B2, "CWKONLS": 0x0181BB,
    },
    "me711": {
        "CDEHFM": 0x01819A, "CDHSVE": 0x01819F, "CDKAT": 0x0181A0, "CDKVS": 0x0181A1,
        "CDLSH": 0x0181A8, "CDLSHV": 0x0181A9, "CDLSV": 0x0181AA, "CDNWS": 0x0181AD,
        "CDSLS": 0x0181AE, "CDTANKL": 0x0181AF, "CDTES": 0x0181B0, "CWKONLS": 0x0181B9,
    },
}
LAYOUTS["4b0"] = dict(LAYOUTS["me71"])

# Build number (field 5 of the version string, before the dot) → layout.
# The leading field distinguishes the ME7.1 2.7T generations (40/ vs 42/).
_ME71_BUILDS  = {"6001", "6005", "6010", "6025"}       # with leading "40/"
_ME711_BUILDS = {"6030", "6011", "8001", "8542"}
_RS4_6024     = {"6024"}                                # 8D0907551K/Q only
_ME75_06A     = {"4013", "4018", "4019"}
_ME75_4B0     = {"4012", "4016"}

# Part numbers whose stock bytes contradict the build rule.
EXCEPTIONS = {
    "4B0906018R",     # 4016.31 but a different byte order (CDNWS-like 2 at 0x1B1)
    "4D1907558D",     # 8542.05 but me71-like bytes
    "4D0907560BR",    # 8542.01 Touareg, me71-like bytes, no XDF
    "8D0907551F",     # 6024.02 RS4 ASJ: its XDF is shifted five bytes
}

_VS = re.compile(r"^(\d+)/(\d+)/(ME7[\.\d]*)/(\d+)/([0-9A-Za-z]+)")


def parse_version(version_string: str):
    """("40", "ME7.5", "3", "4019") from "40/1/ME7.5/3/4019.20//24b/..."."""
    m = _VS.match((version_string or "").strip())
    if not m:
        return None
    lead, _, hw, field3, build = m.groups()
    return lead, hw, field3, build.split(".")[0]


def codeword_layout(version_string: str, part_number: str = "") -> Optional[str]:
    """Layout name for this ROM, or None when the build is not covered."""
    pn = re.sub(r"[^0-9A-Za-z]", "", (part_number or "")).upper()
    if pn in EXCEPTIONS:
        return None
    v = parse_version(version_string)
    if not v:
        return None
    lead, hw, field3, build = v
    if hw == "ME7.5":
        if build in _ME75_06A or (build == "4518" and field3 == "120"):
            return "06a"
        if build in _ME75_4B0:
            return "4b0"
        return None
    if hw == "ME7.1":
        if build in _ME71_BUILDS and lead == "40":
            return "me71"
        if build in _RS4_6024 and pn.startswith("8D0907551"):
            return "me711"
        return None
    if hw == "ME7.1.1":
        if build in _ME711_BUILDS and pn[:9] in ("4Z7907551", "4D0907559", "4D0907560", "4D1907558"):
            return "me711"
        return None
    return None


def layout_tag(layout: Optional[str]) -> Optional[str]:
    return LAYOUT_TAG_PREFIX + layout if layout else None


def layout_from_tags(tags) -> Optional[str]:
    for t in tags or ():
        if t.startswith(LAYOUT_TAG_PREFIX) and t[len(LAYOUT_TAG_PREFIX):] in LAYOUTS:
            return t[len(LAYOUT_TAG_PREFIX):]
    return None


def address(layout: str, codeword: str) -> Optional[int]:
    return LAYOUTS.get(layout, {}).get(codeword)
