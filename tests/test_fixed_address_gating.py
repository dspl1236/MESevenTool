"""
Part-number gating for fixed-address patches and scalars.

Fixed-address patches have no needle to prove they're looking at the right
ECU, so a patch tied to a part number must only fire on a ROM whose profile
carries that part number — and never when no profile is given.
"""

import os
import subprocess
import sys

from meseventool.dpp import DPPValues
from meseventool.ecu_id import ECUIdentity, part_number_tags, is_part_number_tag
from meseventool.patches import (
    ALL_PATCHES, ALL_SCALAR_PATCHES, FixedAddressPatchDef,
    FixedAddressScalarDef, PatchState, detect_all,
)
from meseventool.profiles import (
    PROFILE_AGU_ME71, PROFILE_06B, detect_profile, detect_rom_profile,
)
from meseventool.rom import ROMImage
from meseventool.version import __version__

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rom(fill=0x01, size=0x40000):
    return ROMImage(data=bytearray([fill] * size))


def _patch(name_fragment):
    return next(p for p in ALL_PATCHES if name_fragment in p.name)


def _scalar(name_fragment):
    return next(p for p in ALL_SCALAR_PATCHES if name_fragment in p.name)


def _pn_gated_fixed_patches():
    return [p for p in ALL_PATCHES
            if isinstance(p, FixedAddressPatchDef)
            and any(is_part_number_tag(t) for t in p.applies_to)]


# ── Part-number tags ──────────────────────────────────────────────────────────

class TestPartNumberTags:

    def test_full_and_base_tag(self):
        assert part_number_tags("06A906018CG") == {"06a906018cg", "06a906018"}

    def test_normalises_case_and_spaces(self):
        assert part_number_tags(" 4b0 906 018 cm ") == {"4b0906018cm", "4b0906018"}

    def test_rejects_non_part_numbers(self):
        assert part_number_tags("") == set()
        assert part_number_tags("0261206890") == set()   # Bosch HW number

    def test_platform_tags_are_not_part_numbers(self):
        for tag in ("me7.1", "me7.5", "1.8t", "turbo", "narrowband", "bosch_hfm5"):
            assert not is_part_number_tag(tag)
        for tag in ("4b0906018", "4z7907551", "06a906018cg", "4b0907558m"):
            assert is_part_number_tag(tag)


class TestProfileWithPartNumber:

    def test_adds_tags_without_touching_shared_profile(self):
        before = set(PROFILE_AGU_ME71.platforms)
        tagged = PROFILE_AGU_ME71.with_part_number("06A906018CG")
        assert {"06a906018cg", "06a906018"} <= tagged.platforms
        assert PROFILE_AGU_ME71.platforms == before
        assert tagged.name == PROFILE_AGU_ME71.name

    def test_no_part_number_returns_same_profile(self):
        assert PROFILE_AGU_ME71.with_part_number("") is PROFILE_AGU_ME71

    def test_detect_rom_profile_tags_part_number(self):
        ident = ECUIdentity(vmecuhn="06A906018CG")
        prof = detect_rom_profile(ident, DPPValues())
        assert prof.name == detect_profile(ident, DPPValues()).name
        assert "06a906018cg" in prof.platforms


# ── Fixed-address patch gating ───────────────────────────────────────────────

class TestFixedAddressGating:

    def test_pn_gated_patches_not_applicable_without_profile(self):
        """Previously every one of these reported STOCK on a 0x01-filled ROM."""
        rom = _rom()
        gated = _pn_gated_fixed_patches()
        assert gated
        for p in gated:
            assert p.detect(rom).state == PatchState.NOT_APPLICABLE, p.name

    def test_detect_all_without_profile_skips_pn_gated(self):
        rom = _rom()
        gated = {p.name for p in _pn_gated_fixed_patches()}
        for r in detect_all(rom):
            if r.patch.name in gated:
                assert r.state == PatchState.NOT_APPLICABLE

    def test_family_profile_without_part_number_not_applicable(self):
        rom = _rom()
        p = _patch("CDTES (06A906018CG")
        assert p.detect(rom, profile=PROFILE_AGU_ME71).state == PatchState.NOT_APPLICABLE

    def test_matching_part_number_applies(self):
        """Previously hidden in the GUI even on the ECU it was written for."""
        rom = _rom()
        prof = detect_rom_profile(ECUIdentity(vmecuhn="06A906018CG"), DPPValues())
        p = _patch("CDTES (06A906018CG")
        r = p.detect(rom, profile=prof)
        assert r.state == PatchState.STOCK
        assert prof.patch_applies(p)
        assert p.apply(rom, r)
        assert rom.data[p.fixed_addr] == 0x00

    def test_other_part_number_not_applicable(self):
        rom = _rom()
        prof = detect_rom_profile(ECUIdentity(vmecuhn="06A906018CG"), DPPValues())
        p = _patch("CDTES (06A906018R")
        assert p.detect(rom, profile=prof).state == PatchState.NOT_APPLICABLE
        assert not prof.patch_applies(p)

    def test_base_part_number_tag_matches_suffixed_ecu(self):
        """4B0906018 patches are gated on the 9-char base; a CM ROM must match."""
        rom = ROMImage(data=bytearray(0x100000))
        p = _patch("Catalyst Monitor Disable CDKAT (4B0906018")
        rom.data[p.fixed_addr] = p.stock_bytes[0]
        prof = PROFILE_06B.with_part_number("4B0906018CM")
        assert p.detect(rom, profile=prof).state == PatchState.STOCK

    def test_family_gated_fixed_patch_unchanged_without_profile(self):
        """Non-part-number fixed patches keep their no-profile behaviour."""
        rom = ROMImage(data=bytearray(0x100000))
        p = _patch("5th-Gear Torque Mode Disable")
        rom.data[p.fixed_addr] = 0x0F
        assert p.detect(rom).state == PatchState.STOCK


# ── Fixed-address scalars ────────────────────────────────────────────────────

class TestFixedAddressScalar:

    NAME = "Rev Limit NMAXDV (06A906018CG"

    def _profile(self):
        return detect_rom_profile(ECUIdentity(vmecuhn="06A906018CG"), DPPValues())

    def _rom_with_raw(self, raw):
        rom = _rom(0x00)
        s = _scalar(self.NAME)
        rom.data[s.fixed_addr:s.fixed_addr + 2] = raw.to_bytes(2, 'big')
        return rom

    def test_nmaxdv_uses_fixed_address_type(self):
        for s in ALL_SCALAR_PATCHES:
            if "NMAXDV" in s.name:
                assert isinstance(s, FixedAddressScalarDef), s.name

    def test_reads_plausible_value(self):
        s = _scalar(self.NAME)
        assert s.read(self._rom_with_raw(170), profile=self._profile()) == 6800.0

    def test_implausible_value_hidden(self):
        """0x0101 × 40 = 10280 RPM > 9000 max — site doesn't hold NMAXDV."""
        s = _scalar(self.NAME)
        rom = _rom(0x01)
        prof = self._profile()
        assert s.read(rom, profile=prof) is None
        before = bytes(rom.data)
        assert not s.write(rom, 7000, profile=prof)
        assert bytes(rom.data) == before

    def test_needs_part_number_profile(self):
        s = _scalar(self.NAME)
        rom = self._rom_with_raw(170)
        assert s.read(rom) is None
        assert s.read(rom, profile=PROFILE_AGU_ME71) is None
        assert not s.write(rom, 7000)

    def test_write_roundtrip(self):
        s = _scalar(self.NAME)
        rom = self._rom_with_raw(170)
        prof = self._profile()
        assert s.write(rom, 7000, profile=prof)
        assert rom.data[s.fixed_addr:s.fixed_addr + 2] == (175).to_bytes(2, 'big')
        assert s.read(rom, profile=prof) == 7000.0

    def test_write_rejects_out_of_range(self):
        s = _scalar(self.NAME)
        assert not s.write(self._rom_with_raw(170), 9500, profile=self._profile())


# ── Confidence of datasheet-only entries ─────────────────────────────────────

def test_m38x_datasheet_entries_not_confirmed():
    """Values from the M38x datasheet alone haven't been tested on real ROMs."""
    entries = [p for p in ALL_PATCHES + ALL_SCALAR_PATCHES
               if "M38x M592 Function Datasheet" in p.notes]
    assert len(entries) >= 20
    for p in entries:
        assert p.confidence == "PROVISIONAL", p.name
        assert p.warning, p.name


# ── Packaging ────────────────────────────────────────────────────────────────

def test_setup_version_matches_package():
    out = subprocess.run([sys.executable, "setup.py", "--version"],
                         cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == __version__
