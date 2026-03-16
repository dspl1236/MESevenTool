"""Tests for patch detection/apply/revert — uses synthetic ROMs."""
import pytest
from meseventool.rom import ROMImage
from meseventool.needle import MASK, XXXX
from meseventool.patches import (
    PatchDef, PatchState, PatchResult, ScalarPatchDef, PatchCategory,
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
        for p in PATCH_REGISTRY:
            assert p.name
            assert p.description
            assert isinstance(p.category, PatchCategory)
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
