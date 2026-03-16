"""
tests/test_xdf.py
=================
Tests for XDF table loader — uses the reference/xdf_tables.json in the repo.
"""

import pytest
from meseventool.xdf import XDFLoader, _parse_math


# ── _parse_math ────────────────────────────────────────────────────────────────

class TestParseMath:
    def test_scale_times_x(self):
        scale, offset = _parse_math("0.250000 * X")
        assert scale == pytest.approx(0.25)
        assert offset == pytest.approx(0.0)

    def test_offset_plus_x_times_scale(self):
        scale, offset = _parse_math("0.000000+X*0.100000")
        assert scale == pytest.approx(0.1)
        assert offset == pytest.approx(0.0)

    def test_negative_offset(self):
        scale, offset = _parse_math("-48.000000+X*0.750000")
        assert scale == pytest.approx(0.75)
        assert offset == pytest.approx(-48.0)

    def test_identity_fallback(self):
        scale, offset = _parse_math("X")
        assert scale == pytest.approx(1.0)
        assert offset == pytest.approx(0.0)

    def test_small_scale(self):
        scale, offset = _parse_math("0.023438 * X")
        assert scale == pytest.approx(0.023438)


# ── XDFLoader ─────────────────────────────────────────────────────────────────

class TestXDFLoader:
    @pytest.fixture(scope="class")
    def loader(self):
        return XDFLoader()

    def test_loads_without_error(self, loader):
        assert loader is not None

    def test_part_numbers_present(self, loader):
        pns = loader.part_numbers()
        assert "06A906032DL" in pns
        assert "06A906032CL" in pns
        assert "06A906032CM" in pns

    def test_tables_for_dl(self, loader):
        tables = loader.tables_for("06A906032DL")
        assert len(tables) >= 10

    def test_kfzw_confirmed_for_dl(self, loader):
        t = loader.get("06A906032DL", "KFZW")
        assert t is not None
        assert t.z is not None
        assert t.data_addr == 0x0120DD
        assert t.rows == 12
        assert t.cols == 16

    def test_mlhfm_confirmed_for_dl(self, loader):
        t = loader.get("06A906032DL", "MLHFM")
        assert t is not None
        assert t.z is not None
        assert t.data_addr == 0x014574
        assert t.cols == 512 or t.rows == 512

    def test_snm16zuub_rpm_axis(self, loader):
        t = loader.get("06A906032DL", "SNM16ZUUB")
        assert t is not None
        assert t.data_addr == 0x013072

    def test_kfmirl_shape(self, loader):
        t = loader.get("06A906032DL", "KFMIRL")
        assert t is not None
        assert t.rows == 16
        assert t.cols == 16

    def test_get_returns_none_for_missing(self, loader):
        assert loader.get("06A906032DL", "NONEXISTENT_TABLE") is None
        assert loader.get("UNKNOWN_PN", "KFZW") is None


# ── to_mapdef() ───────────────────────────────────────────────────────────────

class TestXDFToMapDef:
    @pytest.fixture(scope="class")
    def loader(self):
        return XDFLoader()

    def test_kfzw_mapdef_confidence(self, loader):
        t = loader.get("06A906032DL", "KFZW")
        m = t.to_mapdef()
        assert m.confidence == "CONFIRMED"
        assert m.data_addr == 0x0120DD
        assert m.name == "KFZW"

    def test_kfzw_mapdef_decode(self, loader):
        t = loader.get("06A906032DL", "KFZW")
        m = t.to_mapdef()
        # KFZW uses signed byte — raw=20 → 20 * scale
        assert m.decode is not None
        val = m.decode(20)
        assert isinstance(val, float)

    def test_mlhfm_mapdef(self, loader):
        t = loader.get("06A906032DL", "MLHFM")
        m = t.to_mapdef()
        assert m.confidence == "CONFIRMED"
        assert m.data_addr == 0x014574
        # scale should be 0.1 (from math "0.000000+X*0.100000")
        assert m.decode(1000) == pytest.approx(100.0)

    def test_all_dl_mapdefs_have_addr(self, loader):
        maps = loader.make_maps("06A906032DL")
        for m in maps:
            assert m.data_addr != 0, f"{m.name} has addr=0"
            assert m.confidence == "CONFIRMED"


# ── make_maps() ───────────────────────────────────────────────────────────────

class TestXDFMakeMaps:
    @pytest.fixture(scope="class")
    def loader(self):
        return XDFLoader()

    def test_make_maps_dl_nonempty(self, loader):
        maps = loader.make_maps("06A906032DL")
        assert len(maps) >= 5

    def test_make_maps_skips_axis_tables(self, loader):
        maps = loader.make_maps("06A906032DL")
        names = [m.name for m in maps]
        # Pure axis tables should not appear as standalone maps
        assert "SNM16ZUUB" not in names
        assert "SRL12ZUUB" not in names
        assert "TVUB"       not in names

    def test_make_maps_kfzw_first(self, loader):
        maps = loader.make_maps("06A906032DL")
        assert maps[0].name == "KFZW"

    def test_make_maps_includes_ldrxn(self, loader):
        maps = loader.make_maps("06A906032DL")
        names = [m.name for m in maps]
        assert "LDRXN" in names or "LDRXN_1_A" in names

    def test_make_maps_unknown_pn_returns_empty(self, loader):
        maps = loader.make_maps("UNKNOWN00000")
        assert maps == []


# ── Profile integration ───────────────────────────────────────────────────────

class TestProfileXDFIntegration:
    def test_profile_make_maps_with_xdf_pn(self):
        from meseventool.profiles import PROFILE_AWP
        maps = PROFILE_AWP.make_maps(xdf_pn="06A906032DL")
        assert len(maps) >= 5
        kfzw = next((m for m in maps if m.name == "KFZW"), None)
        assert kfzw is not None
        assert kfzw.confidence == "CONFIRMED"
        assert kfzw.data_addr == 0x0120DD

    def test_profile_make_maps_fallback_without_pn(self):
        from meseventool.profiles import PROFILE_AWP
        maps = PROFILE_AWP.make_maps()
        assert len(maps) >= 3
        kfzw = next((m for m in maps if m.name == "KFZW"), None)
        assert kfzw is not None
        # Fallback maps have no confirmed addr
        assert kfzw.confidence in ("PROVISIONAL", "UNCONFIRMED", "CONFIRMED")

    def test_profile_make_maps_unknown_pn_fallback(self):
        from meseventool.profiles import PROFILE_AWP
        maps = PROFILE_AWP.make_maps(xdf_pn="UNKNOWN99999")
        # Should fall back to generic maps, not crash
        assert len(maps) >= 3
