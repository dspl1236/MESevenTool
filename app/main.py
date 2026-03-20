"""
MESevenTool — Bosch ME7.x ROM Editor
app/main.py

Qt GUI with three panels:
  ROM Info    — ECU identification, checksum status, DPP values
  Patches     — Click-box toggleable patches (PatchDef + ScalarPatchDef)
  Maps        — Calibration map viewer/editor (KFZW, MLHFM, LDRXN, etc.)

Usage:
    python -m app.main
    python -m app.main path/to/rom.bin
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QFileDialog, QTabWidget, QScrollArea,
        QGroupBox, QCheckBox, QDoubleSpinBox, QFrame,
        QTableWidget, QTableWidgetItem, QHeaderView, QStatusBar,
        QTextEdit, QGridLayout, QMessageBox, QAction, QSplitter,
        QDialogButtonBox, QDialog,
    )
    from PyQt5.QtCore import Qt, pyqtSignal, QTimer
    from PyQt5.QtGui import QColor
    _HAS_QT = True
except ImportError:
    _HAS_QT = False

from meseventool.rom import ROMImage
from meseventool.needle import Searcher
from meseventool.dpp import DPPExtractor, DPPValues
from meseventool.checksum import ChecksumManager
from meseventool.ecu_id import identify
from meseventool.patches import (
    ALL_PATCHES, ALL_SCALAR_PATCHES, detect_all,
    PatchDef, ScalarPatchDef, PatchState, PatchCategory,
)
from meseventool.profiles import detect_profile
from meseventool.known_roms import lookup_rom, is_known_stock
from meseventool import __version__


# ── Colour palette ─────────────────────────────────────────────────────────────
C_BG      = "#0d0d0f"
C_BG2     = "#141417"
C_BG3     = "#1c1c20"
C_BORDER  = "#2a2a30"
C_FG      = "#e2e2e8"
C_DIM     = "#6b6b78"
C_AMBER   = "#ffaa00"
C_GREEN   = "#3ddc84"
C_RED     = "#ff5252"
C_BLUE    = "#4db8ff"
C_PURPLE  = "#aa66ff"

_BASE_STYLE = f"""
    QMainWindow, QDialog  {{ background:{C_BG}; color:{C_FG}; }}
    QWidget               {{ background:{C_BG}; color:{C_FG};
                             font-family: Consolas, 'Courier New', monospace;
                             font-size: 12px; }}
    QTabWidget::pane      {{ border:1px solid {C_BORDER}; background:{C_BG2}; }}
    QTabBar::tab          {{ background:{C_BG3}; color:{C_DIM};
                             padding:6px 14px; border:1px solid {C_BORDER};
                             border-bottom:none; }}
    QTabBar::tab:selected {{ background:{C_BG2}; color:{C_FG}; }}
    QGroupBox             {{ border:1px solid {C_BORDER}; border-radius:3px;
                             margin-top:8px; padding-top:8px;
                             color:{C_DIM}; font-size:10px;
                             letter-spacing:1px; text-transform:uppercase; }}
    QGroupBox::title      {{ subcontrol-origin:margin; left:8px; top:0; }}
    QPushButton           {{ background:{C_BG3}; color:{C_FG};
                             border:1px solid {C_BORDER}; border-radius:3px;
                             padding:5px 14px; }}
    QPushButton:hover     {{ border-color:{C_BLUE}; color:{C_BLUE}; }}
    QPushButton:disabled  {{ color:{C_DIM}; border-color:{C_BORDER}; }}
    QLabel                {{ color:{C_FG}; background:transparent; }}
    QCheckBox             {{ color:{C_FG}; spacing:6px; }}
    QCheckBox::indicator  {{ width:14px; height:14px; }}
    QCheckBox::indicator:unchecked {{ border:1px solid {C_BORDER};
                                      background:{C_BG3}; border-radius:2px; }}
    QCheckBox::indicator:checked   {{ background:{C_GREEN}; border:1px solid {C_GREEN};
                                      border-radius:2px; }}
    QScrollArea           {{ border:none; background:{C_BG}; }}
    QScrollBar:vertical   {{ background:{C_BG}; width:6px; }}
    QScrollBar::handle:vertical {{ background:{C_BORDER}; border-radius:3px; }}
    QTextEdit             {{ background:{C_BG2}; color:{C_FG};
                             border:1px solid {C_BORDER}; }}
    QTableWidget          {{ background:{C_BG2}; color:{C_FG};
                             gridline-color:{C_BORDER}; border:1px solid {C_BORDER};
                             selection-background-color:#1a1e2a; }}
    QHeaderView::section  {{ background:{C_BG3}; color:{C_DIM};
                             border:none; border-bottom:1px solid {C_BORDER};
                             padding:4px 8px; font-size:10px;
                             letter-spacing:1px; text-transform:uppercase; }}
    QStatusBar            {{ background:{C_BG3}; color:{C_DIM};
                             border-top:1px solid {C_BORDER};
                             font-size:10px; padding:2px 8px; }}
    QSpinBox, QDoubleSpinBox {{ background:{C_BG3}; color:{C_FG};
                                border:1px solid {C_BORDER}; padding:3px; }}
    QSplitter::handle     {{ background:{C_BORDER}; }}
"""


def btn_style(colour: str) -> str:
    return (f"QPushButton {{ background:{C_BG3}; color:{colour}; "
            f"border:1px solid {colour}44; border-radius:3px; padding:5px 14px; }}"
            f"QPushButton:hover {{ background:{colour}22; }}"
            f"QPushButton:disabled {{ color:{C_DIM}; border-color:{C_BORDER}; }}")


# ── ROM Info panel ─────────────────────────────────────────────────────────────

class ROMInfoWidget(QWidget):
    """Shows ECU ID strings, checksum status, DPP values, profile."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(10)

        # Banner
        banner_frame = QFrame()
        banner_frame.setStyleSheet(
            f"background:{C_BG2}; border:1px solid {C_BORDER}; border-radius:3px;")
        b_lay = QHBoxLayout(banner_frame)
        b_lay.setContentsMargins(12, 8, 12, 8)
        self._lbl_pn = QLabel("No ROM loaded")
        self._lbl_pn.setStyleSheet(f"color:{C_BLUE}; font-size:14px; font-weight:bold;")
        b_lay.addWidget(self._lbl_pn)
        b_lay.addStretch()
        self._lbl_profile = QLabel("")
        self._lbl_profile.setStyleSheet(f"color:{C_DIM}; font-size:11px;")
        b_lay.addWidget(self._lbl_profile)
        root.addWidget(banner_frame)

        # Two-column grid: ECU fields + checksum status
        grid_w = QWidget()
        grid    = QGridLayout(grid_w)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)

        self._fields: dict[str, QLabel] = {}
        left_rows = [
            ("VAG PN",    "_f_pn"),
            ("Bosch HW",  "_f_bosch"),
            ("Engine",    "_f_engine"),
            ("ROM size",  "_f_size"),
            ("ECU HW",    "_f_hw"),
            ("Profile",   "_f_prof"),
        ]
        right_rows = [
            ("Main cksum",  "_f_cksum_main"),
            ("Multipoint",  "_f_cksum_multi"),
            ("DPP0",        "_f_dpp0"),
            ("DPP1",        "_f_dpp1"),
            ("DPP2",        "_f_dpp2"),
            ("DPP3",        "_f_dpp3"),
        ]
        for row, (label, attr) in enumerate(left_rows):
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(f"color:{C_DIM}; font-size:10px;")
            val = QLabel("—")
            val.setStyleSheet(f"color:{C_FG};")
            grid.addWidget(lbl, row, 0)
            grid.addWidget(val, row, 1)
            setattr(self, attr, val)

        for row, (label, attr) in enumerate(right_rows):
            lbl = QLabel(f"{label}:")
            lbl.setStyleSheet(f"color:{C_DIM}; font-size:10px;")
            val = QLabel("—")
            val.setStyleSheet(f"color:{C_FG};")
            grid.addWidget(lbl, row, 2, Qt.AlignRight)
            grid.addWidget(val, row, 3)
            setattr(self, attr, val)

        root.addWidget(grid_w)

        # EPK / EROTAN
        epk_box = QGroupBox("ECU Description (EROTAN / EPK)")
        epk_lay = QVBoxLayout(epk_box)
        self._txt_epk = QTextEdit()
        self._txt_epk.setReadOnly(True)
        self._txt_epk.setMaximumHeight(80)
        epk_lay.addWidget(self._txt_epk)
        root.addWidget(epk_box)

        # Validation status banner
        self._lbl_validation = QLabel()
        self._lbl_validation.setWordWrap(True)
        self._lbl_validation.setStyleSheet(
            f"color:{C_AMBER}; font-size:10px; padding:6px 8px; "
            f"background:{C_BG2}; border:1px solid {C_BORDER}; border-radius:3px;")
        self._lbl_validation.setText(
            "⚠  No ROM loaded — map offsets are PROVISIONAL until validated against a real .bin.  "
            "Do not write to any ECU until needle hits have been confirmed.")
        root.addWidget(self._lbl_validation)

        root.addStretch()

    def update(self, rom: ROMImage, ident, dpp: DPPValues,
               cksum_result, profile):
        self._lbl_pn.setText(ident.display_name or "Unknown ECU")
        self._lbl_profile.setText(profile.name if profile else "")

        self._f_pn.setText(ident.vmecuhn or "—")
        self._f_bosch.setText(ident.ssecuhn or "—")
        self._f_engine.setText(ident.engine_code or "—")
        self._f_size.setText(f"{rom.size_kb} KB")
        self._f_hw.setText(profile.ecu_hw if profile else "—")
        self._f_prof.setText(profile.name if profile else "Unknown")

        # Checksum
        if cksum_result.main_found:
            ok = cksum_result.main_ok
            self._f_cksum_main.setText("✓ OK" if ok else "✗ BAD")
            self._f_cksum_main.setStyleSheet(
                f"color:{'#3ddc84' if ok else '#ff5252'}; font-weight:bold;")
        else:
            self._f_cksum_main.setText("not found")
            self._f_cksum_main.setStyleSheet(f"color:{C_DIM};")

        multi_ok = cksum_result.multipoint_ok
        self._f_cksum_multi.setText(
            "✓ OK" if multi_ok and cksum_result.multipoint_found
            else ("not present" if not cksum_result.multipoint_found else "✗ BAD"))
        self._f_cksum_multi.setStyleSheet(
            f"color:{'#3ddc84' if multi_ok else '#ff5252'};")

        # DPP
        for attr, val in [("_f_dpp0", dpp.dpp0), ("_f_dpp1", dpp.dpp1),
                           ("_f_dpp2", dpp.dpp2), ("_f_dpp3", dpp.dpp3)]:
            lbl = getattr(self, attr)
            lbl.setText(f"0x{val:04X}" if dpp.found else "—")

        # Description
        desc_parts = [s for s in [ident.erotan, ident.epk] if s]
        self._txt_epk.setPlainText("\n".join(desc_parts) if desc_parts else "(none)")

        # Known ROM stock check
        import zlib
        crc = zlib.crc32(rom.data) & 0xFFFFFFFF
        known = lookup_rom(crc)
        if known:
            self._lbl_profile.setText(
                f"{profile.name if profile else ''}  ·  "
                f"<span style='color:#3ddc84'>✓ KNOWN STOCK</span>  ·  "
                f"{known.label}"
            )
        elif profile:
            self._lbl_profile.setText(profile.name)

        # Validation status
        if profile:
            maps = profile.make_maps(xdf_pn=ident.vmecuhn or None)
            n_confirmed   = sum(1 for m in maps if m.confidence == "CONFIRMED")
            n_provisional = sum(1 for m in maps if m.confidence == "PROVISIONAL")
            n_unconfirmed = sum(1 for m in maps if m.confidence == "UNCONFIRMED")
            total = len(maps)
            if n_confirmed == total and total > 0:
                self._lbl_validation.setText(
                    f"✓  All {total} maps have CONFIRMED offsets for this part number.")
                self._lbl_validation.setStyleSheet(
                    f"color:#3ddc84; font-size:10px; padding:6px 8px; "
                    f"background:{C_BG2}; border:1px solid {C_BORDER}; border-radius:3px;")
            elif n_confirmed > 0:
                self._lbl_validation.setText(
                    f"⚠  {n_confirmed}/{total} maps CONFIRMED · "
                    f"{n_provisional} PROVISIONAL · {n_unconfirmed} UNCONFIRMED  — "
                    "verify needle hits before writing.")
                self._lbl_validation.setStyleSheet(
                    f"color:{C_AMBER}; font-size:10px; padding:6px 8px; "
                    f"background:{C_BG2}; border:1px solid {C_BORDER}; border-radius:3px;")
            else:
                self._lbl_validation.setText(
                    f"⚠  Map offsets PROVISIONAL/UNCONFIRMED for this variant — "
                    "do not write to ECU until needle hits are confirmed against a real .bin.")
                self._lbl_validation.setStyleSheet(
                    f"color:{C_AMBER}; font-size:10px; padding:6px 8px; "
                    f"background:{C_BG2}; border:1px solid {C_BORDER}; border-radius:3px;")


# ── Patches panel ─────────────────────────────────────────────────────────────

class PatchesWidget(QWidget):
    """
    Click-box patch panel — one checkbox per PatchDef, grouped by category.
    Scalar patches show a numeric spinner instead.

    Signals are emitted on any change; the main window handles
    apply/revert and triggers checksum correction + save.
    """

    patch_toggled = pyqtSignal(object, bool)   # (PatchDef, apply=True/False)
    scalar_changed = pyqtSignal(object, float)  # (ScalarPatchDef, new_value)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rom: ROMImage | None = None
        self._searcher: Searcher | None = None
        self._profile = None
        self._checks: dict[str, QCheckBox] = {}
        self._spinners: dict[str, QDoubleSpinBox] = {}
        self._status_labels: dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        self._content_lay = QVBoxLayout(content)
        self._content_lay.setContentsMargins(16, 12, 16, 12)
        self._content_lay.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll)

        # Placeholder — real content populated in load_rom()
        self._placeholder = QLabel(
            "Load a ROM to detect available patches.\n\n"
            "Patches are discovered by C167 machine-code needle search\n"
            "and work across all ME7.x variants without hardcoded offsets.")
        self._placeholder.setStyleSheet(
            f"color:{C_DIM}; font-size:12px; padding:40px;")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._content_lay.addWidget(self._placeholder)
        self._content_lay.addStretch()

    def load_rom(self, rom: ROMImage, searcher: Searcher, profile=None):
        self._rom      = rom
        self._searcher = searcher
        self._profile  = profile
        self._checks.clear()
        self._spinners.clear()
        self._status_labels.clear()

        # Clear existing widgets
        while self._content_lay.count():
            item = self._content_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Run detection — pass profile for NOT_APPLICABLE filtering
        results = detect_all(rom, searcher, profile)
        result_map = {r.patch.name: r for r in results}

        # Group PatchDef by category
        categories: dict[str, list] = {}
        for patch in ALL_PATCHES:
            cat = patch.category.value if isinstance(patch.category, PatchCategory) else str(patch.category)
            categories.setdefault(cat, []).append(('toggle', patch))

        for scalar in ALL_SCALAR_PATCHES:
            cat = scalar.category.value if isinstance(scalar.category, PatchCategory) else str(scalar.category)
            categories.setdefault(cat, []).append(('scalar', scalar))

        for cat_name, items in sorted(categories.items()):
            box = QGroupBox(cat_name)
            box_lay = QVBoxLayout(box)
            box_lay.setSpacing(4)

            for kind, patch in items:
                row = QWidget()
                row_lay = QHBoxLayout(row)
                row_lay.setContentsMargins(4, 2, 4, 2)
                row_lay.setSpacing(8)

                if kind == 'toggle':
                    # Check platform applicability
                    if self._profile and not self._profile.patch_applies(patch):
                        # Grey-out row with NOT_APPLICABLE label
                        lbl_na = QLabel(f"{patch.name}  — not applicable for this ECU")
                        lbl_na.setStyleSheet(f"color:{C_DIM}; font-size:11px; padding:2px 6px;")
                        box_lay.addWidget(lbl_na)
                        continue

                    result = result_map.get(patch.name)
                    state  = result.state if result else PatchState.MISSING

                    cb = QCheckBox(patch.name)
                    cb.setEnabled(state != PatchState.MISSING)
                    cb.setChecked(state == PatchState.PATCHED)
                    cb.setToolTip(
                        f"{patch.description}\n\n"
                        f"Confidence: {patch.confidence}\n"
                        f"Category: {cat_name}"
                        + (f"\n\n⚠ {patch.warning}" if patch.warning else ""))

                    state_lbl = QLabel(self._state_text(state))
                    state_lbl.setStyleSheet(f"color:{self._state_colour(state)}; font-size:10px;")
                    state_lbl.setFixedWidth(70)

                    conf_lbl = QLabel(patch.confidence)
                    conf_lbl.setStyleSheet(
                        f"color:{self._conf_colour(patch.confidence)}; font-size:9px;")
                    conf_lbl.setFixedWidth(90)

                    cb.toggled.connect(lambda checked, p=patch: self.patch_toggled.emit(p, checked))
                    self._checks[patch.name]        = cb
                    self._status_labels[patch.name] = state_lbl

                    row_lay.addWidget(cb, 1)
                    row_lay.addWidget(conf_lbl)
                    row_lay.addWidget(state_lbl)

                else:  # scalar
                    if self._profile and not self._profile.patch_applies(patch):
                        lbl_na = QLabel(f"{patch.name}  — not applicable for this ECU")
                        lbl_na.setStyleSheet(f"color:{C_DIM}; font-size:11px; padding:2px 6px;")
                        box_lay.addWidget(lbl_na)
                        continue
                    lbl = QLabel(f"{patch.name}:")
                    lbl.setFixedWidth(180)
                    lbl.setToolTip(
                        f"{patch.description}\n\n"
                        f"Range: {patch.min_val}–{patch.max_val} {patch.unit}\n"
                        f"Confidence: {patch.confidence}")

                    current = patch.read(rom, searcher)
                    spin = QDoubleSpinBox()
                    spin.setRange(patch.min_val, patch.max_val)
                    spin.setSuffix(f"  {patch.unit}")
                    spin.setDecimals(0 if patch.scale >= 1.0 else 1)
                    spin.setSingleStep(max(1.0, patch.scale * 50))
                    if current is not None:
                        spin.setValue(current)
                        spin.setEnabled(True)
                    else:
                        spin.setEnabled(False)
                        spin.setToolTip("Needle not found in this ROM variant")

                    apply_btn = QPushButton("Apply")
                    apply_btn.setFixedWidth(60)
                    apply_btn.setStyleSheet(btn_style(C_AMBER))
                    apply_btn.setEnabled(current is not None)
                    apply_btn.clicked.connect(
                        lambda _, p=patch, sp=spin: self.scalar_changed.emit(p, sp.value()))

                    self._spinners[patch.name] = spin

                    row_lay.addWidget(lbl)
                    row_lay.addWidget(spin, 1)
                    row_lay.addWidget(apply_btn)

                box_lay.addWidget(row)

            self._content_lay.addWidget(box)

        self._content_lay.addStretch()

    def refresh_states(self):
        """Re-run detection and update checkbox states without rebuilding UI."""
        if not self._rom or not self._searcher:
            return
        results = detect_all(self._rom, self._searcher)
        for r in results:
            cb  = self._checks.get(r.patch.name)
            lbl = self._status_labels.get(r.patch.name)
            if cb:
                cb.blockSignals(True)
                cb.setChecked(r.state == PatchState.PATCHED)
                cb.setEnabled(r.state != PatchState.MISSING)
                cb.blockSignals(False)
            if lbl:
                lbl.setText(self._state_text(r.state))
                lbl.setStyleSheet(f"color:{self._state_colour(r.state)}; font-size:10px;")

    @staticmethod
    def _state_text(state: PatchState) -> str:
        return {
            PatchState.STOCK:          "stock",
            PatchState.PATCHED:        "✓ patched",
            PatchState.UNKNOWN:        "modified",
            PatchState.MISSING:        "not found",
            PatchState.NOT_APPLICABLE: "N/A",
        }.get(state, "?")

    @staticmethod
    def _state_colour(state: PatchState) -> str:
        return {
            PatchState.STOCK:          C_DIM,
            PatchState.PATCHED:        C_GREEN,
            PatchState.UNKNOWN:        C_AMBER,
            PatchState.MISSING:        C_DIM,
            PatchState.NOT_APPLICABLE: C_DIM,
        }.get(state, C_DIM)

    @staticmethod
    def _conf_colour(conf: str) -> str:
        return {
            "CONFIRMED":    C_GREEN,
            "PROVISIONAL":  C_AMBER,
            "UNCONFIRMED":  C_RED,
        }.get(conf, C_DIM)


# ── Maps panel ────────────────────────────────────────────────────────────────

class MapsWidget(QWidget):
    """Calibration map viewer/editor with stock diff highlighting."""

    map_written = pyqtSignal(str)   # emits map name when cells written to ROM

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rom:        ROMImage | None = None
        self._maps:       list = []
        self._cur_idx:    int  = -1
        self._stock_data: dict = {}   # map_name → List[List[float]] from stock ROM
        self._diff_mode:  bool = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Map selector bar ──────────────────────────────────────────────────
        bar = QWidget()
        bar.setStyleSheet(f"background:{C_BG2}; border-bottom:1px solid {C_BORDER};")
        bar.setFixedHeight(40)
        bar_lay = QHBoxLayout(bar)
        bar_lay.setContentsMargins(12, 0, 12, 0)
        bar_lay.setSpacing(6)
        bar_lay.addWidget(QLabel("Map:"))
        self._btn_group_w   = QWidget()
        self._btn_group_lay = QHBoxLayout(self._btn_group_w)
        self._btn_group_lay.setContentsMargins(0, 0, 0, 0)
        self._btn_group_lay.setSpacing(4)
        bar_lay.addWidget(self._btn_group_w)
        bar_lay.addStretch()

        # Diff mode toggle
        self._btn_diff = QPushButton("Diff: OFF")
        self._btn_diff.setCheckable(True)
        self._btn_diff.setStyleSheet(btn_style(C_DIM))
        self._btn_diff.setToolTip(
            "Toggle stock diff highlighting.\n"
            "Cells changed from stock baseline are highlighted in magenta.\n"
            "Requires a stock baseline to be loaded (auto-loaded for known stock ROMs).")
        self._btn_diff.clicked.connect(self._on_diff_toggle)
        bar_lay.addWidget(self._btn_diff)

        # Load baseline button
        self._btn_baseline = QPushButton("Load Baseline…")
        self._btn_baseline.setStyleSheet(btn_style(C_PURPLE))
        self._btn_baseline.setToolTip(
            "Load a known stock ROM as the diff baseline.\n"
            "Cells in the current ROM that differ from the baseline\n"
            "will be highlighted when Diff mode is ON.")
        self._btn_baseline.clicked.connect(self._on_load_baseline)
        bar_lay.addWidget(self._btn_baseline)

        self._btn_write = QPushButton("Write to ROM")
        self._btn_write.setStyleSheet(btn_style(C_AMBER))
        self._btn_write.setEnabled(False)
        self._btn_write.setToolTip(
            "Encode edited cell values and write them into the ROM buffer.\n"
            "Fix Checksums and Save to make the change permanent.")
        self._btn_write.clicked.connect(self._on_write_map)
        bar_lay.addWidget(self._btn_write)
        root.addWidget(bar)

        # ── Table ─────────────────────────────────────────────────────────────
        self._table = QTableWidget(0, 0)
        self._table.setEditTriggers(QTableWidget.DoubleClicked |
                                    QTableWidget.SelectedClicked)
        self._table.setSelectionBehavior(QTableWidget.SelectItems)
        self._table.itemChanged.connect(self._on_cell_changed)
        root.addWidget(self._table, 1)

        # ── Info bar ──────────────────────────────────────────────────────────
        info_bar = QWidget()
        info_bar.setStyleSheet(
            f"background:{C_BG3}; border-top:1px solid {C_BORDER};")
        info_bar.setFixedHeight(28)
        ib_lay = QHBoxLayout(info_bar)
        ib_lay.setContentsMargins(12, 0, 12, 0)
        self._lbl_map_info = QLabel("Load a ROM to view calibration maps")
        self._lbl_map_info.setStyleSheet(f"color:{C_DIM}; font-size:10px;")
        ib_lay.addWidget(self._lbl_map_info)
        self._lbl_dirty = QLabel("")
        self._lbl_dirty.setStyleSheet(f"color:{C_AMBER}; font-size:10px;")
        ib_lay.addWidget(self._lbl_dirty)
        root.addWidget(info_bar)

        self._map_buttons: list[QPushButton] = []
        self._pending_edits: dict[tuple, float] = {}  # (row,col) → new value

    def set_stock_baseline(self, rom: ROMImage, maps: list):
        """Snapshot map data from a stock ROM as the diff baseline."""
        self._stock_data.clear()
        for m in maps:
            data = m.read(rom)
            if data:
                self._stock_data[m.name] = data
        changed = len(self._stock_data)
        if changed:
            self._btn_diff.setStyleSheet(btn_style(C_PURPLE))
            self._btn_diff.setToolTip(
                f"Diff baseline set ({changed} maps).\n"
                "Magenta cells = changed from stock.")
        if self._cur_idx >= 0:
            self._show_map(self._cur_idx)

    def _on_diff_toggle(self, checked: bool):
        self._diff_mode = checked
        self._btn_diff.setText("Diff: ON" if checked else "Diff: OFF")
        self._btn_diff.setStyleSheet(
            btn_style(C_PURPLE) if checked else btn_style(C_DIM))
        if self._cur_idx >= 0:
            self._show_map(self._cur_idx)

    def _on_load_baseline(self):
        if not _HAS_QT:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load Stock Baseline ROM", "",
            "ROM files (*.bin *.ori *.org *.orig *.BIN *.ORI)")
        if not path:
            return
        try:
            baseline_rom = ROMImage.load(path)
            import sys as _sys
            _sys.path.insert(0, str(__file__))
            from meseventool.profiles import detect_profile
            from meseventool.ecu_id import identify
            from meseventool.dpp import extract_dpp
            ecu  = identify(baseline_rom)
            dpp  = extract_dpp(baseline_rom)
            prof = detect_profile(ecu, dpp)
            maps = prof.make_maps(ecu.vmecuhn or None)
            self.set_stock_baseline(baseline_rom, maps)
            # Auto-enable diff mode
            self._diff_mode = True
            self._btn_diff.setChecked(True)
            self._btn_diff.setText("Diff: ON")
            self._btn_diff.setStyleSheet(btn_style(C_PURPLE))
        except Exception as exc:
            QMessageBox.warning(self, "Baseline Error",
                                f"Could not load baseline:\n{exc}")

    def load_rom(self, rom: ROMImage, searcher: Searcher, maps: list):
        self._rom      = rom
        self._maps     = maps
        self._cur_idx  = -1
        self._pending_edits.clear()

        while self._btn_group_lay.count():
            item = self._btn_group_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._map_buttons.clear()

        for i, m in enumerate(maps):
            btn = QPushButton(m.name)
            btn.setCheckable(True)
            btn.setStyleSheet(btn_style(C_BLUE))
            btn.setToolTip(f"{m.description}\n\nConfidence: {m.confidence}")
            btn.clicked.connect(lambda _, idx=i: self._show_map(idx))
            self._map_buttons.append(btn)
            self._btn_group_lay.addWidget(btn)

        if maps:
            self._show_map(0)

    def _show_map(self, idx: int):
        if not self._maps or idx >= len(self._maps):
            return

        self._cur_idx = idx
        self._pending_edits.clear()
        self._lbl_dirty.setText("")
        self._btn_write.setEnabled(False)

        for i, btn in enumerate(self._map_buttons):
            btn.setChecked(i == idx)

        m   = self._maps[idx]
        rom = self._rom

        if m.data_addr == 0:
            self._table.blockSignals(True)
            self._table.setRowCount(1)
            self._table.setColumnCount(1)
            item = QTableWidgetItem(
                f"Address not yet located for {m.name}\n\n"
                "Drop a real ROM — needle search will resolve the offset.")
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(0, 0, item)
            self._table.blockSignals(False)
            self._lbl_map_info.setText(
                f"{m.name}  ·  {m.description}  ·  addr: pending ROM")
            return

        data = m.read(rom)
        if not data:
            self._table.blockSignals(True)
            self._table.setRowCount(1)
            self._table.setColumnCount(1)
            self._table.setItem(0, 0, QTableWidgetItem("No data"))
            self._table.blockSignals(False)
            return

        rows = len(data)
        cols = len(data[0]) if data else 0

        # Compute range for heatmap normalisation
        flat = [v for row in data for v in row]
        lo, hi = min(flat), max(flat)
        span = max(hi - lo, 1e-6)

        # Stock baseline for diff highlighting
        stock = self._stock_data.get(m.name) if self._diff_mode else None
        diff_count = 0

        self._table.blockSignals(True)
        self._table.setRowCount(rows)
        self._table.setColumnCount(cols)

        # ── Axis labels as headers ─────────────────────────────────────────────
        if m.x_values and len(m.x_values) == cols:
            x_ax = m.x_axis
            self._table.setHorizontalHeaderLabels(
                [f"{v:{x_ax.fmt.replace('{:.', '').replace('}','')}}" 
                 if hasattr(x_ax, 'fmt') else f"{v:.1f}"
                 for v in m.x_values])
        else:
            self._table.setHorizontalHeaderLabels([str(c) for c in range(cols)])

        if m.y_values and len(m.y_values) == rows:
            y_ax = m.y_axis
            self._table.setVerticalHeaderLabels(
                [f"{v:{y_ax.fmt.replace('{:.', '').replace('}','')}}"
                 if hasattr(y_ax, 'fmt') else f"{v:.1f}"
                 for v in m.y_values])
        else:
            self._table.setVerticalHeaderLabels([str(r) for r in range(rows)])

        self._table.horizontalHeader().setStyleSheet(
            f"QHeaderView::section {{ background:{C_BG3}; color:{C_DIM}; "
            f"font-size:9px; padding:2px; border:1px solid {C_BORDER}; }}")
        self._table.verticalHeader().setStyleSheet(
            f"QHeaderView::section {{ background:{C_BG3}; color:{C_DIM}; "
            f"font-size:9px; padding:2px; border:1px solid {C_BORDER}; }}")
        self._table.verticalHeader().setFixedWidth(48)

        for r, row in enumerate(data):
            for c, val in enumerate(row):
                item = QTableWidgetItem(f"{val:.2f}")
                item.setTextAlignment(Qt.AlignCenter)
                t = (val - lo) / span   # 0→1
                if t < 0.5:
                    bg = QColor(
                        int(20 + 10 * t),
                        int(40 + 160 * (t * 2)),
                        int(80 - 60 * (t * 2)),
                    )
                else:
                    bg = QColor(
                        int(20 + 200 * ((t - 0.5) * 2)),
                        int(200 - 160 * ((t - 0.5) * 2)),
                        20,
                    )

                # Diff overlay — magenta border/tint for cells changed from stock
                is_diff = False
                if stock and r < len(stock) and c < len(stock[r]):
                    stock_val = stock[r][c]
                    if abs(val - stock_val) > 1e-4:
                        is_diff = True
                        diff_count += 1
                        # Blend towards magenta: darken bg and add pink cast
                        bg = QColor(
                            min(255, bg.red()   + 80),
                            max(0,   bg.green() - 40),
                            min(255, bg.blue()  + 80),
                        )
                        delta = val - stock_val
                        item.setToolTip(
                            f"Stock: {stock_val:.2f}  Current: {val:.2f}  "
                            f"Δ {delta:+.2f}")

                item.setBackground(bg)
                lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
                item.setForeground(QColor("#e8eaf0" if lum < 100 else "#0d0d0f"))
                self._table.setItem(r, c, item)

        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.blockSignals(False)

        conf_colour = {"CONFIRMED": C_GREEN, "PROVISIONAL": C_AMBER}.get(
            m.confidence, C_RED)
        diff_txt = ""
        if stock is not None:
            diff_txt = (f"  ·  <span style='color:{C_PURPLE}'>"
                        f"Δ {diff_count} cell(s) from stock</span>")
        elif self._diff_mode and m.name not in self._stock_data:
            diff_txt = f"  ·  <span style='color:{C_DIM}'>no baseline for {m.name}</span>"

        self._lbl_map_info.setText(
            f"{m.name}  ·  {rows}×{cols}  ·  "
            f"range: {lo:.2f} – {hi:.2f}  ·  "
            f"addr: <span style='color:{C_BLUE}'>0x{m.data_addr:06X}</span>  ·  "
            f"<span style='color:{conf_colour}'>{m.confidence}</span>"
            f"{diff_txt}")

    def _on_cell_changed(self, item: QTableWidgetItem):
        """Track edited cells — don't write until user clicks Write to ROM."""
        try:
            val = float(item.text())
        except ValueError:
            return
        self._pending_edits[(item.row(), item.column())] = val
        item.setForeground(QColor(C_AMBER))
        self._lbl_dirty.setText(f"  {len(self._pending_edits)} cell(s) edited")
        self._btn_write.setEnabled(True)

    def _on_write_map(self):
        """Encode all pending edits and write them into the ROM buffer."""
        if not self._rom or self._cur_idx < 0 or not self._pending_edits:
            return

        m = self._maps[self._cur_idx]
        if m.data_addr == 0:
            return

        # Re-read current map data, apply pending edits, write back
        data = m.read(self._rom)
        if not data:
            return

        for (r, c), val in self._pending_edits.items():
            if r < len(data) and c < len(data[r]):
                data[r][c] = val

        m.write(self._rom, data)

        # Clear pending state, recolour cells to default
        self._pending_edits.clear()
        self._lbl_dirty.setText("")
        self._btn_write.setEnabled(False)

        self._table.blockSignals(True)
        for r in range(self._table.rowCount()):
            for c in range(self._table.columnCount()):
                item = self._table.item(r, c)
                if item:
                    item.setForeground(QColor(C_FG))
        self._table.blockSignals(False)

        self.map_written.emit(m.name)


# ── Main window ───────────────────────────────────────────────────────────────

class MESevenWindow(QMainWindow):
    """Main application window."""

    def __init__(self, rom_path: str = ""):
        super().__init__()
        self._rom:     ROMImage | None = None
        self._searcher: Searcher | None = None
        self._dpp:     DPPValues = DPPValues()
        self._dirty:   bool = False

        self.setWindowTitle(f"MESevenTool  v{__version__}")
        self.resize(1100, 760)
        self.setStyleSheet(_BASE_STYLE)

        # ── KWPBridge live overlay (optional) ─────────────────────────────────
        from meseventool.kwp import (KWPMonitor, LiveValues,
                                     kwpbridge_available, kwpbridge_running,
                                     status_label as kwp_status_label,
                                     live_summary as kwp_live_summary)
        self._KWPMonitor        = KWPMonitor
        self._kwpbridge_avail   = kwpbridge_available
        self._kwpbridge_running = kwpbridge_running
        self._kwp_status_label  = kwp_status_label
        self._kwp_live_summary  = kwp_live_summary
        self._kwp_monitor       = KWPMonitor(self)
        self._kwp_matched       = False
        self._kwp_monitor.connected.connect(self._on_kwp_connected)
        self._kwp_monitor.disconnected.connect(self._on_kwp_disconnected)
        self._kwp_monitor.live_data.connect(self._on_kwp_live_data)
        self._kwp_monitor.mismatch.connect(self._on_kwp_mismatch)

        self._setup_ui()
        self._build_menu()
        self._connect_signals()

        if rom_path and os.path.exists(rom_path):
            self._load_rom(rom_path)

        if rom_path and os.path.exists(rom_path):
            self._load_rom(rom_path)

    def _build_menu(self):
        mb = self.menuBar()
        mb.setStyleSheet(
            f"QMenuBar {{ background:{C_BG2}; color:{C_FG}; }}"
            f"QMenuBar::item:selected {{ background:{C_BG3}; }}"
            f"QMenu {{ background:{C_BG2}; color:{C_FG}; border:1px solid {C_BORDER}; }}"
            f"QMenu::item:selected {{ background:{C_BG3}; }}")

        # ── File ─────────────────────────────────────────────────────────────
        fm = mb.addMenu("File")
        for label, shortcut, slot in [
            ("Open ROM…",   "Ctrl+O",       self._on_open),
            ("Save ROM",    "Ctrl+S",       self._on_save),
            ("Save As…",    "Ctrl+Shift+S", self._on_save_as),
        ]:
            a = QAction(label, self)
            a.setShortcut(shortcut)
            a.triggered.connect(slot)
            fm.addAction(a)
        fm.addSeparator()
        a = QAction("Fix Checksums", self)
        a.setShortcut("Ctrl+F")
        a.triggered.connect(self._on_fix_checksums)
        fm.addAction(a)
        fm.addSeparator()
        fm.addAction("Quit", self.close)

        # ── Tools ─────────────────────────────────────────────────────────────
        tm = mb.addMenu("Tools")

        self._act_kwp_status = QAction("KWPBridge: not running", self)
        self._act_kwp_status.setEnabled(False)
        tm.addAction(self._act_kwp_status)

        tm.addSeparator()

        a = QAction("Live Data Connection…", self)
        a.setShortcut("Ctrl+K")
        a.triggered.connect(self._show_kwp_dialog)
        tm.addAction(a)

        self._kwp_menu_timer = QTimer(self)
        self._kwp_menu_timer.timeout.connect(self._refresh_kwp_menu_label)
        self._kwp_menu_timer.start(2000)

        # ── Help ─────────────────────────────────────────────────────────────
        hm = mb.addMenu("Help")
        hm.addAction("About MESevenTool", self._on_about)

    def _on_about(self):
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.about(self, "MESevenTool",
                          f"<b>MESevenTool</b>  v{__version__}<br><br>"
                          "Bosch ME7.x ROM editor for VAG 1.8T / 2.0T engines.<br>"
                          "06A-906-032 (AWP/AUM/AUQ/BAM) and related families.<br><br>"
                          "Needle-based map discovery — works across all ME7.x variants.")

    def _refresh_kwp_menu_label(self):
        if not hasattr(self, '_act_kwp_status'):
            return
        if not self._kwpbridge_avail():
            self._act_kwp_status.setText("KWPBridge: not installed")
        elif self._kwpbridge_running():
            pn = self._kwp_monitor.current_pn()
            if pn:
                self._act_kwp_status.setText(f"KWPBridge: connected  ·  {pn}")
            else:
                self._act_kwp_status.setText("KWPBridge: running — no ECU")
        else:
            self._act_kwp_status.setText("KWPBridge: not running")

    def _show_kwp_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Live Data — KWPBridge Connection")
        dlg.setMinimumWidth(440)
        dlg.setStyleSheet(f"background:{C_BG2}; color:{C_FG};")
        lay = QVBoxLayout(dlg)
        lay.setSpacing(12)

        if not self._kwpbridge_avail():
            dot, body = "⚫", (
                "<b>KWPBridge is not installed.</b><br><br>"
                "MESevenTool works fully standalone without it.<br><br>"
                "KWPBridge adds optional live ECU data overlay:<br>"
                "• Real-time RPM, load, coolant on map tabs<br>"
                "• Lambda and ignition timing overlaid on cells<br>"
                "• Part-number safety gate before writes<br><br>"
                "Run KWPBridge alongside MESevenTool and connect<br>"
                "a KL-line interface.")
        elif self._kwpbridge_running():
            pn = self._kwp_monitor.current_pn()
            rom_pn = ""
            if self._rom:
                from meseventool.ecu_id import identify
                ident = identify(self._rom)
                rom_pn = ident.vmecuhn or ""
            if pn:
                dot  = "🟢" if self._kwp_matched else "🟡"
                if self._kwp_matched:
                    body = (f"<b>KWPBridge connected.</b><br><br>"
                            f"ECU: <b>{pn}</b><br>"
                            "ECU matches loaded ROM — live overlay active.")
                else:
                    body = (f"<b>KWPBridge connected.</b><br><br>"
                            f"ECU: <b>{pn}</b><br>"
                            f"ROM: <b>{rom_pn or '(none loaded)'}</b><br>"
                            "Load the matching ROM to enable overlay.")
            else:
                dot  = "🟡"
                body = ("<b>KWPBridge running — no ECU detected.</b><br><br>"
                        "Connect KL-line interface and turn ignition on.")
        else:
            dot  = "🔴"
            body = ("<b>KWPBridge is installed but not running.</b><br><br>"
                    "MESevenTool is fully operational without it.<br><br>"
                    "Start KWPBridge to enable live data overlay.<br>"
                    "Auto-detected within 2 seconds of starting.")

        icon = QLabel(dot)
        icon.setStyleSheet("font-size: 28px;")
        msg = QLabel(body)
        msg.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(icon)
        row.addWidget(msg, 1)
        w = QWidget()
        w.setLayout(row)
        lay.addWidget(w)
        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(dlg.accept)
        lay.addWidget(bb)
        dlg.exec_()

    # ── KWPBridge live data handlers ──────────────────────────────────────────

    def _on_kwp_connected(self, ecu_pn: str):
        self._kwp_matched = self._kwp_monitor.is_matched()
        self._refresh_kwp_menu_label()
        if self._kwp_matched:
            self._set_status(
                f"KWPBridge connected  ·  {ecu_pn}  ·  ECU matches ROM  ·  live overlay active")
        else:
            self._set_status(
                f"KWPBridge connected  ·  {ecu_pn}  ·  load matching ROM to enable overlay")

    def _on_kwp_disconnected(self):
        self._kwp_matched = False
        self._refresh_kwp_menu_label()
        self._set_status("KWPBridge disconnected")

    def _on_kwp_mismatch(self, ecu_pn: str, rom_pn: str):
        self._kwp_matched = False
        self._refresh_kwp_menu_label()

    def _on_kwp_live_data(self, lv):
        summary = self._kwp_live_summary(lv)
        if summary and self._kwp_matched:
            self._set_status(f"🟢  {self._kwp_monitor.current_pn()}  ·  {summary}")
        self._refresh_kwp_menu_label()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ─────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(
            f"background:{C_BG2}; border-bottom:1px solid {C_BORDER};")
        toolbar.setFixedHeight(46)
        tb_lay = QHBoxLayout(toolbar)
        tb_lay.setContentsMargins(12, 0, 12, 0)
        tb_lay.setSpacing(8)

        self.btn_open = QPushButton("Open ROM…")
        self.btn_open.setStyleSheet(btn_style(C_BLUE))
        tb_lay.addWidget(self.btn_open)

        self.btn_save = QPushButton("Save ROM")
        self.btn_save.setStyleSheet(btn_style(C_GREEN))
        self.btn_save.setEnabled(False)
        tb_lay.addWidget(self.btn_save)

        self.btn_save_as = QPushButton("Save As…")
        self.btn_save_as.setStyleSheet(btn_style(C_GREEN))
        self.btn_save_as.setEnabled(False)
        tb_lay.addWidget(self.btn_save_as)

        sep = QFrame(); sep.setFrameShape(QFrame.VLine)
        sep.setStyleSheet(f"color:{C_BORDER};")
        tb_lay.addWidget(sep)

        self.btn_fix_checksums = QPushButton("Fix Checksums")
        self.btn_fix_checksums.setStyleSheet(btn_style(C_AMBER))
        self.btn_fix_checksums.setEnabled(False)
        self.btn_fix_checksums.setToolTip(
            "Recompute and write all ME7 checksums (main + multipoint CRC32).\n"
            "Must be done after any ROM modification before flashing.")
        tb_lay.addWidget(self.btn_fix_checksums)

        tb_lay.addStretch()

        self._lbl_rom_path = QLabel("No ROM loaded")
        self._lbl_rom_path.setStyleSheet(f"color:{C_DIM}; font-size:10px;")
        tb_lay.addWidget(self._lbl_rom_path)

        root.addWidget(toolbar)

        # ── Tab panel ────────────────────────────────────────────────────────
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)

        self._w_info    = ROMInfoWidget()
        self._w_patches = PatchesWidget()
        self._w_maps    = MapsWidget()

        self._tabs.addTab(self._w_info,    "ROM Info")
        self._tabs.addTab(self._w_patches, "Patches")
        self._tabs.addTab(self._w_maps,    "Maps")

        root.addWidget(self._tabs, 1)

        # ── Status bar ───────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._set_status("Ready — open a ROM to begin")

    def _connect_signals(self):
        self.btn_open.clicked.connect(self._on_open)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_save_as.clicked.connect(self._on_save_as)
        self.btn_fix_checksums.clicked.connect(self._on_fix_checksums)
        self._w_patches.patch_toggled.connect(self._on_patch_toggled)
        self._w_patches.scalar_changed.connect(self._on_scalar_changed)
        self._w_maps.map_written.connect(self._on_map_written)

    def _on_map_written(self, map_name: str):
        self._dirty = True
        self._set_status(
            f"Map '{map_name}' written to buffer  —  "
            "Fix Checksums then Save before flashing")

    # ── File I/O ──────────────────────────────────────────────────────────────

    def _on_open(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open ME7 ROM", "", "ROM files (*.bin *.rom);;All (*)")
        if path:
            self._load_rom(path)

    def _load_rom(self, path: str):
        try:
            rom = ROMImage.load(path)
        except Exception as e:
            QMessageBox.critical(self, "Load Error", str(e))
            return

        self._rom      = rom
        self._searcher = Searcher(rom)
        self._dirty    = False

        # DPP extraction
        ex = DPPExtractor(self._searcher)
        if self._searcher.find_dppx():
            pass
        self._dpp = ex.extract()

        # ECU identification
        ident = identify(rom)

        # Checksum verification
        cs_mgr  = ChecksumManager(rom)
        cs_result = cs_mgr.verify()

        # Profile detection
        profile = detect_profile(ident, self._dpp)

        # Maps — use confirmed XDF offsets if we know the exact part number
        xdf_pn = ident.vmecuhn or None
        maps = profile.make_maps(xdf_pn=xdf_pn)

        # Update UI panels
        self._w_info.update(rom, ident, self._dpp, cs_result, profile)
        self._w_patches.load_rom(rom, self._searcher, profile)
        self._w_maps.load_rom(rom, self._searcher, maps)

        # Auto-set stock baseline when loading a confirmed stock ROM
        # (diff mode highlights changes vs the factory calibration)
        import zlib as _zlib
        _crc = _zlib.crc32(rom.data) & 0xFFFFFFFF
        if is_known_stock(_crc):
            self._w_maps.set_stock_baseline(rom, maps)

        # Tell KWP monitor which part numbers are valid for this ROM
        pns = [ident.vmecuhn] if ident.vmecuhn else []
        if ident.ssecuhn and ident.ssecuhn not in pns:
            pns.append(ident.ssecuhn)
        self._kwp_monitor.set_rom_part_numbers(pns)
        self._refresh_kwp_menu_label()

        # Toolbar state
        self.btn_save.setEnabled(True)
        self.btn_save_as.setEnabled(True)
        self.btn_fix_checksums.setEnabled(True)

        name = Path(path).name
        self._lbl_rom_path.setText(name)
        self.setWindowTitle(f"MESevenTool  v{__version__}  —  {name}")

        cs_txt = "✓ checksums OK" if cs_result.all_ok else "⚠ checksum FAIL"
        self._set_status(
            f"Loaded {name}  ·  {rom.size_kb} KB  ·  "
            f"{ident.display_name}  ·  {cs_txt}")

    def _on_save(self):
        if not self._rom or not self._rom.path:
            self._on_save_as()
            return
        try:
            self._rom.save()
            self._dirty = False
            self._set_status(f"Saved  {self._rom.path}")
        except Exception as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _on_save_as(self):
        if not self._rom:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save ROM As",
            self._rom.path or "", "ROM files (*.bin);;All (*)")
        if path:
            try:
                self._rom.save_as(path)
                self._dirty = False
                self._set_status(f"Saved  {path}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", str(e))

    # ── Checksum fix ─────────────────────────────────────────────────────────

    def _on_fix_checksums(self):
        if not self._rom:
            return
        cs = ChecksumManager(self._rom)
        result = cs.fix()
        self._dirty = True
        ok_txt = "✓ all checksums corrected" if result.all_ok else "⚠ partial"
        self._set_status(f"Fix checksums: {ok_txt}")
        QMessageBox.information(self, "Checksums Fixed",
                                result.summary())
        # Refresh info panel
        ident   = identify(self._rom)
        profile = detect_profile(ident, self._dpp)
        self._w_info.update(self._rom, ident, self._dpp, result, profile)

    # ── Patch handlers ────────────────────────────────────────────────────────

    def _on_patch_toggled(self, patch: PatchDef, apply: bool):
        if not self._rom or not self._searcher:
            return
        result = patch.detect(self._rom, self._searcher)
        ok = patch.apply(self._rom, result) if apply else patch.revert(self._rom, result)
        if ok:
            self._dirty = True
            action = "applied" if apply else "reverted"
            self._set_status(f"Patch '{patch.name}' {action}  —  fix checksums before saving")
            self._w_patches.refresh_states()
        else:
            self._set_status(f"Patch '{patch.name}' failed — needle not found in this variant")

    def _on_scalar_changed(self, patch: ScalarPatchDef, value: float):
        if not self._rom or not self._searcher:
            return
        ok = patch.write(self._rom, value, self._searcher)
        if ok:
            self._dirty = True
            self._set_status(
                f"Scalar '{patch.name}' → {value:.1f} {patch.unit}  "
                "—  fix checksums before saving")
        else:
            self._set_status(f"Scalar '{patch.name}' write failed — out of range or needle missing")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _set_status(self, msg: str):
        self._status.showMessage(msg)

    def closeEvent(self, event):
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "ROM has unsaved modifications. Save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Save:
                self._on_save()
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        event.accept()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    if not _HAS_QT:
        print("PyQt5 not installed. Run: pip install PyQt5")
        sys.exit(1)

    app = QApplication(sys.argv)
    app.setApplicationName("MESevenTool")
    app.setApplicationVersion(__version__)

    rom_path = sys.argv[1] if len(sys.argv) > 1 else ""
    win = MESevenWindow(rom_path)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
