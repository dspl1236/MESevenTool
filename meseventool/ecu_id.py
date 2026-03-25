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
    # ME7.5 1.8T (C167) — 06A906032xx
    "AWW", "AWD",                          # 150hp (DL/CL/CM variants)
    "AWP", "AUQ", "BAM", "AVC",           # 180hp / 190hp / 225hp
    "AUM", "APH", "AWV", "AJQ", "ARY", "APP",  # other 1.8T
    "AGU", "AEB", "ANB", "AQY",           # early 1.8T (AGU/AEB/ANB)
    # ME7.1 2.7T biturbo
    "AGB", "AZR", "BES", "BCZ",
    # ME7.1 2.8 30v
    "ACK", "APR", "AQD", "ATQ",
    # ME7 1.8T others
    "AMU", "APX", "BFV", "BKG", "BFB",
    "AWM", "AUG", "AWT", "AVJ", "AZM",
    "BAM", "BEV", "BGP", "BGQ", "BKF",
    "AZG", "AGN",
]
# Deduplicate preserving order
_seen = set()
_ENGINE_CODES = [x for x in _ENGINE_CODES if not (x in _seen or _seen.add(x))]

_ENGINE_CODE_RE = re.compile(
    r'\b(' + '|'.join(_ENGINE_CODES) + r')\b'
)

# VAG part number pattern
# VAG part number — covers:
#   06A906032xx (1.8T), 06B906018xx (2.0T) — digit-digit-letter-6digits-suffix
#   8D0907551xx (S4 B5), 4Z7907551xx (Allroad), 4B0907551xx (A6 C5)
#   4D1907558xx (RS4/S8 V8) — digit-letter-7digits-suffix
# ME7.x version string: "40/1/ME7.5/..." or "42/1/ME7.1.1/..."
_VS_RE = re.compile(rb'(?:40|42|43|44)/1/ME7[.0-9A-Za-z]{1,8}')

_PN_RE = re.compile(rb'(?:'
    rb'[0-9][A-Z][0-9]{6,7}[A-Z]{0,4}'   # 8D0907551M, 4Z7907551AA, 4D1907558
    rb'|0[0-9][A-Z][0-9]{6}[A-Z]{0,4}'   # 06A906032DL, 06B906018, 06A906032
    rb'|022906032[A-Z]{0,4}'              # VR6 Golf4/Jetta/R32: 022906032E/CS/CP/EG
    rb'|021906018[A-Z]{0,4}'              # VR6 Golf3/T4: 021906018R/M/B
    rb')')

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
    version_string: str = ""  # ME7.x build version e.g. "40/1/ME7.5/3/4019.20"
    source:       str = "unknown"

    @property
    def is_me75(self) -> bool:
        """ME7.5 ROMs are 512KB (ECUFlash extract) or 1024KB (full flash)."""
        return self.rom_size_kb in (512, 1024)

    @property
    def is_me71(self) -> bool:
        """ME7.1 early ROMs are 256KB."""
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
    - Engine code inferred from PN suffix when not found in ROM strings
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

    # ── EROTAN / engine code from printable runs ──────────────────────────────
    # Two capture strategies:
    #   A) Run contains a known engine code → set both engine_code and erotan
    #   B) Run contains the VAG PN + displacement text (e.g. "06A906032DL 1.8L")
    #      → set erotan even if no engine code is in that string
    #      (ME7.5 DL/CL/CM variants omit engine code from the embedded descriptor)
    _pn_prefix = ident.vmecuhn[:9] if ident.vmecuhn else None
    i = 0
    while i < len(raw) - 4:
        if 32 <= raw[i] < 127:
            j = i
            while j < len(raw) and (32 <= raw[j] < 127 or raw[j] == 0):
                j += 1
            if j - i >= 8:
                text = _clean_string(raw[i:j])
                # Strategy A: engine code present
                m = _ENGINE_CODE_RE.search(text)
                if m:
                    ident.engine_code = m.group(1)
                    if not ident.erotan:
                        ident.erotan = text.strip()[:60]
                    break
                # Strategy B: PN + displacement (e.g. "06A906032DL 1.8L R4/5VT")
                if (_pn_prefix and _pn_prefix in text and
                        any(x in text for x in
                            ['1.', '2.', '3.', 'R4', 'R5', 'V6', 'V8'])):
                    if not ident.erotan:
                        ident.erotan = text.strip()[:60]
                    # Don't break — continue scanning for an engine code in later runs
            i = j
        else:
            i += 1

    # ── Engine code from PN suffix (fallback) ─────────────────────────────────
    # ME7.5 1.8T: the embedded strings don't always spell out the 3-letter code.
    # Map known PN suffixes to engine codes.
    if not ident.engine_code and ident.vmecuhn:
        suffix = ident.vmecuhn[-2:] if len(ident.vmecuhn) >= 2 else ""
        suffix_map = {
            # 06A906032xx — 1.8T ME7.5
            "DL": "AWW",  "CL": "AWD",  "CM": "AWD",
            "BN": "AWP",  "AX": "AWP",  "GE": "AWP",
            "DN": "AUM",  "GF": "AUM",
            "GD": "AUQ",  "GL": "AUQ",
            "HM": "BAM",
            # 06B906018xx — 1.8T ME7.1 (AGU/AEB)
            "AA": "AGU",  "AC": "AGU",
            "AB": "AEB",  "AD": "AEB",
        }
        code = suffix_map.get(suffix)
        if code:
            ident.engine_code = code

    # ── ME7.x version string ─────────────────────────────────────────────────
    vs_match = _VS_RE.search(raw)
    if vs_match:
        # Extend to full slash-delimited version string (up to 60 chars)
        start = vs_match.start()
        end   = min(start + 60, len(raw))
        run   = raw[start:end]
        # Trim at first non-printable or non-path character
        stop  = next((k for k, b in enumerate(run) if b < 0x20 or b > 0x7E), len(run))
        ident.version_string = run[:stop].decode('ascii', 'replace').rstrip('/')

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
