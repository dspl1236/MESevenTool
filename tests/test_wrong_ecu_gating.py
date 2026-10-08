"""
Review items B1–B6, B9, C1–C3: a patch must only be offered on the ECU it was
written for, and every profile must be reachable.
"""
import pytest
from meseventool.rom import ROMImage
from meseventool.dpp import DPPValues
from meseventool.ecu_id import ECUIdentity
from meseventool.patches import (ALL_PATCHES, FixedAddressPatchDef, PatchState,
                                 FIXED_ADDR_ROM_SIZE)
from meseventool.profiles import (ALL_PROFILES, PROFILE_AWP, PROFILE_06B,
                                  PROFILE_AGU_ME71, PROFILE_VR6_ME71, PROFILE_VR6_ME711,
                                  PROFILE_V6_27T_ME71, PROFILE_V6_27T_ME711,
                                  PROFILE_V8_D2, PROFILE_V8_D2_ME711, PROFILE_AMU,
                                  PROFILE_AUQ, detect_profile, detect_rom_profile,
                                  get_profile)
from tests.rom_corpus import find_rom


def _patch(prefix):
    return next(p for p in ALL_PATCHES if p.name.startswith(prefix))


def _fixed():
    return [p for p in ALL_PATCHES if isinstance(p, FixedAddressPatchDef)]


# ── B1: fixed addresses only on 1 MB images ───────────────────────────────────

class TestFixedAddressNeeds1MB:
    @pytest.mark.parametrize("size", [0x40000, 0x80000])
    def test_not_applicable_on_smaller_images(self, size):
        """Even with the stock byte present at the address: 0x0181A2 is code on a
        256 KB AGU ROM and the wrong half of the image on a 512 KB extract."""
        for p in _fixed():
            if p.fixed_addr + len(p.stock_bytes) > size:
                continue
            rom = ROMImage(data=bytearray([0xAA]) * size)
            rom.data[p.fixed_addr:p.fixed_addr + len(p.stock_bytes)] = p.stock_bytes
            r = p.detect(rom)
            assert r.state == PatchState.NOT_APPLICABLE, p.name
            assert not p.apply(rom, r)
            assert not rom.is_modified

    def test_applicable_on_1mb(self):
        p = _patch("Rear O2 Heater Diagnosis Disable — CDLSH (universal")
        rom = ROMImage(data=bytearray([0xAA]) * FIXED_ADDR_ROM_SIZE)
        rom.data[p.fixed_addr] = p.stock_bytes[0]
        assert p.detect(rom).state == PatchState.STOCK

    def test_agu_profile_is_256k(self):
        assert PROFILE_AGU_ME71.rom_size == 0x40000

    def test_catalogue_fixed_patches_are_1mb(self):
        for p in _fixed():
            assert p.rom_size == FIXED_ADDR_ROM_SIZE, p.name


# ── B2: one meaning per codeword address ──────────────────────────────────────

class TestCodewordNamesConsistent:
    def test_same_address_same_codeword(self):
        """Two entries at one fixed address must name the same codeword."""
        import re
        by_addr = {}
        for p in _fixed():
            m = re.search(r"\b(C[DW][A-Z0-9]+)\b", p.name)
            if m:
                by_addr.setdefault(p.fixed_addr, set()).add(m.group(1))
        clashes = {hex(a): n for a, n in by_addr.items() if len(n) > 1}
        assert not clashes, clashes

    def test_4b0_entries_match_xdf_map(self):
        names = {p.fixed_addr: p.name for p in _fixed() if "4b0906018" in p.applies_to}
        assert "CDHSVE" in names[0x0181A1]
        assert "CDKVS" in names[0x0181A3]
        assert 0x0181A2 not in names          # CDKAT is the universal entry


# ── B3: the two CDNWS entries at 0x0181AF ─────────────────────────────────────

class TestCDNWSFamilies:
    def test_06a_entry_only_on_transverse(self):
        p = _patch("VVT Cam Position Monitor Disable — CDNWS (ME7.5 1.8T AWW")
        assert get_profile("06A906032DL").patch_applies(p)
        assert not get_profile("4B0906018CM").patch_applies(p)
        assert not get_profile("8E0906018B").patch_applies(p)

    def test_4b0_entry_only_on_longitudinal(self):
        p = _patch("VVT Cam Position Monitor Disable — CDNWS (4B0906018CM")
        assert get_profile("4B0906018CM").patch_applies(p)
        assert get_profile("8E0909518AK").patch_applies(p)
        assert not get_profile("06A906032DL").patch_applies(p)

    def test_exactly_one_cdnws_applies_per_me75_ecu(self):
        both = [_patch("VVT Cam Position Monitor Disable — CDNWS (ME7.5 1.8T AWW"),
                _patch("VVT Cam Position Monitor Disable — CDNWS (4B0906018CM")]
        for pn in ("06A906032DL", "06A906032HN", "4B0906018CM", "8E0909518AK"):
            prof = get_profile(pn)
            assert sum(prof.patch_applies(p) for p in both) == 1, pn


# ── B4 / B5 / B6: ME7.1 vs ME7.1.1 gating ─────────────────────────────────────

class TestMe71FamilyGating:
    def test_me71x_tag(self):
        for prof in (PROFILE_VR6_ME71, PROFILE_VR6_ME711, PROFILE_V6_27T_ME71,
                     PROFILE_V6_27T_ME711, PROFILE_AGU_ME71, PROFILE_V8_D2_ME711):
            assert "me7.1x" in prof.platforms, prof.name
        for prof in (PROFILE_AWP, PROFILE_06B):
            assert "me7.1x" not in prof.platforms, prof.name

    def test_immo_off_me711_gated_on_me711(self):
        p = _patch("IMMO-OFF — ME7.1.1")
        assert PROFILE_V6_27T_ME711.patch_applies(p)
        assert PROFILE_VR6_ME711.patch_applies(p)
        assert not PROFILE_V6_27T_ME71.patch_applies(p)

    def test_and_set_patches_apply_to_both_27t_profiles(self):
        """These were gated {me7.1, me7.1.1, 2.7t}: an AND-set no profile satisfies."""
        both = [p for p in ALL_PATCHES if {"me7.1x", "2.7t"} <= p.applies_to]
        assert len(both) >= 3, [p.name for p in both]
        for p in both:
            assert PROFILE_V6_27T_ME71.patch_applies(p), p.name
            assert PROFILE_V6_27T_ME711.patch_applies(p), p.name

    def test_no_patch_requires_both_me71_and_me711(self):
        for p in ALL_PATCHES:
            assert not {"me7.1", "me7.1.1"} <= p.applies_to, p.name

    def test_eskonf_newer_on_me711(self):
        p = _patch("ESKONF Rear O2 Heater Disable (newer")
        assert PROFILE_V6_27T_ME711.patch_applies(p)
        assert PROFILE_V6_27T_ME71.patch_applies(p)


# ── B9: factory-off value is not "PATCHED" ────────────────────────────────────

class TestFactoryOff:
    def test_cdehfm_factory_zero_not_patched(self):
        p = _patch("MAF Sensor Diagnosis Disable — CDEHFM")
        rom = ROMImage(data=bytearray([0xAA]) * FIXED_ADDR_ROM_SIZE)
        rom.data[p.fixed_addr] = 0x00
        r = p.detect(rom, profile=get_profile("06A906032DL"))
        assert r.state == PatchState.NOT_APPLICABLE
        assert not p.apply(rom, r)
        rom.data[p.fixed_addr] = 0x01
        assert p.detect(rom, profile=get_profile("06A906032SL")).state == PatchState.STOCK


# ── C1 / C2 / C3: profile reachability and ME7.1.1 detection ──────────────────

class TestProfilesReachable:
    def test_every_profile_reachable_by_prefix_and_version(self):
        """Each profile must be returned for its own first prefix when the
        version string names its ecu_hw (review C1)."""
        for prof in ALL_PROFILES:
            if not prof.part_prefixes:
                continue
            ecu = ECUIdentity(vmecuhn=prof.part_prefixes[0] + "ZZ",
                              version_string=f"42/1/{prof.ecu_hw}/5/0000.00")
            got = detect_profile(ecu, DPPValues())
            assert got is prof, f"{prof.name} unreachable: got {got.name}"

    def test_amu_auq_fold_into_awp(self):
        assert PROFILE_AMU is PROFILE_AWP and PROFILE_AUQ is PROFILE_AWP
        assert any("AMU" in v for v in PROFILE_AWP.variants)
        assert PROFILE_AWP in ALL_PROFILES and ALL_PROFILES.count(PROFILE_AWP) == 1

    @pytest.mark.parametrize("pn,vs,expected", [
        ("022906032CS", "44/1/ME7.1.1/120/6428.AA", PROFILE_VR6_ME711),
        ("022906032EG", "42/1/ME7.1.1/3/6432.06",   PROFILE_VR6_ME711),
        ("022906032E",  "42/1/ME7.1/120/6228.A5",   PROFILE_VR6_ME71),
        ("021906018R",  "",                          PROFILE_VR6_ME71),
        ("4D0907559E",  "42/1/ME7.1.1/5/8001.07",   PROFILE_V8_D2_ME711),
        ("4D0907560AF", "42/1/ME7.1.1/5/8001.02",   PROFILE_V8_D2_ME711),
        ("4D0907559D",  "42/1/ME7.1/5/8000.07",     PROFILE_V8_D2),
        ("4Z7907551R",  "42/1/ME7.1.1/5/6030.03",   PROFILE_V6_27T_ME711),
        ("8D0907551M",  "40/1/ME7.1/5/6005.01",     PROFILE_V6_27T_ME71),
        ("8L0906018N",  "",                          PROFILE_AWP),
        ("8E0906018B",  "",                          PROFILE_06B),
        ("8D0907558M",  "",                          PROFILE_AGU_ME71),
    ])
    def test_detection(self, pn, vs, expected):
        got = detect_profile(ECUIdentity(vmecuhn=pn, version_string=vs), DPPValues())
        assert got is expected, got.name

    def test_me711_vmax_applies_on_r32(self):
        """Review C2: the ME7.1.1 Vmax patch was NOT_APPLICABLE on R32 ROMs."""
        p = next(p for p in ALL_PATCHES if p.applies_to == {"me7.1.1"} and "Vmax" in p.name)
        prof = detect_rom_profile(
            ECUIdentity(vmecuhn="022906032EG", version_string="42/1/ME7.1.1/3/6432.06"),
            DPPValues())
        assert prof.patch_applies(p)


# ── Real ROMs ─────────────────────────────────────────────────────────────────

def _load(name):
    path = find_rom(name)
    if not path:
        pytest.skip(f"{name} not available")
    return ROMImage.load(path)


class TestRealROMs:
    def _profile(self, rom):
        from meseventool.ecu_id import identify
        from meseventool.dpp import extract_dpp
        return detect_rom_profile(identify(rom), extract_dpp(rom))

    def test_vr6_me711_dump(self):
        prof = self._profile(_load("022906032cs 0006.bin"))
        assert prof.ecu_hw == "ME7.1.1" and "VR6" in prof.name

    def test_v8_me711_dumps(self):
        for name in ("Audi S6 4.2L 4D0907559E 0002 0261206846 360170.bin",
                     "4.2v8_flash_4D0907560AF.bin"):
            prof = self._profile(_load(name))
            assert prof.ecu_hw == "ME7.1.1" and "V8" in prof.name, name

    def test_18cm_only_longitudinal_cdnws(self):
        rom = _load("18CM.Bin")
        prof = self._profile(rom)
        p06a = _patch("VVT Cam Position Monitor Disable — CDNWS (ME7.5 1.8T AWW")
        p4b0 = _patch("VVT Cam Position Monitor Disable — CDNWS (4B0906018CM")
        assert p06a.detect(rom, profile=prof).state == PatchState.NOT_APPLICABLE
        assert p4b0.detect(rom, profile=prof).state == PatchState.STOCK

    def test_dl_only_transverse_cdnws(self):
        rom = _load("06A906032DL_0261206890_v360227_MT_OEM.bin")
        prof = self._profile(rom)
        p06a = _patch("VVT Cam Position Monitor Disable — CDNWS (ME7.5 1.8T AWW")
        p4b0 = _patch("VVT Cam Position Monitor Disable — CDNWS (4B0906018CM")
        assert p06a.detect(rom, profile=prof).state == PatchState.STOCK
        assert p4b0.detect(rom, profile=prof).state == PatchState.NOT_APPLICABLE

    def test_256k_aeb_dump_gets_no_fixed_patches(self):
        rom = _load("Audi A4 1.8T 150HP 8D0907557P 0261204258 350269.bin")
        assert rom.size == 0x40000
        prof = self._profile(rom)
        for p in _fixed():
            assert p.detect(rom, profile=prof).state == PatchState.NOT_APPLICABLE, p.name
