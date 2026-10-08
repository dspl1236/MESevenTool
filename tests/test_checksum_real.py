"""
Checksum tests against real ME7.5 ROMs.  Skipped when the files are absent.

Looks in $MESEVENTOOL_ROM_DIR, then /mnt/user-data/uploads, then the
archive folder noted in docs/checksum_port_handoff.md.
"""
import os
import pytest
from meseventool.rom import ROMImage
from meseventool.checksum import ChecksumManager

_DIRS = [d for d in [
    os.environ.get("MESEVENTOOL_ROM_DIR"),
    "/mnt/user-data/uploads",
    r"Z:\Archive\Google Drive\home flashing\ME7",
] if d]


def _find(name: str):
    for d in _DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def _load(name: str) -> ROMImage:
    p = _find(name)
    if p is None:
        pytest.skip(f"{name} not available")
    return ROMImage.load(p)


class TestRealROMs:
    def test_18cm_all_layers(self):
        """4B0906018CM: main + 66 multipoint blocks OK, no CRC32 layer."""
        r = ChecksumManager(_load("18CM.Bin")).verify()
        assert r.main.offset == 0xFFFE0
        assert r.main.regions == [(0x0, 0xFBFF), (0x20000, 0xFFFFF)]
        assert r.main.stored == 0x00903D56 and r.main_ok
        assert r.multi.table_offset == 0x1FBDE and r.multi.count == 66
        assert r.multipoint_ok
        assert not r.crc_found and not r.crc.note
        assert r.all_ok

    def test_adamfixed_all_layers(self):
        """06A906032HN after me7sum: every layer verifies, CRCs chained."""
        r = ChecksumManager(_load("adamfixed.bin")).verify()
        assert r.main.stored == 0x43C6CC9A and r.main_ok
        assert r.multipoint_ok and r.multi.n_ok == 66
        assert r.crc_found
        assert r.crc.pre_block == (0x183C8, 0x183D1)
        assert [(b.start, b.end) for b in r.crc.blocks] == [
            (0x10002, 0x13FFE), (0x14252, 0x17F4E),
            (0x18192, 0x1FBDC), (0x26A00, 0x2FFFC)]
        assert [b.offset for b in r.crc.blocks] == [0x90B4E, 0x90B54, None, 0x90B5A]
        assert [b.stored for b in r.crc.blocks if b.offset is not None] == [
            0xF32D6517, 0x54B731DB, 0x990BFF49]
        assert r.crc_ok and r.all_ok

    def test_adam_before_fix(self):
        r = ChecksumManager(_load("adam.bin")).verify()
        assert r.main_ok
        assert [b.index for b in r.multi.blocks if not b.ok] == [7, 8, 10]
        assert r.crc_found and r.crc.n_bad == 3
        assert not r.all_ok

    def test_fix_adam_equals_adamfixed(self):
        """Acceptance test: our fix() must reproduce me7sum's output exactly."""
        rom = _load("adam.bin")
        with open(_find("adamfixed.bin") or pytest.skip("adamfixed.bin"), "rb") as f:
            expected = f.read()
        result = ChecksumManager(rom).fix()
        assert result.all_ok
        assert bytes(rom.data) == expected
        snap = bytes(rom.data)
        ChecksumManager(rom).fix()
        assert bytes(rom.data) == snap

    def test_032rn(self):
        """06A906032RN: not pristine (one stale multipoint block) but CRCs OK."""
        r = ChecksumManager(_load("032rn.bin")).verify()
        assert r.main_ok and r.main.stored == 0x43D04E38
        assert r.crc_found and r.crc_ok
        assert r.multi.n_bad == 1
