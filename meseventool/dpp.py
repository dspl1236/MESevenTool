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
        """Segment page used for most ROM data refs: dpp1 - 1."""
        return max(0, self.dpp1 - 1)

    def seg_to_file(self, seg: int, offset: int, rom_size: int = 0x80000) -> int:
        physical = seg * SEGMENT_SIZE + (offset & 0x3FFF)
        return physical & (rom_size - 1)

    def dpp1_to_file(self, offset: int, rom_size: int = 0x80000) -> int:
        return self.seg_to_file(self.dpp1_seg, offset, rom_size)

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
