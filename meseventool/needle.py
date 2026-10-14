"""
meseventool/needle.py
=====================
Byte-pattern needle search for ME7.x ROM images.

Ported from ME7RomTool_Ferrari (360trev / nyet, MIT licence).
The core approach: search for masked byte sequences (C167 machine code
snippets) that are stable across ROM versions, then extract absolute
addresses from the surrounding operands.

The C167CR uses a segmented 24-bit address space.  All ROM variables are
accessed via DPP (Data Page Pointer) segments.  After extracting the DPP
values from the startup code we can translate any seg:offset pair to a
flat file offset.

C167 instruction encodings used here
--------------------------------------
E6 Rw lo hi    MOV Rw, #data16      (Rw = 0x00-0x0F for R0-R15)
F6 Rw lo hi    MOV mem16, Rw        (store register to memory address)
F2 Rw lo hi    MOV Rw, mem16        (load register from memory address)
D7 40 lo hi    EXTP #page, #1       (set extended data page for next instr)
C2 Rw lo hi    MOVBZ Rw, mem8       (zero-extending byte load)
B2 Rw lo hi    MOVBZ Rw, mem8       (alternate form used in some needles)
DB 00          RETS                 (return from subroutine)
8D xx          JMPR cc_C, rel       (short conditional jump)
60 Rw          ADD Rw, Rw           (Rw = Rw + Rw, i.e. ×2)

The DPP registers are SFR-bank registers; their immediate-load encoding
uses the low nibble as the DPP index:
  E6 00 lo hi  → MOV DPP0, #val
  E6 01 lo hi  → MOV DPP1, #val
  E6 02 lo hi  → MOV DPP2, #val
  E6 03 lo hi  → MOV DPP3, #val

Note: the "EXTP" instruction prefixes the *next* memory instruction with a
literal 14-bit page number (bits [13:0] of the next physical address high
word), overriding the DPP for that one access.  Map pointers are found by
reading the page from EXTP and the offset from the following MOV.

Usage
-----
    from meseventool.rom import ROMImage
    from meseventool.needle import Searcher

    rom = ROMImage.load("awp.bin")
    s   = Searcher(rom)
    ok  = s.find_dppx()           # extract DPP0-3 from startup code
    if ok:
        print(s.dpp1)             # page that covers most ROM variables

    hit = s.search_one(NEEDLE_KFZW, MASK_KFZW)
    if hit:
        seg    = hit.get_u16_le(KFZW_EXTP_OFFSET)
        offset = hit.get_u16_le(KFZW_DATA_OFFSET)
        file_off = s.extp_to_file(seg, offset)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .rom import ROMImage


# Wildcard constant for needle / mask arrays
XXXX = 0x00   # matches any byte when mask byte is 0x00
MASK = 0xFF   # must match exactly when mask byte is 0xFF


@dataclass
class SearchHit:
    """A needle match within the ROM."""
    file_offset: int    # byte offset into the flat file where needle starts
    data:        bytes  # matched bytes (exactly needle length)

    def get_u16_le(self, rel: int) -> int:
        """Little-endian 16-bit word at rel bytes from hit start."""
        return self.data[rel] | (self.data[rel + 1] << 8)

    def get_u16_be(self, rel: int) -> int:
        return (self.data[rel] << 8) | self.data[rel + 1]

    def get_u8(self, rel: int) -> int:
        return self.data[rel]


class Searcher:
    """
    Masked byte-pattern search over a ROMImage.

    All needles and masks must be the same length.  A byte at position i
    matches when:
        (rom_byte[i] & mask[i]) == (needle[i] & mask[i])

    XXXX (0x00) in the mask is a wildcard — the ROM byte can be anything.
    MASK (0xFF) requires an exact byte match.
    """

    def __init__(self, rom: ROMImage):
        self.rom   = rom
        self._data = bytes(rom.data)
        self._len  = rom.size

        # DPP register values populated by find_dppx()
        self.dpp0: int = 0
        self.dpp1: int = 0
        self.dpp2: int = 0
        self.dpp3: int = 0

    # ── Core search ────────────────────────────────────────────────────────────

    def search(
        self,
        needle: Sequence[int],
        mask:   Sequence[int],
        start:  int = 0,
        count:  int = 0,     # 0 = return all
    ) -> list[SearchHit]:
        """
        Return all (or up to count) occurrences of needle/mask in the ROM.
        """
        assert len(needle) == len(mask), "needle and mask must be same length"
        nlen  = len(needle)
        data  = self._data
        rlen  = self._len
        hits: list[SearchHit] = []

        i = start
        while i <= rlen - nlen:
            for j in range(nlen):
                if mask[j] and (data[i + j] & mask[j]) != (needle[j] & mask[j]):
                    break
            else:
                hits.append(SearchHit(file_offset=i, data=data[i: i + nlen]))
                if count and len(hits) >= count:
                    return hits
            i += 1

        return hits

    def search_one(
        self,
        needle: Sequence[int],
        mask:   Sequence[int],
        start:  int = 0,
    ) -> Optional[SearchHit]:
        """Return the first match, or None."""
        hits = self.search(needle, mask, start=start, count=1)
        return hits[0] if hits else None

    # ── DPP register extraction ────────────────────────────────────────────────

    def find_dppx(self) -> bool:
        """
        Extract DPP0-DPP3 values from the C167 startup code.

        The startup code sets DPP0..DPP3 with four direct immediates:
            E6 0x lo hi   MOV DPPx, #val   (x = 0..3)
        This is the only form seen on 269 of 284 corpus images (the 256 KB
        ME7.1 dumps use something else and report not-found).  An earlier
        "indirect via R0" form (E6 F0 lo hi / FD 0x) was not valid C167 and
        never matched a real ROM (review D5); it has been removed.

        dpp1 is the critical value: it determines the base page for most
        ROM calibration table references.

        Returns True on success, False if the needle was not found.
        """
        hit = self.search_one(NEEDLE_DPP_DIRECT, MASK_DPP_DIRECT)
        if hit is not None:
            # Each MOV DPPx is 4 bytes
            self.dpp0 = hit.get_u16_le(2)    # E6 00 [lo hi] at +0
            self.dpp1 = hit.get_u16_le(6)    # E6 01 [lo hi] at +4
            self.dpp2 = hit.get_u16_le(10)   # E6 02 [lo hi] at +8
            self.dpp3 = hit.get_u16_le(14)   # E6 03 [lo hi] at +12
            return True
        return False

    # ── Address translation ────────────────────────────────────────────────────

    def extp_to_file(self, extp_page: int, offset: int) -> int:
        """
        Translate an EXTP page + 16-bit offset pair to a flat file offset.

        The C167 EXTP instruction encodes a 14-bit page number.  Each page
        is 0x4000 bytes.  The physical address is:
            physical = (page << 14) | (offset & 0x3FFF)

        For a 512 KB ROM mapped at physical base 0x80000:
            file_offset = physical & 0x7FFFF

        For a 256 KB ROM mapped at physical base 0xC0000:
            file_offset = physical & 0x3FFFF
        """
        mask = self.rom.size - 1
        physical = (extp_page << 14) | (offset & 0x3FFF)
        return physical & mask

    def seg_offset_to_file(self, seg: int, offset: int) -> int:
        """
        Translate a segment:offset pair to a flat file offset.
        file_offset = (seg * 0x4000 + (offset & 0x3FFF)) & (rom_size - 1)
        """
        physical = (seg * 0x4000) + (offset & 0x3FFF)
        return physical & (self.rom.size - 1)

    def data_addr_to_file(self, addr16: int) -> int:
        """
        Translate a 16-bit C167 data address (a MOV operand) to a file offset.

        Bits 15:14 of the address select DPP0..DPP3; the page register
        supplies bits 23:14 of the physical address and the low 14 bits
        come from the operand:
            physical = DPPn * 0x4000 + (addr16 & 0x3FFF)

        When DPP0 is 0 in the startup code (RAM at run time) a DPP0-window
        operand is resolved with page DPP1 - 1, which is where ME7 lays
        the DPP0 ROM window (me7romtool convention; DPP0 = 0x204 and
        DPP1 = 0x205 on every corpus image that sets both).
        """
        page_sel = (addr16 >> 14) & 3
        dpps = [self.dpp0, self.dpp1, self.dpp2, self.dpp3]
        page = dpps[page_sel]
        if page_sel == 0 and self.dpp0 == 0:
            page = max(0, self.dpp1 - 1)
        physical = page * 0x4000 + (addr16 & 0x3FFF)
        return physical & (self.rom.size - 1)

    def dpp1_to_file(self, offset: int) -> int:
        """
        Translate a 16-bit data operand to a file offset.

        Kept for callers that pass needle operands: the operand's top two
        bits pick the DPP, so this is data_addr_to_file().  The previous
        implementation both subtracted a page from DPP1 and masked the
        operand to 14 bits, which was one page off for any operand in the
        DPP1 window (review D4).
        """
        return self.data_addr_to_file(offset)


# ══════════════════════════════════════════════════════════════════════════════
# Needle definitions
# Ported from me7romtool / needles.c (MIT licence, 360trev / nyet)
# Format: list of ints.  MASK (0xFF) = must match.  XXXX (0x00) = wildcard.
# ══════════════════════════════════════════════════════════════════════════════

# ── DPP register initialisation ───────────────────────────────────────────────
# Fires at C167 cold boot, sets DPP0-DPP3 from immediate constants.
# Correct C167 encoding: E6 <dpp_index> <lo> <hi>
#   where dpp_index is 0x00-0x03 (not the F0-FF SFR naming)
# Direct-form DPP initialisation — the form every 512 KB / 1 MB ME7 image
# in the corpus uses (review D5):
#   E6 00 lo hi   MOV DPP0, #val
#   E6 01 lo hi   MOV DPP1, #val
#   E6 02 lo hi   MOV DPP2, #val
#   E6 03 lo hi   MOV DPP3, #val
NEEDLE_DPP_DIRECT = [
    0xE6, 0x00, XXXX, XXXX,   # MOV DPP0, #val
    0xE6, 0x01, XXXX, XXXX,   # MOV DPP1, #val
    0xE6, 0x02, XXXX, XXXX,   # MOV DPP2, #val
    0xE6, 0x03, XXXX, XXXX,   # MOV DPP3, #val
]
MASK_DPP_DIRECT = [
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
]
# Exported names kept for callers; they are the direct form.
NEEDLE_DPP = NEEDLE_DPP_DIRECT
MASK_DPP   = MASK_DPP_DIRECT

# Checksum needles live in checksum.py (ported from me7romtool and ME7Sum).

# ── SSTB — shared axis-lookup subroutine ─────────────────────────────────────
# Called by KFZW (ignition) and other 2D maps.  Finding SSTB gives the
# addresses of SNM16ZUUB (RPM axis) and SRL12ZUUB (load axis).
# Offsets into hit for axis pointers:
#   SNM16ZUUB: +150  (EXTP page at +148, offset at +152)
#   SRL12ZUUB: +170  (EXTP page at +168, offset at +172)
NEEDLE_SSTB = [
    0xD7, 0x40, XXXX, XXXX,   # EXTP #page, #1
    0xF2, 0xF4, XXXX, XXXX,   # MOV R4, SNM16ZUUB
    0xD7, 0x40, XXXX, XXXX,   # EXTP #page, #1
    0xF2, 0xF6, XXXX, XXXX,   # MOV R6, SRL12ZUUB
    0xD7, 0x40, XXXX, XXXX,   # EXTP #page, #1
    0xF2, 0xF8, XXXX, XXXX,   # MOV R8, word_xxx
]
MASK_SSTB = [
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
]

# ── ZWGRU — ignition map (KFZW) lookup caller ────────────────────────────────
# Calls the ignition timing lookup with a pointer to the KFZW table.
# KFZW address extracted from:  hit.get_u16_le(+58) → offset, use dpp1
# KFZW2 (variant 2) from:       hit.get_u16_le(+20)
NEEDLE_ZWGRU = [
    0xD7, 0x40, XXXX, XXXX,   # EXTP #page, #1
    0xF2, 0xFC, XXXX, XXXX,   # MOV R12, KFZW_addr
    0x60, 0xFC,                # ADD R12, R12       (×2 for word indexing)
    0xEC, 0xFC,                # MOV [-R0], R12     (push onto stack)
    0xD7, 0x40, XXXX, XXXX,   # EXTP #page, #1
    0xF2, 0xFA, XXXX, XXXX,   # MOV R10, word_xxx
]
MASK_ZWGRU = [
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK,
    MASK, MASK,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
]

# ── MLHFM — MAF linearisation table ──────────────────────────────────────────
# 512 entries × 2 bytes = 1024 bytes total.
# Table address extracted from the EXTP+MOVBZ pair.
NEEDLE_MLHFM = [
    0xD7, 0x40, XXXX, XXXX,   # EXTP #page, #1
    0xB2, 0xFF, XXXX, XXXX,   # MOVBZ R15, MLHFM[R15]
    0xD7, 0x40, XXXX, XXXX,   # EXTP #page, #1
    0xB2, 0xFE, XXXX, XXXX,   # MOVBZ R14, MLHFM+1[R15]
]
MASK_MLHFM = [
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
]

# ── KFKHFM — MAF air temperature correction table ────────────────────────────
NEEDLE_KFKHFM = [
    0xD7, 0x40, XXXX, XXXX,   # EXTP #page, #1
    0xC2, 0xFA, XXXX, XXXX,   # MOVBZ R10, KFKHFM_Y_NUM
    0xD7, 0x40, XXXX, XXXX,   # EXTP #page, #1
    0xC2, 0xF8, XXXX, XXXX,   # MOVBZ R8,  KFKHFM_X_NUM
]
MASK_KFKHFM = [
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
    MASK, MASK, XXXX, XXXX,
]

# Extraction offsets within ZWGRU hit for table addresses
KFZW_DATA_EXTP_OFFSET = 0    # +0: EXTP page word (LE) for KFZW data
KFZW_DATA_ADDR_OFFSET = 6    # +6: 16-bit offset for KFZW data address
KFZW_SNM_EXTP_OFFSET  = 16   # (in SSTB hit) +148 for SNM16ZUUB
KFZW_SRL_EXTP_OFFSET  = 20   # (in SSTB hit) +168 for SRL12ZUUB
