"""Tests for ECU identification."""
import pytest
from meseventool.rom import ROMImage
from meseventool.ecu_id import identify, ECUIdentity


def make_rom(size=0x80000, fill=0xFF):
    return ROMImage(data=bytearray([fill] * size))


def rom_with_string(s: str, offset: int = 0x1000) -> ROMImage:
    rom = make_rom()
    enc = s.encode('ascii')
    rom.data[offset:offset+len(enc)] = enc
    return rom


class TestECUIdentify:
    def test_returns_identity(self):
        rom = make_rom()
        ident = identify(rom)
        assert isinstance(ident, ECUIdentity)

    def test_rom_size_set(self):
        rom = make_rom(0x80000)
        ident = identify(rom)
        assert ident.rom_size_kb == 512

    def test_256k_size(self):
        rom = make_rom(0x40000)
        ident = identify(rom)
        assert ident.rom_size_kb == 256

    def test_bosch_number_extracted(self):
        # Bosch number format: 0261XXXXXX (10 digits)
        rom = rom_with_string("0261207952", offset=0x5000)
        ident = identify(rom)
        assert ident.bosch_number == "0261207952"

    def test_vag_pn_extracted(self):
        rom = rom_with_string("06A906032GD", offset=0x6000)
        ident = identify(rom)
        assert "06A906032GD" in ident.part_number

    def test_engine_code_awp(self):
        rom = rom_with_string("1.8l T  180hp AWP ", offset=0x7000)
        ident = identify(rom)
        assert ident.engine_code == "AWP"

    def test_engine_code_aum(self):
        rom = rom_with_string("1.8l T  150hp AUM ", offset=0x7000)
        ident = identify(rom)
        assert ident.engine_code == "AUM"

    def test_engine_code_bam(self):
        rom = rom_with_string("1.8l T  225hp BAM ", offset=0x7000)
        ident = identify(rom)
        assert ident.engine_code == "BAM"

    def test_is_me75(self):
        rom = make_rom(0x80000)
        ident = identify(rom)
        assert ident.is_me75
        assert not ident.is_me71

    def test_is_me71(self):
        rom = make_rom(0x40000)
        ident = identify(rom)
        assert ident.is_me71
        assert not ident.is_me75

    def test_variant_falls_back_to_unknown(self):
        rom = make_rom()
        ident = identify(rom)
        # No strings → variant should still be a string
        assert isinstance(ident.variant, str)

    def test_str_representation(self):
        rom = rom_with_string("0261207952", 0x5000)
        ident = identify(rom)
        s = str(ident)
        assert "Bosch HW" in s
        assert "ROM size" in s

    def test_no_crash_on_empty_rom(self):
        rom = make_rom(fill=0x00)
        ident = identify(rom)
        assert ident is not None
