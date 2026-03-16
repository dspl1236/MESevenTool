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

import struct
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
    decode:      Optional[Callable] = None   # raw → physical
    encode:      Optional[Callable] = None   # physical → raw
    confidence:  str = "UNCONFIRMED"         # CONFIRMED | PROVISIONAL | UNCONFIRMED
    map_type:    str = "2d"                  # "2d" | "1d" | "raw"
    notes:       str = ""

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
                raw = int.from_bytes(rom.data[off:off+width],
                                     'big' if self.data_width > 0 else 'little',
                                     signed=(self.data_width < 0))
                row.append(dec(raw))
            rows.append(row)
        return rows

    def write(self, rom: ROMImage, values: List[List[float]]) -> None:
        """Encode and write physical values back to the ROM."""
        if self.data_addr == 0:
            return
        width = abs(self.data_width)
        enc   = self.encode or (lambda x: int(round(x)))
        for r, row in enumerate(values):
            for c, v in enumerate(row):
                off = self.data_addr + (r * self.cols + c) * width
                raw = enc(v)
                raw = max(0, min((1 << (width * 8)) - 1, raw))
                rom.data[off:off+width] = raw.to_bytes(width, 'big')


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


def make_awp_maps() -> List[MapDef]:
    """
    Return canonical MapDef list for the AWP/AUM 1.8T 180hp variant.

    Offsets marked CONFIRMED are validated against 06A906032DL ROM.
    Others are PROVISIONAL pending real ROM verification.
    """
    return [
        MapDef(
            name="KFZW",
            description="Ignition timing base map (°BTDC vs RPM×Load)",
            rows=12, cols=16,
            data_width=S8,
            data_addr=0,         # discovered at runtime by needle
            decode=lambda x: x * 0.75,
            encode=lambda x: int(round(x / 0.75)),
            x_axis=AXIS_RPM,
            y_axis=AXIS_LOAD,
            confidence="PROVISIONAL",
            notes="Address found by SSTB+ZWGRU needle. Scale: raw*0.75=°BTDC.",
        ),
        MapDef(
            name="MLHFM",
            description="MAF linearisation (HFM voltage count → kg/h)",
            rows=1, cols=512,
            data_width=U16,
            data_addr=0,
            decode=lambda x: x * 0.1,
            encode=lambda x: int(round(x / 0.1)),
            x_axis=AxisDef(name="HFM count", unit="counts", scale=1.0),
            y_axis=AxisDef(name="Air flow",  unit="kg/h",   scale=0.1),
            confidence="PROVISIONAL",
            map_type="1d",
            notes="512×u16. Address found by MLHFM needle.",
        ),
        MapDef(
            name="LDRXN",
            description="N75 boost solenoid duty cycle (% vs RPM×Boost req)",
            rows=9, cols=8,
            data_width=U8,
            data_addr=0,
            decode=lambda x: x / 2.55,
            encode=lambda x: int(round(x * 2.55)),
            x_axis=AxisDef(name="Boost req", unit="bar",  scale=0.005),
            y_axis=AXIS_RPM,
            confidence="PROVISIONAL",
            notes="Controls wastegate solenoid N75. Key boost tuning map.",
        ),
        MapDef(
            name="KFKHFM",
            description="MAF temperature correction (multiplier vs IAT×Load)",
            rows=8, cols=8,
            data_width=U16,
            data_addr=0,
            decode=lambda x: x / 4096.0,
            encode=lambda x: int(round(x * 4096.0)),
            x_axis=AxisDef(name="IAT",  unit="°C",    scale=0.5, offset=-48.0),
            y_axis=AXIS_LOAD,
            confidence="PROVISIONAL",
            notes="Corrects MAF reading for air temperature. KFKHFM needle.",
        ),
        MapDef(
            name="KFMIRL",
            description="Requested torque map (% load vs RPM×throttle)",
            rows=16, cols=16,
            data_width=U16,
            data_addr=0,
            decode=lambda x: x * 0.023438,
            encode=lambda x: int(round(x / 0.023438)),
            x_axis=AXIS_RPM,
            y_axis=AXIS_LOAD,
            confidence="PROVISIONAL",
        ),
    ]
