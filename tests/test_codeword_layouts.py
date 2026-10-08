"""
Review item A7: the emissions codeword block has a different byte order per
software build.  Codeword patches must resolve their address from the ROM's
build and be withheld when the build is unknown.
"""
import pytest
from meseventool.rom import ROMImage
from meseventool.dpp import DPPValues, extract_dpp
from meseventool.ecu_id import ECUIdentity, identify
from meseventool.codewords import (LAYOUTS, codeword_layout, parse_version,
                                   layout_from_tags, address)
from meseventool.patches import ALL_PATCHES, FixedAddressPatchDef, PatchState
from meseventool.profiles import detect_rom_profile, get_profile
from tests.rom_corpus import find_rom


def _cw(fragment):
    return next(p for p in ALL_PATCHES
                if isinstance(p, FixedAddressPatchDef) and p.codeword and fragment in p.name)


def _codeword_patches():
    return [p for p in ALL_PATCHES if isinstance(p, FixedAddressPatchDef) and p.codeword]


# ── Layout selection ─────────────────────────────────────────────────────────

class TestLayoutSelection:
    @pytest.mark.parametrize("vs,pn,expected", [
        ("40/1/ME7.5/3/4019.20//24b/Dst03o/280800",  "06A906032DL",  "06a"),
        ("42/1/ME7.5/120/4013.00//24B/Dst01o/290102", "06A906032RN",  "06a"),
        ("40/1/ME7.5/5/4018.20//24B/Dst01o/140801",  "8N0906018BH",  "06a"),
        ("42/1/ME7.5/120/4518.KE//24b/Dst5So/121000", "06A906032GQ",  "06a"),
        ("42/1/ME7.5/381/4518.SA//22L/DstAAo/150104", "06A906032QJ",  None),   # Sharan build
        ("40/1/ME7.5/120/X505R//24D/Dst03o/080404",  "06A906032SL",  None),
        ("42/1/ME7.5/120/4220.AA//23f/Dst03o/191200", "06A906032DS",  None),
        ("40/1/ME7.5/3/4012.31//24E/Dst06o/020402",  "4B0906018CM",  "4b0"),
        ("40/1/ME7.5/5/4016.32//24E/Dst02o/301101",  "8E0909518M",   "4b0"),
        ("40/1/ME7.5/5/4016.31//24b/Dst02o/190400",  "4B0906018R",   None),   # exception
        ("40/1/ME7.1/5/6005.01//22m/DstC2o/011200",  "8D0907551M",   "me71"),
        ("40/1/ME7.1/5/6025.02//22m/DstG1o/130",     "4Z7907551",    "me71"),
        ("42/1/ME7.1/5/6005.01//X22k6/Dstc2g/3",     "8D0907551A",   None),   # early build
        ("40/1/ME7.1/5/6024.02//23g/DstW1o/051",     "8D0907551K",   "me711"),
        ("40/1/ME7.1/5/6024.02//23g/DstW1o/160",     "8D0907551F",   None),   # exception
        ("42/1/ME7.1.1/5/6030.03//25A/DstU2o/2",     "4Z7907551R",   "me711"),
        ("43/1/ME7.1.1/5/6011.02//A25an/Dst5A/",     "4Z7907551R",   "me711"),
        ("42/1/ME7.1.1/5/8001.07//23h/Dst03o/0",     "4D0907559E",   "me711"),
        ("42/1/ME7.1.1/5/8542.05//25C/Dst01o/0",     "4D1907558",    "me711"),
        ("42/1/ME7.1.1/5/8542.05//25C/Dst03o/1",     "4D1907558D",   None),   # exception
        ("42/1/ME7.1.1/3/8542.01//25D/DstA6o/1",     "4D0907560BR",  None),   # exception
        ("42/1/ME7.1.1/3/6432.06//24F/Dst22o/2",     "022906032EG",  None),   # VR6: no evidence
        ("42/1/ME7.1.1/3/S1103A//25G/5g50q21/1",     "022906032CD",  None),
        ("",                                          "06A906032DL",  None),
    ])
    def test_build_to_layout(self, vs, pn, expected):
        assert codeword_layout(vs, pn) == expected

    def test_parse_version(self):
        assert parse_version("40/1/ME7.5/3/4019.20//24b/Dst03o/280800") == ("40", "ME7.5", "3", "4019")
        assert parse_version("garbage") is None

    def test_profile_carries_layout_tag(self):
        prof = detect_rom_profile(
            ECUIdentity(vmecuhn="06A906032DL", version_string="40/1/ME7.5/3/4019.20"), DPPValues())
        assert "cw_06a" in prof.platforms
        assert prof.codeword_layout == "06a"
        assert layout_from_tags(prof.platforms) == "06a"

    def test_profile_without_version_has_no_layout(self):
        assert get_profile("06A906032DL").codeword_layout is None
        assert get_profile("06A906032DL", "40/1/ME7.5/3/4019.20").codeword_layout == "06a"


# ── Layout tables ────────────────────────────────────────────────────────────

class TestLayoutTables:
    def test_06a_has_cdhsvsa_and_no_cdlshv(self):
        assert LAYOUTS["06a"]["CDHSVSA"] == 0x0181A2
        assert LAYOUTS["06a"]["CDKAT"] == 0x0181A3
        assert "CDLSHV" not in LAYOUTS["06a"]

    def test_me711_is_me71_minus_two(self):
        for cw, addr in LAYOUTS["me71"].items():
            assert LAYOUTS["me711"][cw] == addr - 2, cw

    def test_4b0_matches_me71(self):
        assert LAYOUTS["4b0"] == LAYOUTS["me71"]

    def test_common_codewords_agree_where_documented(self):
        for cw in ("CDNWS", "CDSLS", "CDTES", "CDHSVE", "CDEHFM"):
            assert LAYOUTS["06a"][cw] == LAYOUTS["me71"][cw], cw


# ── Patch resolution ─────────────────────────────────────────────────────────

class TestResolution:
    def _rom(self):
        return ROMImage(data=bytearray([0x01]) * 0x100000)

    def test_no_layout_means_not_applicable(self):
        rom = self._rom()
        prof = get_profile("06A906032DL")   # no version string → no layout tag
        for p in _codeword_patches():
            r = p.detect(rom, profile=prof)
            assert r.state == PatchState.NOT_APPLICABLE, p.name
            if p.applies_to <= prof.platforms:      # passed the tag gate: layout is the reason
                assert "layout" in r.detail, (p.name, r.detail)
            assert p.detect(rom).state == PatchState.NOT_APPLICABLE, p.name

    def test_address_follows_layout(self):
        p = _cw("CDKAT")
        rom = self._rom()
        for vs, pn, addr in [("40/1/ME7.5/3/4019.20", "06A906032DL", 0x0181A3),
                             ("40/1/ME7.1/5/6005.01", "8D0907551M", 0x0181A2),
                             ("42/1/ME7.1.1/5/6030.03", "4Z7907551R", 0x0181A0)]:
            r = p.detect(rom, profile=get_profile(pn, vs))
            assert r.state == PatchState.STOCK and r.addr == addr, (pn, hex(r.addr))

    def test_apply_and_revert_use_resolved_address(self):
        p = _cw("CDKAT")
        rom = self._rom()
        prof = get_profile("4Z7907551R", "42/1/ME7.1.1/5/6030.03")
        r = p.detect(rom, profile=prof)
        assert p.apply(rom, r)
        assert rom.data[0x0181A0] == 0x00 and rom.data[0x0181A2] == 0x01
        r2 = p.detect(rom, profile=prof)
        assert r2.state == PatchState.PATCHED
        assert p.revert(rom, r2)
        assert rom.data[0x0181A0] == 0x01

    def test_codeword_missing_in_layout_is_not_applicable(self):
        """CDLSHV does not exist in the 06a layout."""
        p = _cw("CDLSHV")
        r = p.detect(self._rom(), profile=get_profile("06A906032DL", "40/1/ME7.5/3/4019.20"))
        assert r.state == PatchState.NOT_APPLICABLE

    def test_layout_specific_stock_value(self):
        """CDNWS stock is 0x01 on me71 and 0x03 on me711 (VVT) builds."""
        p = _cw("CDNWS (ME7.1/ME7.1.1)")
        rom = self._rom()
        rom.data[0x0181AD] = 0x03
        prof = get_profile("4Z7907551R", "42/1/ME7.1.1/5/6030.03")
        r = p.detect(rom, profile=prof)
        assert r.state == PatchState.STOCK and r.addr == 0x0181AD
        assert p.apply(rom, r) and rom.data[0x0181AD] == 0x00
        r2 = p.detect(rom, profile=prof)
        assert p.revert(rom, r2) and rom.data[0x0181AD] == 0x03

    def test_every_codeword_entry_declares_layouts(self):
        for p in _codeword_patches():
            assert p.layouts, p.name
            for layout in p.layouts:
                assert layout in LAYOUTS, (p.name, layout)
                assert address(layout, p.codeword) is not None, (p.name, layout)

    def test_no_universal_fixed_codeword_entries_remain(self):
        """Any fixed-address entry inside the codeword block must be layout-aware."""
        for p in ALL_PATCHES:
            if isinstance(p, FixedAddressPatchDef) and 0x018194 <= p.fixed_addr <= 0x0181C8:
                assert p.codeword, p.name

    def test_one_entry_per_codeword_per_layout(self):
        seen = {}
        for p in _codeword_patches():
            for layout in p.layouts:
                key = (layout, p.codeword, tuple(sorted(p.applies_to - {"me7.5", "me7.1x", "1.8t", "2.7t"})))
                assert key not in seen, (p.name, seen.get(key))
                seen[key] = p.name


# ── Real ROMs ────────────────────────────────────────────────────────────────

def _load(name):
    path = find_rom(name)
    if not path:
        pytest.skip(f"{name} not available")
    rom = ROMImage.load(path)
    return rom, detect_rom_profile(identify(rom), extract_dpp(rom))


class TestRealROMs:
    def test_late_allroad_cdnws_at_1ad(self):
        rom, prof = _load("4Z7907551R.bin")
        assert prof.codeword_layout == "me711"
        r = _cw("CDNWS (ME7.1/ME7.1.1)").detect(rom, profile=prof)
        assert r.state == PatchState.STOCK and r.addr == 0x0181AD
        assert rom.data[0x0181AF] == 0x01          # CDTANKL, what the old entry would have cleared

    def test_s4_b5_cdnws_at_1af(self):
        rom, prof = _load("8D0907551M-0001.bin")
        assert prof.codeword_layout == "me71"
        r = _cw("CDNWS (ME7.1/ME7.1.1)").detect(rom, profile=prof)
        assert r.state == PatchState.STOCK and r.addr == 0x0181AF

    def test_06a_cdkat_at_1a3(self):
        rom, prof = _load("06A906032LP 0005.bin")
        assert prof.codeword_layout == "06a"
        r = _cw("CDKAT").detect(rom, profile=prof)
        assert r.addr == 0x0181A3 and r.state == PatchState.STOCK

    def test_18cm_4b0_layout(self):
        rom, prof = _load("18CM.Bin")
        assert prof.codeword_layout == "4b0"
        assert _cw("CDKVS").detect(rom, profile=prof).state == PatchState.STOCK

    def test_early_s4_build_gets_nothing(self):
        rom, prof = _load("8D0907551A-0002.bin")
        assert prof.codeword_layout is None
        for p in _codeword_patches():
            assert p.detect(rom, profile=prof).state == PatchState.NOT_APPLICABLE, p.name

    def test_sl_x505r_build_gets_nothing(self):
        rom, prof = _load("032sl_auto_revo_1.bin")
        assert prof.codeword_layout is None
        for p in _codeword_patches():
            assert p.detect(rom, profile=prof).state == PatchState.NOT_APPLICABLE, p.name
