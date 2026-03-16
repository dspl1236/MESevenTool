"""
meseventool/ecu_id.py
=====================
ECU identification from ROM content.

Reads VMECUHN, SSECUHN, EROTAN, EPK etc. from the ME7 string table.
Also provides filename-based identification as a fallback.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .rom import ROMImage

# Known VAG engine codes (3-letter, all uppercase)
_ENGINE_CODES = [
    "AWP", "AUM", "AUQ", "BAM", "AVC", "AZG", "AGN",
    "AMU", "APX", "BFV", "BKG", "BFB",
    "AGU", "AEB", "ANB", "AQY",
    "AWM", "AUG", "AWT", "AVJ", "AZM",
    "BAM", "BEV", "BGP", "BGQ", "BKF",
]
# Sorted longest-first and by length to avoid partial matches
_ENGINE_CODE_RE = re.compile(
    r'\b(' + '|'.join(_ENGINE_CODES) + r')\b'
)

# VAG part number pattern
_PN_RE = re.compile(rb'0[6-9][A-Z]\d{6}[A-Z]{0,4}')

# Bosch number pattern: 0261 followed by 6 digits
_BOSCH_RE = re.compile(rb'0261\d{6}')


def _clean_string(raw: bytes) -> str:
    """Replace non-printable bytes with spaces."""
    return "".join(chr(b) if 32 <= b < 127 else " " for b in raw)


@dataclass
class ECUIdentity:
    """Strings and metadata extracted from a ME7 ROM."""
    vmecuhn:      str = ""    # VAG part number  e.g. "06A906032BN"
    ssecuhn:      str = ""    # Bosch hardware number  e.g. "0261206890"
    ssecusn:      str = ""    # Bosch serial number
    erotan:       str = ""    # Model/engine description string
    epk:          str = ""    # KWP2000 ECU identification string
    dif:          str = ""
    bosch_number: str = ""    # 10-digit Bosch number (0261XXXXXX)
    engine_code:  str = ""    # 3-letter engine code (AWP, AUM, BAM …)
    rom_size_kb:  int = 0     # ROM size in KB
    source:       str = "unknown"

    @property
    def is_me75(self) -> bool:
        return self.rom_size_kb == 512

    @property
    def is_me71(self) -> bool:
        return self.rom_size_kb == 256

    @property
    def variant(self) -> str:
        return self.engine_code or "unknown"

    @property
    def part_number(self) -> str:
        """Best available part number."""
        return self.vmecuhn or self.ssecuhn or ""

    @property
    def display_name(self) -> str:
        parts = []
        if self.vmecuhn:
            parts.append(self.vmecuhn)
        if self.erotan:
            parts.append(self.erotan)
        return "  —  ".join(parts) if parts else "(unknown ECU)"

    def __str__(self) -> str:
        lines = []
        if self.vmecuhn:      lines.append(f"VMECUHN  : {self.vmecuhn}")
        if self.bosch_number: lines.append(f"Bosch HW : {self.bosch_number}")
        if self.ssecuhn:      lines.append(f"SSECUHN  : {self.ssecuhn}")
        if self.erotan:       lines.append(f"EROTAN   : {self.erotan}")
        if self.epk:          lines.append(f"EPK      : {self.epk}")
        if self.rom_size_kb:  lines.append(f"ROM size : {self.rom_size_kb} KB")
        if self.engine_code:  lines.append(f"Engine   : {self.engine_code}")
        return "\n".join(lines) if lines else "ECUIdentity(empty)"


def identify(rom: ROMImage) -> ECUIdentity:
    """
    Extract ECU identification from ROM content.

    Scans for:
    - VAG part number pattern (06A906032XX)
    - Bosch number pattern (0261XXXXXX)
    - Engine code (AWP, AUM, BAM, etc.) from printable strings
    """
    ident = ECUIdentity(source="rom", rom_size_kb=rom.size_kb)
    raw   = bytes(rom.data)

    # ── VAG part number ───────────────────────────────────────────────────────
    pn_matches = _PN_RE.findall(raw)
    if pn_matches:
        seen = {}
        for m in pn_matches:
            s = m.decode('ascii', errors='replace')
            seen[s] = seen.get(s, 0) + 1
        ident.vmecuhn = max(seen, key=seen.get)

    # ── Bosch number ──────────────────────────────────────────────────────────
    bosch_matches = _BOSCH_RE.findall(raw)
    if bosch_matches:
        seen = {}
        for m in bosch_matches:
            s = m.decode('ascii', errors='replace')
            seen[s] = seen.get(s, 0) + 1
        ident.bosch_number = max(seen, key=seen.get)
        if not ident.ssecuhn:
            ident.ssecuhn = ident.bosch_number

    # ── Engine code from printable runs ───────────────────────────────────────
    # Collect contiguous printable runs ≥8 bytes then search for engine code
    i = 0
    while i < len(raw) - 4:
        if 32 <= raw[i] < 127:
            j = i
            while j < len(raw) and (32 <= raw[j] < 127 or raw[j] == 0):
                j += 1
            if j - i >= 8:
                text = _clean_string(raw[i:j])
                m = _ENGINE_CODE_RE.search(text)
                if m:
                    ident.engine_code = m.group(1)
                    if not ident.erotan:
                        ident.erotan = text.strip()[:60]
                    break
            i = j
        else:
            i += 1

    return ident


def identify_from_filename(filename: str) -> ECUIdentity:
    """Extract part number from a filename like '06A906032BN_OEM.bin'."""
    ident = ECUIdentity(source="filename")
    m = re.search(r'(0[6-9][A-Z]\d{6}[A-Z]{0,4})', filename, re.IGNORECASE)
    if m:
        ident.vmecuhn = m.group(1).upper()
    return ident


# Alias
ECUIDReader = identify
