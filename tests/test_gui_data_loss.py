"""
Review items E2–E7: the GUI must not lose or mis-save work.
Runs the real window offscreen; dialogs are stubbed.
"""
import os
import tempfile

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt5.QtWidgets")
from PyQt5.QtWidgets import QApplication, QMessageBox   # noqa: E402

from meseventool.rom import ROMImage                    # noqa: E402
from tests.synthetic_rom import make_rom_with_checksum  # noqa: E402

import app.main as appmain                              # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def rom_file(tmp_path):
    path = tmp_path / "synthetic.bin"
    make_rom_with_checksum(0x100000).save(str(path))
    return str(path)


@pytest.fixture
def window(qapp, monkeypatch):
    # Silence every modal dialog; tests override question() as needed.
    # warning() is the "checksums not OK, save anyway?" prompt: answer Yes
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "critical", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "information", staticmethod(lambda *a, **k: QMessageBox.Ok))
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Discard))
    w = appmain.MESevenWindow()
    yield w
    w._dirty = False
    w.close()


class _Event:
    def __init__(self):
        self.accepted = None

    def accept(self):
        self.accepted = True

    def ignore(self):
        self.accepted = False


# ── E7: Save As retargets later saves ────────────────────────────────────────

class TestSaveAsRetargets:
    def test_rom_save_as_changes_path(self, tmp_path):
        a = tmp_path / "a.bin"
        b = tmp_path / "b.bin"
        rom = make_rom_with_checksum(0x40000)
        rom.save(str(a))
        rom.data[0x100] ^= 0xFF
        rom.save_as(str(b))
        assert rom.path == str(b)
        assert not rom.is_modified
        rom.data[0x101] ^= 0xFF
        rom.save()
        assert open(str(a), "rb").read()[0x101] != rom.data[0x101]   # original untouched
        assert open(str(b), "rb").read()[0x101] == rom.data[0x101]

    def test_window_save_as_then_save(self, window, rom_file, monkeypatch, tmp_path):
        window._load_rom(rom_file)
        assert window._rom is not None
        original = open(rom_file, "rb").read()
        window._rom.data[0x200] ^= 0xFF
        window._dirty = True
        out = str(tmp_path / "tuned.bin")
        monkeypatch.setattr(appmain.QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: (out, "")))
        window._on_save_as()
        assert window._rom.path == out
        assert window._lbl_rom_path.text() == "tuned.bin"
        window._rom.data[0x201] ^= 0xFF
        window._dirty = True
        window._on_save()
        assert open(rom_file, "rb").read() == original
        assert open(out, "rb").read()[0x201] == window._rom.data[0x201]


# ── E2: opening another ROM while dirty ──────────────────────────────────────

class TestOpenWhileDirty:
    def test_cancel_keeps_current_rom(self, window, rom_file, monkeypatch, tmp_path):
        window._load_rom(rom_file)
        first = window._rom
        window._dirty = True
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Cancel))
        other = tmp_path / "other.bin"
        make_rom_with_checksum(0x100000).save(str(other))
        window._load_rom(str(other))
        assert window._rom is first
        assert window._dirty

    def test_discard_loads_new_rom(self, window, rom_file, monkeypatch, tmp_path):
        window._load_rom(rom_file)
        first = window._rom
        window._dirty = True
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Discard))
        other = tmp_path / "other.bin"
        make_rom_with_checksum(0x100000).save(str(other))
        window._load_rom(str(other))
        assert window._rom is not first
        assert not window._dirty

    def test_save_then_load(self, window, rom_file, monkeypatch, tmp_path):
        window._load_rom(rom_file)
        window._rom.data[0x300] ^= 0xFF
        window._dirty = True
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Save))
        other = tmp_path / "other.bin"
        make_rom_with_checksum(0x100000).save(str(other))
        window._load_rom(str(other))
        assert open(rom_file, "rb").read()[0x300] == (0xAA ^ 0xFF)   # edit was saved
        assert window._rom.path == str(other)


# ── E3: a failed analysis leaves the window on the old ROM ───────────────────

class TestAnalysisFailure:
    def test_old_rom_kept(self, window, rom_file, monkeypatch, tmp_path):
        window._load_rom(rom_file)
        first = window._rom
        first_searcher = window._searcher
        window._dirty = True   # must also survive
        other = tmp_path / "other.bin"
        make_rom_with_checksum(0x100000).save(str(other))
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Discard))

        def boom(rom):
            raise RuntimeError("identify blew up")
        monkeypatch.setattr(appmain, "identify", boom)
        window._load_rom(str(other))
        assert window._rom is first
        assert window._searcher is first_searcher
        assert window._rom.path == rom_file


# ── E6: close only when nothing is lost ──────────────────────────────────────

class TestClose:
    def test_cancel_keeps_window(self, window, rom_file, monkeypatch):
        window._load_rom(rom_file)
        window._dirty = True
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Cancel))
        ev = _Event()
        window.closeEvent(ev)
        assert ev.accepted is False

    def test_failed_save_keeps_window(self, window, rom_file, monkeypatch):
        window._load_rom(rom_file)
        window._dirty = True
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Save))

        def fail(*a, **k):
            raise OSError("disk full")
        monkeypatch.setattr(window._rom, "save", fail)
        ev = _Event()
        window.closeEvent(ev)
        assert ev.accepted is False
        assert window._dirty

    def test_cancelled_save_as_keeps_window(self, window, monkeypatch):
        rom = make_rom_with_checksum(0x100000)          # no path: Save → Save As
        window._rom = rom
        window._dirty = True
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Save))
        monkeypatch.setattr(appmain.QFileDialog, "getSaveFileName",
                            staticmethod(lambda *a, **k: ("", "")))
        ev = _Event()
        window.closeEvent(ev)
        assert ev.accepted is False

    def test_successful_save_closes(self, window, rom_file, monkeypatch):
        window._load_rom(rom_file)
        window._rom.data[0x400] ^= 0xFF
        window._dirty = True
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: QMessageBox.Save))
        ev = _Event()
        window.closeEvent(ev)
        assert ev.accepted is True
        assert not window._dirty

    def test_clean_closes_without_asking(self, window, rom_file, monkeypatch):
        window._load_rom(rom_file)
        monkeypatch.setattr(QMessageBox, "question",
                            staticmethod(lambda *a, **k: pytest.fail("asked")))
        ev = _Event()
        window.closeEvent(ev)
        assert ev.accepted is True


# ── E4 / E5: the patch panel follows the ROM ─────────────────────────────────

class TestPanelSync:
    def test_failed_apply_unticks_checkbox(self, window, rom_file, monkeypatch):
        from PyQt5.QtWidgets import QCheckBox
        from meseventool.patches import PatchDef, PatchResult, PatchState, PatchCategory
        window._load_rom(rom_file)
        patch = PatchDef(name="test-only", description="", category=PatchCategory.EMISSIONS,
                         needle=bytes([0x11, 0x22]), mask=bytes([0xFF, 0xFF]), offset=0,
                         stock_bytes=bytes([0x11]), patch_bytes=bytes([0x99]))
        cb = QCheckBox(patch.name)
        cb.setChecked(True)                           # the user just ticked it
        window._w_patches._checks[patch.name] = cb
        missing = PatchResult(patch, PatchState.MISSING, 0, "no needle")
        monkeypatch.setattr(patch, "detect", lambda rom, s=None, profile=None: missing)
        monkeypatch.setattr(patch, "apply", lambda rom, r: False)
        # refresh_states() re-detects through detect_all(): include the fake patch
        monkeypatch.setattr(appmain, "detect_all", lambda rom, s=None, profile=None: [missing])
        window._on_patch_toggled(patch, True)
        assert not cb.isChecked()
        assert not window._dirty

    def test_spinner_refreshes_from_rom(self, window, rom_file, monkeypatch):
        from PyQt5.QtWidgets import QDoubleSpinBox
        from meseventool.patches import FixedAddressScalarDef, PatchCategory
        window._load_rom(rom_file)
        scalar = FixedAddressScalarDef(
            name="test-only scalar", description="", category=PatchCategory.PERFORMANCE,
            fixed_addr=0x5000, size=2, big_endian=True, scale=40.0, unit="RPM",
            min_val=4000.0, max_val=9000.0)
        window._profile = None            # synthetic ROM: no profile, scalar is not PN-gated
        window._w_patches._profile = None
        window._rom.data[0x5000:0x5002] = (170).to_bytes(2, "big")   # 6800 RPM
        spin = QDoubleSpinBox()
        spin.setRange(4000, 9000)
        spin.setValue(4000)
        window._w_patches._spinners[scalar.name] = spin
        monkeypatch.setattr(appmain, "ALL_SCALAR_PATCHES", [scalar])
        window._on_scalar_changed(scalar, 7000.0)
        assert window._dirty
        assert spin.value() == pytest.approx(7000.0)
        assert window._rom.data[0x5000:0x5002] == (175).to_bytes(2, "big")
        # a value the ROM rejects: spinner snaps back to the real value
        window._on_scalar_changed(scalar, 20000.0)
        assert spin.value() == pytest.approx(7000.0)
