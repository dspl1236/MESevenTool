"""
tests/test_known_roms.py
Tests for KNOWN_ROMS catalog and VR6 profile detection.
"""
import sys, zlib, os
sys.path.insert(0, '/home/claude/MESevenTool')
import pytest
from meseventool.known_roms import (
    KNOWN_ROMS, lookup_rom, is_known_stock, KnownROM, _CATALOG
)
from meseventool.profiles import (
    detect_profile, PROFILE_VR6_ME71, PROFILE_V5_ME75, ALL_PROFILES
)
from meseventool.ecu_id import ECUIdentity
from meseventool.dpp import DPPValues


class TestKnownROMsCatalog:

    def test_catalog_not_empty(self):
        assert len(KNOWN_ROMS) >= 85

    def test_all_crcs_unique(self):
        crcs = [r.crc32 for r in _CATALOG]
        assert len(crcs) == len(set(crcs)), "Duplicate CRC32 in catalog"

    def test_all_vmecuhn_strings(self):
        for r in _CATALOG:
            assert isinstance(r.vmecuhn, str)
            assert isinstance(r.bosch, str)
            assert isinstance(r.label, str)

    def test_all_ecu_hw_valid(self):
        valid = {"ME7.5", "ME7.1", "ME7.1.1", "ME7.5.10"}
        for r in _CATALOG:
            assert r.ecu_hw in valid, f"Unknown ecu_hw {r.ecu_hw!r} in {r.label}"

    def test_all_size_kb_valid(self):
        valid = {256, 512, 1024}
        for r in _CATALOG:
            assert r.size_kb in valid, f"Unexpected size_kb {r.size_kb} in {r.label}"

    def test_lookup_known_crc(self):
        # S4 2.7T 265hp
        result = lookup_rom(0xb8c7dbce)
        assert result is not None
        assert result.vmecuhn == "8D0907551A"
        assert result.ecu_hw == "ME7.1"

    def test_lookup_vr6_crc(self):
        result = lookup_rom(0x1c8e82c6)
        assert result is not None
        assert "022906032E" in result.vmecuhn
        assert result.ecu_hw == "ME7.1"

    def test_lookup_r32_crc(self):
        result = lookup_rom(0xbc7b5d85)
        assert result is not None
        assert "022906032EG" in result.vmecuhn
        assert result.ecu_hw == "ME7.1.1"

    def test_lookup_passat_4b0_crc(self):
        result = lookup_rom(0xf7b8ce22)
        assert result is not None
        assert result.vmecuhn == "4B0906018B"
        assert result.ecu_hw == "ME7.5"

    def test_lookup_aww_dl_crc(self):
        result = lookup_rom(0x1e1bc31a)
        assert result is not None
        assert result.vmecuhn == "06A906032DL"

    def test_lookup_unknown_crc(self):
        assert lookup_rom(0xDEADBEEF) is None

    def test_is_known_stock_true(self):
        assert is_known_stock(0xb8c7dbce) is True

    def test_is_known_stock_false(self):
        assert is_known_stock(0x12345678) is False

    def test_all_labels_nonempty(self):
        for r in _CATALOG:
            assert r.label.strip(), f"Empty label for CRC {r.crc32:#010x}"


class TestVR6Profile:

    def test_vr6_profile_in_all_profiles(self):
        assert PROFILE_VR6_ME71 in ALL_PROFILES

    def test_v5_profile_in_all_profiles(self):
        assert PROFILE_V5_ME75 in ALL_PROFILES

    def test_vr6_profile_na_induction(self):
        assert PROFILE_VR6_ME71.induction == "na"

    def test_vr6_profile_na_tag(self):
        assert "na" in PROFILE_VR6_ME71.platforms

    def test_vr6_profile_not_turbo(self):
        assert "turbo" not in PROFILE_VR6_ME71.platforms

    def test_vr6_profile_part_prefixes(self):
        prefixes = PROFILE_VR6_ME71.part_prefixes
        assert "022906032" in prefixes
        assert "021906018" in prefixes

    def test_vr6_profile_detects_golf4_pn(self):
        ecu = ECUIdentity(vmecuhn="022906032E", bosch_number="0261206619")
        dpp = DPPValues(dpp1=0x0205)
        prof = detect_profile(ecu, dpp)
        assert prof is PROFILE_VR6_ME71

    def test_vr6_profile_detects_r32_pn(self):
        ecu = ECUIdentity(vmecuhn="022906032EG", bosch_number="0261208344")
        dpp = DPPValues(dpp1=0x0205)
        prof = detect_profile(ecu, dpp)
        assert prof is PROFILE_VR6_ME71

    def test_vr6_profile_detects_golf3_pn(self):
        ecu = ECUIdentity(vmecuhn="021906018R", bosch_number="0261206814")
        dpp = DPPValues(dpp1=0x0205)
        prof = detect_profile(ecu, dpp)
        assert prof is PROFILE_VR6_ME71

    def test_vr6_boost_patch_not_applicable(self):
        """Boost patches should not apply to N/A VR6 profile."""
        from meseventool.patches import ALL_PATCHES
        boost_patches = [p for p in ALL_PATCHES
                        if "turbo" in getattr(p, "applies_to", set())]
        for p in boost_patches:
            assert not PROFILE_VR6_ME71.patch_applies(p), \
                f"Boost patch {p.name!r} should not apply to VR6 N/A"

    def test_v5_profile_na_induction(self):
        assert PROFILE_V5_ME75.induction == "na"

    def test_v5_profile_detects_pn(self):
        ecu = ECUIdentity(vmecuhn="071906018AE", bosch_number="0261206620")
        dpp = DPPValues(dpp1=0x0205)
        prof = detect_profile(ecu, dpp)
        assert prof is PROFILE_V5_ME75


class TestImmoPatchStructure:
    """Structural tests for immo patches — not real-ROM validation."""

    def test_immo_patches_in_all_patches(self):
        from meseventool.patches import ALL_PATCHES, PatchCategory
        immo = [p for p in ALL_PATCHES
                if p.category == PatchCategory.IMMOBILISER]
        assert len(immo) >= 5, f"Expected ≥5 immo patches, got {len(immo)}"

    def test_immo_patch_stock_patch_same_length(self):
        from meseventool.patches import ALL_PATCHES, PatchCategory
        for p in ALL_PATCHES:
            if p.category != PatchCategory.IMMOBILISER:
                continue
            assert len(p.stock_bytes) == len(p.patch_bytes), \
                f"{p.name}: stock/patch byte length mismatch"
            assert len(p.needle) == len(p.mask), \
                f"{p.name}: needle/mask length mismatch"

    def test_immo_off_me75_has_applies_to(self):
        from meseventool.patches import ALL_PATCHES, PatchCategory
        for p in ALL_PATCHES:
            if p.category == PatchCategory.IMMOBILISER and "ME7.5" in p.name:
                assert "me7.5" in p.applies_to, f"{p.name} missing me7.5 tag"

    def test_immo_off_me71_has_applies_to(self):
        from meseventool.patches import ALL_PATCHES, PatchCategory
        for p in ALL_PATCHES:
            if p.category == PatchCategory.IMMOBILISER and "ME7.1" in p.name:
                assert "me7.1" in p.applies_to, f"{p.name} missing me7.1 tag"

    def test_immo_patches_not_applicable_to_fsi(self):
        """FSI engines have separate immo architecture — not applicable."""
        from meseventool.patches import ALL_PATCHES, PatchCategory
        from meseventool.profiles import PROFILE_BGU_FSI
        immo = [p for p in ALL_PATCHES
                if p.category == PatchCategory.IMMOBILISER
                and p.applies_to]  # skip universal patches
        for p in immo:
            if "fsi" in p.applies_to:
                continue  # explicitly targeting FSI — fine
            # mpi-only patches should not match FSI profile
            if "mpi" in p.applies_to:
                assert not PROFILE_BGU_FSI.patch_applies(p), \
                    f"{p.name} should not apply to FSI profile"


class TestECUIdVR6Regex:
    """Test that the extended PN regex correctly identifies VR6 part numbers."""

    def _make_rom_with_pn(self, pn: str) -> bytes:
        """Build a minimal 1MB synthetic ROM with a PN string embedded."""
        data = bytearray(0x100000)
        # Write PN at a position the scanner will find
        pos = 0x0114C3
        for i, c in enumerate(pn.encode('ascii')):
            data[pos + i] = c
        # Minimal ME7 version string
        vs = b'42/1/ME7.1/3/6428.AA'
        data[0xF0000:0xF0000+len(vs)] = vs
        return bytes(data)

    @pytest.mark.skipif(
        not os.path.exists("/tmp/me7_scan/206619.ori"),
        reason="VR6 ROM file not available"
    )
    def test_golf4_vr6_pn_detected(self):
        import zlib
        from meseventool.rom import ROMImage
        from meseventool.ecu_id import identify
        rom = ROMImage.load("/tmp/me7_scan/206619.ori")
        ecu = identify(rom)
        assert ecu.vmecuhn == "022906032E"

    @pytest.mark.skipif(
        not os.path.exists("/tmp/me7_scan/VW golf 3.2 VR6 250HP 022906032EG 0261208344 373693.ori"),
        reason="R32 ROM file not available"
    )
    def test_r32_pn_detected(self):
        from meseventool.rom import ROMImage
        from meseventool.ecu_id import identify
        rom = ROMImage.load("/tmp/me7_scan/VW golf 3.2 VR6 250HP 022906032EG 0261208344 373693.ori")
        ecu = identify(rom)
        assert ecu.vmecuhn == "022906032EG"
