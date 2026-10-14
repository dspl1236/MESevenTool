"""
Review items C4–C9: identification edge cases.
"""
import pytest
from meseventool.rom import ROMImage
from meseventool.dpp import DPPValues
from meseventool.ecu_id import ECUIdentity, identify, identify_from_filename
from meseventool.profiles import (PROFILE_UNKNOWN, PROFILE_AWP, PROFILE_V6_27T_ME71,
                                  detect_profile, detect_rom_profile)
from tests.rom_corpus import find_rom


def _rom(strings, size=0x100000):
    rom = ROMImage(data=bytearray([0xFF]) * size)
    off = 0x1000
    for s in strings:
        enc = s.encode("ascii")
        rom.data[off:off + len(enc)] = enc
        off += len(enc) + 0x100          # separate runs
    return rom


# ── C8: version string leading field ─────────────────────────────────────────

class TestVersionString:
    @pytest.mark.parametrize("vs", ["40/1/ME7.5/3/4019.20", "36/1/ME7.5/5/4018.10",
                                    "39/1/ME7.5/51/X505R", "41/1/ME7.1/120/F1031",
                                    "45/1/ME7.1.1/120/C1103", "41/1/ME7.1.1/5/A1105A"])
    def test_any_two_digit_lead(self, vs):
        assert identify(_rom([vs + "//24b/Dst03o/280800"])).version_string.startswith(vs)

    def test_tuner_file_in_corpus(self):
        """Unitronic 630HN carries '41/1/ME7.5/51/4019.0…', missed before."""
        path = find_rom("uni_630HN.bin")
        if not path:
            pytest.skip("uni_630HN.bin")
        ident = identify(ROMImage.load(path))
        assert ident.version_string.startswith("41/1/ME7.5")
        assert ident.ecu_hw == "ME7.5"


# ── C9: generation from the version string ───────────────────────────────────

class TestGenerationFlags:
    def test_1mb_me711_is_not_me75(self):
        ident = ECUIdentity(rom_size_kb=1024, version_string="42/1/ME7.1.1/5/6030.03")
        assert ident.ecu_hw == "ME7.1.1"
        assert ident.is_me71 and not ident.is_me75

    def test_size_fallback_without_version(self):
        assert ECUIdentity(rom_size_kb=512).is_me75
        assert ECUIdentity(rom_size_kb=256).is_me71
        assert ECUIdentity(rom_size_kb=1024).is_me75

    def test_me75_by_version(self):
        ident = ECUIdentity(rom_size_kb=1024, version_string="40/1/ME7.5/3/4019.20")
        assert ident.is_me75 and not ident.is_me71


# ── C7: filename parsing ─────────────────────────────────────────────────────

class TestFilename:
    @pytest.mark.parametrize("name,pn", [
        ("06A906032BN_OEM.bin", "06A906032BN"),
        ("8D0907551M_oem.bin", "8D0907551M"),
        ("4Z7907551AA.bin", "4Z7907551AA"),
        ("022906032CP.bin", "022906032CP"),
        ("021906018R_Golf_AFP_12V_fw6228.bin", "021906018R"),
        ("4D1907558-0002.bin", "4D1907558"),
        ("Audi S4 2.7T 265HP 8D0907551A 0261206110 352345.bin", "8D0907551A"),
        ("VW Golf4 1.8T 06A906032DL 0261206890 354821 Original.bin", "06A906032DL"),
    ])
    def test_families(self, name, pn):
        assert identify_from_filename(name).vmecuhn == pn

    def test_bosch_and_serial_numbers_are_not_part_numbers(self):
        assert identify_from_filename("0261206890_1037358134.bin").vmecuhn == ""


# ── C6: part-number vote ─────────────────────────────────────────────────────

class TestPartNumberVote:
    def test_suffixed_form_beats_bare_base(self):
        rom = _rom(["06A906032 ", "06A906032 ", "06A906032 ", "06A906032DL 1.8L R4/5VT"])
        assert identify(rom).vmecuhn == "06A906032DL"

    def test_family_majority_wins_over_single_other_family(self):
        rom = _rom(["06A906032DL 1.8L", "06A906032DL", "4B0907551AA"])
        assert identify(rom).vmecuhn == "06A906032DL"

    def test_bare_base_used_when_nothing_else(self):
        assert identify(_rom(["06A906032 "])).vmecuhn == "06A906032"


# ── C5: engine code only from descriptor-like runs ───────────────────────────

class TestEngineCodeScan:
    def test_spurious_code_in_ordinary_text_ignored(self):
        rom = _rom(["PLEASE ACK THE MESSAGE NOW", "06A906032DL 1.8L R4/5VT AWW"])
        ident = identify(rom)
        assert ident.engine_code == "AWW"

    def test_suffix_fallback_not_blocked_by_spurious_hit(self):
        rom = _rom(["PLEASE ACK THE MESSAGE NOW", "06A906032DL "])
        ident = identify(rom)
        assert ident.engine_code == "AWW"          # from the DL suffix map

    def test_descriptor_with_power_rating(self):
        assert identify(_rom(["1.8l T  180hp AWP "])).engine_code == "AWP"


# ── C4: no DPP fallback; Bosch number recovers a wiped part number ───────────

class TestNoDppGuess:
    def test_no_pn_is_unknown(self):
        assert detect_profile(ECUIdentity(), DPPValues(dpp1=0x0200)) is PROFILE_UNKNOWN
        assert detect_profile(ECUIdentity(version_string="40/1/ME7.1/5/6005.01"),
                              DPPValues(dpp1=0x0205)) is PROFILE_UNKNOWN

    def test_pn_still_detects_without_dpp(self):
        assert detect_profile(ECUIdentity(vmecuhn="8D0907551M",
                                          version_string="40/1/ME7.1/5/6005.01"),
                              DPPValues()) is PROFILE_V6_27T_ME71

    def test_bosch_number_recovers_part_number(self):
        """Catalogue Bosch number 0261206890 → 06A906032DL when the PN string is gone."""
        rom = _rom(["0261206890", "40/1/ME7.5/3/4019.20//24b/Dst03o/280800"])
        ident = identify(rom)
        assert ident.vmecuhn == "06A906032DL"
        assert ident.source == "rom+bosch"
        assert detect_rom_profile(ident, DPPValues()) is not PROFILE_UNKNOWN
        assert detect_rom_profile(ident, DPPValues()).name == PROFILE_AWP.name

    def test_unknown_bosch_number_stays_unknown(self):
        rom = _rom(["0261200000", "40/1/ME7.5/3/4019.20"])
        ident = identify(rom)
        assert ident.vmecuhn == ""
        assert detect_profile(ident, DPPValues(dpp1=0x0200)) is PROFILE_UNKNOWN
