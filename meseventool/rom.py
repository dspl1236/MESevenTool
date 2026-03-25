"""
meseventool/rom.py
==================
ROMImage — load, validate, and manage a ME7.x binary ROM image.

ME7.x ROM characteristics
--------------------------
CPU:   Infineon C167 (16-bit, little-endian)
Flash: 1 MB (0x100000 bytes) for ME7.5 — Bosch uses a 1MB NOR flash chip
       (Intel 28F800 or equivalent) on all ME7.5 ECUs.
       256 KB for some ME7.1 variants (older, smaller flash).

       Note: some community tools (ECUFlash, WinOLS) export only the
       calibration window (typically the last 512KB or last 64KB of the
       flash), producing smaller files. These are supported as a
       convenience but the full 1MB file is the native format.

Memory layout (1 MB / 06A-906-032 family):
  file[0x000000] = C167 address 0x80000  (start of flash in C167 space)
  file[0x0FFFFF] = C167 address 0xFFFFF  (end of flash / reset vectors)

  Calibration tables are scattered through the flash alongside code.
  XDF offsets are flat file offsets (e.g. KFZW at 0x0120DD in the 1MB file).
  There is NO address-line mirroring in ME7 — the full 1MB is live.
  (Mirroring is a Digifant/Motronic 2.x EPROM phenomenon.)

Older Motronic 5.x / Digifant:
  Use 32KB or 64KB EPROMs (27C256/27C512). A15-mirroring occurs when a
  27C512 is used in a 32KB socket (A15 not connected → 64KB chip behaves
  as two identical 32KB halves).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional


# Known valid ROM sizes
VALID_SIZES = {
    0x040000: "256 KB (ME7.1)",
    0x080000: "512 KB (ECUFlash/extracted cal region)",
    0x100000: "1 MB (ME7.5 full flash)",
}

# Calibration page constants (used for 512KB ECUFlash-style extracts)
CAL_PAGE_SIZE        = 0x10000
CAL_PAGE_OFFSET_512K = 0x70000   # last 64KB of a 512KB extract
CAL_PAGE_OFFSET_256K = 0x30000   # last 64KB of a 256KB ROM
CAL_PAGE_OFFSET_1MB  = 0xF0000   # last 64KB of the 1MB flash


@dataclass
class ROMImage:
    """
    A loaded ME7.x ROM binary.

    Usage:
        rom = ROMImage.load("my_awp.bin")
        print(rom.size_kb, "KB")
        print(rom.variant)          # detected from content
        data = rom.read(0x1234, 2)  # read 2 bytes at file offset
        rom.write(0x1234, b'\\xAB\\xCD')
        rom.save("modified.bin")
    """

    data:      bytearray
    path:      Optional[str] = None
    _modified: bool = field(default=False, repr=False, compare=False)

    # ── Factory methods ────────────────────────────────────────────────────────

    @classmethod
    def load(cls, path: str) -> "ROMImage":
        """
        Load a ROM from a .bin file. Validates size.

        Accepted sizes:
          1 MB  — full ME7.5 flash chip dump (native format)
          512 KB — ECUFlash / WinOLS extracted calibration region
          256 KB — ME7.1 variants
        """
        with open(path, "rb") as f:
            raw = f.read()
        size = len(raw)

        if size not in VALID_SIZES:
            raise ValueError(
                f"Unexpected ROM size: 0x{size:X} bytes ({size // 1024} KB). "
                f"Expected one of: {', '.join(VALID_SIZES.values())}"
            )

        return cls(data=bytearray(raw), path=path)

    @classmethod
    def from_bytes(cls, data: bytes | bytearray) -> "ROMImage":
        """Create from raw bytes (e.g. from SGO extraction). Validates size."""
        ba = bytearray(data)
        if len(ba) not in VALID_SIZES:
            raise ValueError(
                f"Unexpected ROM size: 0x{len(ba):X} bytes ({len(ba)//1024} KB). "
                f"Expected one of: {', '.join(VALID_SIZES.values())}"
            )
        return cls(data=ba, path=None)

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self.data)

    @property
    def size_kb(self) -> int:
        return self.size // 1024

    @property
    def is_1mb(self) -> bool:
        return self.size == 0x100000

    @property
    def is_512k(self) -> bool:
        """True for ECUFlash-style 512KB extracted cal regions."""
        return self.size == 0x80000

    @property
    def is_256k(self) -> bool:
        return self.size == 0x40000

    @property
    def cal_page_offset(self) -> int:
        """File offset where the 64KB calibration page begins."""
        if self.is_1mb:
            return CAL_PAGE_OFFSET_1MB   # last 64KB of the 1MB flash
        if self.is_512k:
            return CAL_PAGE_OFFSET_512K  # last 64KB of a 512KB extract
        if self.is_256k:
            return CAL_PAGE_OFFSET_256K
        return self.size - CAL_PAGE_SIZE

    @property
    def cal_page(self) -> memoryview:
        """Read-only view of the calibration page."""
        off = self.cal_page_offset
        return memoryview(self.data)[off : off + CAL_PAGE_SIZE]

    @property
    def is_modified(self) -> bool:
        return self._modified

    # ── Read / write ───────────────────────────────────────────────────────────

    def read(self, offset: int, length: int) -> bytes:
        """Read bytes at file offset."""
        return bytes(self.data[offset : offset + length])

    def read_u8(self, offset: int) -> int:
        return self.data[offset]

    def read_u16_be(self, offset: int) -> int:
        return (self.data[offset] << 8) | self.data[offset + 1]

    def read_u16_le(self, offset: int) -> int:
        return self.data[offset] | (self.data[offset + 1] << 8)

    def read_u32_le(self, offset: int) -> int:
        d = self.data
        return d[offset] | (d[offset+1] << 8) | (d[offset+2] << 16) | (d[offset+3] << 24)

    def read_u32_be(self, offset: int) -> int:
        d = self.data
        return (d[offset] << 24) | (d[offset+1] << 16) | (d[offset+2] << 8) | d[offset+3]

    def write(self, offset: int, data: bytes | bytearray) -> None:
        """Write bytes at file offset. Marks ROM as modified."""
        end = offset + len(data)
        if end > self.size:
            raise ValueError(f"Write at 0x{offset:X}+{len(data)} exceeds ROM size 0x{self.size:X}")
        self.data[offset:end] = data
        self._modified = True

    def write_u16_be(self, offset: int, value: int) -> None:
        self.write(offset, bytes([(value >> 8) & 0xFF, value & 0xFF]))

    def write_u16_le(self, offset: int, value: int) -> None:
        self.write(offset, bytes([value & 0xFF, (value >> 8) & 0xFF]))

    def write_u32_le(self, offset: int, value: int) -> None:
        self.write(offset, bytes([
             value & 0xFF,        (value >>  8) & 0xFF,
            (value >> 16) & 0xFF, (value >> 24) & 0xFF,
        ]))

    def write_u32_be(self, offset: int, value: int) -> None:
        self.write(offset, bytes([
            (value >> 24) & 0xFF, (value >> 16) & 0xFF,
            (value >>  8) & 0xFF,  value & 0xFF,
        ]))

    # ── Save ───────────────────────────────────────────────────────────────────

    def save(self, path: Optional[str] = None) -> str:
        """Save ROM to path. Returns path written."""
        out = path or self.path
        if out is None:
            raise ValueError("No output path specified")
        with open(out, "wb") as f:
            f.write(self.data)
        self._modified = False
        return out

    def save_as(self, path: str) -> str:
        """Save to a new path (leaves self.path unchanged)."""
        with open(path, "wb") as f:
            f.write(self.data)
        return path

    # ── Utilities ──────────────────────────────────────────────────────────────

    def snapshot(self) -> bytearray:
        """Return a copy of the current data."""
        return bytearray(self.data)

    def hexdump(self, offset: int, length: int = 16) -> str:
        """Return a hexdump string for debugging."""
        chunk = self.data[offset : offset + length]
        hex_part = " ".join(f"{b:02X}" for b in chunk)
        asc_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
        return f"  {offset:06X}:  {hex_part:<48}  {asc_part}"

    def __repr__(self) -> str:
        name = os.path.basename(self.path) if self.path else "<memory>"
        mod = " [modified]" if self._modified else ""
        return f"ROMImage({name!r}, {self.size_kb} KB{mod})"
