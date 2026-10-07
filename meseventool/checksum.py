"""
meseventool/checksum.py
=======================
ME7.x checksum verification and correction.

Three independent layers, every one located by machine-code needles so the
tool never guesses a storage address.  If a needle is missing, the layer is
reported as not verified and is never written.

1. Main checksum  (me7romtool ``fixsums.c``)
   N regions (1-3, usually 2) summed as little-endian 16-bit words into a
   32-bit accumulator; stored as ``[sum:u32][~sum:u32]``.  On a 1 MB ME7.5
   image the regions are ``0x00000-0x0FBFF`` and ``0x20000-0xFFFFF`` and the
   pair lives at ``0xFFFE0``.  The second region contains the stored pair
   itself: that works because ``lo(x)+hi(x)+lo(~x)+hi(~x)`` is a constant.

2. Multipoint block sums  (``fixsums.c``)
   A table of ``[start:u32][end:u32][sum:u32][~sum:u32]`` entries, same word
   sum as layer 1 (NOT CRC32).  66 entries on ME7.5, stepping through the
   image in 16 KB blocks.  One block covers the table itself and others
   cover layer-3 storage, so the fix loop iterates until stable.

3. Main CRC32  (``ME7Sum``: ``FindMainCRC*`` / ``DoMainCRCs``)
   Up to four code/data regions CRC32'd (reflected, poly 0xEDB88320, zlib
   semantics) and compared with three constants embedded in the verify
   routine.  The CRCs are *chained*: a short pre-block seeds region 1, and
   each region's result seeds the next.  When four regions exist, region 3
   has no stored value and region 4 is compared against the third constant.
   This layer is absent on some ROMs (e.g. 4B0906018CM), which is normal.

Fix order is CRC32 -> multipoint -> main, because the main regions contain
the CRC constants and a multipoint block contains them too.

Validated byte-for-byte against 06A906032RN, 4B0906018CM and 06A906032HN
(before/after ``me7sum``).  See ``docs/checksum_port_handoff.md``.
"""

from __future__ import annotations

import re
import struct
import sys
import zlib
from array import array
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .rom import ROMImage

# C167 physical base of the flash on ME7.5.  File offset = phys & (size-1).
ROM_PHYS_BASE = 0x800000


# ── Low-level helpers (exported for tests) ─────────────────────────────────────

def _le16(data: bytes, off: int) -> int:
    return data[off] | (data[off + 1] << 8)


def _le32(data: bytes, off: int) -> int:
    return struct.unpack_from('<I', data, off)[0]


def _word_sum_bytes(data: bytes, start: int, end: int) -> int:
    """
    CalcChecksumBlk() from fixsums.c: sum of LE16 words from the word
    containing ``start`` through the word containing ``end`` (inclusive),
    mod 2**32.
    """
    if start > end:
        return 0
    first = (start // 2) * 2
    last  = (end // 2) * 2 + 2          # exclusive byte bound
    last  = min(last, len(data) & ~1)
    if last <= first:
        return 0
    words = array('H', bytes(data[first:last]))
    if sys.byteorder == 'big':
        words.byteswap()
    return sum(words) & 0xFFFFFFFF


def calc_sum_block(rom: ROMImage, start: int, end: int) -> int:
    """16-bit LE word sum over rom[start..end] inclusive (fixsums.c)."""
    return _word_sum_bytes(rom.data, start, end)


def calc_crc32(rom: ROMImage, start: int, end: int, seed: int = 0) -> int:
    """
    CRC32 (reflected, poly 0xEDB88320, init/xorout 0xFFFFFFFF) over
    rom[start..end] inclusive.  ``seed`` is a previous result, which chains
    the way ME7Sum's ``crc32(seed, ...)`` does.
    """
    if start > end:
        return seed & 0xFFFFFFFF
    return zlib.crc32(bytes(rom.data[start:end + 1]), seed) & 0xFFFFFFFF


# ── Masked needle search ───────────────────────────────────────────────────────

def _compile_needle(needle: Sequence[int], mask: Sequence[int]) -> "re.Pattern[bytes]":
    """Build a regex equivalent to the masked byte match ((b & m) == (n & m))."""
    assert len(needle) == len(mask)
    parts: List[bytes] = []
    for n, m in zip(needle, mask):
        if m == 0:
            parts.append(b'.')
        elif m == 0xFF:
            parts.append(re.escape(bytes([n])))
        else:
            allowed = bytes(b for b in range(256) if (b & m) == (n & m))
            parts.append(b'[' + re.escape(allowed) + b']')
    return re.compile(b''.join(parts), re.DOTALL)


def _find_all(data: bytes, needle: Sequence[int], mask: Sequence[int],
              step: int = 1) -> List[int]:
    """All match offsets (overlapping allowed).  ``step=2`` keeps word alignment."""
    pat = _compile_needle(needle, mask)
    hits: List[int] = []
    pos = 0
    while True:
        m = pat.search(data, pos)
        if not m:
            break
        if step == 1 or m.start() % step == 0:
            hits.append(m.start())
        pos = m.start() + 1
    return hits


# ── Needles ────────────────────────────────────────────────────────────────────
# me7romtool needles.c (layers 1-2).  X = wildcard byte.
X = 0x00
_M = 0xFF

# needle_2b: region count, byte at +27 (0xA2 -> 1, 0xA4 -> 2, 0xA6 -> 3)
NEEDLE_MAIN_COUNT = [
    0x88, 0x90, 0x88, 0x80, 0x88, 0x70, 0x88, 0x60, 0xDA, X, X, X,
    0xF3, 0xF8, X, X, 0x49, 0x81, 0xEA, 0x30, X, X, 0xF3, 0xFA, X, X,
    0x49, X, 0x9D, 0x27, 0xF2, 0xF8, X, X, 0xF2, 0xF9, X, X, 0xE0, 0x07,
    0x0D, 0x0A]
MASK_MAIN_COUNT = [
    _M, _M, _M, _M, _M, _M, _M, _M, _M, X, X, X,
    _M, _M, X, X, _M, _M, _M, _M, X, X, _M, _M, X, X,
    _M, X, _M, _M, _M, _M, X, X, _M, _M, X, X, _M, _M,
    _M, _M]
MAIN_COUNT_BYTE = 27
MAIN_COUNT_CODES = {0xA2: 1, 0xA4: 2, 0xA6: 3}

# needle_2: region start/end tables.  page +14; start lo +18, hi +22;
# end lo +44, hi +48.  Entries are 8 bytes apart.
NEEDLE_MAIN_REGIONS = [
    0xF6, 0x8E, X, X, 0xF6, 0x8E, X, X, 0xF7, 0x8E, X, X, 0xD7, 0x50, X, X,
    0xF2, X, X, X, 0xF2, X, X, X, 0xF6, X, X, X, 0xF6, X, X, X, 0xE1, 0x18,
    0xF7, X, X, X, 0xD7, 0x50, X, X, 0xF2, X, X, X, 0xF2, X, X, X,
    0xF6, X, X, X, 0xF6, X, X, X, 0xDB, 0x00]
MASK_MAIN_REGIONS = [
    _M, _M, X, X, _M, _M, X, X, _M, _M, X, X, _M, _M, X, X,
    _M, X, X, X, _M, X, X, X, _M, X, X, X, _M, X, X, X, _M, _M,
    _M, X, X, X, _M, _M, X, X, _M, X, X, X, _M, X, X, X,
    _M, X, X, X, _M, X, X, X, _M, _M]
MAIN_REGIONS_PAGE, MAIN_REGIONS_SLO, MAIN_REGIONS_SHI = 14, 18, 22
MAIN_REGIONS_ELO, MAIN_REGIONS_EHI = 44, 48
MAIN_REGION_STRIDE = 8

# needle_3: stored main checksum pair.  page +10, offset +14.
NEEDLE_MAIN_STORE = [
    0xF2, 0xF4, X, X, 0xF2, 0xF5, X, X, 0xD7, 0x50, X, X, 0x22, 0xF4, X, X,
    0x32, 0xF5, X, X, 0x3D, X, 0xE6, 0xF4, X, X, 0xE6, 0xF5, X, X, 0xDC, 0x45,
    0xA9, 0x64, 0x77, 0xF6, 0x08, 0x00, 0xE6, 0xF4, X, X, 0xE6, 0xF5, X, X,
    0xDC, 0x45, 0xB9, 0x64, 0x0D, 0x0E]
MASK_MAIN_STORE = [
    _M, _M, X, X, _M, _M, X, X, _M, _M, X, X, _M, _M, X, X,
    _M, _M, X, X, _M, X, _M, _M, X, X, _M, _M, X, X, _M, _M,
    _M, _M, _M, _M, _M, _M, _M, _M, X, X, _M, _M, X, X,
    _M, _M, _M, _M, _M, _M]
MAIN_STORE_PAGE, MAIN_STORE_OFF = 10, 14

# needle_4b: multipoint block count, u16 at +42.  Fallback needle_4c: +44.
NEEDLE_MULTI_COUNT = [
    0x98, 0x4A, 0xA8, 0x5A, 0xF6, 0xF4, X, X, 0xF6, 0xF5, X, X, 0xF6, 0x8E, X, X,
    0xF6, 0x8E, X, X, 0xF2, 0xF2, X, X, 0x66, 0xF2, 0xFF, 0x47, 0x76, 0xF2, 0xFF, 0x40,
    0xF6, 0xF2, X, X, 0xF2, 0xF4, X, X, 0x46, 0xF4, X, X, 0xEA, 0x90, X, X]
MASK_MULTI_COUNT = [
    _M, _M, _M, _M, _M, _M, X, X, _M, _M, X, X, _M, _M, X, X,
    _M, _M, X, X, _M, _M, X, X, _M, _M, _M, _M, _M, _M, _M, _M,
    _M, _M, X, X, _M, _M, X, X, _M, _M, X, X, _M, _M, X, X]
MULTI_COUNT_OFF = 42
NEEDLE_MULTI_COUNT_ALT = [
    0xF3, 0xF8, X, X, 0x43, 0xF8, X, X, 0xEA, 0x30, X, X, 0xF3, 0xFA, X, X,
    0x49, 0xA1, 0xEA, 0x20, X, X, 0xF7, 0x8F, X, X, 0x46, 0xF6, 0x00, 0x10,
    0xEA, 0x30, X, X, 0xF2, 0xF6, X, X, 0x66, 0xF6, 0xFF, 0x00, 0x46, 0xF6, X, X,
    0xEA, 0xE0, X, X, 0xF0, 0x46]
MASK_MULTI_COUNT_ALT = [
    _M, _M, X, X, _M, _M, X, X, _M, _M, X, X, _M, _M, X, X,
    _M, _M, _M, _M, X, X, _M, _M, X, X, _M, _M, _M, _M,
    _M, _M, X, X, _M, _M, X, X, _M, _M, _M, _M, _M, _M, X, X,
    _M, _M, X, X, _M, _M]
MULTI_COUNT_ALT_OFF = 44

# needle_4: multipoint table.  page +58, offset +54.
NEEDLE_MULTI_TABLE = [
    0x98, 0x24, 0xA8, 0x34, 0x00, 0xA2, 0x10, 0xB3, 0x26, 0xFA, 0xFF, 0xFF,
    0x36, 0xFB, 0xFF, 0xFF, 0x3D, 0x08, 0xE6, 0xF4, X, X, 0xE0, 0x05,
    0xF6, 0xF4, X, X, 0xF6, 0xF5, X, X, 0xDB, 0x00, 0xE6, 0xF4, X, X,
    0xE6, 0xF5, X, X, 0xF6, 0xF4, X, X, 0xF6, 0xF5, X, X, 0xDB, 0x00,
    0xE6, 0xF4, X, X, 0xE6, 0xF5, X, X, 0xF6, 0xF4, X, X, 0xF6, 0xF5, X, X,
    0xDB, 0x00]
MASK_MULTI_TABLE = [
    _M, _M, _M, _M, _M, _M, _M, _M, _M, _M, _M, _M,
    _M, _M, _M, _M, _M, _M, _M, _M, X, X, _M, _M,
    _M, _M, X, X, _M, _M, X, X, _M, _M, _M, _M, X, X,
    _M, _M, X, X, _M, _M, X, X, _M, _M, X, X, _M, _M,
    _M, _M, X, X, _M, _M, X, X, _M, _M, X, X, _M, _M, X, X,
    _M, _M]
MULTI_TABLE_OFF, MULTI_TABLE_PAGE = 54, 58
MULTI_ENTRY_SIZE = 16

# ME7Sum needles (layer 3).  Operands are decoded FindData-style: a u16 low
# word and a u16 high word; high<<16 unless it looks like a page (>=0x200),
# then high<<14.  Offsets below are byte offsets into the hit.
NEEDLE_CRC_PRE = [0xE6, 0xFC, X, X, 0xE6, 0xFD, 0x80, 0x00, 0xE0, 0x0E,
                  0xDA, X, X, X, 0xF6, 0xF4]
MASK_CRC_PRE   = [_M, _M, X, X, _M, _M, 0xF0, _M, _M, 0x0F,
                  _M, X, X, X, _M, _M]
CRC_PRE_LO, CRC_PRE_HI, CRC_PRE_LEN_BYTE = 2, 6, 9

NEEDLE_CRC_START = [0xE6, 0xF8, X, X, 0xE6, 0xF9, 0x80, 0x00, 0xF2, 0xF4]
MASK_CRC_START   = [_M, _M, X, X, _M, _M, 0xF0, _M, _M, _M]
CRC_START_LO, CRC_START_HI = 2, 6

NEEDLE_CRC_END = [0x10, 0x9B, 0xE6, 0xF4, X, X, 0xE6, 0xF5, 0x80, 0x00]
MASK_CRC_END   = [_M, _M, _M, _M, X, X, _M, _M, 0xF0, _M]
CRC_END_LO, CRC_END_HI = 4, 8

NEEDLE_CRC_STORE = [0xF6, 0xF5, X, X, 0xE6, 0xF4, X, X, 0xE6, 0xF5, 0x80, 0x00,
                    0xDA, 0x00]
MASK_CRC_STORE   = [_M, _M, X, X, _M, _M, 0x01, X, _M, _M, 0xF0, _M,
                    _M, _M]
CRC_STORE_LO, CRC_STORE_HI = 6, 10
MAX_CRC_BLOCKS = 4


# ── Result dataclasses ─────────────────────────────────────────────────────────

@dataclass
class MainChecksumResult:
    found:    bool = False
    main_ok:  bool = False
    comp_ok:  bool = False
    offset:   int  = 0          # file offset of [sum][~sum]
    stored:   int  = 0
    stored_c: int  = 0
    calc:     int  = 0
    regions:  List[Tuple[int, int]] = field(default_factory=list)  # inclusive file ranges
    note:     str  = ""         # why it was not found

    @property
    def all_ok(self) -> bool:
        return self.found and self.main_ok and self.comp_ok

    @property
    def ok(self) -> bool:
        return self.all_ok

    def summary(self) -> str:
        if not self.found:
            return f"Main checksum: ✗ not verified ({self.note or 'needle missing'})"
        ok = "✓" if self.all_ok else "✗"
        return (f"Main checksum: {ok}  calc=0x{self.calc:08X}  "
                f"stored=0x{self.stored:08X} @0x{self.offset:05X}")


@dataclass
class MultiBlock:
    index:      int
    start:      int
    end:        int
    stored_crc: int          # historical name: this is a word sum, not a CRC
    stored_neg: int
    calc_crc:   int
    crc_ok:     bool
    neg_ok:     bool

    @property
    def ok(self) -> bool:
        return self.crc_ok and self.neg_ok

    # Clearer aliases
    @property
    def stored_sum(self) -> int:
        return self.stored_crc

    @property
    def calc_sum(self) -> int:
        return self.calc_crc


@dataclass
class MultiChecksumResult:
    blocks:       List[MultiBlock] = field(default_factory=list)
    found:        bool = False
    table_offset: int  = 0
    count:        int  = 0
    note:         str  = ""     # set when detection was partial/inconsistent

    @property
    def all_ok(self) -> bool:
        if not self.found:
            return not self.note        # absent is fine; half-found is not
        return all(b.ok for b in self.blocks)

    @property
    def n_ok(self) -> int:
        return sum(1 for b in self.blocks if b.ok)

    @property
    def n_bad(self) -> int:
        return sum(1 for b in self.blocks if not b.ok)

    def summary(self) -> str:
        if not self.found:
            return ("Multipoint sums: not present" if not self.note
                    else f"Multipoint sums: ✗ not verified ({self.note})")
        ok = "✓" if self.all_ok else "✗"
        return (f"Multipoint sums: {ok}  {self.n_ok}/{len(self.blocks)} OK  "
                f"table @0x{self.table_offset:05X}")


@dataclass
class CrcBlock:
    index:  int
    start:  int
    end:    int                      # inclusive
    calc:   int
    offset: Optional[int] = None     # file offset of the stored u32, None = not stored
    stored: Optional[int] = None

    @property
    def ok(self) -> bool:
        return self.offset is None or self.stored == self.calc


@dataclass
class CrcChecksumResult:
    blocks:    List[CrcBlock] = field(default_factory=list)
    found:     bool = False
    pre_block: Optional[Tuple[int, int]] = None
    note:      str  = ""

    @property
    def all_ok(self) -> bool:
        if not self.found:
            return not self.note
        return all(b.ok for b in self.blocks)

    @property
    def n_ok(self) -> int:
        return sum(1 for b in self.blocks if b.offset is not None and b.ok)

    @property
    def n_bad(self) -> int:
        return sum(1 for b in self.blocks if not b.ok)

    def summary(self) -> str:
        if not self.found:
            return ("Main CRC32: not present" if not self.note
                    else f"Main CRC32: ✗ not verified ({self.note})")
        ok = "✓" if self.all_ok else "✗"
        n = sum(1 for b in self.blocks if b.offset is not None)
        return f"Main CRC32: {ok}  {self.n_ok}/{n} OK"


@dataclass
class ChecksumResult:
    main:  MainChecksumResult  = field(default_factory=MainChecksumResult)
    multi: MultiChecksumResult = field(default_factory=MultiChecksumResult)
    crc:   CrcChecksumResult   = field(default_factory=CrcChecksumResult)

    @property
    def main_found(self) -> bool:       return self.main.found
    @property
    def main_ok(self) -> bool:          return self.main.all_ok
    @property
    def multipoint_found(self) -> bool: return self.multi.found
    @property
    def multipoint_ok(self) -> bool:    return self.multi.all_ok
    @property
    def crc_found(self) -> bool:        return self.crc.found
    @property
    def crc_ok(self) -> bool:           return self.crc.all_ok
    @property
    def all_ok(self) -> bool:
        return self.main.all_ok and self.multi.all_ok and self.crc.all_ok
    @property
    def main_regions(self):             return [self.main]   # compatibility

    def summary(self) -> str:
        return "\n".join([self.main.summary(), self.multi.summary(),
                          self.crc.summary()])


# ── Layout (where things are) ──────────────────────────────────────────────────

@dataclass
class _MainLayout:
    regions: List[Tuple[int, int]]
    store:   int


@dataclass
class _MultiLayout:
    table: int
    count: int


@dataclass
class _CrcLayout:
    pre:     Optional[Tuple[int, int]]
    regions: List[Tuple[int, int]]
    stores:  List[Optional[int]]      # per region; None = no stored value


class ChecksumManager:
    """Verify and correct all three ME7.x checksum layers of a ROMImage."""

    def __init__(self, rom: ROMImage):
        self.rom = rom

    # ── Public API ─────────────────────────────────────────────────────────────

    def verify(self) -> ChecksumResult:
        """Verify every layer.  Does not modify the ROM."""
        data = bytes(self.rom.data)
        result = ChecksumResult()
        result.crc   = self._verify_crc(data)
        result.multi = self._verify_multi(data)
        result.main  = self._verify_main(data)
        return result

    def fix(self) -> ChecksumResult:
        """
        Recompute and write every layer whose storage was located, in the
        order CRC32 -> multipoint -> main, then return a fresh verify().
        Layers whose needles are missing are left untouched.
        """
        self._fix_crc()
        self._fix_multi()
        self._fix_main()
        return self.verify()

    # ── Address helpers ────────────────────────────────────────────────────────

    def _page_off_to_file(self, page: int, off: int) -> int:
        return ((page * 0x4000) + (off & 0x3FFF)) & 0xFFFFF & (self.rom.size - 1)

    def _phys_to_file(self, phys: int) -> int:
        return phys & 0xFFFFF & (self.rom.size - 1)

    def _decode_lohi(self, data: bytes, lo_at: int, hi_at: int) -> Optional[int]:
        """ME7Sum FindData() operand decode -> file offset, or None if out of range."""
        lo, hi = _le16(data, lo_at), _le16(data, hi_at)
        shift = 14 if hi & 0xFE00 else 16
        phys = (hi << shift) | lo
        if not (ROM_PHYS_BASE < phys < ROM_PHYS_BASE + 0x100000):
            return None
        f = self._phys_to_file(phys)
        return f if f < self.rom.size else None

    # ── Layer 1: main checksum ─────────────────────────────────────────────────

    def _locate_main(self, data: bytes) -> Tuple[Optional[_MainLayout], str]:
        size = self.rom.size
        hits = _find_all(data, NEEDLE_MAIN_COUNT, MASK_MAIN_COUNT)
        if len(hits) != 1:
            return None, f"region-count needle: {len(hits)} hits"
        nreg = MAIN_COUNT_CODES.get(data[hits[0] + MAIN_COUNT_BYTE], 0)
        if not nreg:
            return None, "region-count byte unrecognised"

        hits = _find_all(data, NEEDLE_MAIN_REGIONS, MASK_MAIN_REGIONS)
        if len(hits) != 1:
            return None, f"region-table needle: {len(hits)} hits"
        a = hits[0]
        page = _le16(data, a + MAIN_REGIONS_PAGE)
        slo = self._page_off_to_file(page, _le16(data, a + MAIN_REGIONS_SLO))
        shi = self._page_off_to_file(page, _le16(data, a + MAIN_REGIONS_SHI))
        elo = self._page_off_to_file(page, _le16(data, a + MAIN_REGIONS_ELO))
        ehi = self._page_off_to_file(page, _le16(data, a + MAIN_REGIONS_EHI))
        regions: List[Tuple[int, int]] = []
        for i in range(nreg):
            k = i * MAIN_REGION_STRIDE
            if max(shi, ehi) + k + 2 > size:
                return None, "region table out of range"
            s = self._phys_to_file(_le16(data, shi + k) << 16 | _le16(data, slo + k))
            e = self._phys_to_file(_le16(data, ehi + k) << 16 | _le16(data, elo + k))
            if s > e or e >= size:
                return None, f"region {i + 1} invalid: 0x{s:X}-0x{e:X}"
            regions.append((s, e))

        hits = _find_all(data, NEEDLE_MAIN_STORE, MASK_MAIN_STORE)
        if len(hits) != 1:
            return None, f"store needle: {len(hits)} hits"
        a = hits[0]
        store = self._page_off_to_file(_le16(data, a + MAIN_STORE_PAGE),
                                       _le16(data, a + MAIN_STORE_OFF))
        if store + 8 > size:
            return None, "store offset out of range"
        return _MainLayout(regions=regions, store=store), ""

    def _main_calc(self, data: bytes, lay: _MainLayout) -> int:
        total = 0
        for s, e in lay.regions:
            total = (total + _word_sum_bytes(data, s, e)) & 0xFFFFFFFF
        return total

    def _verify_main(self, data: bytes) -> MainChecksumResult:
        lay, why = self._locate_main(data)
        if lay is None:
            return MainChecksumResult(found=False, note=why)
        calc     = self._main_calc(data, lay)
        stored   = _le32(data, lay.store)
        stored_c = _le32(data, lay.store + 4)
        return MainChecksumResult(
            found=True, main_ok=(calc == stored),
            comp_ok=((~calc & 0xFFFFFFFF) == stored_c),
            offset=lay.store, stored=stored, stored_c=stored_c, calc=calc,
            regions=list(lay.regions))

    def _fix_main(self) -> None:
        lay, _ = self._locate_main(bytes(self.rom.data))
        if lay is None:
            return
        # The stored pair usually sits inside a region.  A consistent
        # [x][~x] pair contributes a constant, so once one is in place the
        # next pass reproduces itself; a corrupted pair needs two passes.
        for _ in range(3):
            data = bytes(self.rom.data)
            calc = self._main_calc(data, lay)
            new = struct.pack('<II', calc, ~calc & 0xFFFFFFFF)
            if data[lay.store:lay.store + 8] == new:
                break
            self.rom.write(lay.store, new)

    # Kept for tests
    def _word_sum(self, start: int, end: int) -> int:
        return calc_sum_block(self.rom, start, end)

    # ── Layer 2: multipoint block sums ─────────────────────────────────────────

    def _locate_multi(self, data: bytes) -> Tuple[Optional[_MultiLayout], str]:
        size = self.rom.size
        count = None
        hits = _find_all(data, NEEDLE_MULTI_COUNT, MASK_MULTI_COUNT)
        if len(hits) == 1:
            count = _le16(data, hits[0] + MULTI_COUNT_OFF)
        elif len(hits) == 0:
            alt = _find_all(data, NEEDLE_MULTI_COUNT_ALT, MASK_MULTI_COUNT_ALT)
            if len(alt) == 1:
                count = _le16(data, alt[0] + MULTI_COUNT_ALT_OFF)
            elif len(alt) > 1:
                return None, f"count needle (alt): {len(alt)} hits"
        else:
            return None, f"count needle: {len(hits)} hits"

        hits = _find_all(data, NEEDLE_MULTI_TABLE, MASK_MULTI_TABLE)
        if count is None and not hits:
            return None, ""                         # layer absent
        if count is None:
            return None, "table found but count needle missing"
        if len(hits) != 1:
            return None, f"table needle: {len(hits)} hits"
        a = hits[0]
        table = self._page_off_to_file(_le16(data, a + MULTI_TABLE_PAGE),
                                       _le16(data, a + MULTI_TABLE_OFF))
        if count <= 0 or count > 256 or table + count * MULTI_ENTRY_SIZE > size:
            return None, f"table 0x{table:X} x{count} out of range"
        return _MultiLayout(table=table, count=count), ""

    def _multi_blocks(self, data: bytes, lay: _MultiLayout) -> List[MultiBlock]:
        blocks: List[MultiBlock] = []
        for j in range(lay.count):
            b = lay.table + j * MULTI_ENTRY_SIZE
            s = self._phys_to_file(_le32(data, b))
            e = self._phys_to_file(_le32(data, b + 4))
            stored, stored_c = _le32(data, b + 8), _le32(data, b + 12)
            calc = _word_sum_bytes(data, s, e) if s < e else 0
            blocks.append(MultiBlock(
                index=j + 1, start=s, end=e,
                stored_crc=stored, stored_neg=stored_c, calc_crc=calc,
                crc_ok=(calc == stored),
                neg_ok=((~calc & 0xFFFFFFFF) == stored_c)))
        return blocks

    def _verify_multi(self, data: bytes) -> MultiChecksumResult:
        lay, why = self._locate_multi(data)
        if lay is None:
            return MultiChecksumResult(found=False, note=why)
        return MultiChecksumResult(blocks=self._multi_blocks(data, lay), found=True,
                                   table_offset=lay.table, count=lay.count)

    def _fix_multi(self) -> None:
        lay, _ = self._locate_multi(bytes(self.rom.data))
        if lay is None:
            return
        # A block may cover the table itself (its own entry contributes a
        # constant, other entries do not), so iterate until nothing changes.
        for _ in range(8):
            data = bytes(self.rom.data)
            wrote = False
            for blk in self._multi_blocks(data, lay):
                if blk.ok:
                    continue
                off = lay.table + (blk.index - 1) * MULTI_ENTRY_SIZE + 8
                self.rom.write(off, struct.pack('<II', blk.calc_crc,
                                                ~blk.calc_crc & 0xFFFFFFFF))
                wrote = True
            if not wrote:
                break

    # ── Layer 3: chained main CRC32 ────────────────────────────────────────────

    def _locate_crc(self, data: bytes) -> Tuple[Optional[_CrcLayout], str]:
        starts = [self._decode_lohi(data, h + CRC_START_LO, h + CRC_START_HI)
                  for h in _find_all(data, NEEDLE_CRC_START, MASK_CRC_START, step=2)]
        ends   = [self._decode_lohi(data, h + CRC_END_LO, h + CRC_END_HI)
                  for h in _find_all(data, NEEDLE_CRC_END, MASK_CRC_END, step=2)]
        stores = [self._decode_lohi(data, h + CRC_STORE_LO, h + CRC_STORE_HI)
                  for h in _find_all(data, NEEDLE_CRC_STORE, MASK_CRC_STORE, step=2)]
        starts = [x for x in starts if x is not None]
        ends   = [x for x in ends if x is not None]
        stores = [x for x in stores if x is not None]

        if not stores:
            # ME7Sum: no CRC offsets means the ECU does not check main CRCs.
            return None, ""
        if len(stores) != 3:
            return None, f"{len(stores)} CRC store hits (need 3)"
        if not starts or len(starts) != len(ends) or len(starts) > MAX_CRC_BLOCKS:
            return None, f"CRC regions: {len(starts)} starts / {len(ends)} ends"
        regions = []
        for s, e in zip(starts, ends):
            if s > e or e >= self.rom.size:
                return None, f"CRC region invalid: 0x{s:X}-0x{e:X}"
            regions.append((s, e))
        for o in stores:
            if o + 4 > self.rom.size:
                return None, "CRC store out of range"

        pre = None
        pre_hits = _find_all(data, NEEDLE_CRC_PRE, MASK_CRC_PRE, step=2)
        if len(pre_hits) == 1:
            h = pre_hits[0]
            p = self._decode_lohi(data, h + CRC_PRE_LO, h + CRC_PRE_HI)
            if p is not None:
                n = data[h + CRC_PRE_LEN_BYTE] >> 4
                if n and p + n <= self.rom.size:
                    pre = (p, p + n - 1)

        # Region 3 has no stored value when a 4th region exists; the third
        # constant then belongs to region 4 (ME7Sum FindMainCRCOffsets).
        slots: List[Optional[int]] = list(stores)
        if len(regions) == 4:
            slots = [stores[0], stores[1], None, stores[2]]
        else:
            slots = slots[:len(regions)] + [None] * (len(regions) - len(slots))
        return _CrcLayout(pre=pre, regions=regions, stores=slots), ""

    def _crc_blocks(self, data: bytes, lay: _CrcLayout) -> List[CrcBlock]:
        seed = 0
        chained = lay.pre is not None
        if chained:
            seed = zlib.crc32(data[lay.pre[0]:lay.pre[1] + 1], 0) & 0xFFFFFFFF
        blocks: List[CrcBlock] = []
        for i, (s, e) in enumerate(lay.regions):
            calc = zlib.crc32(data[s:e + 1], seed) & 0xFFFFFFFF
            off = lay.stores[i]
            blocks.append(CrcBlock(
                index=i + 1, start=s, end=e, calc=calc, offset=off,
                stored=_le32(data, off) if off is not None else None))
            if chained:
                seed = calc
        return blocks

    def _verify_crc(self, data: bytes) -> CrcChecksumResult:
        lay, why = self._locate_crc(data)
        if lay is None:
            return CrcChecksumResult(found=False, note=why)
        return CrcChecksumResult(blocks=self._crc_blocks(data, lay), found=True,
                                 pre_block=lay.pre)

    def _fix_crc(self) -> None:
        data = bytes(self.rom.data)
        lay, _ = self._locate_crc(data)
        if lay is None:
            return
        for blk in self._crc_blocks(data, lay):
            if blk.offset is not None and not blk.ok:
                self.rom.write(blk.offset, struct.pack('<I', blk.calc))


# Alias for __init__ compatibility
ChecksumChecker = ChecksumManager


def verify_and_fix(rom: ROMImage) -> ChecksumResult:
    """Convenience: verify, fix if needed, return final result."""
    cs = ChecksumManager(rom)
    result = cs.verify()
    if not result.all_ok:
        result = cs.fix()
    return result
