"""
meseventool/dpp.py
==================
C167 DPP register extraction and address translation.
"""

from __future__ import annotations
from .rom import ROMImage
from .needle import Searcher

SEGMENT_SIZE = 0x4000   # C167 page = 16 KB


class DPPValues:
    """Extracted DPP0-DPP3 register values with address translation."""

    def __init__(self, dpp0: int = 0, dpp1: int = 0,
                 dpp2: int = 0, dpp3: int = 0):
        self.dpp0  = dpp0
        self.dpp1  = dpp1
        self.dpp2  = dpp2
        self.dpp3  = dpp3
        self.found = False

    @property
    def dpp1_seg(self) -> int:
        """Page that DPP0-window operands resolve to: dpp1 - 1 (the ME7
        convention; equals dpp0 whenever the startup code sets DPP0)."""
        return max(0, self.dpp1 - 1)

    def seg_to_file(self, seg: int, offset: int, rom_size: int = 0x100000) -> int:
        physical = seg * SEGMENT_SIZE + (offset & 0x3FFF)
        return physical & (rom_size - 1)

    def data_addr_to_file(self, addr16: int, rom_size: int = 0x100000) -> int:
        """16-bit data operand → file offset; bits 15:14 pick DPP0..3
        (see Searcher.data_addr_to_file)."""
        page_sel = (addr16 >> 14) & 3
        page = [self.dpp0, self.dpp1, self.dpp2, self.dpp3][page_sel]
        if page_sel == 0 and self.dpp0 == 0:
            page = self.dpp1_seg
        return self.seg_to_file(page, addr16, rom_size)

    def dpp1_to_file(self, offset: int, rom_size: int = 0x100000) -> int:
        """Operand → file offset (review D4: no longer subtracts a page
        AND masks; the operand's own window bits select the DPP)."""
        return self.data_addr_to_file(offset, rom_size)

    def describe(self) -> str:
        return (f"DPP0=0x{self.dpp0:04X}  DPP1=0x{self.dpp1:04X}  "
                f"DPP2=0x{self.dpp2:04X}  DPP3=0x{self.dpp3:04X}  "
                f"found={self.found}")

    def __repr__(self) -> str:
        return (f"DPPValues(dpp0=0x{self.dpp0:04X}, dpp1=0x{self.dpp1:04X}, "
                f"dpp2=0x{self.dpp2:04X}, dpp3=0x{self.dpp3:04X})")


# Backwards-compatible alias
DPPInfo = DPPValues


class DPPExtractor:
    """Extracts DPP register values from a Searcher."""

    def __init__(self, searcher: Searcher):
        self._s = searcher

    def extract(self) -> DPPValues:
        s   = self._s
        dpp = DPPValues(s.dpp0, s.dpp1, s.dpp2, s.dpp3)
        if any([s.dpp0, s.dpp1, s.dpp2, s.dpp3]):
            dpp.found = True
        elif s.find_dppx():
            dpp = DPPValues(s.dpp0, s.dpp1, s.dpp2, s.dpp3)
            dpp.found = True
        return dpp


def extract_dpp(rom: ROMImage) -> DPPValues:
    s  = Searcher(rom)
    s.find_dppx()
    ex = DPPExtractor(s)
    return ex.extract()
