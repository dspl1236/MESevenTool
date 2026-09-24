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
    FixedAddressScalarDef, PatchCategory, PatchState, detect_all,
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
        p = _patch("Catalyst Monitor Disable CDKAT (4B0906018")
        assert p.detect(rom, profile=PROFILE_06B).state == PatchState.NOT_APPLICABLE

    def test_matching_part_number_applies(self):
        """Previously hidden in the GUI even on the ECU it was written for."""
        rom = _rom()
        prof = detect_rom_profile(ECUIdentity(vmecuhn="4B0906018CM"), DPPValues())
        p = _patch("Catalyst Monitor Disable CDKAT (4B0906018")
        r = p.detect(rom, profile=prof)
        assert r.state == PatchState.STOCK
        assert prof.patch_applies(p)
        assert p.apply(rom, r)
        assert rom.data[p.fixed_addr] == 0x00

    def test_other_part_number_not_applicable(self):
        rom = _rom()
        prof = detect_rom_profile(ECUIdentity(vmecuhn="06A906018CG"), DPPValues())
        p = FixedAddressPatchDef(
            name="test-only", description="test-only",
            category=PatchCategory.EMISSIONS, fixed_addr=0x100,
            stock_bytes=bytes([0x01]), patch_bytes=bytes([0x00]),
            applies_to={"me7.1", "06a906018r"})
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

def _scalar():
    """Test-only rev limit + linked hard cut, modelled on NMAXDV/NMAXF."""
    return FixedAddressScalarDef(
        name="test-only rev limit", description="test-only",
        category=PatchCategory.PERFORMANCE,
        fixed_addr=0x0693A, size=2, big_endian=True, scale=40.0, unit="RPM",
        min_val=4000.0, max_val=9000.0,
        applies_to={"me7.1", "1.8t", "06a906018cg"},
        linked_name="NMAXF", linked_addr=0x069EC,
        linked_scale=0.25, linked_delta=300.0)


class TestFixedAddressScalar:

    def _profile(self):
        return detect_rom_profile(ECUIdentity(vmecuhn="06A906018CG"), DPPValues())

    def _rom_with_raw(self, raw, nmaxf_raw=None):
        """Rev-limit raw count (×40 RPM); linked value defaults to +300 RPM."""
        rom = _rom(0x00)
        s = _scalar()
        if nmaxf_raw is None:
            nmaxf_raw = int((raw * 40 + 300) / 0.25)
        rom.data[s.fixed_addr:s.fixed_addr + 2] = raw.to_bytes(2, 'big')
        rom.data[s.linked_addr:s.linked_addr + 2] = nmaxf_raw.to_bytes(2, 'big')
        return rom

    def test_reads_plausible_value(self):
        s = _scalar()
        assert s.read(self._rom_with_raw(170), profile=self._profile()) == 6800.0

    def test_implausible_value_hidden(self):
        """0x0101 × 40 = 10280 RPM > 9000 max — site doesn't hold NMAXDV."""
        s = _scalar()
        rom = _rom(0x01)
        prof = self._profile()
        assert s.read(rom, profile=prof) is None
        before = bytes(rom.data)
        assert not s.write(rom, 7000, profile=prof)
        assert bytes(rom.data) == before

    def test_needs_part_number_profile(self):
        s = _scalar()
        rom = self._rom_with_raw(170)
        assert s.read(rom) is None
        assert s.read(rom, profile=PROFILE_AGU_ME71) is None
        assert not s.write(rom, 7000)

    def test_write_roundtrip(self):
        s = _scalar()
        rom = self._rom_with_raw(170)
        prof = self._profile()
        assert s.write(rom, 7000, profile=prof)
        assert rom.data[s.fixed_addr:s.fixed_addr + 2] == (175).to_bytes(2, 'big')
        assert s.read(rom, profile=prof) == 7000.0

    def test_write_keeps_nmaxf_300_above(self):
        """Raising NMAXDV must move the NMAXF hard cut with it."""
        s = _scalar()
        rom = self._rom_with_raw(170)
        assert s.read_linked(rom) == 7100.0
        assert s.write(rom, 7400, profile=self._profile())
        assert s.read_linked(rom) == 7700.0
        assert rom.data[s.linked_addr:s.linked_addr + 2] == (30800).to_bytes(2, 'big')

    def test_implausible_nmaxf_hidden(self):
        """A plausible NMAXDV alone isn't enough — NMAXF must look right too."""
        s = _scalar()
        rom = self._rom_with_raw(170, nmaxf_raw=0x0101)   # 64.25 RPM
        prof = self._profile()
        assert s.read(rom, profile=prof) is None
        before = bytes(rom.data)
        assert not s.write(rom, 7000, profile=prof)
        assert bytes(rom.data) == before

    def test_write_rejects_out_of_range(self):
        s = _scalar()
        assert not s.write(self._rom_with_raw(170), 9500, profile=self._profile())


# ── Removed M3.8 / M5.9 entries ──────────────────────────────────────────────

def test_no_m38x_datasheet_entries_in_catalogue():
    """M3.8.x / M5.9.x addresses live in docs/m38x_codeword_addresses.md, not
    in the ME7 catalogue."""
    for p in ALL_PATCHES + ALL_SCALAR_PATCHES:
        assert "M38x M592 Function Datasheet" not in p.notes, p.name
        for tag in ("4b0907557b", "4b0907557p", "4b0907558m",
                    "06a906018r", "06a906018cg", "06a906018cj"):
            assert tag not in p.applies_to, p.name


# ── Packaging ────────────────────────────────────────────────────────────────

def test_setup_version_matches_package():
    out = subprocess.run([sys.executable, "setup.py", "--version"],
                         cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    assert out.stdout.strip().splitlines()[-1] == __version__
