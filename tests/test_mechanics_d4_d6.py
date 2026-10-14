"""
Review items D4–D6: DPP address translation, the real DPP needle form, and
bounded ROM reads.
"""
import pytest
from meseventool.rom import ROMImage
from meseventool.needle import Searcher, NEEDLE_DPP, NEEDLE_DPP_DIRECT
from meseventool.dpp import DPPValues, extract_dpp
from tests.rom_corpus import find_rom


def _searcher(dpp0, dpp1, dpp2=0xE0, dpp3=3, size=0x100000):
    s = Searcher(ROMImage(data=bytearray(size)))
    s.dpp0, s.dpp1, s.dpp2, s.dpp3 = dpp0, dpp1, dpp2, dpp3
    return s


# ── D4: window-aware translation ─────────────────────────────────────────────

class TestDataAddressTranslation:
    def test_dpp0_window_with_dpp0_set(self):
        """KFZW on DL: operand 0x20DD in the DPP0 window, DPP0=0x204 → 0x120DD."""
        s = _searcher(0x204, 0x205)
        assert s.data_addr_to_file(0x20DD) == 0x0120DD
        assert s.dpp1_to_file(0x20DD) == 0x0120DD

    def test_dpp0_window_with_dpp0_unset_uses_dpp1_minus_one(self):
        """132 corpus images set DPP0=0 at startup; ROM operands in that
        window still resolve to page DPP1-1 (me7romtool convention)."""
        s = _searcher(0x0, 0x205)
        assert s.data_addr_to_file(0x20DD) == 0x0120DD

    def test_dpp1_window_is_not_a_page_low(self):
        """Operand 0x4194 (DPP1 window) → DPP1*0x4000 + 0x194 = file 0x14194.
        The old code gave 0x10194: it subtracted a page AND masked."""
        s = _searcher(0x204, 0x205)
        assert s.data_addr_to_file(0x4194) == 0x014194
        assert s.dpp1_to_file(0x4194) == 0x014194

    def test_dpp2_and_dpp3_windows(self):
        s = _searcher(0x204, 0x205, dpp2=0x207, dpp3=0x23F)
        assert s.data_addr_to_file(0x8000 | 0x3BDE) == (0x207 * 0x4000 + 0x3BDE) & 0xFFFFF   # 0x1FBDE
        assert s.data_addr_to_file(0xC000 | 0x3FE0) == (0x23F * 0x4000 + 0x3FE0) & 0xFFFFF

    def test_dppvalues_agrees_with_searcher(self):
        d = DPPValues(dpp0=0x204, dpp1=0x205, dpp2=0xE0, dpp3=3)
        s = _searcher(0x204, 0x205)
        for op in (0x20DD, 0x4194, 0x0010, 0x7FFF):
            assert d.data_addr_to_file(op) == s.data_addr_to_file(op), hex(op)
            assert d.dpp1_to_file(op) == s.dpp1_to_file(op), hex(op)
        assert d.dpp1_seg == 0x204

    def test_mask_to_rom_size(self):
        s = _searcher(0x204, 0x205, size=0x80000)
        assert s.data_addr_to_file(0x4194) == 0x014194 & 0x7FFFF


# ── D5: the real DPP needle ──────────────────────────────────────────────────

class TestDppNeedleForm:
    def test_exported_needle_is_direct_form(self):
        assert NEEDLE_DPP is NEEDLE_DPP_DIRECT
        assert NEEDLE_DPP[:2] == [0xE6, 0x00] and NEEDLE_DPP[4:6] == [0xE6, 0x01]

    def test_old_indirect_form_does_not_match(self):
        rom = ROMImage(data=bytearray([0xFF]) * 0x80000)
        seq = bytes([0xE6, 0xF0, 0x04, 0x02, 0xFD, 0x00, 0xE6, 0xF0, 0x05, 0x02, 0xFD, 0x01,
                     0xE6, 0xF0, 0xE0, 0x00, 0xFD, 0x02, 0xE6, 0xF0, 0x03, 0x00, 0xFD, 0x03])
        rom.data[0x1000:0x1000 + len(seq)] = seq
        assert not Searcher(rom).find_dppx()

    def test_direct_form_matches(self):
        rom = ROMImage(data=bytearray([0xFF]) * 0x80000)
        seq = bytes([0xE6, 0x00, 0x04, 0x02, 0xE6, 0x01, 0x05, 0x02,
                     0xE6, 0x02, 0xE0, 0x00, 0xE6, 0x03, 0x03, 0x00])
        rom.data[0x1000:0x1000 + len(seq)] = seq
        s = Searcher(rom)
        assert s.find_dppx()
        assert (s.dpp0, s.dpp1, s.dpp2, s.dpp3) == (0x204, 0x205, 0xE0, 0x3)

    @pytest.mark.parametrize("name,dpp0", [
        ("06A906032DL_0261206890_v360227_MT_OEM.bin", 0x0),
        ("18CM.Bin", 0x0),
        ("8D0907551M-0001.bin", 0x204),
    ])
    def test_real_roms(self, name, dpp0):
        path = find_rom(name)
        if not path:
            pytest.skip(name)
        d = extract_dpp(ROMImage.load(path))
        assert d.found
        assert d.dpp1 == 0x205 and d.dpp2 == 0xE0 and d.dpp3 == 0x3
        assert d.dpp0 in (0x0, 0x204)


# ── D6: bounded reads ────────────────────────────────────────────────────────

class TestRomRead:
    def test_read_past_end_raises(self):
        rom = ROMImage(data=bytearray(0x40000))
        with pytest.raises(ValueError, match="outside ROM"):
            rom.read(0x3FFFE, 4)

    def test_negative_offset_raises(self):
        rom = ROMImage(data=bytearray(0x40000))
        with pytest.raises(ValueError):
            rom.read(-1, 1)

    def test_exact_end_ok(self):
        rom = ROMImage(data=bytearray(0x40000))
        assert rom.read(0x3FFFC, 4) == b"\x00" * 4
        assert rom.read(0x40000, 0) == b""
