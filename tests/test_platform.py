"""
tests/test_platform.py
======================
Tests for platform-based patch applicability filtering.

Covers:
  - ROMProfile.platforms tag set auto-construction
  - patch_applies() with patch objects (new-style)
  - patch_applies() with 4-list legacy calling convention
  - PatchDef.applies_to migration from requires_* fields
  - detect_all() with profile returns NOT_APPLICABLE for mismatched patches
  - N/A induction blocks turbo patches
  - Wideband O2 blocks narrowband patches
  - FSI fuel_system blocks MPI patches
  - Universal patches (empty applies_to) always apply
"""

import pytest
from meseventool.patches import (
    PatchDef, ScalarPatchDef, PatchState, PatchCategory,
    ALL_PATCHES, ALL_SCALAR_PATCHES, detect_all,
)
from meseventool.profiles import (
    ROMProfile, PROFILE_AWP, PROFILE_UNKNOWN,
    ALL_PROFILES, detect_profile,
)
from meseventool.ecu_id import ECUIdentity
from meseventool.dpp import DPPValues
from meseventool.rom import ROMImage
from meseventool.needle import MASK, XXXX

XX = XXXX
MM = MASK


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_rom():
    return ROMImage(data=bytearray([0xFF] * 0x80000))


def make_profile(**kwargs) -> ROMProfile:
    """Build a minimal ROMProfile with only the fields we care about."""
    defaults = dict(
        name="Test",
        part_prefixes=["TEST000000"],
        rom_size=0x80000,
        ecu_hw="ME7.5",
        variants=[],
    )
    defaults.update(kwargs)
    return ROMProfile(**defaults)


def make_patch(applies_to=None, requires_induction=None,
               requires_lambda=None, requires_fuel=None) -> PatchDef:
    """Build a minimal PatchDef."""
    kw = dict(
        name="test_patch",
        description="test",
        category=PatchCategory.DIAGNOSTICS,
        needle=[0xE6, 0xF0, XX, XX],
        mask  =[MM,   MM,   XX, XX],
        offset=0,
        stock_bytes=b'\x00\x00',
        patch_bytes=b'\x01\x00',
    )
    if applies_to is not None:
        kw['applies_to'] = set(applies_to)
    if requires_induction is not None:
        kw['requires_induction'] = requires_induction
    if requires_lambda is not None:
        kw['requires_lambda'] = requires_lambda
    if requires_fuel is not None:
        kw['requires_fuel'] = requires_fuel
    return PatchDef(**kw)


# ── ROMProfile.platforms auto-construction ─────────────────────────────────────

class TestProfilePlatforms:
    def test_turbo_profile_has_turbo_tag(self):
        p = make_profile(induction="turbo")
        assert "turbo" in p.platforms

    def test_na_profile_has_na_tag(self):
        p = make_profile(induction="na")
        assert "na" in p.platforms
        assert "turbo" not in p.platforms

    def test_narrowband_tag(self):
        p = make_profile(o2_system="narrowband")
        assert "narrowband" in p.platforms
        assert "wideband"   not in p.platforms

    def test_wideband_tag(self):
        p = make_profile(o2_system="wideband")
        assert "wideband"   in p.platforms
        assert "narrowband" not in p.platforms

    def test_mpi_tag(self):
        p = make_profile(fuel_system="mpi")
        assert "mpi" in p.platforms
        assert "fsi" not in p.platforms

    def test_fsi_tag(self):
        p = make_profile(fuel_system="fsi")
        assert "fsi" in p.platforms
        assert "mpi" not in p.platforms

    def test_ecu_hw_lowercase_tag(self):
        p = make_profile(ecu_hw="ME7.5")
        assert "me7.5" in p.platforms

    def test_displacement_tag_from_variants(self):
        p = make_profile(variants=["AWP 1.8T 180hp"])
        assert "1.8t" in p.platforms

    def test_v6_tag(self):
        p = make_profile(variants=["2.7T biturbo V6"])
        assert "2.7t" in p.platforms

    def test_awp_profile_tags(self):
        tags = PROFILE_AWP.platforms
        assert "turbo"      in tags
        assert "narrowband" in tags
        assert "mpi"        in tags
        assert "me7.5"      in tags
        assert "1.8t"       in tags


# ── patch_applies() with patch objects ────────────────────────────────────────

class TestPatchAppliesObject:
    def test_universal_patch_applies_everywhere(self):
        patch = make_patch(applies_to=set())
        turbo  = make_profile(induction="turbo")
        na     = make_profile(induction="na")
        assert turbo.patch_applies(patch)
        assert na.patch_applies(patch)

    def test_turbo_patch_blocked_on_na(self):
        patch = make_patch(applies_to={"turbo"})
        na    = make_profile(induction="na")
        assert not na.patch_applies(patch)

    def test_turbo_patch_passes_on_turbo(self):
        patch = make_patch(applies_to={"turbo"})
        turbo = make_profile(induction="turbo")
        assert turbo.patch_applies(patch)

    def test_narrowband_patch_blocked_on_wideband(self):
        patch = make_patch(applies_to={"narrowband"})
        wb    = make_profile(o2_system="wideband")
        assert not wb.patch_applies(patch)

    def test_narrowband_patch_passes_on_nb(self):
        patch = make_patch(applies_to={"narrowband"})
        nb    = make_profile(o2_system="narrowband")
        assert nb.patch_applies(patch)

    def test_mpi_patch_blocked_on_fsi(self):
        patch = make_patch(applies_to={"mpi"})
        fsi   = make_profile(fuel_system="fsi")
        assert not fsi.patch_applies(patch)

    def test_multi_tag_patch_requires_all(self):
        """Patch requires BOTH turbo AND narrowband — wideband turbo blocked."""
        patch = make_patch(applies_to={"turbo", "narrowband"})
        turbo_wb = make_profile(induction="turbo", o2_system="wideband")
        turbo_nb = make_profile(induction="turbo", o2_system="narrowband")
        assert not turbo_wb.patch_applies(patch)
        assert     turbo_nb.patch_applies(patch)


# ── patch_applies() legacy 4-list calling convention ──────────────────────────

class TestPatchAppliesLegacy:
    def test_empty_lists_applies_everywhere(self):
        turbo = make_profile(induction="turbo")
        assert turbo.patch_applies([], [], [], [])

    def test_turbo_req_blocked_on_na(self):
        na = make_profile(induction="na")
        assert not na.patch_applies(["turbo"], [], [], [])

    def test_narrowband_req_blocked_on_wideband(self):
        wb = make_profile(o2_system="wideband")
        assert not wb.patch_applies([], ["narrowband"], [], [])

    def test_mpi_req_blocked_on_fsi(self):
        fsi = make_profile(fuel_system="fsi")
        assert not fsi.patch_applies([], [], ["MPI"], [])

    def test_mpi_req_case_insensitive(self):
        mpi = make_profile(fuel_system="mpi")
        assert mpi.patch_applies([], [], ["mpi"], [])
        assert mpi.patch_applies([], [], ["MPI"], [])


# ── PatchDef.applies_to migration from requires_* ─────────────────────────────

class TestAppliestoMigration:
    def test_requires_lambda_migrates(self):
        patch = make_patch(requires_lambda=["narrowband"])
        assert "narrowband" in patch.applies_to

    def test_requires_fuel_migrates(self):
        patch = make_patch(requires_fuel=["MPI"])
        assert "mpi" in patch.applies_to

    def test_requires_induction_migrates(self):
        patch = make_patch(requires_induction=["turbo"])
        assert "turbo" in patch.applies_to

    def test_explicit_applies_to_preserved(self):
        patch = make_patch(applies_to={"wideband"}, requires_fuel=["fsi"])
        assert "wideband" in patch.applies_to
        assert "fsi"      in patch.applies_to

    def test_universal_patch_empty_applies_to(self):
        patch = make_patch()   # no requires_* set
        assert patch.applies_to == set()


# ── Existing patches in catalogue ────────────────────────────────────────────

class TestCataloguePatches:

    def test_rear_o2_applies_to_awp(self):
        """Rear O2 delete should apply to AWP (NB MPI)."""
        o2_patch = next(p for p in ALL_PATCHES if "Rear O2" in p.name)
        assert PROFILE_AWP.patch_applies(o2_patch)


    def test_all_patches_valid_applies_to(self):
        """Every patch's applies_to contains only known tag strings."""
        known_tags = {
            "turbo", "na", "narrowband", "wideband",
            "mpi", "fsi", "tfsi",
            "me7.5", "me7.1", "me7.1.1", "me7",
            "bosch_hfm5", "hitachi",
            "dual_bank",
            "1.8t", "2.0t", "2.7t", "3.0t", "v6", "v8",
            "4b0906018", "me7.1.1", "2.7t", "4z7907551",
        }
        for p in ALL_PATCHES + ALL_SCALAR_PATCHES:
            for tag in p.applies_to:
                assert tag in known_tags, \
                    f"Patch '{p.name}' has unknown tag '{tag}'"


class TestProfileNewFields:
    def test_dual_bank_false_by_default(self):
        p = make_profile()
        assert p.dual_bank is False

    def test_dual_bank_true_on_v6_biturbo(self):
        from meseventool.profiles import PROFILE_V6_2_7T
        assert PROFILE_V6_2_7T.dual_bank is True
        assert "dual_bank" in PROFILE_V6_2_7T.platforms

    def test_maf_type_default_bosch(self):
        p = make_profile()
        assert p.maf_type == "bosch_hfm5"
        assert "bosch_hfm5" in p.platforms

    def test_maf_type_hitachi_tag(self):
        p = make_profile(maf_type="hitachi")
        assert "hitachi" in p.platforms
        assert "bosch_hfm5" not in p.platforms

    def test_awp_has_bosch_maf_tag(self):
        from meseventool.profiles import PROFILE_AWP
        assert "bosch_hfm5" in PROFILE_AWP.platforms

    def test_na_v6_is_not_dual_bank(self):
        from meseventool.profiles import PROFILE_NA_V6
        assert PROFILE_NA_V6.dual_bank is False


# ── detect_all() with profile ─────────────────────────────────────────────────

class TestDetectAllWithProfile:
    def test_na_profile_marks_turbo_patches_na(self):
        rom = make_rom()
        na_profile = make_profile(induction="na", o2_system="narrowband",
                                   fuel_system="mpi")
        # Any patch with applies_to={"turbo"} should be NOT_APPLICABLE
        turbo_patch = make_patch(applies_to={"turbo"})
        result = turbo_patch.detect(rom, profile=na_profile)
        assert result.state == PatchState.NOT_APPLICABLE

    def test_no_profile_returns_missing_not_na(self):
        """Without a profile, turbo patches should be MISSING (needle absent),
        not NOT_APPLICABLE."""
        rom = make_rom()
        turbo_patch = make_patch(applies_to={"turbo"})
        result = turbo_patch.detect(rom, profile=None)
        assert result.state == PatchState.MISSING

    def test_detect_all_with_na_profile(self):
        """detect_all with an NA profile should return some NOT_APPLICABLE."""
        rom = make_rom()
        # Build patch with turbo requirement
        turbo_patch = make_patch(applies_to={"turbo"})
        na_profile  = make_profile(induction="na")
        result = turbo_patch.detect(rom, profile=na_profile)
        assert result.state == PatchState.NOT_APPLICABLE

    def test_detect_all_awp_profile_no_na(self):
        """AWP is turbo NB MPI single-bank — the only NOT_APPLICABLE results
        should be for patches that explicitly require 'dual_bank'."""
        from meseventool.patches import ALL_PATCHES
        rom     = make_rom()
        results = detect_all(rom, profile=PROFILE_AWP)
        for r in results:
            if r.state == PatchState.NOT_APPLICABLE:
                # Patches are N/A on AWP when they require a platform tag not in AWP.
                # Valid reasons: 'dual_bank', or any platform tag (e.g. '2.7t') that
                # AWP doesn't carry.
                awp_platforms = set(PROFILE_AWP.platforms)
                patch_requires = set(r.patch.applies_to)
                assert patch_requires and not patch_requires.issubset(awp_platforms), \
                    (f"Patch '{r.patch.name}' returned NOT_APPLICABLE for AWP "
                     f"but applies_to={r.patch.applies_to} should match AWP platforms {awp_platforms}")


# ── ECU ID and profile detection — corpus tests ───────────────────────────────

class TestECUIdentityVersionString:
    """version_string field populated by identify() from ROM content."""

    def _make_rom_with_vs(self, vs_bytes):
        import io
        from meseventool.rom import ROMImage
        data = bytearray(0x100000)
        pos  = 0x010007
        data[pos:pos+len(vs_bytes)] = vs_bytes
        # ROMImage.load reads from a file-like; use a temp file
        import tempfile, os
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
            f.write(data); tmp = f.name
        try:
            rom = ROMImage.load(tmp)
        finally:
            os.unlink(tmp)
        return rom

    def test_me75_version_string_extracted(self):
        from meseventool.ecu_id import identify
        vs = b'40/1/ME7.5/3/4019.20//24b/Dst06o/110303//'
        rom = self._make_rom_with_vs(vs)
        ident = identify(rom)
        assert 'ME7.5' in ident.version_string

    def test_me711_version_string_extracted(self):
        from meseventool.ecu_id import identify
        vs = b'42/1/ME7.1.1/5/8542.05//25C/Dst01o/'
        rom = self._make_rom_with_vs(vs)
        ident = identify(rom)
        assert 'ME7.1.1' in ident.version_string

    def test_me71_version_string_extracted(self):
        from meseventool.ecu_id import identify
        vs = b'40/1/ME7.1/5/6005.02//22m/DstE1o/110700//'
        rom = self._make_rom_with_vs(vs)
        ident = identify(rom)
        assert 'ME7.1' in ident.version_string

    def test_no_vs_gives_empty_string(self):
        from meseventool.ecu_id import identify
        rom = self._make_rom_with_vs(b'\x00' * 40)
        ident = identify(rom)
        assert ident.version_string == ''


class TestProfileVersionStringTiebreaker:
    """detect_profile uses version_string to break DPP1=0x0205 ambiguity."""

    def _detect(self, pn, vs_tag):
        from meseventool.ecu_id import ECUIdentity
        from meseventool.dpp import DPPValues
        from meseventool.profiles import detect_profile
        ident = ECUIdentity(vmecuhn=pn, version_string=vs_tag)
        dpp   = DPPValues(dpp0=0, dpp1=0x0205, dpp2=0x00E0, dpp3=3)
        return detect_profile(ident, dpp)

    def test_8d0907551_detects_27t(self):
        p = self._detect('8D0907551M', '40/1/ME7.1/5/6005.01')
        assert '2.7T' in p.name

    def test_4z7907551_detects_27t(self):
        p = self._detect('4Z7907551AA', '42/1/ME7.1.1/5/6030.03')
        assert '2.7T' in p.name

    def test_4d1907558_detects_v8(self):
        p = self._detect('4D1907558B', '42/1/ME7.1.1/5/8542.05')
        assert 'V8' in p.name

    def test_06a906032_detects_18t(self):
        p = self._detect('06A906032DL', '40/1/ME7.5/3/4019.20')
        assert '1.8T' in p.name

    def test_me711_no_pn_uses_vs_tiebreaker(self):
        """No PN, but ME7.1.1 version string → should prefer ME7.1.1 profiles over ME7.1."""
        from meseventool.ecu_id import ECUIdentity
        from meseventool.dpp import DPPValues
        from meseventool.profiles import detect_profile
        ident = ECUIdentity(vmecuhn='', version_string='43/1/ME7.1.1/5/8100.00')
        dpp   = DPPValues(dpp0=0, dpp1=0x0205, dpp2=0x00E0, dpp3=3)
        p = detect_profile(ident, dpp)
        assert 'ME7.1.1' in p.ecu_hw, \
            f"Expected ME7.1.1 profile from version string, got {p.name}"

    def test_dual_bank_27t_profile(self):
        p = self._detect('8D0907551M', '40/1/ME7.1/5/6005.01')
        assert p.dual_bank, "2.7T profile should be dual_bank=True"

    def test_v8_rs4_is_dual_bank(self):
        p = self._detect('4D1907558B', '42/1/ME7.1.1/5/8542.05')
        assert p.dual_bank, "V8 RS4 profile should be dual_bank=True"


class TestNewPNRegex:
    """_PN_RE must match all VAG ECU part number formats."""

    def _match(self, b):
        import re
        from meseventool.ecu_id import _PN_RE
        m = _PN_RE.search(b)
        return m.group().decode() if m else None

    def test_18t_dl(self):    assert self._match(b'06A906032DL') == '06A906032DL'
    def test_18t_bn(self):    assert self._match(b'06A906032BN') == '06A906032BN'
    def test_s4_b5(self):     assert self._match(b'8D0907551M')  == '8D0907551M'
    def test_allroad(self):   assert self._match(b'4Z7907551AA') == '4Z7907551AA'
    def test_a6_c5(self):     assert self._match(b'4B0907551K')  == '4B0907551K'
    def test_rs4_v8(self):    assert self._match(b'4D1907558B')  == '4D1907558B'
    def test_20t_06b(self):   assert self._match(b'06B906018EL') == '06B906018EL'
    def test_no_false_pos(self): assert self._match(b'234567890AB') is None
    def test_no_garbage(self):   assert self._match(b'XXXXXXXXXX') is None
