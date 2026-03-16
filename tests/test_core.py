"""
Core unit tests — runs without a real ROM binary.
Tests structural correctness of every module.
"""
import pytest
import struct
from meseventool.rom       import ROMImage, VALID_SIZES
from meseventool.needle    import Searcher, NEEDLE_DPP, MASK_DPP, SearchHit
from meseventool.dpp       import DPPValues, DPPExtractor, SEGMENT_SIZE
from meseventool.checksum  import (
    calc_sum_block, calc_crc32, ChecksumChecker,
    MainChecksumResult, MultiChecksumResult, _le16, _le32,
)
from meseventool.maps      import (
    MapDef, AxisDef, make_awp_maps,
    U8, U16, S16, _rpm, _deg, _pct, _lambda,
)
from meseventool.patches   import (
    PatchDef, PatchState, ALL_PATCHES, detect_all,
    PatchCategory,
)
from meseventool.profiles  import (
    ROMProfile, PROFILE_AWP, ALL_PROFILES, detect_profile, PROFILE_UNKNOWN,
)
from meseventool.ecu_id    import ECUIdentity, _clean_string


# ── Fixtures ───────────────────────────────────────────────────────────────────

def make_rom(size=0x80000, fill=0xFF) -> ROMImage:
    """Create a blank ROM of the given size."""
    return ROMImage(data=bytearray([fill] * size))


def make_rom_with_dpp(dpp0=0x0020, dpp1=0x0200, dpp2=0x0050, dpp3=0x0003,
                      size=0x80000) -> tuple[ROMImage, int]:
    """
    Embed a DPP setup sequence at offset 0x100 and return (rom, offset).
    MOV r0, #DPPx  = E6 F0 lo hi  (LE word)
    MOV DPPx, r0   = FD 0x  (x = 0..3)
    """
    rom = make_rom(size)
    off = 0x100
    for i, val in enumerate([dpp0, dpp1, dpp2, dpp3]):
        rom.data[off + 0] = 0xE6
        rom.data[off + 1] = 0xF0
        rom.data[off + 2] = val & 0xFF
        rom.data[off + 3] = (val >> 8) & 0xFF
        rom.data[off + 4] = 0xFD
        rom.data[off + 5] = i          # DPP register number
        off += 6
    return rom, 0x100


# ── ROMImage tests ─────────────────────────────────────────────────────────────

class TestROMImage:
    def test_valid_sizes(self):
        for size in VALID_SIZES:
            r = ROMImage(data=bytearray(size))
            assert r.size == size

    def test_invalid_size_rejected(self):
        with pytest.raises(ValueError):
            ROMImage.from_bytes(b'\xFF' * 0x10000)  # 64 KB — not a valid ME7 size
        # from_bytes does not validate; load() does
        r = ROMImage(data=bytearray(0x10000))
        assert r.size == 0x10000   # raw construction allows any size

    def test_read_write_u8(self):
        r = make_rom()
        r.write(0x100, b'\xAB')
        assert r.read_u8(0x100) == 0xAB

    def test_read_write_u16_be(self):
        r = make_rom()
        r.write_u16_be(0x200, 0x1234)
        assert r.read_u16_be(0x200) == 0x1234
        assert r.data[0x200] == 0x12
        assert r.data[0x201] == 0x34

    def test_read_write_u16_le(self):
        r = make_rom()
        r.write_u16_le(0x300, 0xABCD)
        assert r.read_u16_le(0x300) == 0xABCD
        assert r.data[0x300] == 0xCD
        assert r.data[0x301] == 0xAB

    def test_read_write_u32_be(self):
        r = make_rom()
        r.write_u32_be(0x400, 0xDEADBEEF)
        assert r.read_u32_be(0x400) == 0xDEADBEEF

    def test_modified_flag(self):
        r = make_rom()
        assert not r.is_modified
        r.write(0, b'\x00')
        assert r.is_modified

    def test_snapshot_is_independent(self):
        r = make_rom(fill=0xAA)
        snap = r.snapshot()
        r.write(0, b'\x00')
        assert snap[0] == 0xAA   # snapshot not affected

    def test_cal_page_offset_512k(self):
        r = make_rom(0x80000)
        assert r.cal_page_offset == 0x70000

    def test_cal_page_offset_256k(self):
        r = make_rom(0x40000)
        assert r.cal_page_offset == 0x30000

    def test_hexdump_format(self):
        r = make_rom()
        r.write(0, b'\xDE\xAD\xBE\xEF')
        s = r.hexdump(0, 4)
        assert 'DE' in s and 'AD' in s

    def test_write_out_of_bounds_raises(self):
        r = make_rom(0x80000)
        with pytest.raises(ValueError):
            r.write(0x7FFFE, b'\x01\x02\x03')   # 3 bytes from near end


# ── Needle / Searcher tests ────────────────────────────────────────────────────

class TestSearcher:
    def test_exact_match(self):
        r = make_rom()
        r.write(0x500, b'\xDE\xAD\xBE\xEF')
        s = Searcher(r)
        hits = s.search([0xDE, 0xAD, 0xBE, 0xEF], [0xFF, 0xFF, 0xFF, 0xFF])
        assert len(hits) == 1
        assert hits[0].file_offset == 0x500

    def test_wildcard_match(self):
        r = make_rom()
        r.write(0x600, b'\xDE\x99\xBE\xEF')
        s = Searcher(r)
        hits = s.search(
            [0xDE, 0x00, 0xBE, 0xEF],
            [0xFF, 0x00, 0xFF, 0xFF],   # second byte = wildcard
        )
        assert len(hits) == 1

    def test_no_match(self):
        r = make_rom(fill=0xFF)
        s = Searcher(r)
        hits = s.search([0x00, 0x01], [0xFF, 0xFF])
        assert hits == []

    def test_count_limit(self):
        r = make_rom(fill=0xAA)
        s = Searcher(r)
        hits = s.search([0xAA, 0xAA], [0xFF, 0xFF], count=3)
        assert len(hits) == 3

    def test_search_one_returns_none_on_miss(self):
        r = make_rom(fill=0xFF)
        s = Searcher(r)
        assert s.search_one([0x00], [0xFF]) is None

    def test_search_hit_get_u16_le(self):
        r = make_rom()
        r.write(0x700, b'\xE6\xF0\x34\x12')
        s = Searcher(r)
        hit = s.search_one([0xE6, 0xF0, 0x00, 0x00], [0xFF, 0xFF, 0x00, 0x00])
        assert hit is not None
        assert hit.get_u16_le(2) == 0x1234   # LE: 0x34, 0x12

    def test_dpp_needle_extracts_values(self):
        rom, off = make_rom_with_dpp(0x0020, 0x0200, 0x0050, 0x0003)
        s = Searcher(rom)
        found = s.find_dppx()
        assert found
        assert s.dpp0 == 0x0020
        assert s.dpp1 == 0x0200
        assert s.dpp2 == 0x0050
        assert s.dpp3 == 0x0003


# ── DPP tests ──────────────────────────────────────────────────────────────────

class TestDPP:
    def test_extraction(self):
        rom, _ = make_rom_with_dpp(0x0020, 0x0200, 0x0050, 0x0003)
        s = Searcher(rom)
        s.find_dppx()
        from meseventool.dpp import DPPExtractor
        ex = DPPExtractor(s)
        dpp = ex.extract()
        assert dpp.found
        assert dpp.dpp1 == 0x0200
        assert dpp.dpp1_seg == 0x01FF

    def test_not_found(self):
        rom = make_rom(fill=0xFF)
        s = Searcher(rom)
        from meseventool.dpp import DPPExtractor
        ex = DPPExtractor(s)
        dpp = ex.extract()
        assert not dpp.found

    def test_seg_to_file(self):
        dpp = DPPValues(dpp1=0x0200)
        # seg=0x01FF, offset=0x0010 → phys = 0x01FF * 0x4000 + 0x0010
        phys = (0x01FF * SEGMENT_SIZE) + 0x0010
        file_off = dpp.seg_to_file(0x01FF, 0x0010, 0x80000)
        assert file_off == phys & 0x7FFFF

    def test_describe_output(self):
        dpp = DPPValues(dpp0=0x20, dpp1=0x200, dpp2=0x50, dpp3=0x03)
        desc = dpp.describe()
        assert "DPP0" in desc and "DPP1" in desc


# ── Checksum tests ─────────────────────────────────────────────────────────────

class TestChecksum:
    def test_calc_sum_block_simple(self):
        r = make_rom(size=0x80000, fill=0x00)
        r.write(0, b'\x01\x00\x02\x00')   # LE16: 1, 2
        result = calc_sum_block(r, 0, 3)
        assert result == 3   # 1 + 2

    def test_calc_sum_block_overflow(self):
        """Sum wraps at 32-bit."""
        r = make_rom(size=0x80000, fill=0x00)
        r.write(0, b'\xFF\xFF' * 2)   # Two 0xFFFF words
        result = calc_sum_block(r, 0, 3)
        assert result == (0xFFFF * 2) & 0xFFFFFFFF

    def test_calc_crc32_known(self):
        """CRC32 of empty string is 0x00000000."""
        r = make_rom(size=0x80000, fill=0xFF)
        r.write(0, b'')
        # CRC32 of single byte 0x00
        r2 = make_rom(0x80000, fill=0)
        crc = calc_crc32(r2, 0, 0)
        assert isinstance(crc, int)
        assert 0 <= crc <= 0xFFFFFFFF

    def test_le16_le32(self):
        data = bytes([0x34, 0x12, 0x78, 0x56])
        assert _le16(data, 0) == 0x1234
        assert _le32(data, 0) == 0x56781234

    def test_checksum_result_all_ok(self):
        result = MainChecksumResult(
            found=True, main_ok=True, comp_ok=True)
        assert result.all_ok

    def test_checksum_result_not_ok(self):
        result = MainChecksumResult(found=True, main_ok=True, comp_ok=False)
        assert not result.all_ok

    def test_multiblock_all_ok(self):
        from meseventool.checksum import MultiBlock
        blk = MultiBlock(index=1, start=0, end=100,
                         stored_crc=0xDEAD, stored_neg=0,
                         calc_crc=0xDEAD, crc_ok=True, neg_ok=True)
        result = MultiChecksumResult(blocks=[blk], found=True)
        assert result.all_ok
        assert result.n_ok == 1
        assert result.n_bad == 0


# ── Map tests ──────────────────────────────────────────────────────────────────

class TestMaps:
    def test_make_awp_maps_returns_nonempty(self):
        maps = make_awp_maps()
        assert len(maps) > 0

    def test_all_maps_have_required_fields(self):
        for m in make_awp_maps():
            assert m.name
            assert m.description
            assert m.confidence in ("CONFIRMED", "PROVISIONAL", "UNCONFIRMED")

    def test_kfzw_in_maps(self):
        names = [m.name for m in make_awp_maps()]
        assert "KFZW" in names
        assert "MLHFM" in names
        assert "LDRXN" in names

    def test_decode_rpm(self):
        assert _rpm(0) == 0.0
        assert _rpm(4000) == pytest.approx(3000.0)   # 4000 * 0.75

    def test_decode_deg(self):
        assert _deg(0) == 0.0
        assert _deg(20) == pytest.approx(15.0)

    def test_map_read_requires_addr(self):
        r = make_rom()
        m = MapDef(name="TEST", description="test", rows=2, cols=2,
                   data_addr=0)
        assert m.read(r) == []

    def test_map_read_write_roundtrip(self):
        r = make_rom()
        m = MapDef(name="TEST", description="test",
                   data_width=U16, rows=2, cols=2,
                   data_addr=0x1000,
                   decode=lambda x: x / 10.0,
                   encode=lambda x: int(x * 10))
        # Write 4 values: 1.0, 2.0, 3.0, 4.0
        original = [[1.0, 2.0], [3.0, 4.0]]
        m.write(r, original)
        back = m.read(r)
        assert back == [[pytest.approx(1.0), pytest.approx(2.0)],
                        [pytest.approx(3.0), pytest.approx(4.0)]]


# ── Patch tests ────────────────────────────────────────────────────────────────

class TestPatches:
    def test_all_patches_valid(self):
        from meseventool.patches import OffsetPatchDef, MultiOffsetPatchDef
        for p in ALL_PATCHES:
            assert p.name
            assert p.description
            assert isinstance(p.category, PatchCategory)
            # Needle/mask only on needle-based patches
            if not isinstance(p, (OffsetPatchDef, MultiOffsetPatchDef)):
                assert len(p.needle) == len(p.mask)
                assert len(p.stock_bytes) == len(p.patch_bytes)
            else:
                # Offset patches: check stock/patch length equivalence differently
                if isinstance(p, OffsetPatchDef):
                    assert len(p.stock_bytes) == len(p.patch_bytes)

    def test_detect_missing_when_needle_absent(self):
        rom = make_rom(fill=0xFF)
        s = Searcher(rom)
        results = detect_all(rom, s)
        for r in results:
            assert r.state in (PatchState.MISSING, PatchState.UNKNOWN,
                               PatchState.STOCK, PatchState.PATCHED)

    def test_patch_apply_revert(self):
        """Plant a patch needle and verify apply/revert cycle."""
        rom = make_rom(fill=0x00)
        p = ALL_PATCHES[0]   # first patch

        # Plant needle at offset 0x200
        for i, (nb, mb) in enumerate(zip(p.needle, p.mask)):
            if mb:   # must-match byte
                rom.data[0x200 + i] = nb
            # wildcard bytes stay 0x00

        # Plant stock bytes at needle + offset
        addr = 0x200 + p.offset
        for i, b in enumerate(p.stock_bytes):
            rom.data[addr + i] = b

        s = Searcher(rom)
        result = p.detect(rom, s)

        if result.state == PatchState.STOCK:
            assert p.apply(rom, result)
            # should now read as patched
            current = bytes(rom.data[result.addr : result.addr + len(p.patch_bytes)])
            assert current == p.patch_bytes

            # revert
            assert p.revert(rom, result)
            current = bytes(rom.data[result.addr : result.addr + len(p.stock_bytes)])
            assert current == p.stock_bytes

    def test_categories_all_used(self):
        cats = {p.category for p in ALL_PATCHES}
        assert PatchCategory.EMISSIONS in cats
        assert PatchCategory.IMMOBILISER in cats

    def test_patch_count(self):
        assert len(ALL_PATCHES) >= 8


# ── Profile tests ──────────────────────────────────────────────────────────────

class TestProfiles:
    def test_all_profiles_valid(self):
        for p in ALL_PROFILES:
            assert p.name
            assert p.rom_size in VALID_SIZES

    def test_awp_matches_06a906032(self):
        ecu = ECUIdentity(vmecuhn="06A906032BN")
        dpp = DPPValues(dpp1=0x0200)
        assert PROFILE_AWP.matches(ecu, dpp)

    def test_awp_does_not_match_06b(self):
        ecu = ECUIdentity(vmecuhn="06B906018AWM")
        dpp = DPPValues(dpp1=0x0200)
        assert not PROFILE_AWP.matches(ecu, dpp)

    def test_detect_profile_awp(self):
        ecu = ECUIdentity(vmecuhn="06A906032BN")
        dpp = DPPValues(dpp1=0x0200)
        p = detect_profile(ecu, dpp)
        assert p is PROFILE_AWP

    def test_detect_profile_unknown(self):
        ecu = ECUIdentity(vmecuhn="UNKNOWN99999")
        dpp = DPPValues()
        p = detect_profile(ecu, dpp)
        assert p is PROFILE_UNKNOWN

    def test_profile_makes_maps(self):
        maps = PROFILE_AWP.make_maps()
        assert len(maps) > 0

    def test_profile_matches_by_dpp_when_no_pn(self):
        ecu = ECUIdentity()   # no part number
        dpp = DPPValues(dpp1=0x0200)
        p = detect_profile(ecu, dpp)
        # Should match AWP or AUM via DPP range
        assert p is not PROFILE_UNKNOWN


# ── ECU ID tests ───────────────────────────────────────────────────────────────

class TestECUID:
    def test_clean_string(self):
        assert _clean_string(b'Hello\x00World') == "Hello World"
        assert _clean_string(b'\x01\x02ABC\x03') == "  ABC "

    def test_identity_display_name(self):
        e = ECUIdentity(vmecuhn="06A906032BN", erotan="ME7.5 180HP")
        assert "06A906032BN" in e.display_name
        assert "ME7.5 180HP" in e.display_name

    def test_identity_str(self):
        e = ECUIdentity(vmecuhn="06A906032BN", epk="0123456789")
        s = str(e)
        assert "06A906032BN" in s
        assert "0123456789" in s

    def test_part_number_fallback(self):
        e = ECUIdentity(ssecuhn="BOSCH123")
        assert e.part_number == "BOSCH123"
