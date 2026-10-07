"""Tests for the checksum layer on synthetic ROMs with a real needle layout."""
import struct
import pytest
from meseventool.rom import ROMImage
from meseventool.checksum import ChecksumManager, calc_sum_block, calc_crc32
from tests.synthetic_rom import (make_rom_with_checksum, main_sum_offset,
                           multi_blocks, word_sum)


class TestMainChecksum:
    def test_verify_correct_checksum(self):
        rom = make_rom_with_checksum()
        result = ChecksumManager(rom).verify()
        assert result.main_found
        assert len(result.main_regions) == 1
        assert result.main_regions[0].ok
        assert result.main_ok
        assert result.main.offset == main_sum_offset(rom.size)
        assert result.main.regions == [(0x0, 0xFBFF), (0x20000, rom.size - 1)]

    def test_verify_corrupted_stored_value(self):
        rom = make_rom_with_checksum()
        rom.data[main_sum_offset(rom.size)] ^= 0xFF
        result = ChecksumManager(rom).verify()
        assert result.main_found
        assert not result.main_regions[0].ok
        assert not result.main_ok

    def test_verify_corrupted_cal_data(self):
        rom = make_rom_with_checksum()
        rom.data[rom.cal_page_offset + 0x100] ^= 0x01
        result = ChecksumManager(rom).verify()
        assert not result.main_ok
        assert not result.multipoint_ok          # block 3 covers that byte
        assert result.multi.n_bad == 1

    def test_fix_restores_correct_checksum(self):
        rom = make_rom_with_checksum()
        off = main_sum_offset(rom.size)
        rom.data[off:off + 2] = b'\x00\x00'
        cs = ChecksumManager(rom)
        assert not cs.verify().main_ok
        result = cs.fix()
        assert result.all_ok
        assert cs.verify().all_ok

    def test_fix_marks_rom_modified(self):
        rom = make_rom_with_checksum()
        rom.data[main_sum_offset(rom.size)] ^= 0x01
        ChecksumManager(rom).fix()
        assert rom.is_modified

    def test_fix_on_valid_rom_writes_nothing(self):
        rom = make_rom_with_checksum()
        ChecksumManager(rom).fix()
        assert not rom.is_modified

    def test_complement_stored_correctly(self):
        rom = make_rom_with_checksum()
        rom.data[0x100] ^= 0x55
        ChecksumManager(rom).fix()
        off = main_sum_offset(rom.size)
        s, c = struct.unpack_from('<II', rom.data, off)
        assert (~s & 0xFFFFFFFF) == c

    def test_stored_value_matches_independent_sum(self):
        rom = make_rom_with_checksum()
        res = ChecksumManager(rom).verify()
        expected = (word_sum(rom.data, 0, 0xFBFF)
                    + word_sum(rom.data, 0x20000, rom.size - 1)) & 0xFFFFFFFF
        assert res.main.calc == expected == res.main.stored

    def test_summary_string(self):
        rom = make_rom_with_checksum()
        summary = ChecksumManager(rom).verify().summary()
        assert 'Main checksum' in summary
        assert 'Multipoint' in summary
        assert 'CRC32' in summary
        assert '✓' in summary and '✗' not in summary

    @pytest.mark.parametrize("size", [0x40000, 0x80000, 0x100000])
    def test_all_sizes(self, size):
        rom = make_rom_with_checksum(size)
        result = ChecksumManager(rom).verify()
        assert result.main_found and result.main_ok
        assert result.multipoint_found and result.multipoint_ok
        assert result.all_ok


class TestMultipoint:
    def test_table_located_and_verified(self):
        rom = make_rom_with_checksum()
        res = ChecksumManager(rom).verify().multi
        assert res.found
        assert res.count == 4
        assert [(b.start, b.end) for b in res.blocks] == multi_blocks(rom.size)
        assert res.all_ok and res.n_ok == 4

    def test_fix_multipoint_block(self):
        rom = make_rom_with_checksum()
        rom.data[0x4100] ^= 0xFF          # block 2, outside the main regions? no: region 1
        cs = ChecksumManager(rom)
        before = cs.verify()
        assert not before.multipoint_ok and before.multi.n_bad == 1
        assert not before.main_ok
        after = cs.fix()
        assert after.all_ok
        blk = after.multi.blocks[1]
        assert blk.stored_sum == blk.calc_sum == word_sum(rom.data, 0x4000, 0x7FFF)

    def test_is_word_sum_not_crc32(self):
        rom = make_rom_with_checksum()
        blk = ChecksumManager(rom).verify().multi.blocks[0]
        assert blk.calc_sum == word_sum(rom.data, 0, 0x3FFF)
        assert blk.calc_sum != calc_crc32(rom, 0, 0x3FFF)


class TestNeedleMissing:
    def test_plain_rom_is_not_verified(self):
        """No needles at all: nothing is 'OK', nothing is written."""
        rom = ROMImage(data=bytearray([0xAA]) * 0x80000)
        cs = ChecksumManager(rom)
        result = cs.verify()
        assert not result.main_found
        assert not result.main_ok
        assert result.main.note
        assert not result.multipoint_found
        assert not result.crc_found
        assert not result.all_ok
        cs.fix()
        assert not rom.is_modified
        assert 'not verified' in result.summary()

    def test_multipoint_absent_is_ok(self):
        """Absent multipoint layer (both needles missing) does not fail all_ok."""
        rom = make_rom_with_checksum()
        T = rom.size - 0x1000
        rom.data[T + 0xC0:T + 0xC0 + 46] = bytes(46)     # count needle
        rom.data[T + 0x100:T + 0x100 + 78] = bytes(78)   # table needle
        ChecksumManager(rom).fix()                      # main pair now stale
        result = ChecksumManager(rom).verify()
        assert not result.multipoint_found
        assert result.multipoint_ok
        assert result.all_ok

    def test_multipoint_partial_is_not_ok(self):
        """Count needle present but table needle missing: refuse to call it OK."""
        rom = make_rom_with_checksum()
        T = rom.size - 0x1000
        rom.data[T + 0x100:T + 0x100 + 78] = bytes(78)
        result = ChecksumManager(rom).verify()
        assert not result.multipoint_found
        assert result.multi.note
        assert not result.multipoint_ok
        assert not result.all_ok


class TestWordSum:
    def test_word_sum_simple(self):
        rom = ROMImage(data=bytearray(0x80000))
        cal = rom.cal_page_offset
        rom.data[cal:cal + 4] = b'\x01\x00\x02\x00'
        assert ChecksumManager(rom)._word_sum(cal, cal + 3) == 3

    def test_inclusive_of_end_word(self):
        """fixsums.c sums words start//2 .. end//2 inclusive."""
        rom = ROMImage(data=bytearray(0x80000))
        rom.data[0:6] = b'\x01\x00\x02\x00\x04\x00'
        assert calc_sum_block(rom, 0, 3) == 3
        assert calc_sum_block(rom, 0, 4) == 7      # even end includes word at 4
        assert calc_sum_block(rom, 0, 5) == 7
        assert calc_sum_block(rom, 1, 5) == 7      # odd start rounds down

    def test_word_sum_wraps_32bit(self):
        rom = ROMImage(data=bytearray([0xFF] * 0x80000))
        s = ChecksumManager(rom)._word_sum(0, 0x3FF)
        assert s == 0xFFFF * 0x200


class TestChecksumResult:
    def test_all_ok_with_correct_rom(self):
        rom = make_rom_with_checksum()
        assert ChecksumManager(rom).verify().all_ok

    def test_fix_returns_fresh_verify(self):
        rom = make_rom_with_checksum()
        rom.data[0x10] ^= 0x0F
        result = ChecksumManager(rom).fix()
        assert result.all_ok
        assert result.main.stored == result.main.calc
