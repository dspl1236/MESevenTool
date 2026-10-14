"""
Review items E8 (cell display precision) and E11 (512 KB builds are not
halves of a 1 MB image; the 1 MB fallback maps must not be shown there).
"""
import os
import pytest
from meseventool.rom import ROMImage
from meseventool.maps import MapDef, make_awp_maps, U16, S8
from meseventool.profiles import PROFILE_AWP, PROFILE_V6_27T_ME71, detect_rom_profile
from meseventool.ecu_id import identify
from meseventool.dpp import extract_dpp
from tests.rom_corpus import find_rom


# ── E8 ───────────────────────────────────────────────────────────────────────

class TestDisplayPrecision:
    @pytest.mark.parametrize("name,decimals", [
        ("KFZW", 1),       # 0.75 deg/count  → 0.1 resolution, error 0.05 < 0.375
        ("MLHFM", 2),      # 0.1             → 0.01
        ("KFMIRL", 2),     # 0.023438        → 0.01, error 0.005 < 0.0117
        ("KFMIOP", 3),     # 0.001526        → 0.001, error 0.0005 < 0.00076
        ("KFLBTS", 3),     # 0.007813
        ("LAMFA", 3),      # 0.007813
        ("KFDLULS", 0),    # 5.0
    ])
    def test_decimals_for_dl_maps(self, name, decimals):
        m = next(x for x in make_awp_maps("06A906032DL") if x.name == name)
        assert m.display_decimals == decimals, (name, m.step)

    @pytest.mark.parametrize("name", ["KFMIOP", "KFLBTS", "LAMFA", "KFMIRL", "KFZW", "MLHFM"])
    def test_displayed_text_reencodes_to_same_raw(self, name):
        """For every raw count, format → float → encode gives the same count.
        With .2f this failed for KFMIOP/KFLBTS/LAMFA (±3 counts)."""
        m = next(x for x in make_awp_maps("06A906032DL") if x.name == name)
        width = abs(m.data_width)
        lo, hi = (-(1 << (8 * width - 1)), (1 << (8 * width - 1)) - 1) if m.data_width < 0 \
            else (0, (1 << (8 * width)) - 1)
        step = max(1, (hi - lo) // 4096)
        for raw in range(lo, hi + 1, step):
            phys = m.decode(raw)
            assert m.encode(float(m.format_value(phys))) == raw, (name, raw)

    def test_two_decimals_were_too_coarse(self):
        m = next(x for x in make_awp_maps("06A906032DL") if x.name == "KFMIOP")
        bad = sum(1 for raw in range(0, 4000)
                  if m.encode(float(f"{m.decode(raw):.2f}")) != raw)
        assert bad > 0                      # the old display really drifted

    def test_same_raw(self):
        m = next(x for x in make_awp_maps("06A906032DL") if x.name == "KFLBTS")
        assert m.same_raw(1.0, 1.0 + m.step * 0.4)
        assert not m.same_raw(1.0, 1.0 + m.step)

    def test_step_and_decimals_for_plain_map(self):
        m = MapDef("t", rows=1, cols=1, data_width=U16)
        assert m.step == 1.0 and m.display_decimals == 0
        m2 = MapDef("t", rows=1, cols=1, data_width=S8, decode=lambda x: x * 0.5)
        assert m2.display_decimals == 1 and m2.format_value(1.5) == "1.5"   # step 0.5


class TestMapsPanelEdit:
    def test_retyping_displayed_value_is_not_an_edit(self, monkeypatch):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        pytest.importorskip("PyQt5.QtWidgets")
        from PyQt5.QtWidgets import QApplication
        _app = QApplication.instance() or QApplication([])   # noqa: F841 (keeps Qt alive)
        import app.main as appmain
        from meseventool.needle import Searcher
        rom = ROMImage(data=bytearray(0x100000))
        m = next(x for x in make_awp_maps("06A906032DL") if x.name == "KFMIOP")
        for i in range(m.rows * m.cols):          # distinct raw values
            rom.data[m.data_addr + 2 * i:m.data_addr + 2 * i + 2] = (1000 + 7 * i).to_bytes(2, "little")
        w = appmain.MapsWidget()
        w.load_rom(rom, Searcher(rom), [m])
        item = w._table.item(2, 3)
        shown = item.text()
        item.setText(shown)                       # user re-commits the shown text
        assert not w._pending_edits
        assert not w._btn_write.isEnabled()
        item.setText(str(float(shown) + 10 * m.step))
        assert (2, 3) in w._pending_edits
        w._on_write_map()
        raw = int.from_bytes(rom.data[m.data_addr + 2 * (2 * m.cols + 3):][:2], "little")
        assert raw == 1000 + 7 * (2 * m.cols + 3) + 10


# ── E11 ──────────────────────────────────────────────────────────────────────

class TestMapsForImageSize:
    def test_fallback_withheld_on_512k_and_256k(self):
        assert PROFILE_AWP.make_maps("06A906032ZZ", rom_size=0x80000) == []
        assert PROFILE_AWP.make_maps(None, rom_size=0x40000) == []
        assert PROFILE_V6_27T_ME71.make_maps("8D0907551ZZ", rom_size=0x80000) == []

    def test_fallback_on_1mb_unchanged(self):
        assert PROFILE_AWP.make_maps("06A906032ZZ", rom_size=0x100000)
        assert PROFILE_AWP.make_maps("06A906032ZZ")        # size unknown: as before

    def test_xdf_part_numbers_work_on_their_own_size(self):
        maps = PROFILE_AWP.make_maps("06A906032CL", rom_size=0x80000)
        assert maps and all(m.data_addr < 0x80000 for m in maps if m.data_addr)

    @pytest.mark.parametrize("name,pn", [("06A906032CL.bin", "06A906032CL"),
                                         ("06A906032CM.bin", "06A906032CM")])
    def test_real_512k_dump_reads_plausible_ignition(self, name, pn):
        path = find_rom(name)
        if not path:
            pytest.skip(name)
        rom = ROMImage.load(path)
        assert rom.size == 0x80000
        prof = detect_rom_profile(identify(rom), extract_dpp(rom))
        maps = prof.make_maps(pn, rom_size=rom.size)
        kfzw = next(m for m in maps if m.name == "KFZW")
        flat = [v for row in kfzw.read(rom) for v in row]
        assert -25.0 <= min(flat) and max(flat) <= 48.0
        # the 1 MB DL fallback read garbage here (−96 … 94.5)
        fb = next(m for m in make_awp_maps(pn) if m.name == "KFZW")
        flat_fb = [v for row in fb.read(rom) for v in row]
        assert min(flat_fb) < -25.0 or max(flat_fb) > 48.0

    def test_512k_is_not_half_of_1mb(self):
        """Version string lives at a different offset: a separate build."""
        a, b = find_rom("06A906032CL.bin"), find_rom("06A906032DL_0261206890_v360227_MT_OEM.bin")
        if not (a and b):
            pytest.skip("CL/DL")
        import re
        va = re.search(rb"[0-9]{2}/[0-9]/ME7", bytes(ROMImage.load(a).data)).start()
        vb = re.search(rb"[0-9]{2}/[0-9]/ME7", bytes(ROMImage.load(b).data)).start()
        assert va != vb and va != vb - 0x80000
