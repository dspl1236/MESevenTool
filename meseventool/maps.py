"""
meseventool/maps.py
===================
MapDef, AxisDef, MapFinder — map table definitions and needle-based discovery.

Bosch ME7 nomenclature:
  KF  = Kennfeld (2D map)   KL = Kennlinie (1D curve)
  ZW  = Zündwinkel (ignition timing)
  KC  = Kraftstoff (fuel)
  LDR = Ladedruckregler (boost pressure controller)
  MLHFM = MAF linearisation
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .rom import ROMImage
from .needle import Searcher

# ── Data widths ────────────────────────────────────────────────────────────────
U8  =  1
S8  = -1
U16 =  2
S16 = -2

# ── Standard decode/encode functions ──────────────────────────────────────────
def _rpm(raw: int) -> float:    return raw * 0.75
def _deg(raw: int) -> float:    return raw * 0.75
def _pct(raw: int) -> float:    return raw / 2.55
def _lambda(raw: int) -> float: return raw / 32768.0
def _raw(raw: int) -> float:    return float(raw)

def _enc_rpm(v): return int(round(v / 0.75))
def _enc_deg(v): return int(round(v / 0.75))
def _enc_pct(v): return int(round(v * 2.55))
def _enc_lambda(v): return int(round(v * 32768.0))
def _enc_raw(v): return int(round(v))


@dataclass
class AxisDef:
    """One axis of a map (RPM, load, etc.)."""
    name:    str   = ""
    unit:    str   = ""
    scale:   float = 1.0     # physical = raw * scale
    offset:  float = 0.0
    fmt:     str   = "{:.1f}"

    def decode(self, raw: int) -> float:
        return raw * self.scale + self.offset

    def encode(self, phys: float) -> int:
        return round((phys - self.offset) / self.scale)


# Standard shared axes
AXIS_RPM      = AxisDef(name="RPM",       unit="rpm",    scale=40.0,       fmt="{:.0f}")
AXIS_LOAD     = AxisDef(name="Load",      unit="g/rev",  scale=0.001,      fmt="{:.3f}")
AXIS_IGN_DEG  = AxisDef(name="Ignition",  unit="°BTDC",  scale=0.5,        fmt="{:.1f}")
AXIS_BOOST    = AxisDef(name="N75 Duty",  unit="%",      scale=1.0/2.55,   fmt="{:.1f}")
AXIS_LAMBDA   = AxisDef(name="Lambda",    unit="λ",      scale=1.0/128.0,  fmt="{:.3f}")


@dataclass
class MapDef:
    """
    Definition of a single calibration map.

    data_addr = 0 means 'not yet located' — read() returns [].

    x_values / y_values: optional pre-computed axis breakpoints in physical units.
    When set, the UI uses them as column/row header labels instead of indices.
    They are embedded as constants for well-characterised maps (e.g. KFZW 1.8T),
    since reading axis breakpoints from ROM requires DPP-aware addressing.
    """
    name:        str
    description: str  = ""
    rows:        int  = 0       # y-axis count
    cols:        int  = 0       # x-axis count
    data_width:  int  = U8      # cell element size in bytes (U8 or U16)
    data_addr:   int  = 0       # file offset of cell data (0 = unknown)
    x_axis_addr: int  = 0       # file offset of x-axis values
    y_axis_addr: int  = 0       # file offset of y-axis values
    x_axis:      AxisDef = field(default_factory=lambda: AXIS_RPM)
    y_axis:      AxisDef = field(default_factory=lambda: AXIS_LOAD)
    x_values:    Optional[list] = None   # pre-computed x-axis breakpoints (physical)
    y_values:    Optional[list] = None   # pre-computed y-axis breakpoints (physical)
    decode:      Optional[Callable] = None   # raw → physical
    encode:      Optional[Callable] = None   # physical → raw
    confidence:  str = "UNCONFIRMED"         # CONFIRMED | PROVISIONAL | UNCONFIRMED
    map_type:    str = "2d"                  # "2d" | "1d" | "raw"
    notes:       str = ""

    @property
    def size(self) -> int:
        """Total byte size of cell data: rows × cols × |data_width|."""
        return self.rows * self.cols * abs(self.data_width)

    def read(self, rom: ROMImage) -> List[List[float]]:
        """Read and decode cell data. Returns [] if data_addr == 0."""
        if self.data_addr == 0 or self.rows == 0 or self.cols == 0:
            return []
        width = abs(self.data_width)
        rows  = []
        dec   = self.decode or (lambda x: float(x))
        for r in range(self.rows):
            row = []
            for c in range(self.cols):
                off = self.data_addr + (r * self.cols + c) * width
                if off + width > rom.size:
                    row.append(0.0)
                    continue
                # C167 is little-endian — always read LE regardless of sign
                raw = int.from_bytes(rom.data[off:off+width],
                                     'little',
                                     signed=(self.data_width < 0))
                row.append(dec(raw))
            rows.append(row)
        return rows

    def write(self, rom: ROMImage, values: List[List[float]]) -> None:
        """Encode and write physical values back to the ROM."""
        if self.data_addr == 0:
            return
        width  = abs(self.data_width)
        signed = self.data_width < 0
        enc    = self.encode or (lambda x: int(round(x)))
        bits   = width * 8
        if signed:
            lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
        else:
            lo, hi = 0, (1 << bits) - 1
        for r, row in enumerate(values):
            for c, v in enumerate(row):
                off = self.data_addr + (r * self.cols + c) * width
                raw = max(lo, min(hi, enc(v)))
                # C167 is little-endian — always write LE
                rom.data[off:off+width] = raw.to_bytes(width, byteorder='little',
                                                        signed=signed)


class MapFinder:
    """
    Discovers map locations in a ROM using needle search.
    Ported from kfzw.c / table_spec.c (me7romtool, MIT).
    """

    def __init__(self, rom: ROMImage, searcher: Searcher):
        self.rom     = rom
        self.searcher = searcher

    def find_kfzw(self) -> int:
        """Return file offset of KFZW ignition map, 0 if not found."""
        from .needle import NEEDLE_ZWGRU, MASK_ZWGRU
        hit = self.searcher.search_one(NEEDLE_ZWGRU, MASK_ZWGRU)
        if hit is None:
            return 0
        offset = hit.get_u16_le(6)   # KFZW data offset from ZWGRU needle
        return self.searcher.dpp1_to_file(offset)

    def find_mlhfm(self) -> int:
        """Return file offset of MLHFM MAF linearisation table, 0 if not found."""
        from .needle import NEEDLE_MLHFM, MASK_MLHFM
        hit = self.searcher.search_one(NEEDLE_MLHFM, MASK_MLHFM)
        if hit is None:
            return 0
        seg    = hit.get_u16_le(2)
        offset = hit.get_u16_le(6)
        return self.searcher.extp_to_file(seg, offset)


def make_awp_maps(part_number: str = "") -> List[MapDef]:
    """
    Return MapDef list for ME7.5 1.8T (AWP/AWW/AWD/AUM/AUQ family).

    Addresses marked CONFIRMED are validated against 06A906032DL XDF
    (from reference/xdf_tables.json).  All addresses are flat file offsets
    into the full 1MB ROM.  Other variants in the family have nearby offsets
    discoverable by the needle search in MapFinder.

    Key maps for tuning:
      KFZW   — ignition advance (the primary timing map)
      MLHFM  — MAF linearisation (changes effective load at any given voltage)
      KFLBTS — lambda target (stoich/rich targets vs RPM×Load)
      LAMFA  — lambda adaptation (learned long-term trims)
      KFMIRL — torque model (throttle-to-load mapping)
    """
    # Confirmed offsets for 06A906032DL (1MB full ROM)
    # Source: reference/xdf_tables.json
    _DL = {
        'KFZW':    (0x0120DD, 12, 16, S8,  lambda x: x * 0.75,       lambda x: int(round(x / 0.75))),
        'MLHFM':   (0x014574, 1,  512, U16, lambda x: x * 0.1,        lambda x: int(round(x / 0.1))),
        'KFMIRL':  (0x0150B6, 16, 16, U16, lambda x: x * 0.023438,   lambda x: int(round(x / 0.023438))),
        'KFMIOP':  (0x01656E, 16, 11, U16, lambda x: x * 0.001526,   lambda x: int(round(x / 0.001526))),
        'KFLBTS':  (0x0192A5, 12, 16, U16, lambda x: x * 0.007813,   lambda x: int(round(x / 0.007813))),
        'KFDLULS': (0x01EB91, 8,  8,  U16, lambda x: x * 5.0,        lambda x: int(round(x / 5.0))),
        'LAMFA':   (0x01C95A, 15, 6,  U16, lambda x: x * 0.007813,   lambda x: int(round(x / 0.007813))),
    }
    conf = "CONFIRMED" if (not part_number or part_number.startswith("06A906032")) else "PROVISIONAL"

    # ── Standard ME7 1.8T axis breakpoints (common across AWP/AWW/AWD/AUM family) ──
    # Source: WinOLS/Nefmoto/s4wiki community, validated against DL ROM readings
    # RPM axis — 12 breakpoints matching KFZW rows (in RPM)
    _RPM12 = [800, 1200, 1600, 2000, 2400, 2800, 3200, 3600, 4000, 4400, 4800, 5200]
    # RPM axis — 16 breakpoints matching KFMIRL/KFLBTS cols
    _RPM16 = [600, 800, 1200, 1600, 2000, 2400, 2800, 3200, 3600, 4000, 4400, 4800,
              5200, 5600, 6000, 6400]
    # Load axis — 16 breakpoints (relative air mass, 0.0–1.5 g/stroke approx)
    _LOAD16 = [0.00, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70,
               0.80, 0.90, 1.00, 1.10, 1.20, 1.30, 1.40, 1.50]
    # Lambda axis — 6 RPM breakpoints for LAMFA
    _LAMFA_RPM6  = [800, 1600, 2400, 3200, 4000, 5200]
    # Lambda load — 15 breakpoints for LAMFA rows
    _LAMFA_LOAD15 = [0.00, 0.08, 0.15, 0.23, 0.30, 0.38, 0.45, 0.53,
                     0.60, 0.68, 0.75, 0.83, 0.90, 1.00, 1.10]

    return [
        # ── Ignition ──────────────────────────────────────────────────────────
        MapDef(
            name="KFZW",
            description="Ignition timing base map — °BTDC vs RPM × air mass load. "
                        "Primary ignition advance map. Scale: raw × 0.75 = °BTDC. "
                        "Positive = BTDC (advance), negative = ATDC (retard).",
            rows=12, cols=16,
            data_width=S8,
            data_addr=_DL['KFZW'][0],
            decode=_DL['KFZW'][4],
            encode=_DL['KFZW'][5],
            x_axis=AxisDef(name="Load", unit="g/rev", scale=0.1),
            y_axis=AxisDef(name="RPM",  unit="rpm",   scale=40.0, fmt="{:.0f}"),
            x_values=_LOAD16,
            y_values=_RPM12,
            confidence=conf,
            notes="Address 0x0120DD confirmed for 06A906032DL. "
                  "Other variants: use MapFinder.find_kfzw() for runtime discovery.",
        ),
        # ── MAF ───────────────────────────────────────────────────────────────
        MapDef(
            name="MLHFM",
            description="MAF linearisation — maps HFM voltage counts to kg/h air mass. "
                        "512-element U16 curve. Modifying this changes load at all points. "
                        "Required recalibration after MAF housing swaps or air filter mods.",
            rows=1, cols=512,
            data_width=U16,
            data_addr=_DL['MLHFM'][0],
            decode=_DL['MLHFM'][4],
            encode=_DL['MLHFM'][5],
            x_axis=AxisDef(name="HFM count", unit="counts", scale=1.0),
            y_axis=AxisDef(name="Air flow",  unit="kg/h",   scale=0.1),
            confidence=conf,
            map_type="1d",
            notes="512×u16. Address 0x014574 confirmed for 06A906032DL.",
        ),
        # ── Torque model ──────────────────────────────────────────────────────
        MapDef(
            name="KFMIRL",
            description="Requested torque — maps throttle position to % load request. "
                        "16×16 U16, scale × 0.023438 = %. Key map for throttle response.",
            rows=16, cols=16,
            data_width=U16,
            data_addr=_DL['KFMIRL'][0],
            decode=_DL['KFMIRL'][4],
            encode=_DL['KFMIRL'][5],
            x_axis=AxisDef(name="RPM",  unit="rpm",   scale=40.0, fmt="{:.0f}"),
            y_axis=AxisDef(name="Load", unit="g/rev", scale=0.1),
            x_values=_RPM16,
            y_values=_LOAD16,
            confidence=conf,
            notes="Address 0x0150B6 confirmed for 06A906032DL.",
        ),
        MapDef(
            name="KFMIOP",
            description="Optimal engine torque — maximum achievable torque vs RPM×load. "
                        "Used by torque coordinator to limit request. 16×11 U16.",
            rows=16, cols=11,
            data_width=U16,
            data_addr=_DL['KFMIOP'][0],
            decode=_DL['KFMIOP'][4],
            encode=_DL['KFMIOP'][5],
            x_axis=AXIS_RPM,
            y_axis=AXIS_LOAD,
            confidence=conf,
            notes="Address 0x01656E confirmed for 06A906032DL.",
        ),
        # ── Lambda ────────────────────────────────────────────────────────────
        MapDef(
            name="KFLBTS",
            description="Lambda target map — closed-loop lambda setpoint vs RPM×load. "
                        "1.0 = stoich, <1.0 = rich. 12×16 U16, scale × 0.007813.",
            rows=12, cols=16,
            data_width=U16,
            data_addr=_DL['KFLBTS'][0],
            decode=_DL['KFLBTS'][4],
            encode=_DL['KFLBTS'][5],
            x_axis=AxisDef(name="Load", unit="g/rev", scale=0.1),
            y_axis=AxisDef(name="RPM",  unit="rpm",   scale=40.0, fmt="{:.0f}"),
            x_values=_LOAD16,
            y_values=_RPM12,
            confidence=conf,
            notes="Address 0x0192A5 confirmed for 06A906032DL.",
        ),
        MapDef(
            name="LAMFA",
            description="Lambda adaptation — long-term fuel trim map vs RPM×load. "
                        "Learned trims; reflects injector wear / MAF drift. "
                        "15×6 U16, scale × 0.007813. Reset by clearing adaptations.",
            rows=15, cols=6,
            data_width=U16,
            data_addr=_DL['LAMFA'][0],
            decode=_DL['LAMFA'][4],
            encode=_DL['LAMFA'][5],
            x_axis=AxisDef(name="RPM",  unit="rpm",   scale=40.0, fmt="{:.0f}"),
            y_axis=AxisDef(name="Load", unit="g/rev", scale=0.1),
            x_values=_LAMFA_RPM6,
            y_values=_LAMFA_LOAD15,
            confidence=conf,
            map_type="2d",
            notes="Address 0x01C95A confirmed for 06A906032DL.",
        ),
        # ── Boost ─────────────────────────────────────────────────────────────
        MapDef(
            name="KFDLULS",
            description="N75 boost solenoid upper limit — maximum duty cycle vs RPM×load. "
                        "8×8 U16, scale × 5.0 = hPa. Higher values = more boost allowed.",
            rows=8, cols=8,
            data_width=U16,
            data_addr=_DL['KFDLULS'][0],
            decode=_DL['KFDLULS'][4],
            encode=_DL['KFDLULS'][5],
            x_axis=AXIS_RPM,
            y_axis=AxisDef(name="Boost req", unit="hPa", scale=5.0),
            confidence=conf,
            notes="Address 0x01EB91 confirmed for 06A906032DL.",
        ),
        # ── Placeholder: discovered at runtime ────────────────────────────────
        MapDef(
            name="LDRXN",
            description="N75 duty cycle request — target solenoid PWM vs RPM×boost req. "
                        "Main boost control map. Needle-discovered at runtime.",
            rows=9, cols=8,
            data_width=U8,
            data_addr=0,    # runtime discovery via needle
            decode=lambda x: x / 2.55,
            encode=lambda x: int(round(x * 2.55)),
            x_axis=AxisDef(name="Boost req", unit="bar",  scale=0.005),
            y_axis=AXIS_RPM,
            confidence="PROVISIONAL",
            notes="Address runtime-discovered. XDF for DL not yet extracted for LDRXN.",
        ),
    ]


def make_v6_biturbo_maps(part_number: str = "") -> List[MapDef]:
    """
    Return MapDef list for ME7.1 2.7T biturbo (S4 B5, A6 C5, Allroad, RS4).

    Addresses confirmed from reference/8D0907551M_L_5.18.13.xdf (Nefmoto/DDillenger).
    Note: 2.7T KFZW is 16×12 (not 12×16 as on 1.8T) — RPM is the row axis.
    All addresses are flat file offsets into the 1MB ROM.
    """
    _M = {
        'KFZW':    0x011C72,
        'KFZW2':   0x011D32,
        'KFZWMS':  0x011BB0,
        'MLHFM':   0x014254,
        'KFMIRL':  0x014BEE,
        'KFMIOP':  0x016186,
        'KFLBTS':  0x019207,
        'KFDLULS': 0x019905,
        'KFMLDMX': 0x01BA86,
        'LAMFA':   0x01C38E,
        'LDRXN_1_A': 0x01DCF4,
        'LDRXNZK': 0x01DD36,
    }
    conf = "CONFIRMED"

    # 2.7T axis breakpoints — 16 RPM rows, 12 load cols (transposed from 1.8T)
    # Source: WinOLS/Nefmoto community, consistent with 8D0907551M XDF
    _RPM16 = [600, 800, 1200, 1600, 2000, 2400, 2800, 3200,
              3600, 4000, 4400, 4800, 5200, 5600, 6000, 6400]
    _LOAD12 = [0.00, 0.10, 0.25, 0.40, 0.55, 0.70, 0.85, 1.00, 1.15, 1.30, 1.45, 1.60]
    _LAMFA_RPM6  = [800, 1600, 2400, 3200, 4000, 5600]
    _LAMFA_LOAD15 = [0.00, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70,
                     0.80, 0.90, 1.00, 1.10, 1.20, 1.35, 1.50]

    return [
        # ── Ignition ──────────────────────────────────────────────────────────
        MapDef(
            name="KFZW",
            description="Main ignition timing — °BTDC vs RPM×load. 16×12 S8. "
                        "Scale: raw × 0.75 = °BTDC. Note: 2.7T uses 16 RPM rows × 12 load cols "
                        "(transposed vs 1.8T 12×16 layout).",
            rows=16, cols=12,
            data_width=S8,
            data_addr=_M['KFZW'],
            decode=lambda x: x * 0.75,
            encode=lambda x: int(round(x / 0.75)),
            x_axis=AxisDef(name="Load", unit="g/rev", scale=0.001),
            y_axis=AXIS_RPM,
            x_values=_LOAD12,
            y_values=_RPM16,
            confidence=conf,
            notes="Address 0x011C72 confirmed from 8D0907551M XDF (Nefmoto/DDillenger).",
        ),
        MapDef(
            name="KFZW2",
            description="Second ignition map — manifold pressure switchover. 16×12 S8.",
            rows=16, cols=12,
            data_width=S8,
            data_addr=_M['KFZW2'],
            decode=lambda x: x * 0.75,
            encode=lambda x: int(round(x / 0.75)),
            x_axis=AxisDef(name="Load", unit="g/rev", scale=0.001),
            y_axis=AXIS_RPM,
            x_values=_LOAD12,
            y_values=_RPM16,
            confidence=conf,
            notes="Address 0x011D32 confirmed from 8D0907551M XDF.",
        ),
        # ── MAF ───────────────────────────────────────────────────────────────
        MapDef(
            name="MLHFM",
            description="MAF linearisation — HFM voltage counts to kg/h. "
                        "512×1 U16, scale × 0.1. "
                        "Different offset from 1.8T (0x014254 vs 0x014574).",
            rows=1, cols=512,
            data_width=U16,
            data_addr=_M['MLHFM'],
            decode=lambda x: x * 0.1,
            encode=lambda x: int(round(x / 0.1)),
            x_axis=AxisDef(name="HFM count", unit="counts", scale=1.0),
            y_axis=AxisDef(name="Air flow",  unit="kg/h",   scale=0.1),
            confidence=conf,
            map_type="1d",
            notes="Address 0x014254 confirmed from 8D0907551M XDF.",
        ),
        # ── Torque model ──────────────────────────────────────────────────────
        MapDef(
            name="KFMIRL",
            description="Requested torque — maps driver demand to % load. 16×12 U16.",
            rows=16, cols=12,
            data_width=U16,
            data_addr=_M['KFMIRL'],
            decode=lambda x: x * 0.023438,
            encode=lambda x: int(round(x / 0.023438)),
            x_axis=AxisDef(name="Load", unit="g/rev", scale=0.001),
            y_axis=AXIS_RPM,
            x_values=_LOAD12,
            y_values=_RPM16,
            confidence=conf,
            notes="Address 0x014BEE confirmed from 8D0907551M XDF.",
        ),
        # ── Lambda ────────────────────────────────────────────────────────────
        MapDef(
            name="KFLBTS",
            description="Lambda target — closed-loop setpoint vs RPM×load. "
                        "16×12 U16, scale × 0.007813. "
                        "Per-bank (B1+B2) on biturbo.",
            rows=16, cols=12,
            data_width=U16,
            data_addr=_M['KFLBTS'],
            decode=lambda x: x * 0.007813,
            encode=lambda x: int(round(x / 0.007813)),
            x_axis=AxisDef(name="Load", unit="g/rev", scale=0.001),
            y_axis=AXIS_RPM,
            x_values=_LOAD12,
            y_values=_RPM16,
            confidence=conf,
            notes="Address 0x019207 confirmed from 8D0907551M XDF.",
        ),
        MapDef(
            name="LAMFA",
            description="Lambda adaptation — long-term trim. 15×6 U16, scale × 0.007813.",
            rows=15, cols=6,
            data_width=U16,
            data_addr=_M['LAMFA'],
            decode=lambda x: x * 0.007813,
            encode=lambda x: int(round(x / 0.007813)),
            x_axis=AXIS_RPM,
            y_axis=AXIS_LOAD,
            x_values=_LAMFA_RPM6,
            y_values=_LAMFA_LOAD15,
            confidence=conf,
            map_type="2d",
            notes="Address 0x01C38E confirmed from 8D0907551M XDF.",
        ),
        # ── Boost ─────────────────────────────────────────────────────────────
        MapDef(
            name="KFDLULS",
            description="N75 boost limit — maximum duty cycle vs RPM×boost. "
                        "8×8 U16, scale × 5.0 = hPa. Twin turbos K03/K04.",
            rows=8, cols=8,
            data_width=U16,
            data_addr=_M['KFDLULS'],
            decode=lambda x: x * 5.0,
            encode=lambda x: int(round(x / 5.0)),
            x_axis=AXIS_RPM,
            y_axis=AxisDef(name="Boost req", unit="hPa", scale=5.0),
            confidence=conf,
            notes="Address 0x019905 confirmed from 8D0907551M XDF.",
        ),
    ]
