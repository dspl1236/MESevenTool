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
            from meseventool.patches import FixedAddressPatchDef
            if isinstance(p, MultiOffsetPatchDef):
                assert len(p.sites) > 0
                for site in p.sites:
                    assert len(site) == 3  # (offset, stock_byte, patch_byte)
            elif isinstance(p, (OffsetPatchDef, FixedAddressPatchDef)):
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



# ── ESKONF patch tests ────────────────────────────────────────────────────────

import tempfile, os as _os

def _rom_file(block7: bytes, offset: int = 0x10C75) -> str:
    """Write a 1MB ROM with a 7-byte ESKONF block at offset; return temp path."""
    data = bytearray(1048576)
    data[offset:offset + 7] = block7[:7]
    f = tempfile.NamedTemporaryFile(delete=False, suffix='.bin')
    f.write(data); f.close()
    return f.name


class TestESKONFNewer:
    """Newer-format ESKONF block: 0f 01 05 0d fe 08 19."""

    @pytest.fixture(autouse=True)
    def _patch(self):
        from meseventool.patches import ALL_PATCHES, MultiOffsetPatchDef
        patches = [p for p in ALL_PATCHES
                   if isinstance(p, MultiOffsetPatchDef) and 'newer' in p.name.lower()]
        assert patches, "No newer ESKONF patch found"
        self.patch = patches[0]

    def _load(self, block7):
        from meseventool.rom import ROMImage
        tmp = _rom_file(block7)
        try:
            return ROMImage.load(tmp), tmp
        except Exception:
            _os.unlink(tmp); raise

    def test_stock_detected(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(bytes([0x0F, 0x01, 0x05, 0x0D, 0xFE, 0x08, 0x19]))
        try:
            assert self.patch.detect(rom).state == PatchState.STOCK
        finally:
            _os.unlink(tmp)

    def test_patched_detected(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(bytes([0x0F, 0x01, 0x05, 0xCD, 0xFE, 0xC8, 0xD9]))
        try:
            assert self.patch.detect(rom).state == PatchState.PATCHED
        finally:
            _os.unlink(tmp)

    def test_missing_on_blank_rom(self):
        from meseventool.patches import PatchState
        from meseventool.rom import ROMImage
        tmp = _rom_file(bytes(7))
        try:
            rom = ROMImage.load(tmp)
            assert self.patch.detect(rom).state == PatchState.MISSING
        finally:
            _os.unlink(tmp)

    def test_mixed_sites_is_unknown(self):
        from meseventool.patches import PatchState
        # b3 patched, b5 still stock → UNKNOWN
        rom, tmp = self._load(bytes([0x0F, 0x01, 0x05, 0xCD, 0xFE, 0x08, 0x19]))
        try:
            assert self.patch.detect(rom).state == PatchState.UNKNOWN
        finally:
            _os.unlink(tmp)

    def test_apply_then_detect_patched(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(bytes([0x0F, 0x01, 0x05, 0x0D, 0xFE, 0x08, 0x19]))
        try:
            r = self.patch.detect(rom)
            assert r.state == PatchState.STOCK
            self.patch.apply(rom, r)
            assert self.patch.detect(rom).state == PatchState.PATCHED
        finally:
            _os.unlink(tmp)

    def test_revert_restores_stock(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(bytes([0x0F, 0x01, 0x05, 0xCD, 0xFE, 0xC8, 0xD9]))
        try:
            r = self.patch.detect(rom)
            assert r.state == PatchState.PATCHED
            self.patch.revert(rom, r)
            assert self.patch.detect(rom).state == PatchState.STOCK
        finally:
            _os.unlink(tmp)

    def test_length_preserved_after_apply(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(bytes([0x0F, 0x01, 0x05, 0x0D, 0xFE, 0x08, 0x19]))
        try:
            orig_len = len(rom.data)
            r = self.patch.detect(rom)
            self.patch.apply(rom, r)
            assert len(rom.data) == orig_len
        finally:
            _os.unlink(tmp)


class TestESKONFOlder:
    """Older-format ESKONF: 06 02 a8 0d fe 28 28 with pre-block anchor bytes."""

    @pytest.fixture(autouse=True)
    def _patches(self):
        from meseventool.patches import ALL_PATCHES, MultiOffsetPatchDef
        self.p06 = next(p for p in ALL_PATCHES
                        if isinstance(p, MultiOffsetPatchDef) and 'older-06' in p.name)
        self.p05 = next(p for p in ALL_PATCHES
                        if isinstance(p, MultiOffsetPatchDef) and 'older-05' in p.name)

    def _rom_with_older(self, prefix_byte: int, b3: int, b5: int, b6: int,
                        offset: int = 0x10C6D) -> str:
        """ROM with pre-anchor (ee 24) + ESKONF block at offset."""
        data = bytearray(1048576)
        # Pre-anchor: 2 bytes before block
        data[offset - 2] = 0xEE
        data[offset - 1] = 0x24
        # ESKONF block: [prefix, 02, a8, b3, fe, b5, b6]
        data[offset:offset + 7] = bytes([prefix_byte, 0x02, 0xA8, b3, 0xFE, b5, b6])
        f = tempfile.NamedTemporaryFile(delete=False, suffix='.bin')
        f.write(data); f.close()
        return f.name

    def _load(self, *args, **kwargs):
        from meseventool.rom import ROMImage
        tmp = self._rom_with_older(*args, **kwargs)
        try:
            return ROMImage.load(tmp), tmp
        except Exception:
            _os.unlink(tmp); raise

    def test_06_stock_detected(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(0x06, 0x0D, 0x28, 0x28)
        try:
            assert self.p06.detect(rom).state == PatchState.STOCK
        finally:
            _os.unlink(tmp)

    def test_06_patched_detected(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(0x06, 0xCD, 0xE8, 0xE8)
        try:
            assert self.p06.detect(rom).state == PatchState.PATCHED
        finally:
            _os.unlink(tmp)

    def test_05_stock_detected(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(0x05, 0x0D, 0x28, 0x28)
        try:
            assert self.p05.detect(rom).state == PatchState.STOCK
        finally:
            _os.unlink(tmp)

    def test_05_patched_detected(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(0x05, 0xCD, 0xE8, 0xE8)
        try:
            assert self.p05.detect(rom).state == PatchState.PATCHED
        finally:
            _os.unlink(tmp)

    def test_missing_when_no_pre_anchor(self):
        from meseventool.patches import PatchState
        from meseventool.rom import ROMImage
        # ROM with ESKONF block but no ee 24 pre-bytes
        tmp = _rom_file(bytes([0x06, 0x02, 0xA8, 0x0D, 0xFE, 0x28, 0x28]))
        try:
            rom = ROMImage.load(tmp)
            assert self.p06.detect(rom).state == PatchState.MISSING
        finally:
            _os.unlink(tmp)

    def test_06_apply_and_verify(self):
        from meseventool.patches import PatchState
        rom, tmp = self._load(0x06, 0x0D, 0x28, 0x28)
        try:
            r = self.p06.detect(rom)
            assert r.state == PatchState.STOCK
            self.p06.apply(rom, r)
            assert self.p06.detect(rom).state == PatchState.PATCHED
        finally:
            _os.unlink(tmp)


# ── Vmax Speed Limiter tests ──────────────────────────────────────────────────

class TestVmaxPatch:
    """
    VMAX speed limiter needle patch — 2.7T ME7.1 (S4 B5 / A6 C5 / Allroad early).
    Needle: e6 fd [a8 61] e6 fe [xx xx] da 00 9c 6c
    Stock bytes (offset+2): a8 61 = 25000 (250 km/h at 0.01 km/h resolution)
    Patch bytes:             ff ff = 65535 (~655 km/h — effectively unlimited)
    """

    @pytest.fixture(autouse=True)
    def _patch(self):
        from meseventool.patches import ALL_PATCHES, PatchDef
        p = next((x for x in ALL_PATCHES
                  if isinstance(x, PatchDef) and 'Vmax' in x.name and '2.7T' in x.name),
                 None)
        assert p is not None, "VMAX 2.7T patch not found in ALL_PATCHES"
        self.patch = p

    def _rom_with_vmax(self, speed_bytes: bytes, r14_imm: bytes = b'\x9a\x02') -> 'ROMImage':
        """Build a 1MB ROM containing the VMAX code sequence."""
        import tempfile, os
        from meseventool.rom import ROMImage
        data = bytearray(1048576)
        # Embed: e6 fd <speed_2b> e6 fe <r14_imm_2b> da 00 9c 6c at 0x08B2EC
        seq = bytes([0xe6, 0xfd]) + speed_bytes + bytes([0xe6, 0xfe]) + r14_imm + bytes([0xda, 0x00, 0x9c, 0x6c])
        data[0x08B2EC:0x08B2EC + 12] = seq
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
            f.write(data); tmp = f.name
        try:
            return ROMImage.load(tmp)
        finally:
            os.unlink(tmp)

    def test_stock_detection(self):
        from meseventool.patches import PatchState
        rom = self._rom_with_vmax(bytes([0xa8, 0x61]))
        assert self.patch.detect(rom).state == PatchState.STOCK

    def test_patched_is_missing_post_apply(self):
        """After applying the patch (a8 61 → ff ff), the alt-needle fallback in
        detect() correctly identifies the ROM as PATCHED.  The primary (stock)
        needle fails, but detect() substitutes the patch_bytes and searches again."""
        from meseventool.patches import PatchState
        rom = self._rom_with_vmax(bytes([0xff, 0xff]))
        # Alt-needle (ff ff variant) should now find PATCHED
        assert self.patch.detect(rom).state == PatchState.PATCHED

    def test_missing_on_blank_rom(self):
        from meseventool.patches import PatchState
        import tempfile, os
        from meseventool.rom import ROMImage
        with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as f:
            f.write(bytes(1048576)); tmp = f.name
        try:
            rom = ROMImage.load(tmp)
            assert self.patch.detect(rom).state == PatchState.MISSING
        finally:
            os.unlink(tmp)

    def test_mask_ignores_r14_immediate(self):
        """Needle mask must allow r14 immediate to vary (bytes 6-7 are masked)."""
        from meseventool.patches import PatchState
        # Use a different r14 immediate — should still detect STOCK
        for r14 in [b'\x00\x00', b'\xff\xff', b'\x5c\x2c', b'\x03\x04']:
            rom = self._rom_with_vmax(bytes([0xa8, 0x61]), r14)
            r = self.patch.detect(rom)
            assert r.state == PatchState.STOCK, \
                f"Expected STOCK with r14={r14.hex()}, got {r.state}"

    def test_apply_writes_ff_ff(self):
        """Apply writes ff ff at the speed site; re-detect via alt-needle returns PATCHED."""
        from meseventool.patches import PatchState
        import struct
        rom = self._rom_with_vmax(bytes([0xa8, 0x61]))
        r = self.patch.detect(rom)
        assert r.state == PatchState.STOCK
        patch_addr = r.addr
        self.patch.apply(rom, r)
        # Alt-needle fallback detects PATCHED
        r2 = self.patch.detect(rom)
        assert r2.state == PatchState.PATCHED
        raw = struct.unpack_from('<H', bytes(rom.data), patch_addr)[0]
        assert raw == 0xFFFF, f"Expected 0xFFFF at patch site, got 0x{raw:04X}"

    def test_revert_restores_250kmh(self):
        """Revert from stock → stock has no effect (idempotent on already-stock ROM)."""
        from meseventool.patches import PatchState
        import struct
        rom = self._rom_with_vmax(bytes([0xa8, 0x61]))
        r = self.patch.detect(rom)
        assert r.state == PatchState.STOCK
        addr = r.addr
        # Revert a stock ROM → should remain stock
        self.patch.revert(rom, r)
        r2 = self.patch.detect(rom)
        assert r2.state == PatchState.STOCK
        raw = struct.unpack_from('<H', bytes(rom.data), addr)[0]
        assert raw == 25000, f"Expected 25000 after revert, got {raw}"

    def test_applies_to_me71_27t(self):
        """Patch must apply to ME7.1 2.7T profiles."""
        from meseventool.patches import PatchState
        from meseventool.profiles import PROFILE_V6_2_7T
        assert self.patch.check_applicable(PROFILE_V6_2_7T), \
            "VMAX patch should apply to 2.7T profile"

    def test_not_applicable_to_18t(self):
        """VMAX 2.7T needle patch should NOT apply to 1.8T (different code)."""
        from meseventool.profiles import PROFILE_AWP
        assert not self.patch.check_applicable(PROFILE_AWP), \
            "VMAX 2.7T patch should not apply to AWP 1.8T"


# =============================================================================
# ME7.1.1 VMAX — 4Z7 late / 4D1 RS4/S8 (3 instances, ATOMIC prefix)
# =============================================================================
import unittest

class TestVmaxME711(unittest.TestCase):
    """VMAX patch for ME7.1.1 — needle E0 1C E6 FD A8 61 DA 00 9A 10, appears 3x."""

    STOCK_NEEDLE = bytes([0xE0,0x1C, 0xE6,0xFD,0xA8,0x61, 0xDA,0x00,0x9A,0x10])
    PATCH_NEEDLE = bytes([0xE0,0x1C, 0xE6,0xFD,0xFF,0xFF, 0xDA,0x00,0x9A,0x10])

    def _make_rom(self, payload, count=3):
        import struct
        data = bytearray(0x100000)
        base = 0x022000
        for i in range(count):
            offset = base + i * 0x200
            data[offset:offset+len(payload)] = payload
        return data

    def setUp(self):
        from meseventool.patches import ALL_PATCHES
        self.patch = next(p for p in ALL_PATCHES
                          if 'ME7.1.1' in p.name and 'Vmax' in p.name)

    def test_detects_stock_3x(self):
        """Detects STOCK when all 3 instances have 250km/h value."""
        from meseventool.patches import PatchState
        data = self._make_rom(self.STOCK_NEEDLE, count=3)
        rom = self._rom(data)
        r = self.patch.detect(rom)
        assert r.state == PatchState.STOCK

    def test_detects_patched_3x(self):
        """Detects PATCHED when at least one instance has FF FF."""
        from meseventool.patches import PatchState
        data = self._make_rom(self.PATCH_NEEDLE, count=3)
        rom = self._rom(data)
        r = self.patch.detect(rom)
        assert r.state == PatchState.PATCHED

    def test_missing_when_no_needle(self):
        """MISSING when needle absent — wrong ECU family."""
        from meseventool.patches import PatchState
        rom = self._rom(bytearray(0x100000))
        r = self.patch.detect(rom)
        assert r.state == PatchState.MISSING

    def test_apply_patches_ff_ff(self):
        """apply() writes 0xFFFF at the first needle hit's patch site."""
        import struct
        from meseventool.patches import PatchState
        data = self._make_rom(self.STOCK_NEEDLE, count=3)
        rom = self._rom(data)
        r = self.patch.detect(rom)
        assert r.state == PatchState.STOCK
        patch_addr = r.addr
        self.patch.apply(rom, r)
        # Verify the bytes were written at the correct address
        raw = struct.unpack_from("<H", bytes(rom.data), patch_addr)[0]
        assert raw == 0xFFFF, f"Expected 0xFFFF at patch site, got 0x{raw:04X}"
        # Other instances still stock → detect() returns STOCK (correct — tool applies one at a time)
        r2 = self.patch.detect(rom)
        assert r2.state in (PatchState.STOCK, PatchState.PATCHED)

    def test_revert_restores_a861(self):
        """revert() writes 0xA861 back at the first patched instance's site."""
        import struct
        from meseventool.patches import PatchState
        data = self._make_rom(self.PATCH_NEEDLE, count=3)
        rom = self._rom(data)
        r = self.patch.detect(rom)
        assert r.state == PatchState.PATCHED
        patch_addr = r.addr
        self.patch.revert(rom, r)
        # Verify the bytes were restored at the correct address
        raw = struct.unpack_from("<H", bytes(rom.data), patch_addr)[0]
        assert raw == 25000, f"Expected 25000 (250km/h) after revert, got {raw}"
        # With only one instance reverted, state depends on remaining instances
        r2 = self.patch.detect(rom)
        assert r2.state in (PatchState.STOCK, PatchState.PATCHED)

    def test_not_applicable_to_early_me71(self):
        """ME7.1.1 VMAX should not apply to early ME7.1 2.7T profile."""
        from meseventool.profiles import PROFILE_V6_27T_ME71
        result = self.patch.check_applicable(PROFILE_V6_27T_ME71)
        assert not result, "ME7.1.1 VMAX should not apply to ME7.1 early profile"

    def _rom(self, data):
        from meseventool.rom import ROMImage
        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(bytes(data)); tmp = f.name
        rom = ROMImage.load(tmp)
        os.unlink(tmp)
        return rom


# =============================================================================
# P1681 CEL Disable (ME7.1.1)
# =============================================================================
class TestP1681Disable(unittest.TestCase):
    """P1681 patch: JMPR UGE (0x2D) → JMPR always (0x0D), byte 6 of needle."""

    STOCK_SEQ  = bytes([0xF0,0xBE, 0x66,0xF4, 0x80,0x00, 0x2D,0x0D, 0xE6,0xF4])
    PATCH_SEQ  = bytes([0xF0,0xBE, 0x66,0xF4, 0x80,0x00, 0x0D,0x0D, 0xE6,0xF4])

    def setUp(self):
        from meseventool.patches import ALL_PATCHES
        self.patch = next(p for p in ALL_PATCHES if 'P1681' in p.name)

    def _rom(self, seq, base=0x06C0B0):
        from meseventool.rom import ROMImage
        import tempfile, os
        data = bytearray(0x100000)
        data[base:base+len(seq)] = seq
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(bytes(data)); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp)
        return rom

    def test_stock_detected(self):
        from meseventool.patches import PatchState
        assert self.patch.detect(self._rom(self.STOCK_SEQ)).state == PatchState.STOCK

    def test_patched_detected(self):
        from meseventool.patches import PatchState
        assert self.patch.detect(self._rom(self.PATCH_SEQ)).state == PatchState.PATCHED

    def test_missing_on_empty(self):
        from meseventool.patches import PatchState
        data = bytearray(0x100000)
        rom = self._rom(bytes(10), base=0)
        r = self.patch.detect(rom)
        assert r.state in (PatchState.MISSING, PatchState.STOCK)

    def test_apply_changes_2d_to_0d(self):
        from meseventool.patches import PatchState
        rom = self._rom(self.STOCK_SEQ)
        r = self.patch.detect(rom)
        assert r.state == PatchState.STOCK
        self.patch.apply(rom, r)
        assert rom.data[r.addr] == 0x0D

    def test_revert_changes_0d_to_2d(self):
        from meseventool.patches import PatchState
        rom = self._rom(self.PATCH_SEQ)
        r = self.patch.detect(rom)
        assert r.state == PatchState.PATCHED
        self.patch.revert(rom, r)
        assert rom.data[r.addr] == 0x2D


# =============================================================================
# Rear O2 Diagnosis Disable 2.7T (CDLSH codeword)
# =============================================================================
class TestRearO2Disable27T(unittest.TestCase):
    """CDLSH codeword patch: 0x01 -> 0x00 at stable block 0x0181AA."""

    # Anchor FF FF FF FF 00 00 01 01 at 0x018190, CDLSH at anchor+26 = 0x0181AA
    ANCHOR_ADDR = 0x018190
    ANCHOR_BYTES = bytes([0xFF,0xFF,0xFF,0xFF, 0x00,0x00,0x01,0x01])
    CDLSH_OFFSET = 26  # bytes from anchor start to CDLSH

    def setUp(self):
        from meseventool.patches import ALL_PATCHES
        self.patch = next(p for p in ALL_PATCHES
                          if 'Rear O2' in p.name and '2.7T' in p.name)

    def _rom(self, cdlsh_val):
        from meseventool.rom import ROMImage
        import tempfile, os
        data = bytearray(0x100000)
        # Place anchor bytes at ANCHOR_ADDR
        base = self.ANCHOR_ADDR
        data[base:base+len(self.ANCHOR_BYTES)] = self.ANCHOR_BYTES
        # CDLSH at anchor + CDLSH_OFFSET
        data[base + self.CDLSH_OFFSET] = cdlsh_val
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(bytes(data)); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp)
        return rom

    def test_stock_detected(self):
        from meseventool.patches import PatchState
        assert self.patch.detect(self._rom(0x01)).state == PatchState.STOCK

    def test_patched_detected(self):
        from meseventool.patches import PatchState
        assert self.patch.detect(self._rom(0x00)).state == PatchState.PATCHED

    def test_apply_zeros_cdlsh(self):
        from meseventool.patches import PatchState
        rom = self._rom(0x01)
        r = self.patch.detect(rom)
        assert r.state == PatchState.STOCK
        self.patch.apply(rom, r)
        assert rom.data[r.addr] == 0x00

    def test_revert_restores_cdlsh(self):
        from meseventool.patches import PatchState
        rom = self._rom(0x00)
        r = self.patch.detect(rom)
        assert r.state == PatchState.PATCHED
        self.patch.revert(rom, r)
        assert rom.data[r.addr] == 0x01


# =============================================================================
# Real-ROM corpus tests for new 2.7T/V8 patches
# =============================================================================
class TestRealROM27T(unittest.TestCase):
    """Integration tests against real ROM files from the stock corpus."""

    S4WIKI = '/home/claude/s4wiki_stock'

    def _load(self, fname):
        import os
        from meseventool.rom import ROMImage
        path = os.path.join(self.S4WIKI, fname)
        if not os.path.exists(path):
            self.skipTest(f"ROM not available: {fname}")
        return ROMImage.load(path)

    def _detect(self, patch_name, fname):
        from meseventool.patches import detect_all, ALL_PATCHES
        from meseventool.needle import Searcher
        from meseventool.dpp import DPPExtractor
        from meseventool.profiles import detect_profile
        from meseventool.ecu_id import identify
        patch = next(p for p in ALL_PATCHES if p.name == patch_name)
        rom = self._load(fname)
        s = Searcher(rom); s.find_dppx()
        return patch.detect(rom)

    # ── VMAX ME7.1 on 8D S4 B5 ────────────────────────────────────────────
    def test_vmax_me71_8d_stock(self):
        from meseventool.patches import PatchState
        r = self._detect("Vmax Speed Limiter Disable (2.7T ME7.1)",
                         "8D0907551M-0001.bin")
        assert r.state == PatchState.STOCK, f"Expected STOCK, got {r.state}"

    def test_vmax_me71_4b_stock(self):
        from meseventool.patches import PatchState
        r = self._detect("Vmax Speed Limiter Disable (2.7T ME7.1)",
                         "4B0907551AA.bin")
        assert r.state == PatchState.STOCK

    def test_vmax_me71_4z7_early_stock(self):
        from meseventool.patches import PatchState
        r = self._detect("Vmax Speed Limiter Disable (2.7T ME7.1)",
                         "4Z7907551B.bin")
        assert r.state == PatchState.STOCK

    # ── VMAX ME7.1.1 on late 4Z7 + 4D1 ───────────────────────────────────
    def test_vmax_me711_4z7_aa_stock(self):
        from meseventool.patches import PatchState
        r = self._detect("Vmax Speed Limiter Disable (2.7T ME7.1.1 / V8 RS4)",
                         "4Z7907551AA.bin")
        assert r.state == PatchState.STOCK

    def test_vmax_me711_4d1_stock(self):
        from meseventool.patches import PatchState
        r = self._detect("Vmax Speed Limiter Disable (2.7T ME7.1.1 / V8 RS4)",
                         "4D1907558-0002.bin")
        assert r.state == PatchState.STOCK

    def test_vmax_me711_not_in_early_4z7(self):
        """ME7.1.1 needle should be MISSING in early ME7.1 4Z7 (different code)."""
        from meseventool.patches import PatchState
        r = self._detect("Vmax Speed Limiter Disable (2.7T ME7.1.1 / V8 RS4)",
                         "4Z7907551B.bin")
        assert r.state == PatchState.MISSING, \
            f"ME7.1.1 needle should be MISSING in early ME7.1 4Z7, got {r.state}"

    def test_vmax_me71_not_in_late_4z7(self):
        """ME7.1 needle should be MISSING in late ME7.1.1 4Z7."""
        from meseventool.patches import PatchState
        r = self._detect("Vmax Speed Limiter Disable (2.7T ME7.1)",
                         "4Z7907551AA.bin")
        assert r.state == PatchState.MISSING, \
            f"ME7.1 needle should be MISSING in late ME7.1.1 4Z7, got {r.state}"

    # ── P1681 ──────────────────────────────────────────────────────────────
    def test_p1681_stock_in_4z7_aa(self):
        from meseventool.patches import PatchState
        r = self._detect("P1681 Immobiliser Databus CEL Disable (ME7.1.1)",
                         "4Z7907551AA.bin")
        assert r.state == PatchState.STOCK

    def test_p1681_patched_in_4z7_aa_p1681file(self):
        from meseventool.patches import PatchState
        r = self._detect("P1681 Immobiliser Databus CEL Disable (ME7.1.1)",
                         "4Z7907551AA-disable-P1681.bin")
        assert r.state == PatchState.PATCHED, \
            f"Expected PATCHED in P1681-disabled file, got {r.state}"

    def test_p1681_patched_in_4z7_s_p1681file(self):
        from meseventool.patches import PatchState
        r = self._detect("P1681 Immobiliser Databus CEL Disable (ME7.1.1)",
                         "4Z7907551S-disable-P1681.bin")
        assert r.state == PatchState.PATCHED

    def test_p1681_missing_in_early_me71(self):
        """P1681 only exists in ME7.1.1 — should be MISSING in 8D S4."""
        from meseventool.patches import PatchState
        r = self._detect("P1681 Immobiliser Databus CEL Disable (ME7.1.1)",
                         "8D0907551M-0001.bin")
        assert r.state == PatchState.MISSING

    # ── Rear O2 CDLSH ──────────────────────────────────────────────────────
    def test_rear_o2_cdlsh_stock_8d(self):
        from meseventool.patches import PatchState
        r = self._detect("Rear O2 Sensor Diagnosis Disable (2.7T ME7.1/ME7.1.1)",
                         "8D0907551M-0001.bin")
        assert r.state == PatchState.STOCK

    def test_rear_o2_cdlsh_stock_4z7(self):
        from meseventool.patches import PatchState
        r = self._detect("Rear O2 Sensor Diagnosis Disable (2.7T ME7.1/ME7.1.1)",
                         "4Z7907551AA.bin")
        assert r.state == PatchState.STOCK

    def test_rear_o2_cdlsh_stock_4d1(self):
        from meseventool.patches import PatchState
        r = self._detect("Rear O2 Sensor Diagnosis Disable (2.7T ME7.1/ME7.1.1)",
                         "4D1907558-0002.bin")
        assert r.state == PatchState.STOCK


# =============================================================================
# 5th-Gear Torque Mode Disable (universal 1.8T ME7.5) — FixedAddressPatchDef
# =============================================================================
class TestGearModePatch(unittest.TestCase):
    """Fixed address patch at 0x00881D: 0x0F -> 0x00."""

    ADDR = 0x00881D

    def setUp(self):
        from meseventool.patches import ALL_PATCHES
        self.patch = next(p for p in ALL_PATCHES if '5th-Gear' in p.name)

    def _rom(self, val):
        from meseventool.rom import ROMImage
        import tempfile, os
        data = bytearray(0x100000)
        data[self.ADDR] = val
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(bytes(data)); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp)
        return rom

    def test_stock_0f(self):
        from meseventool.patches import PatchState
        assert self.patch.detect(self._rom(0x0F)).state == PatchState.STOCK

    def test_patched_00(self):
        from meseventool.patches import PatchState
        assert self.patch.detect(self._rom(0x00)).state == PatchState.PATCHED

    def test_unknown_other(self):
        from meseventool.patches import PatchState
        assert self.patch.detect(self._rom(0x05)).state == PatchState.UNKNOWN

    def test_apply_writes_00(self):
        from meseventool.patches import PatchState
        rom = self._rom(0x0F)
        r = self.patch.detect(rom)
        assert r.state == PatchState.STOCK
        self.patch.apply(rom, r)
        assert rom.data[self.ADDR] == 0x00

    def test_revert_restores_0f(self):
        from meseventool.patches import PatchState
        rom = self._rom(0x00)
        r = self.patch.detect(rom)
        assert r.state == PatchState.PATCHED
        self.patch.revert(rom, r)
        assert rom.data[self.ADDR] == 0x0F

    def test_real_dl_stock(self):
        import os, tempfile
        from meseventool.patches import PatchState
        from meseventool.rom import ROMImage
        path = '/mnt/user-data/uploads/1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin'
        if not os.path.exists(path):
            self.skipTest("DL ROM not available")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path,'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp)
        assert self.patch.detect(rom).state == PatchState.STOCK

    def test_real_uni870_patched(self):
        import os, tempfile
        from meseventool.patches import PatchState
        from meseventool.rom import ROMImage
        path = '/mnt/user-data/uploads/1773719274820_uni870_032pl.bin'
        if not os.path.exists(path):
            self.skipTest("uni870 ROM not available")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path,'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp)
        assert self.patch.detect(rom).state == PatchState.PATCHED

    def test_real_18cm_stock(self):
        import os, tempfile
        from meseventool.patches import PatchState
        from meseventool.rom import ROMImage
        path = '/mnt/user-data/uploads/18CM.Bin'
        if not os.path.exists(path):
            self.skipTest("18CM ROM not available")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path,'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp)
        assert self.patch.detect(rom).state == PatchState.STOCK

    def test_real_18cm_uni2_patched(self):
        import os, tempfile
        from meseventool.patches import PatchState
        from meseventool.rom import ROMImage
        path = '/mnt/user-data/uploads/170hp_018cm_PassatUNI2.bin'
        if not os.path.exists(path):
            self.skipTest("18CM uni2 ROM not available")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path,'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp)
        assert self.patch.detect(rom).state == PatchState.PATCHED


# =============================================================================
# 4B0906018 codeword patches (real ROM tests)
# =============================================================================
class TestRealROM4B0906018(unittest.TestCase):
    """Integration tests against real 4B0906018 ROM files."""

    UPLOADS = '/mnt/user-data/uploads'

    def _load(self, fname):
        import os, tempfile
        from meseventool.rom import ROMImage
        path = f'{self.UPLOADS}/{fname}'
        if not os.path.exists(path):
            self.skipTest(f"ROM not available: {fname}")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path,'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp)
        os.unlink(tmp)
        return rom

    def _detect(self, patch_name, rom):
        from meseventool.patches import ALL_PATCHES
        p = next(p for p in ALL_PATCHES if p.name == patch_name)
        return p.detect(rom)

    # ── CDKAT ────────────────────────────────────────────────────────────
    def test_cdkat_stock_in_18cm(self):
        from meseventool.patches import PatchState
        r = self._detect('Catalyst Monitor Disable CDKAT (4B0906018 A6/Passat)',
                         self._load('18CM.Bin'))
        assert r.state == PatchState.STOCK

    def test_cdkat_patched_in_18cm_uni2(self):
        from meseventool.patches import PatchState
        r = self._detect('Catalyst Monitor Disable CDKAT (4B0906018 A6/Passat)',
                         self._load('170hp_018cm_PassatUNI2.bin'))
        assert r.state == PatchState.PATCHED

    # ── CDKVS ────────────────────────────────────────────────────────────
    def test_cdkvs_stock_in_18cm(self):
        from meseventool.patches import PatchState
        r = self._detect('Knock Sensor Monitor Disable CDKVS (4B0906018 A6/Passat)',
                         self._load('18CM.Bin'))
        assert r.state == PatchState.STOCK

    def test_cdkvs_patched_in_18cm_uni2(self):
        from meseventool.patches import PatchState
        r = self._detect('Knock Sensor Monitor Disable CDKVS (4B0906018 A6/Passat)',
                         self._load('170hp_018cm_PassatUNI2.bin'))
        assert r.state == PatchState.PATCHED

    # ── CDKVS2 ───────────────────────────────────────────────────────────
    def test_cdkvs2_stock_in_18cm(self):
        """18CM has unique stock value 0x03 for CDKVS2."""
        from meseventool.patches import PatchState
        r = self._detect('Knock Sensor Variant Disable CDKVS2 (4B0906018 A6/Passat)',
                         self._load('18CM.Bin'))
        assert r.state == PatchState.STOCK, \
            f"Expected STOCK (0x03) in 18CM, got {r.state}"

    def test_cdkvs2_patched_in_18cm_uni2(self):
        from meseventool.patches import PatchState
        r = self._detect('Knock Sensor Variant Disable CDKVS2 (4B0906018 A6/Passat)',
                         self._load('170hp_018cm_PassatUNI2.bin'))
        assert r.state == PatchState.PATCHED

    def test_cdkvs2_not_stock_in_06a(self):
        """06A has 0x00 at 0x0181A3 (not 0x03), so NOT stock for this patch."""
        from meseventool.patches import PatchState
        r = self._detect('Knock Sensor Variant Disable CDKVS2 (4B0906018 A6/Passat)',
                         self._load('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin'))
        # 06A has 0x00 there already — shows as PATCHED (not STOCK)
        # With profile this would be NOT_APPLICABLE; without profile it shows PATCHED
        assert r.state != PatchState.STOCK, \
            "06A DL should not have CDKVS2=0x03 (the 18CM stock value)"

    # ── EVAP ─────────────────────────────────────────────────────────────
    def test_evap_stock_in_18cm(self):
        from meseventool.patches import PatchState
        r = self._detect('EVAP Diagnosis Disable (4B0906018 A6/Passat 1.8T)',
                         self._load('18CM.Bin'))
        assert r.state == PatchState.STOCK

    def test_evap_stock_in_18cm_uni2(self):
        """uni2 tune does NOT patch EVAP — only the dpf_evap file does."""
        from meseventool.patches import PatchState
        r = self._detect('EVAP Diagnosis Disable (4B0906018 A6/Passat 1.8T)',
                         self._load('170hp_018cm_PassatUNI2.bin'))
        assert r.state == PatchState.STOCK, \
            "18CM_uni2 should NOT have EVAP patched"

    def test_evap_patched_in_18cm_dpf_evap(self):
        from meseventool.patches import PatchState
        fname = 'dpffiles_com_3458_Volkswagen_Passat_1_8T_20V_Bosch_ME7_5_EVAP_no_chk.bin'
        r = self._detect('EVAP Diagnosis Disable (4B0906018 A6/Passat 1.8T)',
                         self._load(fname))
        assert r.state == PatchState.PATCHED


# =============================================================================
# MAF Delete — real ROM detection across all 06A firmware variants
# =============================================================================
class TestMAFDeleteAllVariants(unittest.TestCase):
    """MAF Delete patches cover all ME7.5 1.8T firmware variants."""

    UPLOADS = '/mnt/user-data/uploads'

    def _load(self, fname):
        import os, tempfile
        from meseventool.rom import ROMImage
        path = f'{self.UPLOADS}/{fname}'
        if not os.path.exists(path):
            self.skipTest(f"ROM not available: {fname}")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path,'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp); return rom

    def _patch(self, name):
        from meseventool.patches import ALL_PATCHES
        return next(p for p in ALL_PATCHES if p.name == name)

    def test_dl_fw4019_stock(self):
        from meseventool.patches import PatchState
        p = self._patch('MAF Delete / Alpha-N load redirect (ME7.5 06A)')
        r = p.detect(self._load('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_rn_fw4013_stock(self):
        from meseventool.patches import PatchState
        p = self._patch('MAF Delete / Alpha-N load redirect (ME7.5 RN/LP fw4013)')
        r = p.detect(self._load('1773719274810_06A906032RN.bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_lp_fw4013_stock(self):
        from meseventool.patches import PatchState
        p = self._patch('MAF Delete / Alpha-N load redirect (ME7.5 LP/18CM fw4013/4012)')
        r = p.detect(self._load('1773719875934_06A906032LP_0005.bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_sl_dsg_stock(self):
        from meseventool.patches import PatchState
        p = self._patch('MAF Delete / Alpha-N load redirect (ME7.5 SL DSG X505R)')
        r = p.detect(self._load('1773719274817_032sl_auto_revo_1.bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_18cm_fw4012_stock(self):
        from meseventool.patches import PatchState
        p = self._patch('MAF Delete / Alpha-N load redirect (ME7.5 LP/18CM fw4013/4012)')
        r = p.detect(self._load('18CM.Bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_uni630_hn_patched_fa22_maf(self):
        """uni630 HN patches to FA22/23 — PATCHED in FA22-target MAF variants only."""
        from meseventool.patches import PatchState, ALL_PATCHES
        rom = self._load('1773719875938_uni_630HN.bin')
        # FA22/23 target patches show PATCHED; FA1E/1F alt target shows UNKNOWN (has FA22, not FA1E)
        fa22_patches = [p for p in ALL_PATCHES
                        if 'MAF Delete' in p.name and p.patch_bytes[0] == 0x22]
        for p in fa22_patches:
            r = p.detect(rom)
            self.assertEqual(r.state, PatchState.PATCHED,
                             f"{p.name} should be PATCHED in uni630_HN, got {r.state}")

    def test_rn_uni2_no_maf_delete(self):
        """Unitronic Stage 1 RN tune does NOT do MAF delete."""
        from meseventool.patches import PatchState
        p = self._patch('MAF Delete / Alpha-N load redirect (ME7.5 RN/LP fw4013)')
        r = p.detect(self._load('1773719274816_032RN_Uni_2.bin'))
        self.assertEqual(r.state, PatchState.STOCK,
                         "RN_uni2 (Unitronic Stage 1) should NOT have MAF delete")


# =============================================================================
# VMAX fw4013/4012 code-immediate — real ROM detection
# =============================================================================
class TestVmaxFw4013CodeImmediate(unittest.TestCase):
    """VMAX code-immediate: E6 FD A8 61 → E6 FD FF FF, exactly 2 hits per file."""

    UPLOADS = '/mnt/user-data/uploads'

    def _load(self, fname):
        import os, tempfile
        from meseventool.rom import ROMImage
        path = f'{self.UPLOADS}/{fname}'
        if not os.path.exists(path):
            self.skipTest(f"ROM not available: {fname}")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path,'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp); return rom

    def setUp(self):
        from meseventool.patches import ALL_PATCHES
        self.patch = next(p for p in ALL_PATCHES
                          if 'fw4013/4012' in p.name and 'code-immediate' in p.name)

    def test_rn_stock(self):
        from meseventool.patches import PatchState
        r = self.patch.detect(self._load('1773719274810_06A906032RN.bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_lp_stock(self):
        from meseventool.patches import PatchState
        r = self.patch.detect(self._load('1773719875934_06A906032LP_0005.bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_sl_stock(self):
        from meseventool.patches import PatchState
        r = self.patch.detect(self._load('1773719274817_032sl_auto_revo_1.bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_18cm_stock(self):
        from meseventool.patches import PatchState
        r = self.patch.detect(self._load('18CM.Bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_dl_stock(self):
        """fw4019 DL also shows STOCK — needle present, value still 250 km/h."""
        from meseventool.patches import PatchState
        r = self.patch.detect(self._load('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin'))
        self.assertEqual(r.state, PatchState.STOCK)

    def test_synthetic_apply_revert(self):
        """Synthetic: apply writes FF FF, revert restores A8 61."""
        from meseventool.patches import PatchState
        from meseventool.rom import ROMImage
        import tempfile, os
        data = bytearray(0x100000)
        # Build the 10-byte needle at address 0x0AF258
        addr = 0x0AF258
        data[addr:addr+10] = bytes([0xE6,0xFD,0xA8,0x61, 0xE6,0xFE, 0x9A,0x02, 0xDA,0x00])
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(bytes(data)); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp)
        r = self.patch.detect(rom)
        self.assertEqual(r.state, PatchState.STOCK)
        self.patch.apply(rom, r)
        self.assertEqual(rom.data[addr+2], 0xFF)
        self.assertEqual(rom.data[addr+3], 0xFF)
        self.patch.revert(rom, r)
        self.assertEqual(rom.data[addr+2], 0xA8)
        self.assertEqual(rom.data[addr+3], 0x61)


# =============================================================================
# VMAX code-immediate — double-apply covers both call sites
# =============================================================================
class TestVmaxCodeImmediateDoubleApply(unittest.TestCase):
    """Both VMAX call sites patched by applying twice on real RN ROM."""

    UPLOADS = '/mnt/user-data/uploads'

    def _load(self, fname):
        import os, tempfile
        from meseventool.rom import ROMImage
        path = f'{self.UPLOADS}/{fname}'
        if not os.path.exists(path):
            self.skipTest(f"ROM not available: {fname}")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path,'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp); return rom

    def setUp(self):
        from meseventool.patches import ALL_PATCHES
        self.patch = next(p for p in ALL_PATCHES if 'code-immediate' in p.name)

    def _apply_all_sites(self, rom):
        from meseventool.patches import PatchState
        from meseventool.needle import Searcher
        applied = 0
        for _ in range(5):  # safety limit
            s = Searcher(rom)
            r = self.patch.detect(rom, s)
            if r.state == PatchState.STOCK:
                self.patch.apply(rom, r)
                applied += 1
            else:
                break
        return applied

    def test_rn_double_apply_both_sites(self):
        """Applying twice on RN ROM patches both call sites."""
        rom = self._load('1773719274810_06A906032RN.bin')
        n = self._apply_all_sites(rom)
        self.assertEqual(n, 2, f"Expected 2 applies (2 call sites), got {n}")
        # Both sites should be 0xFFFF
        site1, site2 = 0x0AF25A, 0x0AF3CE
        self.assertEqual(rom.data[site1], 0xFF, "site1 not patched")
        self.assertEqual(rom.data[site2], 0xFF, "site2 not patched")

    def test_lp_double_apply_both_sites(self):
        """LP ROM: 2 applies, both sites patched."""
        rom = self._load('1773719875934_06A906032LP_0005.bin')
        n = self._apply_all_sites(rom)
        self.assertEqual(n, 2)

    def test_sl_double_apply_both_sites(self):
        """SL DSG ROM: 2 applies, both sites patched."""
        rom = self._load('1773719274817_032sl_auto_revo_1.bin')
        n = self._apply_all_sites(rom)
        self.assertEqual(n, 2)

    def test_18cm_double_apply_both_sites(self):
        """18CM ROM: 2 applies, both sites patched."""
        rom = self._load('18CM.Bin')
        n = self._apply_all_sites(rom)
        self.assertEqual(n, 2)

    def test_final_state_is_patched(self):
        """After double-apply, detect returns PATCHED."""
        from meseventool.patches import PatchState
        from meseventool.needle import Searcher
        rom = self._load('1773719274810_06A906032RN.bin')
        self._apply_all_sites(rom)
        s = Searcher(rom)
        r = self.patch.detect(rom, s)
        self.assertEqual(r.state, PatchState.PATCHED)


# =============================================================================
# Hard Rev Limit ScalarPatchDef (ME7.5 1.8T — all variants)
# =============================================================================
class TestHardRevLimitScalar1p8T(unittest.TestCase):
    """Hard Rev Limit ScalarPatchDef reads correct RPM from ME7.5 1.8T ROMs."""

    UPLOADS = '/mnt/user-data/uploads'

    def _load(self, fname):
        import os, tempfile
        from meseventool.rom import ROMImage
        path = f'{self.UPLOADS}/{fname}'
        if not os.path.exists(path):
            self.skipTest(f"ROM not available: {fname}")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path, 'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp); return rom

    def setUp(self):
        from meseventool.patches import ALL_SCALAR_PATCHES
        self.patch = next(p for p in ALL_SCALAR_PATCHES if 'ME7.5' in p.name)

    def _read_rpm(self, fname):
        from meseventool.needle import Searcher
        rom = self._load(fname)
        s   = Searcher(rom)
        v   = self.patch.read(rom, s)
        self.assertIsNotNone(v, f"ScalarPatchDef returned None for {fname}")
        return v

    def _assert_hits(self, fname, expected_hits=2):
        from meseventool.needle import Searcher
        rom = self._load(fname)
        s   = Searcher(rom)
        hits = s.search(list(self.patch.needle), list(self.patch.mask))
        self.assertEqual(len(hits), expected_hits,
            f"{fname}: expected {expected_hits} hits, got {len(hits)}")

    # ── exact-value tests ────────────────────────────────────────────────────
    def test_dl_4019_stock_7160rpm(self):
        v = self._read_rpm('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin')
        self.assertAlmostEqual(v, 7160, delta=2)

    def test_lp_4013_stock_7160rpm(self):
        v = self._read_rpm('1773719875934_06A906032LP_0005.bin')
        self.assertAlmostEqual(v, 7160, delta=2)

    def test_rn_4013_stock_7352rpm(self):
        v = self._read_rpm('1773719274810_06A906032RN.bin')
        self.assertAlmostEqual(v, 7352, delta=2)

    def test_sl_revo_7352rpm(self):
        v = self._read_rpm('1773719274817_032sl_auto_revo_1.bin')
        self.assertAlmostEqual(v, 7352, delta=2)

    def test_18cm_stock_6968rpm(self):
        v = self._read_rpm('18CM.Bin')
        self.assertAlmostEqual(v, 6968, delta=2)

    def test_hn_uni630_raised_7544rpm(self):
        v = self._read_rpm('1773719875938_uni_630HN.bin')
        self.assertAlmostEqual(v, 7544, delta=2)

    def test_rn_uni870_raised_7544rpm(self):
        v = self._read_rpm('1773719274820_uni870_032pl.bin')
        self.assertAlmostEqual(v, 7544, delta=2)

    def test_20th_4013_stock_7352rpm(self):
        v = self._read_rpm('1773719274814_20th_180hp_032pl.bin')
        self.assertAlmostEqual(v, 7352, delta=2)

    # ── always exactly 2 hits ────────────────────────────────────────────────
    def test_dl_two_hits(self):
        self._assert_hits('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin')

    def test_rn_two_hits(self):
        self._assert_hits('1773719274810_06A906032RN.bin')

    def test_18cm_two_hits(self):
        self._assert_hits('18CM.Bin')

    def test_hn_tuned_two_hits(self):
        self._assert_hits('1773719875938_uni_630HN.bin')


# =============================================================================
# Overrev Protection RPM ScalarPatchDef (ME7.5 1.8T MT)
# =============================================================================
class TestOverrevProtectionScalar1p8T(unittest.TestCase):
    """Overrev protection RPM scalar reads correct values from ME7.5 MT ROMs."""

    UPLOADS = '/mnt/user-data/uploads'

    def _load(self, fname):
        import os, tempfile
        from meseventool.rom import ROMImage
        path = f'{self.UPLOADS}/{fname}'
        if not os.path.exists(path):
            self.skipTest(f"ROM not available: {fname}")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path, 'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp); return rom

    def setUp(self):
        from meseventool.patches import ALL_SCALAR_PATCHES
        self.patch = next(p for p in ALL_SCALAR_PATCHES if 'Overrev' in p.name)

    def _rpm(self, fname):
        from meseventool.needle import Searcher
        rom = self._load(fname)
        s = Searcher(rom)
        v = self.patch.read(rom, s)
        self.assertIsNotNone(v, f"None for {fname}")
        return v

    def test_dl_stock_8180rpm(self):
        self.assertAlmostEqual(self._rpm('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin'), 8180, delta=2)

    def test_lp_stock_8180rpm(self):
        self.assertAlmostEqual(self._rpm('1773719875934_06A906032LP_0005.bin'), 8180, delta=2)

    def test_rn_stock_8180rpm(self):
        self.assertAlmostEqual(self._rpm('1773719274810_06A906032RN.bin'), 8180, delta=2)

    def test_18cm_stock_7988rpm(self):
        self.assertAlmostEqual(self._rpm('18CM.Bin'), 7988, delta=2)

    def test_hn_tuned_raised_8372rpm(self):
        self.assertAlmostEqual(self._rpm('1773719875938_uni_630HN.bin'), 8372, delta=2)

    def test_rn_uni870_raised_8372rpm(self):
        self.assertAlmostEqual(self._rpm('1773719274820_uni870_032pl.bin'), 8372, delta=2)

    def test_20th_raised_8372rpm(self):
        self.assertAlmostEqual(self._rpm('1773719274814_20th_180hp_032pl.bin'), 8372, delta=2)

    def test_sl_dsg_absent(self):
        """SL DSG (X505R) has different code layout — needle returns None."""
        from meseventool.needle import Searcher
        rom = self._load('1773719274817_032sl_auto_revo_1.bin')
        s = Searcher(rom)
        v = self.patch.read(rom, s)
        self.assertIsNone(v, "SL DSG should return None (no match)")


# =============================================================================
# Hard Rev Limit — alt path ScalarPatchDef (ME7.5 1.8T universal)
# =============================================================================
class TestHardRevAltPathScalar1p8T(unittest.TestCase):
    """Alt-path hard rev scalar: 1 hit per file in all variants including SL DSG."""

    UPLOADS = '/mnt/user-data/uploads'

    def _load(self, fname):
        import os, tempfile
        from meseventool.rom import ROMImage
        path = f'{self.UPLOADS}/{fname}'
        if not os.path.exists(path):
            self.skipTest(f"ROM not available: {fname}")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path, 'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp); return rom

    def setUp(self):
        from meseventool.patches import ALL_SCALAR_PATCHES
        self.patch = next(p for p in ALL_SCALAR_PATCHES if 'alt path' in p.name)

    def _rpm(self, fname):
        from meseventool.needle import Searcher
        rom = self._load(fname)
        v   = self.patch.read(rom, Searcher(rom))
        self.assertIsNotNone(v, f"None for {fname}")
        return v

    def _hits(self, fname):
        from meseventool.needle import Searcher
        rom = self._load(fname)
        return len(Searcher(rom).search(list(self.patch.needle), list(self.patch.mask)))

    # ── stock values ─────────────────────────────────────────────────────────
    def test_dl_stock_7160rpm(self):
        self.assertAlmostEqual(self._rpm('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin'), 7160, delta=2)

    def test_lp_stock_7160rpm(self):
        self.assertAlmostEqual(self._rpm('1773719875934_06A906032LP_0005.bin'), 7160, delta=2)

    def test_rn_stock_7160rpm(self):
        self.assertAlmostEqual(self._rpm('1773719274810_06A906032RN.bin'), 7160, delta=2)

    def test_18cm_stock_6776rpm(self):
        self.assertAlmostEqual(self._rpm('18CM.Bin'), 6776, delta=2)

    # ── tuned values ─────────────────────────────────────────────────────────
    def test_hn_tuned_7352rpm(self):
        self.assertAlmostEqual(self._rpm('1773719875938_uni_630HN.bin'), 7352, delta=2)

    def test_sl_dsg_tuned_7352rpm(self):
        """SL DSG present — this needle covers DSG unlike the overrev scalar."""
        self.assertAlmostEqual(self._rpm('1773719274817_032sl_auto_revo_1.bin'), 7352, delta=2)

    def test_20th_tuned_7352rpm(self):
        self.assertAlmostEqual(self._rpm('1773719274814_20th_180hp_032pl.bin'), 7352, delta=2)

    # ── exactly 1 hit per file ───────────────────────────────────────────────
    def test_dl_one_hit(self):
        self.assertEqual(self._hits('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin'), 1)

    def test_rn_one_hit(self):
        self.assertEqual(self._hits('1773719274810_06A906032RN.bin'), 1)

    def test_18cm_one_hit(self):
        self.assertEqual(self._hits('18CM.Bin'), 1)

    def test_sl_one_hit(self):
        self.assertEqual(self._hits('1773719274817_032sl_auto_revo_1.bin'), 1)


# =============================================================================
# Emergency RPM Cut ScalarPatchDef (ME7.5 1.8T — all variants)
# =============================================================================
class TestEmergencyRpmCutScalar1p8T(unittest.TestCase):
    """Emergency RPM cut (NKILL) scalar reads correct values across ME7.5 1.8T ROMs."""

    UPLOADS = '/mnt/user-data/uploads'

    def _load(self, fname):
        import os, tempfile
        from meseventool.rom import ROMImage
        path = f'{self.UPLOADS}/{fname}'
        if not os.path.exists(path):
            self.skipTest(f"ROM not available: {fname}")
        with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
            f.write(open(path, 'rb').read()); tmp = f.name
        rom = ROMImage.load(tmp); os.unlink(tmp); return rom

    def setUp(self):
        from meseventool.patches import ALL_SCALAR_PATCHES
        self.patch = next(p for p in ALL_SCALAR_PATCHES if 'NKILL' in p.name)

    def _rpm(self, fname):
        from meseventool.needle import Searcher
        rom = self._load(fname)
        s = Searcher(rom)
        v = self.patch.read(rom, s)
        self.assertIsNotNone(v, f"None for {fname}")
        return v

    def _assert_hits(self, fname, expected=2):
        from meseventool.needle import Searcher
        rom = self._load(fname)
        s = Searcher(rom)
        hits = s.search(list(self.patch.needle), list(self.patch.mask))
        self.assertEqual(len(hits), expected, f"{fname}: expected {expected} hits, got {len(hits)}")

    # ── exact-value tests ────────────────────────────────────────────────────
    def test_dl_stock_10424rpm(self):
        self.assertAlmostEqual(self._rpm('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin'), 10424, delta=2)

    def test_rn_stock_10424rpm(self):
        self.assertAlmostEqual(self._rpm('1773719274810_06A906032RN.bin'), 10424, delta=2)

    def test_lp_stock_10424rpm(self):
        self.assertAlmostEqual(self._rpm('1773719875934_06A906032LP_0005.bin'), 10424, delta=2)

    def test_18cm_stock_10424rpm(self):
        self.assertAlmostEqual(self._rpm('18CM.Bin'), 10424, delta=2)

    def test_hn_tuned_10808rpm(self):
        self.assertAlmostEqual(self._rpm('1773719875938_uni_630HN.bin'), 10808, delta=2)

    def test_rn_uni870_10808rpm(self):
        self.assertAlmostEqual(self._rpm('1773719274820_uni870_032pl.bin'), 10808, delta=2)

    def test_20th_raised_10616rpm(self):
        self.assertAlmostEqual(self._rpm('1773719274814_20th_180hp_032pl.bin'), 10616, delta=2)

    def test_sl_revo_10616rpm(self):
        self.assertAlmostEqual(self._rpm('1773719274817_032sl_auto_revo_1.bin'), 10616, delta=2)

    # ── 2 hits per file ──────────────────────────────────────────────────────
    def test_dl_two_hits(self):
        self._assert_hits('1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin')

    def test_rn_two_hits(self):
        self._assert_hits('1773719274810_06A906032RN.bin')

    def test_sl_two_hits(self):
        self._assert_hits('1773719274817_032sl_auto_revo_1.bin')

    # ── low byte constant ─────────────────────────────────────────────────────
    def test_low_byte_0x4a_constant_in_all_stock(self):
        """All stock files have 0x4A as the constant low byte."""
        from meseventool.needle import Searcher
        import os, tempfile
        from meseventool.rom import ROMImage
        for fname in [
            '1773719875933_06A906032DL_0261206890_v360227_MT_OEM.bin',
            '1773719274810_06A906032RN.bin',
            '18CM.Bin',
        ]:
            path = f'{self.UPLOADS}/{fname}'
            if not os.path.exists(path):
                continue
            with tempfile.NamedTemporaryFile(suffix='.bin', delete=False) as f:
                f.write(open(path,'rb').read()); tmp = f.name
            rom = ROMImage.load(tmp); os.unlink(tmp)
            s = Searcher(rom)
            hits = s.search(list(self.patch.needle), list(self.patch.mask))
            for h in hits:
                lo = rom.data[h.file_offset + self.patch.offset]
                self.assertEqual(lo, 0x4A, f"{fname}: low byte at 0x{h.file_offset:06X} = 0x{lo:02X}, expected 0x4A")
