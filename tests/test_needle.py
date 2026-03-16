"""Tests for needle search engine — no real ROM required."""
import pytest
from meseventool.rom import ROMImage
from meseventool.needle import Searcher, SearchHit, XXXX, MASK, NEEDLE_DPP, MASK_DPP


def make_rom(data: bytes) -> ROMImage:
    # Pad to 512KB
    padded = data + bytes([0xFF] * (0x80000 - len(data)))
    return ROMImage(data=bytearray(padded))


class TestSearcher:
    def test_exact_match(self):
        rom = make_rom(b'\x00' * 0x100 + b'\xDE\xAD\xBE\xEF' + b'\x00' * 100)
        s = Searcher(rom)
        hits = s.search(
            [0xDE, 0xAD, 0xBE, 0xEF],
            [MASK, MASK, MASK, MASK],
        )
        assert len(hits) == 1
        assert hits[0].file_offset == 0x100

    def test_wildcard_match(self):
        rom = make_rom(b'\xAA\xBB\xCC\xDD')
        s = Searcher(rom)
        hits = s.search(
            [0xAA, XXXX, 0xCC, 0xDD],
            [MASK,  XXXX, MASK, MASK],
        )
        assert len(hits) == 1
        assert hits[0].file_offset == 0

    def test_no_match(self):
        rom = make_rom(b'\x00' * 256)
        s = Searcher(rom)
        hits = s.search([0xDE, 0xAD], [MASK, MASK])
        assert hits == []

    def test_search_one_found(self):
        rom = make_rom(b'\xFF' * 0x50 + b'\x01\x02\x03' + b'\xFF' * 0x50)
        s = Searcher(rom)
        hit = s.search_one([0x01, 0x02, 0x03], [MASK, MASK, MASK])
        assert hit is not None
        assert hit.file_offset == 0x50

    def test_search_one_not_found(self):
        rom = make_rom(b'\x00' * 256)
        s = Searcher(rom)
        hit = s.search_one([0xDE, 0xAD], [MASK, MASK])
        assert hit is None

    def test_multiple_hits_limited(self):
        # Pattern appears 3 times; ask for count=2
        rom = make_rom(b'\xAB\xCD' * 3 + b'\x00' * 0x100)
        s = Searcher(rom)
        hits = s.search([0xAB, 0xCD], [MASK, MASK], count=2)
        assert len(hits) == 2

    def test_count_all(self):
        rom = make_rom(b'\xAB\xCD' * 5 + b'\x00' * 0x100)
        s = Searcher(rom)
        hits = s.search([0xAB, 0xCD], [MASK, MASK], count=99)
        assert len(hits) == 5

    def test_mismatched_needle_mask_raises(self):
        rom = make_rom(b'\x00' * 64)
        s = Searcher(rom)
        with pytest.raises(AssertionError):
            s.search([0xAA, 0xBB], [MASK])

    def test_partial_wildcard(self):
        # Needle: 0xAA ?? 0xCC — matches 0xAA 0xFF 0xCC
        rom = make_rom(b'\xAA\xFF\xCC\xDD')
        s = Searcher(rom)
        hits = s.search([0xAA, XXXX, 0xCC], [MASK, XXXX, MASK])
        assert len(hits) == 1
        assert hits[0].data[1] == 0xFF   # wildcard byte preserved


class TestSearchHit:
    def test_get_u16_le(self):
        hit = SearchHit(file_offset=0, data=bytes([0x34, 0x12, 0x00, 0x00]))
        assert hit.get_u16_le(0) == 0x1234

    def test_get_u16_be(self):
        hit = SearchHit(file_offset=0, data=bytes([0x12, 0x34, 0x00, 0x00]))
        assert hit.get_u16_be(0) == 0x1234

    def test_get_u8(self):
        hit = SearchHit(file_offset=0, data=bytes([0xAB, 0xCD]))
        assert hit.get_u8(0) == 0xAB
        assert hit.get_u8(1) == 0xCD


class TestDPPNeedle:
    def test_dpp_needle_found_in_synthetic_rom(self):
        """Build a synthetic ROM that contains the DPP setup sequence."""
        # DPP sequence: mov r0, #DPP0; mov DPP0, r0; ... x4
        # C167 encoding: E6 F0 <lo> <hi>  FD 00  (for DPP0)
        dpp_seq = bytes([
            0xE6, 0xF0, 0x03, 0x00,   # mov r0, #0x0003  (DPP0 = page 3)
            0xFD, 0x00,                # mov DPP0, r0
            0xE6, 0xF0, 0x10, 0x00,   # mov r0, #0x0010  (DPP1 = page 16)
            0xFD, 0x01,                # mov DPP1, r0
            0xE6, 0xF0, 0x20, 0x00,   # mov r0, #0x0020  (DPP2 = page 32)
            0xFD, 0x02,                # mov DPP2, r0
            0xE6, 0xF0, 0x03, 0xFE,   # mov r0, #0xFE03  (DPP3 = stack page)
            0xFD, 0x03,                # mov DPP3, r0
        ])
        rom_data = b'\xFF' * 0x1000 + dpp_seq + b'\xFF' * (0x80000 - 0x1000 - len(dpp_seq))
        rom = ROMImage(data=bytearray(rom_data))
        s = Searcher(rom)
        found = s.find_dppx()
        assert found
        assert s.dpp0 == 0x0003
        assert s.dpp1 == 0x0010
        assert s.dpp2 == 0x0020
        assert s.dpp3 == 0xFE03

    def test_dpp_not_found_returns_false(self):
        rom = ROMImage(data=bytearray(0x80000))
        s = Searcher(rom)
        assert not s.find_dppx()
        assert s.dpp0 == 0
        assert s.dpp1 == 0


class TestAddressTranslation:
    def test_seg_offset_to_file(self):
        rom = ROMImage(data=bytearray(0x80000))
        s = Searcher(rom)
        # seg=2, offset=0x0100 → file = 2*0x4000 + 0x100 = 0x8100
        result = s.seg_offset_to_file(2, 0x0100)
        assert result == 0x8100

    def test_seg_offset_wraps_to_rom_size(self):
        rom = ROMImage(data=bytearray(0x80000))
        s = Searcher(rom)
        # Large seg → wraps within rom_size
        result = s.seg_offset_to_file(0x20, 0x0000)
        assert result < rom.size
