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


# ── 1MB ROM properties ────────────────────────────────────────────────────────

class TestOneMBROM:
    """1MB is the native ME7.5 format. No mirroring. Load as-is."""

    def _make_1mb(self, fill: int = 0x55) -> bytes:
        return bytes([fill] * 0x100000)

    def test_1mb_loads_cleanly(self, tmp_path):
        path = tmp_path / "me7.bin"
        path.write_bytes(self._make_1mb())
        rom = ROMImage.load(str(path))
        assert rom.size == 0x100000
        assert rom.size_kb == 1024

    def test_1mb_is_1mb_property(self, tmp_path):
        path = tmp_path / "me7.bin"
        path.write_bytes(self._make_1mb())
        rom = ROMImage.load(str(path))
        assert rom.is_1mb is True
        assert rom.is_512k is False
        assert rom.is_256k is False

    def test_1mb_cal_page_offset(self, tmp_path):
        path = tmp_path / "me7.bin"
        path.write_bytes(self._make_1mb())
        rom = ROMImage.load(str(path))
        # Cal page is last 64KB of the 1MB file
        assert rom.cal_page_offset == 0xF0000

    def test_1mb_cal_page_length(self, tmp_path):
        path = tmp_path / "me7.bin"
        path.write_bytes(self._make_1mb())
        rom = ROMImage.load(str(path))
        assert len(rom.cal_page) == 0x10000

    def test_1mb_data_intact(self, tmp_path):
        # Bytes at known XDF offset should be readable without normalisation
        data = bytearray(0x100000)
        data[0x0120DD] = 0xAB   # KFZW start byte
        path = tmp_path / "me7.bin"
        path.write_bytes(data)
        rom = ROMImage.load(str(path))
        assert rom.read_u8(0x0120DD) == 0xAB

    def test_1mb_save_roundtrip(self, tmp_path):
        src  = tmp_path / "src.bin"
        dst  = tmp_path / "dst.bin"
        data = bytearray(self._make_1mb())
        data[0x1000] = 0xDE
        src.write_bytes(data)
        rom = ROMImage.load(str(src))
        rom.data[0x1000] = 0xFF   # modify
        rom.save(str(dst))
        result = bytearray(dst.read_bytes())
        assert len(result) == 0x100000
        assert result[0x1000] == 0xFF

    def test_512k_extract_still_loads(self, tmp_path):
        """ECUFlash-style 512KB cal region still accepted."""
        path = tmp_path / "cal.bin"
        path.write_bytes(bytes(0x80000))
        rom = ROMImage.load(str(path))
        assert rom.size == 0x80000
        assert rom.is_512k is True
        assert rom.is_1mb is False
        assert rom.cal_page_offset == 0x70000

    def test_invalid_size_rejected(self, tmp_path):
        import pytest
        path = tmp_path / "bad.bin"
        path.write_bytes(bytes(0x90000))  # 576KB — not valid
        with pytest.raises(ValueError, match="Unexpected ROM size"):
            ROMImage.load(str(path))
# ── 1MB ROM normalisation ─────────────────────────────────────────────────────

class TestOneMBROM:
    """
    ME7.5 ROMs are natively 1MB. No mirroring. Flat file offsets throughout.
    XDF offsets (e.g. KFZW at 0x0120DD) are offsets into the 1MB file.
    """

    def _make_1mb(self, fill: int = 0x41) -> bytes:
        """1MB ROM with a VAG PN string embedded at a realistic offset."""
        rom = bytearray([fill] * 0x100000)
        pn = b'06A906032DL'
        rom[0x400:0x400 + len(pn)] = pn
        return bytes(rom)

    def test_1mb_loads_correctly(self, tmp_path):
        data = self._make_1mb()
        path = tmp_path / "me7.bin"
        path.write_bytes(data)
        rom = ROMImage.load(str(path))
        assert rom.size == 0x100000
        assert rom.size_kb == 1024
        assert rom.is_1mb

    def test_1mb_not_is_512k(self, tmp_path):
        data = self._make_1mb()
        path = tmp_path / "me7.bin"
        path.write_bytes(data)
        rom = ROMImage.load(str(path))
        assert not rom.is_512k
        assert not rom.is_256k

    def test_1mb_cal_page_offset(self, tmp_path):
        """Cal page for 1MB ROM is last 64KB = offset 0xF0000."""
        data = self._make_1mb()
        path = tmp_path / "me7.bin"
        path.write_bytes(data)
        rom = ROMImage.load(str(path))
        assert rom.cal_page_offset == 0xF0000

    def test_1mb_data_intact(self, tmp_path):
        """1MB data loaded without any truncation or transformation."""
        data = self._make_1mb(fill=0x55)
        path = tmp_path / "me7.bin"
        path.write_bytes(data)
        rom = ROMImage.load(str(path))
        assert bytes(rom.data) == data

    def test_1mb_read_at_xdf_offset(self, tmp_path):
        """XDF offset 0x0120DD is directly accessible in 1MB file."""
        data = bytearray(self._make_1mb())
        # Write a sentinel at the KFZW XDF offset
        data[0x0120DD] = 0xAB
        path = tmp_path / "me7.bin"
        path.write_bytes(data)
        rom = ROMImage.load(str(path))
        assert rom.read_u8(0x0120DD) == 0xAB

    def test_1mb_save_roundtrip(self, tmp_path):
        data = self._make_1mb()
        src  = tmp_path / "src.bin"
        dst  = tmp_path / "dst.bin"
        src.write_bytes(data)
        rom = ROMImage.load(str(src))
        rom.data[0x100] = (rom.data[0x100] + 1) & 0xFF
        rom.save(str(dst))
        written = dst.read_bytes()
        assert len(written) == 0x100000
        assert written[0x100] == rom.data[0x100]

    def test_invalid_size_rejected(self, tmp_path):
        import pytest
        path = tmp_path / "bad.bin"
        path.write_bytes(bytes(0x90000))  # 576 KB — not a valid ME7 size
        with pytest.raises(ValueError, match="Unexpected ROM size"):
            ROMImage.load(str(path))

    def test_512kb_extract_still_accepted(self, tmp_path):
        """512KB ECUFlash-style extract remains valid for compatibility."""
        path = tmp_path / "extract.bin"
        path.write_bytes(bytes(0x80000))
        rom = ROMImage.load(str(path))
        assert rom.size_kb == 512
        assert rom.is_512k
        assert rom.cal_page_offset == 0x70000
