"""Tests for patch detection/apply/revert — uses synthetic ROMs."""
import pytest
from meseventool.rom import ROMImage
from meseventool.needle import MASK, XXXX
from meseventool.patches import (
    PatchDef, PatchState, PatchResult, ScalarPatchDef, PatchCategory,
    OffsetPatchDef, MultiOffsetPatchDef,
    ALL_PATCHES, ALL_SCALAR_PATCHES,
    detect_all,
)

# Legacy aliases for registry names
PATCH_REGISTRY  = ALL_PATCHES
SCALAR_REGISTRY = ALL_SCALAR_PATCHES


def make_rom(size=0x80000):
    return ROMImage(data=bytearray([0xFF] * size))


def rom_with_needle(needle: list[int], offset: int = 0x1000) -> ROMImage:
    data = bytearray([0xFF] * 0x80000)
    for i, b in enumerate(needle):
        data[offset + i] = b if b != XXXX else 0x00
    return ROMImage(data=data)


# ── Synthetic patch for unit testing ──────────────────────────────────────────

_TEST_NEEDLE = [0xE6, 0xF4, XXXX, XXXX, 0xDB, 0x00]
_TEST_MASK   = [MASK, MASK, XXXX, XXXX, MASK, MASK]

TEST_PATCH = PatchDef(
    name        = "Test patch",
    description = "Synthetic patch for unit tests",
    category    = PatchCategory.DIAGNOSTICS,
    needle      = _TEST_NEEDLE,
    mask        = _TEST_MASK,
    offset      = 2,
    stock_bytes = b'\x00\x00',
    patch_bytes = b'\x01\x00',
)

TEST_PATCH_OFFSET = 0x1000


def make_test_rom(patched=False) -> ROMImage:
    data = bytearray([0xFF] * 0x80000)
    needle = list(_TEST_NEEDLE)
    needle[2] = 0x01 if patched else 0x00
    needle[3] = 0x00
    for i, b in enumerate(needle):
        data[TEST_PATCH_OFFSET + i] = b
    return ROMImage(data=data)


class TestPatchDetect:
    def test_stock_detected(self):
        rom = make_test_rom(patched=False)
        result = TEST_PATCH.detect(rom)
        assert result.state == PatchState.STOCK

    def test_applied_detected(self):
        rom = make_test_rom(patched=True)
        result = TEST_PATCH.detect(rom)
        assert result.state == PatchState.PATCHED

    def test_unknown_when_needle_missing(self):
        rom = make_rom()
        result = TEST_PATCH.detect(rom)
        assert result.state == PatchState.MISSING

    def test_address_returned(self):
        rom = make_test_rom(patched=False)
        result = TEST_PATCH.detect(rom)
        assert result.addr == TEST_PATCH_OFFSET + 2


class TestPatchApplyRevert:
    def test_apply_changes_bytes(self):
        rom = make_test_rom(patched=False)
        result = TEST_PATCH.detect(rom)
        TEST_PATCH.apply(rom, result)
        site = TEST_PATCH_OFFSET + 2
        assert bytes(rom.data[site:site+2]) == b'\x01\x00'

    def test_apply_marks_modified(self):
        rom = make_test_rom(patched=False)
        result = TEST_PATCH.detect(rom)
        TEST_PATCH.apply(rom, result)
        assert rom.is_modified

    def test_revert_restores_stock(self):
        rom = make_test_rom(patched=True)
        result = TEST_PATCH.detect(rom)
        TEST_PATCH.revert(rom, result)
        site = TEST_PATCH_OFFSET + 2
        assert bytes(rom.data[site:site+2]) == b'\x00\x00'

    def test_apply_then_detect_patched(self):
        rom = make_test_rom(patched=False)
        r = TEST_PATCH.detect(rom)
        TEST_PATCH.apply(rom, r)
        assert TEST_PATCH.detect(rom).state == PatchState.PATCHED

    def test_revert_then_detect_stock(self):
        rom = make_test_rom(patched=True)
        r = TEST_PATCH.detect(rom)
        TEST_PATCH.revert(rom, r)
        assert TEST_PATCH.detect(rom).state == PatchState.STOCK

    def test_apply_missing_returns_false(self):
        rom = make_rom()
        result = PatchResult(TEST_PATCH, PatchState.MISSING, 0)
        ok = TEST_PATCH.apply(rom, result)
        assert not ok
        assert not rom.is_modified

    def test_revert_missing_returns_false(self):
        rom = make_rom()
        result = PatchResult(TEST_PATCH, PatchState.MISSING, 0)
        ok = TEST_PATCH.revert(rom, result)
        assert not ok


# ── Scalar patch ──────────────────────────────────────────────────────────────

_SCALAR_NEEDLE = [0xD7, 0x40, XXXX, XXXX, 0xF2, 0xF4, XXXX, XXXX, 0x40, 0xF4]
_SCALAR_MASK   = [MASK, MASK, XXXX, XXXX, MASK, MASK, XXXX, XXXX, MASK, MASK]
SCALAR_OFFSET  = 0x2000
SCALAR_VAL_OFF = 6

TEST_SCALAR = ScalarPatchDef(
    name        = "Test scalar",
    description = "Synthetic scalar for unit tests",
    category    = PatchCategory.PERFORMANCE,
    needle      = _SCALAR_NEEDLE,
    mask        = _SCALAR_MASK,
    offset      = SCALAR_VAL_OFF,
    size        = 2,
    big_endian  = True,
    scale       = 1.0,
    unit        = "RPM",
    min_val     = 1000,
    max_val     = 9000,
)


def make_scalar_rom(rpm_val: int) -> ROMImage:
    data = bytearray([0xFF] * 0x80000)
    needle = list(_SCALAR_NEEDLE)
    for i, b in enumerate(needle):
        data[SCALAR_OFFSET + i] = b if b != XXXX else 0x00
    data[SCALAR_OFFSET + SCALAR_VAL_OFF]   = (rpm_val >> 8) & 0xFF
    data[SCALAR_OFFSET + SCALAR_VAL_OFF+1] = rpm_val & 0xFF
    return ROMImage(data=data)


class TestScalarPatch:
    def test_read_value(self):
        rom = make_scalar_rom(6860)
        val = TEST_SCALAR.read(rom)
        assert val == pytest.approx(6860)

    def test_write_read_roundtrip(self):
        rom = make_scalar_rom(6860)
        TEST_SCALAR.write(rom, 7200)
        assert TEST_SCALAR.read(rom) == pytest.approx(7200)

    def test_write_marks_modified(self):
        rom = make_scalar_rom(6860)
        TEST_SCALAR.write(rom, 7000)
        assert rom.is_modified

    def test_out_of_range_rejected(self):
        rom = make_scalar_rom(6860)
        assert not TEST_SCALAR.write(rom, 50000)
        assert TEST_SCALAR.read(rom) == pytest.approx(6860)

    def test_read_missing_needle_returns_none(self):
        assert TEST_SCALAR.read(make_rom()) is None

    def test_write_missing_needle_returns_false(self):
        assert not TEST_SCALAR.write(make_rom(), 7000)


# ── Registry ──────────────────────────────────────────────────────────────────

class TestRegistry:
    def test_patches_have_required_fields(self):
        from meseventool.patches import OffsetPatchDef, MultiOffsetPatchDef
        for p in PATCH_REGISTRY:
            assert p.name
            assert p.description
            assert isinstance(p.category, PatchCategory)
            # Needle/mask only on needle-based patches
            if isinstance(p, MultiOffsetPatchDef):
                assert len(p.sites) > 0
                for site in p.sites:
                    assert len(site) == 3  # (offset, stock_byte, patch_byte)
            elif isinstance(p, OffsetPatchDef):
                assert len(p.stock_bytes) == len(p.patch_bytes)
            else:
                assert len(p.needle) == len(p.mask)
                assert len(p.stock_bytes) == len(p.patch_bytes)

    def test_scalars_have_required_fields(self):
        for s in SCALAR_REGISTRY:
            assert s.name
            assert s.unit
            assert s.min_val < s.max_val

    def test_detect_all_on_empty_rom(self):
        rom = make_rom()
        results = detect_all(rom)
        assert len(results) == len(PATCH_REGISTRY)
        for r in results:
            assert isinstance(r.state, PatchState)

    def test_patch_count(self):
        assert len(PATCH_REGISTRY) >= 7

    def test_categories_present(self):
        cats = {p.category for p in PATCH_REGISTRY}
        assert PatchCategory.EMISSIONS in cats
        assert PatchCategory.IMMOBILISER in cats


# ── OffsetPatchDef unit tests ─────────────────────────────────────────────────

class TestOffsetPatchDef:
    """Unit tests for the OffsetPatchDef class (no real ROM required)."""

    def _make_rom_with_anchor(self, anchor: bytes, anchor_pos: int = 0x1000,
                               patch_offset: int = -4,
                               stock_val: bytes = b'\xAB\xCD',
                               size: int = 0x8000) -> ROMImage:
        data = bytearray(size)
        data[anchor_pos:anchor_pos + len(anchor)] = anchor
        site = anchor_pos + patch_offset
        data[site:site + len(stock_val)] = stock_val
        return ROMImage(data=data)

    def test_detect_stock(self):
        p = OffsetPatchDef(
            name="Test", description="Test", category=PatchCategory.EMISSIONS,
            anchor_bytes=b"ANCHOR", anchor_offset=-4,
            stock_bytes=b'\xAB\xCD', patch_bytes=b'\x00\x00',
        )
        rom = self._make_rom_with_anchor(b"ANCHOR", anchor_pos=0x1000,
                                          patch_offset=-4, stock_val=b'\xAB\xCD')
        r = p.detect(rom)
        assert r.state == PatchState.STOCK
        assert r.addr == 0x1000 - 4

    def test_detect_patched(self):
        p = OffsetPatchDef(
            name="Test", description="Test", category=PatchCategory.EMISSIONS,
            anchor_bytes=b"ANCHOR", anchor_offset=-4,
            stock_bytes=b'\xAB\xCD', patch_bytes=b'\x00\x00',
        )
        rom = self._make_rom_with_anchor(b"ANCHOR", anchor_pos=0x1000,
                                          patch_offset=-4, stock_val=b'\x00\x00')
        r = p.detect(rom)
        assert r.state == PatchState.PATCHED

    def test_detect_missing_anchor(self):
        p = OffsetPatchDef(
            name="Test", description="Test", category=PatchCategory.EMISSIONS,
            anchor_bytes=b"NOTHERE", anchor_offset=-4,
            stock_bytes=b'\xAB\xCD', patch_bytes=b'\x00\x00',
        )
        rom = ROMImage(data=bytearray(0x8000))
        r = p.detect(rom)
        assert r.state == PatchState.MISSING

    def test_apply_and_revert(self):
        p = OffsetPatchDef(
            name="Test", description="Test", category=PatchCategory.EMISSIONS,
            anchor_bytes=b"ANCHOR", anchor_offset=-4,
            stock_bytes=b'\xAB\xCD', patch_bytes=b'\x00\x00',
        )
        rom = self._make_rom_with_anchor(b"ANCHOR", anchor_pos=0x1000,
                                          patch_offset=-4, stock_val=b'\xAB\xCD')
        r = p.detect(rom)
        assert r.state == PatchState.STOCK
        p.apply(rom, r)
        r2 = p.detect(rom)
        assert r2.state == PatchState.PATCHED
        p.revert(rom, r2)
        r3 = p.detect(rom)
        assert r3.state == PatchState.STOCK

    def test_positive_offset(self):
        """Anchor offset can be positive (patch site after anchor)."""
        p = OffsetPatchDef(
            name="Test", description="Test", category=PatchCategory.EMISSIONS,
            anchor_bytes=b"TAG", anchor_offset=8,
            stock_bytes=b'\xFF', patch_bytes=b'\x00',
        )
        data = bytearray(0x8000)
        data[0x500:0x503] = b"TAG"
        data[0x508] = 0xFF
        rom = ROMImage(data=data)
        r = p.detect(rom)
        assert r.state == PatchState.STOCK
        assert r.addr == 0x508


# ── MultiOffsetPatchDef unit tests ────────────────────────────────────────────

class TestMultiOffsetPatchDef:
    """Unit tests for the MultiOffsetPatchDef class."""

    def _make_patch(self):
        return MultiOffsetPatchDef(
            name="Test Multi", description="Test", category=PatchCategory.EMISSIONS,
            anchor_bytes=b"BASE",
            sites=[(0x10, 0x03, 0x00), (0x20, 0x03, 0x00), (0x30, 0x03, 0x00)],
        )

    def _make_rom(self, anchor_pos=0x500, site_vals=(0x03, 0x03, 0x03)):
        data = bytearray(0x8000)
        data[anchor_pos:anchor_pos+4] = b"BASE"
        offsets = [0x10, 0x20, 0x30]
        for off, val in zip(offsets, site_vals):
            data[anchor_pos + off] = val
        return ROMImage(data=data)

    def test_detect_all_stock(self):
        p   = self._make_patch()
        rom = self._make_rom(site_vals=(0x03, 0x03, 0x03))
        r   = p.detect(rom)
        assert r.state == PatchState.STOCK

    def test_detect_all_patched(self):
        p   = self._make_patch()
        rom = self._make_rom(site_vals=(0x00, 0x00, 0x00))
        r   = p.detect(rom)
        assert r.state == PatchState.PATCHED

    def test_detect_mixed_is_unknown(self):
        p   = self._make_patch()
        rom = self._make_rom(site_vals=(0x03, 0x00, 0x03))
        r   = p.detect(rom)
        assert r.state == PatchState.UNKNOWN

    def test_detect_missing_anchor(self):
        p   = self._make_patch()
        rom = ROMImage(data=bytearray(0x8000))
        r   = p.detect(rom)
        assert r.state == PatchState.MISSING

    def test_apply_sets_all_sites(self):
        p   = self._make_patch()
        rom = self._make_rom(site_vals=(0x03, 0x03, 0x03))
        r   = p.detect(rom)
        p.apply(rom, r)
        r2  = p.detect(rom)
        assert r2.state == PatchState.PATCHED

    def test_revert_restores_all_sites(self):
        p   = self._make_patch()
        rom = self._make_rom(site_vals=(0x00, 0x00, 0x00))
        r   = p.detect(rom)
        assert r.state == PatchState.PATCHED
        p.revert(rom, r)
        r2  = p.detect(rom)
        assert r2.state == PatchState.STOCK

    def test_apply_revert_roundtrip(self):
        p   = self._make_patch()
        rom = self._make_rom(site_vals=(0x03, 0x03, 0x03))
        r0  = p.detect(rom)
        p.apply(rom, r0)
        r1  = p.detect(rom)
        assert r1.state == PatchState.PATCHED
        p.revert(rom, r1)
        r2  = p.detect(rom)
        assert r2.state == PatchState.STOCK


# ── Real ROM integration tests ────────────────────────────────────────────────

import os as _os
_DL_OEM = '/mnt/user-data/uploads/06A906032DL_0261206890_v360227_MT_OEM.bin'
_REAL_ROM_AVAILABLE = _os.path.exists(_DL_OEM)


@pytest.mark.skipif(not _REAL_ROM_AVAILABLE,
                    reason="Real 06A906032DL ROM not mounted")
class TestRealROMPatches:
    """
    Integration tests against the real 06A906032DL OEM ROM.
    Skip gracefully if the file isn't mounted (CI / other machines).
    """

    @pytest.fixture(scope="class")
    def dl_rom(self):
        from meseventool.rom import ROMImage
        return ROMImage.load(_DL_OEM)

    @pytest.fixture(scope="class")
    def dl_results(self, dl_rom):
        from meseventool.needle import Searcher
        from meseventool.dpp import DPPExtractor
        from meseventool.ecu_id import identify
        from meseventool.profiles import detect_profile
        s = Searcher(dl_rom)
        s.find_dppx()
        profile = detect_profile(identify(dl_rom), DPPExtractor(s).extract())
        return detect_all(dl_rom, s, profile)

    def _get(self, results, name):
        return next((r for r in results if r.patch.name == name), None)

    def test_knock_retard_found_stock(self, dl_results):
        r = self._get(dl_results, "Knock Retard Disable")
        assert r is not None
        assert r.state == PatchState.STOCK
        assert r.addr == 0x035D9E

    def test_o2_threshold_stock_at_correct_addr(self, dl_results):
        r = self._get(dl_results, "Rear O2 Monitor Threshold")
        assert r is not None
        assert r.state == PatchState.STOCK
        assert r.addr == 0x0111D7, f"Expected 0x0111D7, got 0x{r.addr:06X}"

    def test_o2_obd_flags_all_stock(self, dl_results):
        r = self._get(dl_results, "Rear O2 OBD Readiness Flags")
        assert r is not None
        assert r.state == PatchState.STOCK
        assert r.addr == 0x010751, f"Expected 0x010751, got 0x{r.addr:06X}"

    def test_dpp1_correct_value(self, dl_rom):
        from meseventool.needle import Searcher
        s = Searcher(dl_rom)
        assert s.find_dppx()
        assert s.dpp1 == 0x0205, f"DPP1 expected 0x0205, got 0x{s.dpp1:04X}"

    def test_ecu_pn_identified(self, dl_rom):
        from meseventool.ecu_id import identify
        ident = identify(dl_rom)
        assert ident.vmecuhn == "06A906032DL"
        assert ident.ssecuhn == "0261206890"

    def test_profile_detected_correctly(self, dl_rom):
        from meseventool.needle import Searcher
        from meseventool.dpp import DPPExtractor
        from meseventool.ecu_id import identify
        from meseventool.profiles import detect_profile
        s = Searcher(dl_rom)
        s.find_dppx()
        profile = detect_profile(identify(dl_rom), DPPExtractor(s).extract())
        assert profile is not None
        assert "me7.5" in profile.platforms
        assert "1.8t"  in profile.platforms

    def test_kfzw_timing_data_valid(self, dl_rom):
        """KFZW ignition table at XDF offset 0x0120DD should have plausible values."""
        import struct
        from meseventool.xdf import XDFLoader
        loader = XDFLoader()
        kfzw   = loader.get('06A906032DL', 'KFZW')
        addr   = kfzw.z.addr
        raw    = [dl_rom.data[addr + i] for i in range(16)]
        # First row decoded: signed byte * scale (from XDF). Values 0–25° typical.
        decoded = [b if b < 128 else b - 256 for b in raw]
        scale   = kfzw.z.scale
        degrees = [v * scale for v in decoded]
        assert all(-5 <= d <= 40 for d in degrees), \
            f"KFZW row 0 has implausible values: {degrees}"
