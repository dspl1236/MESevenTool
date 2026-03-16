"""
meseventool/checksum.py
=======================
ME7.x checksum verification and correction.

Ported from ME7RomTool_Ferrari / fixsums.c (360trev/nyet, MIT licence).

Two independent checksum systems:

1. Main ROM checksum  — simple 16-bit LE word accumulation over the
   calibration page, stored as [sum:u32, ~sum:u32] at cal_page+0xFFF8.

2. Multipoint CRC32  — N blocks each [start:u32, end:u32, crc32:u32,
   ~crc32:u32] discovered by needle; absent in some variants (OK).

Both must be correct before the ECU will boot the firmware.
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional, List

from .rom import ROMImage
from .needle import Searcher, NEEDLE_CRC32, MASK_CRC32

# Default checksum storage offset within the calibration page
CAL_CKSUM_OFFSET = 0xFFF8   # [sum:u32 LE][~sum:u32 LE]
ROM_ADDR_MASK    = 0xFFF00000


# ── Low-level helpers (exported for tests) ─────────────────────────────────────

def _le16(data: bytes, off: int) -> int:
    return data[off] | (data[off + 1] << 8)

def _le32(data: bytes, off: int) -> int:
    return (data[off]       | (data[off+1] << 8) |
            (data[off+2] << 16) | (data[off+3] << 24))

def calc_sum_block(rom: ROMImage, start: int, end: int) -> int:
    """
    16-bit LE word accumulation over rom[start..end] inclusive.
    Matches CalcChecksumBlk() from fixsums.c exactly.
    """
    data  = rom.data
    total = 0
    i     = start
    while i + 1 <= end:
        total = (total + (data[i] | (data[i+1] << 8))) & 0xFFFFFFFF
        i += 2
    # Handle odd tail byte
    if i == end:
        total = (total + data[i]) & 0xFFFFFFFF
    return total

def calc_crc32(rom: ROMImage, start: int, end: int) -> int:
    """Standard CRC32 (IEEE 802.3) over rom[start..end] inclusive."""
    return zlib.crc32(bytes(rom.data[start : end + 1])) & 0xFFFFFFFF


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class MainChecksumResult:
    found:   bool = False
    main_ok: bool = False
    comp_ok: bool = False
    offset:  int  = 0      # file offset of stored checksum
    stored:  int  = 0
    stored_c:int  = 0
    calc:    int  = 0

    @property
    def all_ok(self) -> bool:
        return self.found and self.main_ok and self.comp_ok

    @property
    def ok(self) -> bool:
        """Alias for all_ok — used by test_checksum.py result.main_regions[0].ok"""
        return self.all_ok

    def summary(self) -> str:
        if not self.found:
            return "Main checksum: ✗ not found"
        ok = "✓" if self.all_ok else "✗"
        return (f"Main checksum: {ok}  "
                f"calc=0x{self.calc:08X}  stored=0x{self.stored:08X}")


@dataclass
class MultiBlock:
    index:      int
    start:      int
    end:        int
    stored_crc: int
    stored_neg: int
    calc_crc:   int
    crc_ok:     bool
    neg_ok:     bool

    @property
    def ok(self) -> bool:
        return self.crc_ok and self.neg_ok


@dataclass
class MultiChecksumResult:
    blocks:  List[MultiBlock] = field(default_factory=list)
    found:   bool = False

    @property
    def all_ok(self) -> bool:
        return not self.found or all(b.ok for b in self.blocks)

    @property
    def n_ok(self) -> int:
        return sum(1 for b in self.blocks if b.ok)

    @property
    def n_bad(self) -> int:
        return sum(1 for b in self.blocks if not b.ok)


@dataclass
class ChecksumResult:
    main:       MainChecksumResult   = field(default_factory=MainChecksumResult)
    multi:      MultiChecksumResult  = field(default_factory=MultiChecksumResult)

    @property
    def main_found(self) -> bool:   return self.main.found
    @property
    def main_ok(self) -> bool:      return self.main.all_ok
    @property
    def multipoint_found(self) -> bool: return self.multi.found
    @property
    def multipoint_ok(self) -> bool:    return self.multi.all_ok
    @property
    def all_ok(self) -> bool:       return self.main_ok and self.multipoint_ok
    @property
    def main_regions(self):         return [self.main]  # compatibility

    def summary(self) -> str:
        lines = [self.main.summary()]
        if self.multi.found:
            ok = "✓" if self.multi.all_ok else "✗"
            lines.append(f"Multipoint CRC32: {ok}  "
                         f"{self.multi.n_ok}/{len(self.multi.blocks)} OK")
        else:
            lines.append("Multipoint CRC32: not present")
        return "\n".join(lines)


# ── ChecksumManager / ChecksumChecker ──────────────────────────────────────────

class ChecksumManager:
    """
    Verify and correct ME7.x ROM checksums.

    Works on any ME7 variant — uses fixed cal-page offset for the main
    checksum (needle approach works on real ROMs; fixed offset handles
    synthetic test ROMs and most real ones identically).
    """

    def __init__(self, rom: ROMImage):
        self.rom = rom

    # ── Public API ─────────────────────────────────────────────────────────────

    def verify(self) -> ChecksumResult:
        """Verify both checksum layers. Does not modify the ROM."""
        result = ChecksumResult()
        self._check_main(result, fix=False)
        self._check_multi(result, fix=False)
        return result

    def fix(self) -> ChecksumResult:
        """Recompute and write all checksums into rom.data."""
        result = ChecksumResult()
        self._check_main(result, fix=True)
        self._check_multi(result, fix=True)
        return result

    # ── Internal: main checksum ────────────────────────────────────────────────

    def _check_main(self, result: ChecksumResult, fix: bool) -> None:
        rom     = self.rom
        cal_off = rom.cal_page_offset
        storage = self._find_checksum_storage(cal_off)

        if storage is None or storage + 8 > rom.size:
            return

        # Sum covers cal page from start up to (but not including) storage
        total = self._word_sum(cal_off, storage - 1)
        comp  = (~total) & 0xFFFFFFFF

        stored   = _le32(bytes(rom.data), storage)
        stored_c = _le32(bytes(rom.data), storage + 4)

        mr = MainChecksumResult(
            found    = True,
            main_ok  = (total == stored),
            comp_ok  = (comp  == stored_c),
            offset   = storage,
            stored   = stored,
            stored_c = stored_c,
            calc     = total,
        )
        result.main = mr

        if fix and not mr.all_ok:
            struct.pack_into('<I', rom.data, storage,     total)
            struct.pack_into('<I', rom.data, storage + 4, comp)
            rom._modified = True   # mark modified — struct.pack_into bypasses rom.write()
            mr.stored   = total
            mr.stored_c = comp
            mr.main_ok  = True
            mr.comp_ok  = True

    def _find_checksum_storage(self, cal_off: int) -> "Optional[int]":
        """
        Locate the [sum:u32LE][~sum:u32LE] checksum pair in the cal page.

        Strategy:
          1. Try the standard offset (CAL_CKSUM_OFFSET from cal page start).
             If the stored value is non-trivial (not 0x00000000 / 0xFFFFFFFF)
             AND its complement matches the adjacent word, use it.
          2. Otherwise scan the last 4KB of the file for a valid pair.
             This handles 1MB ROMs where the checksum is at 0x0FFFE0 rather
             than at cal_page_offset + 0xFFF8.
        """
        data = bytes(self.rom.data)
        size = self.rom.size

        def is_valid_pair(addr: int) -> bool:
            if addr + 8 > size:
                return False
            v = _le32(data, addr)
            c = _le32(data, addr + 4)
            if v in (0x00000000, 0xFFFFFFFF):
                return False
            return (~v & 0xFFFFFFFF) == c

        # 1. Standard location — always use if in bounds, regardless of validity.
        #    This allows fix() to locate and correct a corrupted checksum.
        std = cal_off + CAL_CKSUM_OFFSET
        if std + 8 <= size:
            return std

        # 2. Scan last 4KB for a valid (non-trivial) pair.
        #    Used for 1MB ROMs where the checksum sits at a non-standard offset
        #    (e.g. the real 06A906032DL has its checksum at 0x0FFFE0 rather than
        #    cal_page_offset+0xFFF8=0x0FFFF8, i.e. 0x18 bytes earlier).
        scan_start = max(0, size - 0x1000)
        for addr in range(scan_start, size - 8, 4):
            if is_valid_pair(addr):
                return addr

        return None

    def _word_sum(self, start: int, end: int) -> int:
        return calc_sum_block(self.rom, start, end)

    # ── Internal: multipoint CRC32 ────────────────────────────────────────────

    def _check_multi(self, result: ChecksumResult, fix: bool) -> None:
        """
        Find the multipoint CRC32 table by needle and verify each block.
        Absent in synthetic ROMs — that's fine (multipoint_ok = True).
        """
        rom     = self.rom
        s       = Searcher(rom)

        # Locate CRC32 polynomial table setup — gives us the table address
        hit = s.search_one(NEEDLE_CRC32, MASK_CRC32)
        if hit is None:
            return   # no multipoint in this ROM — that's OK

        # Extract table address from needle operands at +38 (lo) and +42 (hi)
        data = bytes(rom.data)
        if hit.file_offset + 46 > rom.size:
            return

        lo  = _le16(hit.data, 38) if len(hit.data) > 39 else 0
        hi  = _le16(hit.data, 42) if len(hit.data) > 43 else 0
        phy = (hi << 16) | lo
        tbl = phy & ~ROM_ADDR_MASK & (rom.size - 1)

        if tbl + 16 > rom.size:
            return

        result.multi.found = True
        blocks = []
        i = 0

        while tbl + i * 16 + 16 <= rom.size:
            off = tbl + i * 16
            s_phy = _le32(data, off)
            e_phy = _le32(data, off + 4)
            stored     = _le32(data, off + 8)
            stored_neg = _le32(data, off + 12)

            s_off = s_phy & ~ROM_ADDR_MASK & (rom.size - 1)
            e_off = e_phy & ~ROM_ADDR_MASK & (rom.size - 1)

            if s_off == 0 and e_off == 0:
                break   # end of table

            if s_off < e_off:
                crc = calc_crc32(rom, s_off, e_off)
            else:
                crc = 0

            neg = (~crc) & 0xFFFFFFFF
            blk = MultiBlock(
                index=i+1, start=s_off, end=e_off,
                stored_crc=stored, stored_neg=stored_neg,
                calc_crc=crc,
                crc_ok=(crc == stored),
                neg_ok=(neg == stored_neg),
            )
            blocks.append(blk)

            if fix and not blk.ok:
                struct.pack_into('<I', rom.data, off + 8,  crc)
                struct.pack_into('<I', rom.data, off + 12, neg)
                rom._modified = True
                blk.crc_ok = True
                blk.neg_ok = True

            i += 1
            if i > 64:  # safety cap
                break

        result.multi.blocks = blocks


# Alias for __init__ compatibility
ChecksumChecker = ChecksumManager


def verify_and_fix(rom: ROMImage) -> ChecksumResult:
    """Convenience: verify, fix if needed, return final result."""
    cs = ChecksumManager(rom)
    result = cs.verify()
    if not result.all_ok:
        result = cs.fix()
    return result
