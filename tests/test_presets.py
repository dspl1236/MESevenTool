"""
The standalone-swap presets (docs/swap_preset_scope.md, catalogue-only stage).
"""
import pytest
from meseventool.rom import ROMImage
from meseventool.needle import Searcher
from meseventool.dpp import extract_dpp
from meseventool.ecu_id import identify
from meseventool.patches import ALL_PATCHES, PatchState
from meseventool.presets import (ALL_PRESETS, SWAP_KEEP_MAF, SWAP_ALPHA_N,
                                 Preset, PresetMember, PlanAction)
from meseventool.profiles import detect_rom_profile
from tests.rom_corpus import find_rom


def _load(name):
    path = find_rom(name)
    if not path:
        pytest.skip(name)
    rom = ROMImage.load(path)
    return rom, Searcher(rom), detect_rom_profile(identify(rom), extract_dpp(rom))


# ── Catalogue consistency ────────────────────────────────────────────────────

class TestPresetDefinitions:
    def test_every_member_names_real_patches(self):
        names = {p.name for p in ALL_PATCHES}
        for preset in ALL_PRESETS:
            for m in preset.members:
                for n in m.patches:
                    assert n in names, (preset.name, m.job, n)

    def test_excluded_entries(self):
        """Review B7 and the unconfirmed immo no-op stay out of the bundle."""
        for preset in ALL_PRESETS:
            all_names = {n for m in preset.members for n in m.patches}
            assert "Rear O2 OBD Readiness Flags" not in all_names
            assert "IMMO SKC Accept-All — ME7.5 06A/4B0 (force key match)" not in all_names
            assert not any("Knock Retard" in n for n in all_names)

    def test_immobiliser_member_is_flagged(self):
        immo = next(m for m in SWAP_KEEP_MAF.members if m.job == "Immobiliser off")
        assert immo.required and "PROVISIONAL" in immo.note
        assert any("PROVISIONAL" in c for c in SWAP_KEEP_MAF.caveats)

    def test_alpha_n_is_keep_maf_plus_maf_members(self):
        base = [m.job for m in SWAP_KEEP_MAF.members]
        ext = [m.job for m in SWAP_ALPHA_N.members]
        assert ext[:len(base)] == base
        assert "MAF delete (alpha-N load)" in ext and "MAF sensor diagnosis off" in ext

    def test_unknown_patch_name_rejected(self):
        with pytest.raises(KeyError):
            Preset("x", "", [PresetMember("j", ["no such patch"])]).validate()


# ── Planning on synthetic ROMs ───────────────────────────────────────────────

class TestPlanning:
    def test_blank_rom_plans_nothing(self):
        rom = ROMImage(data=bytearray([0xAA]) * 0x100000)
        plan = SWAP_KEEP_MAF.plan(rom, Searcher(rom), profile=None)
        assert not plan.will_write
        assert all(m.action in (PlanAction.NOT_APPLICABLE, PlanAction.MISSING,
                                PlanAction.SKIP_MODIFIED)
                   for m in plan.members)
        assert not plan.complete
        assert "to apply" in plan.summary()

    def test_apply_on_blank_rom_writes_nothing(self):
        rom = ROMImage(data=bytearray([0xAA]) * 0x100000)
        report = SWAP_KEEP_MAF.apply(rom, Searcher(rom), profile=None)
        assert report.ok and not report.applied and not rom.is_modified


# ── Real ROMs ────────────────────────────────────────────────────────────────

class TestRealROMs:
    @pytest.mark.parametrize("name", ["06A906032DL_0261206890_v360227_MT_OEM.bin",
                                      "18CM.Bin", "8D0907551M-0001.bin"])
    def test_plan_apply_revert_round_trip(self, name):
        rom, s, prof = _load(name)
        original = bytes(rom.data)
        plan = SWAP_KEEP_MAF.plan(rom, s, prof)
        to_apply = plan.by_action(PlanAction.APPLY)
        assert to_apply, plan.summary()
        # every chosen entry is one the catalogue validated on this family
        for mp in plan.members:
            if mp.patch is not None and mp.action in (PlanAction.APPLY, PlanAction.ALREADY):
                assert mp.result.state in (PatchState.STOCK, PatchState.PATCHED)

        report = SWAP_KEEP_MAF.apply(rom, s, prof)
        assert report.ok, report.failed
        assert set(report.applied) == {mp.patch.name for mp in to_apply}
        after = report.plan_after
        assert not after.by_action(PlanAction.APPLY)          # nothing left to do
        assert rom.is_modified
        # Known catalogue limitation (review A8): the 2.7T MSLUB entry's anchor
        # IS the stock table, so once zeroed it cannot be re-detected and is
        # reported MISSING instead of ALREADY.  Everything else must re-detect.
        one_way = {"SAP MSLUB Airflow Table Zero (2.7T)"}
        applied_jobs = {mp.member.job for mp in to_apply if mp.patch.name not in one_way}
        assert {m.member.job for m in after.by_action(PlanAction.ALREADY)} >= applied_jobs
        for mp in to_apply:
            if mp.patch.name in one_way:
                st = next(m for m in after.members if m.member.job == mp.member.job)
                assert st.action == PlanAction.MISSING

        back = SWAP_KEEP_MAF.revert(rom, Searcher(rom), prof)
        assert back.ok, back.failed
        diff = {i for i, (a, b) in enumerate(zip(bytes(rom.data), original)) if a != b}
        msl = [mp for mp in to_apply if mp.patch.name in one_way]
        if msl:
            site = msl[0].result.addr
            assert diff and diff <= set(range(site, site + 14)), sorted(diff)[:5]
        else:
            assert not diff

    def test_dl_plan_detail(self):
        """06A build: CDLSHV does not exist (06a layout), the 2.7T-only and
        4B0-only members are N/A, the immobiliser member is the PROVISIONAL one."""
        rom, s, prof = _load("06A906032DL_0261206890_v360227_MT_OEM.bin")
        plan = SWAP_KEEP_MAF.plan(rom, s, prof)
        by_job = {m.member.job: m for m in plan.members}
        assert by_job["Rear O2 interchange diagnosis off"].action == PlanAction.NOT_APPLICABLE
        assert by_job["Rear O2 heater configuration (ESKONF)"].action == PlanAction.NOT_APPLICABLE
        assert by_job["Immobiliser databus CEL off"].action == PlanAction.NOT_APPLICABLE
        immo = by_job["Immobiliser off"]
        assert immo.action in (PlanAction.APPLY, PlanAction.MISSING)
        if immo.action == PlanAction.APPLY:
            assert immo.confidence == "PROVISIONAL"
            assert immo in plan.unproven
        assert by_job["Catalyst monitor off"].result.addr == 0x0181A3     # 06a layout
        assert by_job["VVT cam position monitor off"].patch.name.endswith("AWW/AWP/AUQ/AUM)")

    def test_unverified_build_is_incomplete(self):
        """SL (X505R): no codeword layout, so the codeword members are N/A."""
        rom, s, prof = _load("032sl_auto_revo_1.bin")
        plan = SWAP_KEEP_MAF.plan(rom, s, prof)
        assert not plan.complete
        by_job = {m.member.job: m for m in plan.members}
        assert by_job["Catalyst monitor off"].action == PlanAction.NOT_APPLICABLE

    def test_alpha_n_on_dl(self):
        rom, s, prof = _load("06A906032DL_0261206890_v360227_MT_OEM.bin")
        plan = SWAP_ALPHA_N.plan(rom, s, prof)
        by_job = {m.member.job: m for m in plan.members}
        assert by_job["MAF delete (alpha-N load)"].action == PlanAction.APPLY
        assert by_job["MAF sensor diagnosis off"].action == PlanAction.NOT_APPLICABLE  # DL ships 0


# ── GUI: button present, plan dialog gated ───────────────────────────────────

@pytest.fixture(scope="module")
def qapp():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    QtWidgets = pytest.importorskip("PyQt5.QtWidgets")
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


class TestPanel:
    def test_preset_buttons_and_apply_flow(self, qapp, monkeypatch):
        from PyQt5.QtWidgets import QDialog
        import app.main as appmain
        path = find_rom("06A906032DL_0261206890_v360227_MT_OEM.bin")
        if not path:
            pytest.skip("DL")
        monkeypatch.setattr(appmain.QMessageBox, "warning", staticmethod(lambda *a, **k: None))
        monkeypatch.setattr(appmain.QMessageBox, "information", staticmethod(lambda *a, **k: None))
        w = appmain.MESevenWindow()
        try:
            w._load_rom(path)
            assert w._rom is not None and not w._dirty
            # dialog cancelled → nothing written
            monkeypatch.setattr(QDialog, "exec_", lambda self: QDialog.Rejected)
            w._on_preset_requested(SWAP_KEEP_MAF)
            assert not w._dirty
            # dialog accepted → applied, dirty, panel refreshed
            monkeypatch.setattr(QDialog, "exec_", lambda self: QDialog.Accepted)
            w._on_preset_requested(SWAP_KEEP_MAF)
            assert w._dirty
            after = SWAP_KEEP_MAF.plan(w._rom, Searcher(w._rom), w._profile)
            assert not after.by_action(PlanAction.APPLY)
        finally:
            w._dirty = False
            w.close()
            w.deleteLater()
            qapp.processEvents()
