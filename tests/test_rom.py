"""Tests for ROMImage — no real ROM required."""
import pytest
import os
import tempfile
from meseventool.rom import ROMImage, VALID_SIZES, CAL_PAGE_SIZE


def make_rom(size=0x80000, fill=0xFF):
    """Create a synthetic ROM of the given size."""
    return ROMImage(data=bytearray([fill] * size))


class TestROMBasics:
    def test_valid_sizes_accepted(self):
        for size in VALID_SIZES:
            rom = ROMImage.from_bytes(bytes([0xFF] * size))
            assert rom.size == size

    def test_invalid_size_raises(self):
        # from_bytes validates size
        with pytest.raises(ValueError, match="Unexpected ROM size"):
            ROMImage.from_bytes(bytes([0xFF] * 0x1000))
        # Direct construction is unrestricted (used for synthetic test ROMs)
        rom = ROMImage(data=bytearray(0x1000))
        assert rom.size == 0x1000

    def test_512k_properties(self):
        rom = make_rom(0x80000)
        assert rom.is_512k
        assert not rom.is_256k
        assert rom.size_kb == 512

    def test_256k_properties(self):
        rom = make_rom(0x40000)
        assert rom.is_256k
        assert not rom.is_512k
        assert rom.size_kb == 256

    def test_cal_page_offset_512k(self):
        rom = make_rom(0x80000)
        assert rom.cal_page_offset == 0x70000

    def test_cal_page_offset_256k(self):
        rom = make_rom(0x40000)
        assert rom.cal_page_offset == 0x30000

    def test_cal_page_view(self):
        rom = make_rom(0x80000, fill=0x00)
        # Write known bytes at start of cal page
        rom.data[0x70000] = 0xAB
        rom.data[0x70001] = 0xCD
        cal = rom.cal_page
        assert cal[0] == 0xAB
        assert cal[1] == 0xCD
        assert len(cal) == CAL_PAGE_SIZE


class TestROMReadWrite:
    def test_read_u8(self):
        rom = make_rom()
        rom.data[0x100] = 0x42
        assert rom.read_u8(0x100) == 0x42

    def test_read_u16_be(self):
        rom = make_rom()
        rom.data[0x200] = 0x12
        rom.data[0x201] = 0x34
        assert rom.read_u16_be(0x200) == 0x1234

    def test_read_u16_le(self):
        rom = make_rom()
        rom.data[0x200] = 0x34
        rom.data[0x201] = 0x12
        assert rom.read_u16_le(0x200) == 0x1234

    def test_read_u32_be(self):
        rom = make_rom()
        rom.data[0x300:0x304] = b'\xDE\xAD\xBE\xEF'
        assert rom.read_u32_be(0x300) == 0xDEADBEEF

    def test_write_marks_modified(self):
        rom = make_rom()
        assert not rom.is_modified
        rom.write(0x100, b'\xAA\xBB')
        assert rom.is_modified

    def test_write_u16_be_roundtrip(self):
        rom = make_rom()
        rom.write_u16_be(0x500, 0xCAFE)
        assert rom.read_u16_be(0x500) == 0xCAFE

    def test_write_u16_le_roundtrip(self):
        rom = make_rom()
        rom.write_u16_le(0x500, 0xCAFE)
        assert rom.read_u16_le(0x500) == 0xCAFE

    def test_write_u32_be_roundtrip(self):
        rom = make_rom()
        rom.write_u32_be(0x600, 0x12345678)
        assert rom.read_u32_be(0x600) == 0x12345678

    def test_write_out_of_bounds_raises(self):
        rom = make_rom(0x80000)
        with pytest.raises(ValueError, match="exceeds ROM size"):
            rom.write(0x7FFFF, b'\x00\x00')

    def test_snapshot_is_independent(self):
        rom = make_rom()
        snap = rom.snapshot()
        rom.data[0] = 0x00
        assert snap[0] == 0xFF  # snapshot unaffected

    def test_save_load_roundtrip(self):
        rom = make_rom(0x80000, fill=0xAA)
        rom.data[0x1000] = 0x42
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            path = f.name
        try:
            rom.save(path)
            rom2 = ROMImage.load(path)
            assert rom2.data[0x1000] == 0x42
            assert rom2.size == 0x80000
            assert not rom2.is_modified
        finally:
            os.unlink(path)

    def test_hexdump_format(self):
        rom = make_rom()
        rom.data[0:4] = b'\xDE\xAD\xBE\xEF'
        line = rom.hexdump(0, 4)
        assert 'DE' in line
        assert 'AD' in line

    def test_repr(self):
        rom = ROMImage(data=bytearray(0x80000), path="/fake/rom.bin")
        r = repr(rom)
        assert 'rom.bin' in r
        assert '512' in r


class TestROMCopyAndFrom:
    def test_from_bytes(self):
        data = bytes([0xAA] * 0x80000)
        rom = ROMImage.from_bytes(data)
        assert rom.size == 0x80000
        assert rom.data[0] == 0xAA
        assert rom.path is None
