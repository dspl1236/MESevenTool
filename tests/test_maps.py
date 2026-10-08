"""
tests/test_maps.py
Tests for MapDef read/write, make_awp_maps confirmed addresses,
and signed value handling (KFZW S8 roundtrip).
"""
import os
import pytest
from meseventool.maps import (
    MapDef, make_awp_maps, make_v6_biturbo_maps,
    S8, U8, U16,
)
from meseventool.rom import ROMImage


def _make_rom() -> ROMImage:
    return ROMImage(bytearray(0x100000))


# ── Basics ────────────────────────────────────────────────────────────────────

class TestMapDefBasics:
    def test_dims(self):
        m = MapDef("t", rows=4, cols=8, data_width=U8)
        assert m.rows == 4 and m.cols == 8

    def test_read_empty_when_no_addr(self):
        assert MapDef("t", rows=4, cols=4, data_width=U8, data_addr=0).read(_make_rom()) == []

    def test_read_u8(self):
        rom = _make_rom()
        for i in range(8): rom.data[0x1000+i] = i * 10
        m = MapDef("t", rows=2, cols=4, data_width=U8, data_addr=0x1000,
                   decode=lambda x: float(x))
        assert m.read(rom) == [[0,10,20,30],[40,50,60,70]]

    def test_read_s8_negative(self):
        """0xE5 = -27 signed; must decode as negative."""
        rom = _make_rom()
        for i,b in enumerate([0xE5,0xE5,0x1E,0x1E]): rom.data[0x2000+i] = b
        m = MapDef("t", rows=1, cols=4, data_width=S8, data_addr=0x2000,
                   decode=lambda x: x * 0.75)
        d = m.read(rom)
        assert d[0][0] == pytest.approx(-27 * 0.75, abs=0.01)
        assert d[0][2] == pytest.approx(30 * 0.75, abs=0.01)


# ── Write roundtrip ───────────────────────────────────────────────────────────

class TestMapDefWrite:
    def test_u8_roundtrip(self):
        rom = _make_rom()
        m = MapDef("t", rows=2, cols=4, data_width=U8, data_addr=0x5000,
                   decode=lambda x: x*2.0, encode=lambda x: int(round(x/2.0)))
        vals = [[10,20,30,40],[50,60,70,80]]
        m.write(rom, vals); data = m.read(rom)
        for r in range(2):
            for c in range(4): assert data[r][c] == pytest.approx(vals[r][c], abs=0.01)

    def test_s8_negative_roundtrip(self):
        """S8 write must handle negative BTDC values (retard)."""
        rom = _make_rom()
        m = MapDef("KFZW", rows=2, cols=4, data_width=S8, data_addr=0x6000,
                   decode=lambda x: x*0.75, encode=lambda x: int(round(x/0.75)))
        vals = [[18.0,15.0,-5.25,-20.25],[-18.75,-19.5,0.0,12.0]]
        m.write(rom, vals); data = m.read(rom)
        for r in range(2):
            for c in range(4):
                assert data[r][c] == pytest.approx(vals[r][c], abs=0.1), \
                    f"[{r}][{c}] wrote {vals[r][c]}, got {data[r][c]}"

    def test_s8_clamp(self):
        """S8 must clamp to -128..+127."""
        rom = _make_rom()
        m = MapDef("t", rows=1, cols=4, data_width=S8, data_addr=0x7000,
                   decode=lambda x: float(x), encode=lambda x: int(round(x)))
        m.write(rom, [[-200, 200, -128, 127]])
        raw = [rom.data[0x7000+i] for i in range(4)]
        assert raw[0] == 0x80  # -128 stored as unsigned byte
        assert raw[1] == 0x7F  # +127

    def test_u16_roundtrip(self):
        rom = _make_rom()
        m = MapDef("t", rows=2, cols=3, data_width=U16, data_addr=0x8000,
                   decode=lambda x: x*0.1, encode=lambda x: int(round(x/0.1)))
        vals = [[10.0,25.5,100.0],[0.0,655.3,327.7]]
        m.write(rom, vals); data = m.read(rom)
        for r in range(2):
            for c in range(3): assert data[r][c] == pytest.approx(vals[r][c], abs=0.05)


# ── AWP confirmed addresses ───────────────────────────────────────────────────

class TestAWPMapsAddresses:
    def test_not_empty(self):
        assert len(make_awp_maps()) >= 7

    def test_kfzw_dl_confirmed(self):
        kfzw = next(m for m in make_awp_maps("06A906032DL") if m.name=="KFZW")
        assert kfzw.data_addr == 0x0120DD
        assert kfzw.confidence == "CONFIRMED"
        assert kfzw.data_width == S8

    def test_mlhfm_dl_confirmed(self):
        mlhfm = next(m for m in make_awp_maps("06A906032DL") if m.name=="MLHFM")
        assert mlhfm.data_addr == 0x014574
        assert mlhfm.cols == 512

    def test_kflbts_confirmed(self):
        m = next(x for x in make_awp_maps("06A906032DL") if x.name=="KFLBTS")
        assert m.data_addr == 0x0192A5 and m.confidence == "CONFIRMED"

    def test_lamfa_confirmed(self):
        m = next(x for x in make_awp_maps("06A906032DL") if x.name=="LAMFA")
        assert m.data_addr == 0x01C95A and m.confidence == "CONFIRMED"

    def test_kfdluls_confirmed(self):
        m = next(x for x in make_awp_maps("06A906032DL") if x.name=="KFDLULS")
        assert m.data_addr == 0x01EB91 and m.confidence == "CONFIRMED"

    def test_7_confirmed_for_dl(self):
        confirmed = [m for m in make_awp_maps("06A906032DL")
                     if m.data_addr and m.confidence=="CONFIRMED"]
        assert len(confirmed) >= 7

    def test_kfzw_decode_negative(self):
        kfzw = next(m for m in make_awp_maps() if m.name=="KFZW")
        assert kfzw.decode(-27) == pytest.approx(-20.25, abs=0.01)
        assert kfzw.decode(24)  == pytest.approx(18.0,  abs=0.01)

    def test_kfzw_encode(self):
        kfzw = next(m for m in make_awp_maps() if m.name=="KFZW")
        assert kfzw.encode(18.0)   == 24
        assert kfzw.encode(-20.25) == -27
        assert kfzw.encode(0.0)    == 0


# ── Real ROM (skipped if file absent) ─────────────────────────────────────────

from tests.rom_corpus import find_rom
_DL = find_rom("VW Golf4 1.8T 06A906032DL 0261206890 354821 Original.bin") or find_rom("06A906032DL_0261206890_v360227_MT_OEM.bin")

@pytest.mark.skipif(not _DL, reason="DL ROM not present")
class TestRealROM:
    def test_kfzw_plausible(self):
        rom = ROMImage.load(_DL)
        kfzw = next(m for m in make_awp_maps("06A906032DL") if m.name=="KFZW")
        data = kfzw.read(rom)
        assert len(data) == 12 and all(len(r)==16 for r in data)
        flat = [v for row in data for v in row]
        # Physically plausible ignition window.  The 354821 dump peaks near
        # 25 degrees; the v360227 MT OEM dump reaches 42 at light load.
        assert -25.0 <= min(flat) and max(flat) <= 48.0

    def test_mlhfm_512(self):
        rom = ROMImage.load(_DL)
        mlhfm = next(m for m in make_awp_maps("06A906032DL") if m.name=="MLHFM")
        data = mlhfm.read(rom)
        assert len(data[0]) == 512
        assert max(data[0]) > 500.0   # some point is >500 kg/h

    def test_kfzw_s8_write_roundtrip(self):
        rom = ROMImage.load(_DL)
        kfzw = next(m for m in make_awp_maps("06A906032DL") if m.name=="KFZW")
        orig = kfzw.read(rom)
        mod  = [list(r) for r in orig]
        mod[0][0] = orig[0][0] + 3.0
        kfzw.write(rom, mod)
        result = kfzw.read(rom)
        assert result[0][0] == pytest.approx(orig[0][0]+3.0, abs=0.4)
        for c in range(1,16):
            assert result[0][c] == pytest.approx(orig[0][c], abs=0.01)


# ── V6 biturbo maps ───────────────────────────────────────────────────────────

class TestV6Maps:
    def test_not_empty(self):
        assert len(make_v6_biturbo_maps()) >= 5

    def test_kfzw_confirmed(self):
        kfzw = next(m for m in make_v6_biturbo_maps() if m.name == "KFZW")
        assert kfzw.confidence == "CONFIRMED"
        assert kfzw.data_addr == 0x011C72

    def test_kfzw_dims_transposed(self):
        """2.7T KFZW is 16 rows × 12 cols — transposed vs 1.8T 12×16."""
        kfzw = next(m for m in make_v6_biturbo_maps() if m.name == "KFZW")
        assert kfzw.rows == 16 and kfzw.cols == 12

    def test_mlhfm_confirmed(self):
        mlhfm = next(m for m in make_v6_biturbo_maps() if m.name == "MLHFM")
        assert mlhfm.confidence == "CONFIRMED"
        assert mlhfm.data_addr == 0x014254

    def test_kflbts_confirmed(self):
        kflbts = next(m for m in make_v6_biturbo_maps() if m.name == "KFLBTS")
        assert kflbts.confidence == "CONFIRMED"
        assert kflbts.data_addr == 0x019207

    def test_boost_map_present(self):
        assert any(m.name == "KFDLULS" for m in make_v6_biturbo_maps())


# ── Write bounds (review A4) and widths vs XDF (review A6) ───────────────────

class TestMapWriteBounds:
    def test_write_past_end_raises_and_does_not_grow(self):
        """Slice-assigning past a bytearray's end appends; the old code did that."""
        rom = ROMImage(data=bytearray([0xFF]) * 0x40000)
        m = MapDef("t", rows=1, cols=4, data_width=U16, data_addr=0x3FFFC)
        with pytest.raises(ValueError, match="exceeds ROM size"):
            m.write(rom, [[1.0, 2.0, 3.0, 4.0]])
        assert rom.size == 0x40000
        assert not rom.is_modified

    def test_write_marks_modified_and_writes_only_the_map(self):
        rom = ROMImage(data=bytearray([0xFF]) * 0x40000)
        m = MapDef("t", rows=2, cols=2, data_width=U8, data_addr=0x1000)
        m.write(rom, [[1, 2], [3, 4]])
        assert rom.is_modified
        assert bytes(rom.data[0x1000:0x1004]) == b'\x01\x02\x03\x04'
        assert rom.data[0x0FFF] == 0xFF and rom.data[0x1004] == 0xFF

    def test_unchanged_values_do_not_mark_modified(self):
        rom = ROMImage(data=bytearray([0x05]) * 0x40000)
        m = MapDef("t", rows=2, cols=2, data_width=U8, data_addr=0x1000)
        m.write(rom, [[5, 5], [5, 5]])
        assert not rom.is_modified

    def test_oversized_values_rejected(self):
        rom = ROMImage(data=bytearray([0xFF]) * 0x40000)
        m = MapDef("t", rows=1, cols=2, data_width=U8, data_addr=0x1000)
        with pytest.raises(ValueError, match="exceed"):
            m.write(rom, [[1, 2, 3]])


_XDF_JSON = os.path.join(os.path.dirname(__file__), "..", "reference", "xdf_tables.json")


class TestFallbackWidthsMatchXDF:
    """Every fallback map must have the XDF's element size for its reference PN."""

    @staticmethod
    def _xdf_z(pn):
        import json
        out = {}
        with open(_XDF_JSON, encoding="utf-8") as f:
            for e in json.load(f):
                z = e.get("axes", {}).get("z")
                if e.get("pn") == pn and z:
                    out.setdefault(e["name"], z)
        return out

    def _check(self, maps, pn):
        xdf = self._xdf_z(pn)
        checked = 0
        for m in maps:
            if not m.data_addr:
                continue
            # KFLBTS_0_A on 8D0907551M is the bank-1 table the fallback uses
            z = xdf.get(m.name) or xdf.get(m.name + "_0_A")
            if not z or z["addr"] != m.data_addr:
                continue
            assert z["elemsize"] == abs(m.data_width), \
                f"{m.name}: fallback width {abs(m.data_width)} but XDF elemsize {z['elemsize']}"
            assert {z["rows"], z["cols"]} == {m.rows, m.cols}, m.name
            checked += 1
        assert checked >= 5

    def test_awp_dl(self):
        self._check(make_awp_maps("06A906032DL"), "06A906032DL")

    def test_v6_biturbo_551m(self):
        self._check(make_v6_biturbo_maps(), "8D0907551M")

    @pytest.mark.parametrize("name", ["KFLBTS", "LAMFA", "KFDLULS"])
    def test_dl_single_byte_maps(self, name):
        m = next(x for x in make_awp_maps("06A906032DL") if x.name == name)
        assert m.data_width == U8

    def test_27t_kfdluls_single_byte(self):
        m = next(x for x in make_v6_biturbo_maps() if x.name == "KFDLULS")
        assert m.data_width == U8
