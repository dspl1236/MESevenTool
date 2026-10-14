"""
Review items D1 and D2: multi-site patches must write every site, and no
two scalar entries may resolve to the same byte.
"""
import pytest
from meseventool.rom import ROMImage
from meseventool.needle import Searcher
from meseventool.patches import (ALL_PATCHES, ALL_SCALAR_PATCHES, PatchDef,
                                 ScalarPatchDef, PatchState)
from tests.rom_corpus import find_rom


def _patch(fragment):
    return next(p for p in ALL_PATCHES if fragment in p.name)


def _scalar(fragment):
    return next(p for p in ALL_SCALAR_PATCHES if fragment in p.name)


def _rom_with(needle_bytes, at):
    rom = ROMImage(data=bytearray([0xAA]) * 0x100000)
    for a in at:
        rom.data[a:a + len(needle_bytes)] = needle_bytes
    return rom


# ── D1: PatchDef with two sites ───────────────────────────────────────────────

class TestVmaxBothSites:
    def test_catalogue_flags(self):
        assert _patch("Vmax Speed Limiter Disable (universal").all_hits
        assert _scalar("Hard Rev Limit (ME7.5").all_hits
        assert _scalar("NKILL").all_hits

    def test_apply_and_revert_both_sites(self):
        p = _patch("Vmax Speed Limiter Disable (universal")
        sites = [0x1000, 0x2000]
        rom = _rom_with(bytes(p.needle), sites)
        r = p.detect(rom, Searcher(rom))
        assert r.state == PatchState.STOCK
        assert p.sites(rom) == [a + p.offset for a in sites]

        assert p.apply(rom, r)
        for a in sites:
            assert rom.data[a + p.offset:a + p.offset + 2] == p.patch_bytes, hex(a)

        # the stock-form needle no longer matches, so detect goes through the
        # patched-form search; revert must still find both sites (old bug)
        r2 = p.detect(rom, Searcher(rom))
        assert r2.state == PatchState.PATCHED
        assert p.sites(rom) == [a + p.offset for a in sites]
        assert p.revert(rom, r2)
        for a in sites:
            assert rom.data[a + p.offset:a + p.offset + 2] == p.stock_bytes, hex(a)
        assert p.detect(rom, Searcher(rom)).state == PatchState.STOCK

    def test_mixed_state_revert_cleans_both(self):
        """One site already patched, one stock: revert restores both."""
        p = _patch("Vmax Speed Limiter Disable (universal")
        sites = [0x1000, 0x2000]
        rom = _rom_with(bytes(p.needle), sites)
        rom.data[0x2000 + p.offset:0x2000 + p.offset + 2] = p.patch_bytes
        r = p.detect(rom, Searcher(rom))
        assert p.revert(rom, r)
        for a in sites:
            assert rom.data[a + p.offset:a + p.offset + 2] == p.stock_bytes

    def test_single_site_patch_unchanged(self):
        """Entries without all_hits still write exactly the detected site."""
        p = next(p for p in ALL_PATCHES if isinstance(p, PatchDef) and not p.all_hits
                 and p.needle and p.stock_bytes != p.patch_bytes)
        sites = [0x1000, 0x2000]
        rom = _rom_with(bytes(p.needle), sites)
        rom_bytes = bytes(p.needle)
        # make the wildcard positions deterministic
        for a in sites:
            rom.data[a:a + len(rom_bytes)] = rom_bytes
        r = p.detect(rom, Searcher(rom))
        if r.state != PatchState.STOCK:
            pytest.skip("needle has wildcards the synthetic fill does not satisfy")
        p.apply(rom, r)
        patched = [a for a in sites if rom.data[a + p.offset:a + p.offset + len(p.patch_bytes)] == p.patch_bytes]
        assert patched == [sites[0]]


# ── D1: scalars with two sites ────────────────────────────────────────────────

class TestScalarBothSites:
    def _two_site_rom(self, scalar, raw=0x254A):
        sites = [0x3000, 0x4000]
        rom = ROMImage(data=bytearray([0xAA]) * 0x100000)
        n = bytearray(scalar.needle)
        for i, m in enumerate(scalar.mask):
            if not m:
                n[i] = 0x00
        n[scalar.offset:scalar.offset + 2] = raw.to_bytes(2, "little")
        for a in sites:
            rom.data[a:a + len(n)] = n
        return rom, [a + scalar.offset for a in sites]

    def test_write_updates_both_sites(self):
        sc = _scalar("Hard Rev Limit (ME7.5")
        rom, addrs = self._two_site_rom(sc)
        assert sc.read_all(rom) == [pytest.approx(7159.5)] * 2
        assert sc.write(rom, 7351.5)                    # 0x264A = 9802 * 0.75
        assert sc.read_all(rom) == [pytest.approx(7351.5)] * 2
        for a in addrs:
            assert rom.data[a:a + 2] == (0x264A).to_bytes(2, "little")

    def test_read_reports_first_site(self):
        sc = _scalar("NKILL")
        rom, addrs = self._two_site_rom(sc, raw=0x364A)
        assert sc.read(rom) == pytest.approx(10423.5)

    def test_single_site_scalar_writes_one(self):
        sc = _scalar("Overrev Protection")
        assert not sc.all_hits
        rom, addrs = self._two_site_rom(sc, raw=0x9A2A) if False else (None, None)
        # Overrev's needle layout differs; build directly
        sites = [0x3000, 0x4000]
        rom = ROMImage(data=bytearray([0xAA]) * 0x100000)
        n = bytearray(sc.needle)
        for i, m in enumerate(sc.mask):
            if not m:
                n[i] = 0x00
        n[sc.offset:sc.offset + 2] = (0x2A9A).to_bytes(2, "little")
        for a in sites:
            rom.data[a:a + len(n)] = n
        assert sc.write(rom, 8372.0)
        vals = [int.from_bytes(rom.data[a + sc.offset:a + sc.offset + 2], "little") for a in sites]
        assert vals[0] != 0x2A9A and vals[1] == 0x2A9A


# ── D2: one byte, one scalar ──────────────────────────────────────────────────

class TestNoSharedScalarSites:
    def test_fuel_cut_resume_removed(self):
        assert not any("Fuel Cut Resume" in p.name for p in ALL_SCALAR_PATCHES)

    @pytest.mark.parametrize("name", ["06A906032DL_0261206890_v360227_MT_OEM.bin",
                                      "18CM.Bin", "032sl_auto_revo_1.bin"])
    def test_scalars_do_not_share_addresses_on_real_roms(self, name):
        path = find_rom(name)
        if not path:
            pytest.skip(name)
        rom = ROMImage.load(path)
        s = Searcher(rom)
        owner = {}
        for sc in ALL_SCALAR_PATCHES:
            if not isinstance(sc, ScalarPatchDef):
                continue
            for a in sc._find_addrs(rom, s):
                assert a not in owner, f"{sc.name} and {owner[a]} both at 0x{a:X}"
                owner[a] = sc.name
        assert owner

    def test_two_site_scalars_find_two_sites_on_dl(self):
        path = find_rom("06A906032DL_0261206890_v360227_MT_OEM.bin")
        if not path:
            pytest.skip("DL")
        rom = ROMImage.load(path)
        s = Searcher(rom)
        for frag in ("Hard Rev Limit (ME7.5", "NKILL"):
            sc = _scalar(frag)
            addrs = sc._find_addrs(rom, s)
            assert len(addrs) == 2, (frag, addrs)
            assert len(set(sc.read_all(rom, s))) == 1, frag       # both sites agree
        vm = _patch("Vmax Speed Limiter Disable (universal")
        assert len(vm.sites(rom, s)) == 2
