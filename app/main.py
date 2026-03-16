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
        QTextEdit, QGridLayout, QMessageBox,
    )
    from PyQt5.QtCore import Qt, pyqtSignal
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
    """Calibration map viewer/editor — editable tables for each map."""

    map_written = pyqtSignal(str)   # emits map name when cells written to ROM

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rom:     ROMImage | None = None
        self._maps:    list = []
        self._cur_idx: int  = -1
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

        self._table.blockSignals(True)
        self._table.setRowCount(rows)
        self._table.setColumnCount(cols)

        for r, row in enumerate(data):
            for c, val in enumerate(row):
                item = QTableWidgetItem(f"{val:.2f}")
                item.setTextAlignment(Qt.AlignCenter)
                self._table.setItem(r, c, item)

        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.blockSignals(False)

        conf_colour = {"CONFIRMED": C_GREEN, "PROVISIONAL": C_AMBER}.get(
            m.confidence, C_RED)
        self._lbl_map_info.setText(
            f"{m.name}  ·  {m.description}  ·  "
            f"addr: <span style='color:{C_BLUE}'>0x{m.data_addr:06X}</span>  ·  "
            f"<span style='color:{conf_colour}'>{m.confidence}</span>")

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

        self._setup_ui()
        self._connect_signals()

        if rom_path and os.path.exists(rom_path):
            self._load_rom(rom_path)

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
