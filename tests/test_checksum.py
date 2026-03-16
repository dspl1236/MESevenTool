"""Tests for checksum layer — uses synthetic ROMs."""
import struct
import pytest
from meseventool.rom import ROMImage
from meseventool.checksum import ChecksumManager


def make_rom_with_checksum(size=0x80000) -> tuple[ROMImage, int]:
    """
    Build a synthetic ROM with a correctly computed main checksum.
    Cal page starts at size - 0x10000.
    Checksum stored at cal_page + 0xFFF8.
    Returns (rom, correct_sum).
    """
    data = bytearray([0xAA] * size)
    cal_off  = size - 0x10000
    storage  = cal_off + 0xFFF8

    # Zero out checksum storage first
    data[storage:storage+8] = b'\x00' * 8

    # Calculate sum of cal page (except last 8 bytes)
    total = 0
    for i in range(cal_off, storage - 1, 2):
        word = data[i] | (data[i+1] << 8)
        total += word
    total &= 0xFFFFFFFF

    comp = (~total) & 0xFFFFFFFF
    struct.pack_into('<I', data, storage, total)
    struct.pack_into('<I', data, storage + 4, comp)

    return ROMImage(data=data), total


class TestMainChecksum:
    def test_verify_correct_checksum(self):
        rom, expected_sum = make_rom_with_checksum()
        cs = ChecksumManager(rom)
        result = cs.verify()
        assert result.main_found
        assert len(result.main_regions) == 1
        assert result.main_regions[0].ok
        assert result.main_ok

    def test_verify_corrupted_checksum(self):
        rom, _ = make_rom_with_checksum()
        # Corrupt the stored checksum
        cal_off = rom.cal_page_offset
        rom.data[cal_off + 0xFFF8] ^= 0xFF
        cs = ChecksumManager(rom)
        result = cs.verify()
        assert result.main_found
        assert not result.main_regions[0].ok
        assert not result.main_ok

    def test_fix_restores_correct_checksum(self):
        rom, _ = make_rom_with_checksum()
        # Corrupt it
        cal_off = rom.cal_page_offset
        rom.data[cal_off + 0xFFF8] = 0x00
        rom.data[cal_off + 0xFFF9] = 0x00
        cs = ChecksumManager(rom)
        assert not cs.verify().main_ok
        cs.fix()
        assert cs.verify().main_ok

    def test_fix_marks_rom_modified(self):
        rom, _ = make_rom_with_checksum()
        cal_off = rom.cal_page_offset
        rom.data[cal_off + 0xFFF8] ^= 0x01  # corrupt
        cs = ChecksumManager(rom)
        cs.fix()
        assert rom.is_modified

    def test_complement_stored_correctly(self):
        rom, expected_sum = make_rom_with_checksum()
        cs = ChecksumManager(rom)
        cs.fix()  # re-fix to ensure complement is written
        cal_off = rom.cal_page_offset
        storage = cal_off + 0xFFF8
        stored_sum  = struct.unpack_from('<I', rom.data, storage)[0]
        stored_comp = struct.unpack_from('<I', rom.data, storage + 4)[0]
        assert (stored_sum + stored_comp) & 0xFFFFFFFF == 0xFFFFFFFF
        # Or equivalently:
        assert (~stored_sum & 0xFFFFFFFF) == stored_comp

    def test_summary_string(self):
        rom, _ = make_rom_with_checksum()
        cs = ChecksumManager(rom)
        result = cs.verify()
        summary = result.summary()
        assert 'Main checksum' in summary
        assert '✓' in summary

    def test_256k_rom_cal_page(self):
        data = bytearray([0x55] * 0x40000)
        cal_off = 0x30000
        storage = cal_off + 0xFFF8
        data[storage:storage+8] = b'\x00' * 8

        total = 0
        for i in range(cal_off, storage - 1, 2):
            total += data[i] | (data[i+1] << 8)
        total &= 0xFFFFFFFF
        comp = (~total) & 0xFFFFFFFF
        struct.pack_into('<I', data, storage, total)
        struct.pack_into('<I', data, storage + 4, comp)

        rom = ROMImage(data=data)
        cs  = ChecksumManager(rom)
        result = cs.verify()
        assert result.main_found
        assert result.main_ok


class TestWordSum:
    def test_word_sum_simple(self):
        """Word sum of known bytes matches hand calculation."""
        rom = ROMImage(data=bytearray(0x80000))
        # Write known pattern in cal page
        cal = rom.cal_page_offset
        rom.data[cal]   = 0x01
        rom.data[cal+1] = 0x00   # word = 0x0001
        rom.data[cal+2] = 0x02
        rom.data[cal+3] = 0x00   # word = 0x0002
        cs = ChecksumManager(rom)
        # Sum bytes [cal..cal+3] = 0x0001 + 0x0002 = 3
        s = cs._word_sum(cal, cal + 3)
        assert s == 3

    def test_word_sum_wraps_32bit(self):
        rom = ROMImage(data=bytearray([0xFF] * 0x80000))
        cs = ChecksumManager(rom)
        # Large sum should wrap to 32-bit
        s = cs._word_sum(0, 0x3FF)
        assert s == s & 0xFFFFFFFF


class TestChecksumResult:
    def test_all_ok_with_correct_rom(self):
        rom, _ = make_rom_with_checksum()
        cs = ChecksumManager(rom)
        result = cs.verify()
        assert result.all_ok

    def test_multipoint_ok_when_not_found(self):
        """If multipoint needle not found, multipoint_ok should be True."""
        rom, _ = make_rom_with_checksum()
        cs = ChecksumManager(rom)
        result = cs.verify()
        # No multipoint needle in synthetic ROM
        assert not result.multipoint_found
        assert result.multipoint_ok
