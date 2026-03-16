"""
meseventool/xdf.py
==================
Loader for the XDF table definitions in reference/xdf_tables.json.

The JSON is derived from TunerPro RT XDF files (community-produced,
validated against real ROM dumps). Each entry contains:
  name     : Bosch function name (KFZW, MLHFM, LDRXN_1_A, etc.)
  desc     : Human-readable description
  pn       : Part number the offsets are confirmed against
  axes.z   : Cell data (rows×cols, addr, elemsize, math, units)
  axes.x   : X-axis (optional, cols entries)
  axes.y   : Y-axis (optional, rows entries)

Addresses are flat file offsets into the 512 KB .bin.

Usage:
    from meseventool.xdf import XDFLoader
    loader = XDFLoader()
    maps = loader.make_maps("06A906032DL")
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

from .maps import MapDef, AxisDef


_JSON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "reference", "xdf_tables.json"
)

# Normalise long descriptive names → short Bosch names where possible
_NAME_MAP = {
    "Ignition angle map (KFZW)":                 "KFZW",
    "Ignition angle map (variant 2) (KFZW2)":    "KFZW2",
    "*Optimal ignition angle under monitoring (KFZW_UM)": "KFZW_UM",
    "Optimal ignition angle (KFZWOP)":            "KFZWOP",
    "Optimal ignition angle (variant 2) (KFZWOP2)": "KFZWOP2",
    "Map with permanent latest possible ignition angle (KFZWMS)": "KFZWMS",
    "Minimum ignition angle (KFZWMN)":            "KFZWMN",
    "Engine load desired (KFMIRL)":               "KFMIRL",
    "Maximum specified load (LDRXN)":             "LDRXN",
    "Maximum specified load during continuous knock (LDRXNZK)": "LDRXNZK",
    "Correction  map for MAF (KFKHFM)":           "KFKHFM",
    "Map for linearization of boost pressure (KFLDRL)": "KFLDRL",
    "LDR I-Regulator limit (KFLDIMX)":            "KFLDIMX",
    "LDR I-Regulator limit correction as a function of IAT (LDIATA)": "LDIATA",
    "LDR altitude limitation (maximum pressure ratio) (KFLDHBN)": "KFLDHBN",
    "Lambda - driver desired (LAMFA)":             "LAMFA",
    "Delta desired lambda for component protection (DLBTS)": "DLBTS",
    "Delta ignition angle (overboost) (KFDZWOB)": "KFDZWOB",
    "Delta pressure for overboost protection diagnosis (KFDLULS)": "KFDLULS",
    "Correction factor for fuel supply system (FKKVS)": "FKKVS",
    "Correction factor for combustion chamber pressure (KFPBRK)": "KFPBRK",
    "Factor for maximum pressure ratio with auxilliary load signal  (FPVMXN2)": "FPVMXN2",
    "ML: threshod for B_minflr diagnosis HFM/HLM (KFMLDMN)": "KFMLDMN",
    "ML: threshold for B_maxflr diagnosis HFM/HLM (KFMLDMX)": "KFMLDMX",
    "LAMFA COLUMN": "LAMFA_X",
    "LAMFA ROW":    "LAMFA_Y",
}

# Human descriptions for known Bosch names
_DESCRIPTIONS = {
    "KFZW":     "Ignition timing base map (°BTDC vs RPM×Load)",
    "KFZW2":    "Ignition timing map variant 2",
    "KFZWOP":   "Optimal ignition angle",
    "KFZWMS":   "Maximum ignition angle (permanent)",
    "KFZWMN":   "Minimum ignition angle",
    "KFZW_UM":  "Ignition angle under monitoring",
    "KFMIRL":   "Desired engine load map (torque request)",
    "KFMIOP":   "Optimal engine torque map",
    "LDRXN":    "Maximum specified boost load (N75 target)",
    "LDRXN_1_A":"Maximum specified boost load (stage 1)",
    "LDRXNZK":  "Maximum boost load under knock",
    "KFKHFM":   "MAF air temperature correction",
    "KFLDRL":   "Boost pressure linearisation",
    "KFLDIMX":  "LDR I-regulator limit",
    "KFLDHBN":  "LDR altitude limitation",
    "LDIATA":   "LDR I-limit correction vs IAT",
    "LAMFA":    "Driver desired lambda map",
    "DLBTS":    "Delta lambda for component protection",
    "KFDZWOB":  "Ignition retard for overboost",
    "KFDLULS":  "Overboost diagnosis delta pressure",
    "MLHFM":    "MAF linearisation (HFM voltage → g/s)",
    "MLOFS":    "MAF zero offset",
    "SNM16ZUUB":"RPM axis (engine speed)",
    "SNM16GKUB":"RPM axis (full-load limit)",
    "SRL12ZUUB":"Load axis (g/rev, 12-entry)",
    "SRL12GKUB":"Load axis (g/rev, 8-entry)",
    "SRL12GKUW":"Load axis (g/rev, 12-entry wide)",
    "TVUB":     "Throttle valve reference axis",
    "KFLBTS":   "Full-load boost timing map",
    "KFMLDMX":  "Maximum MAF load threshold",
    "KFPBRK":   "Combustion pressure correction factor",
    "FKKVS":    "Fuel supply correction factor",
    "FPVMXN2":  "Max pressure ratio with aux load",
    "LAMFA_X":  "Lambda map column axis",
    "LAMFA_Y":  "Lambda map row axis",
    "KRKTE":    "Knock retard correction factor",
    "VARDEF":   "Variant definition word",
}


def _parse_math(math_str: str) -> tuple[float, float]:
    """
    Parse TunerPro math expression → (scale, offset).
    Handles:  "0.250000 * X"     → (0.25, 0.0)
              "0.023438 * X"     → (0.023438, 0.0)
              "0.000000+X*0.100000" → (0.1, 0.0)
              "-48.000000+X*0.750000" → (0.75, -48.0)
    """
    math_str = math_str.strip()
    # Try "offset+X*scale" or "offset + X * scale"
    m = re.match(
        r'([-\d.]+)\s*\+\s*[Xx]\s*\*\s*([-\d.]+)', math_str
    )
    if m:
        return float(m.group(2)), float(m.group(1))
    # Try "scale*X" or "scale * X"
    m = re.match(r'([-\d.]+)\s*\*\s*[Xx]', math_str)
    if m:
        return float(m.group(1)), 0.0
    # Try just "X*scale"
    m = re.match(r'[Xx]\s*\*\s*([-\d.]+)', math_str)
    if m:
        return float(m.group(1)), 0.0
    # Fallback — identity
    return 1.0, 0.0


@dataclass
class XDFAxis:
    addr:     int
    elemsize: int
    cols:     int
    rows:     int
    signed:   bool
    scale:    float
    offset:   float
    units:    str


@dataclass
class XDFTable:
    name:  str
    desc:  str
    pn:    str
    z:     Optional[XDFAxis]    # cell data
    x:     Optional[XDFAxis]    # x-axis (cols direction)
    y:     Optional[XDFAxis]    # y-axis (rows direction)

    @property
    def rows(self) -> int:
        return self.z.rows if self.z else (self.y.rows if self.y else 1)

    @property
    def cols(self) -> int:
        return self.z.cols if self.z else (self.x.cols if self.x else 1)

    @property
    def data_addr(self) -> int:
        return self.z.addr if self.z else 0

    def to_mapdef(self) -> MapDef:
        """Convert to a MapDef with confirmed addresses and scaling."""
        z = self.z
        if z is None:
            return MapDef(name=self.name, description=self.desc,
                          data_addr=0, confidence="UNCONFIRMED")

        # Build decode/encode closures from scale+offset
        sc, off = z.scale, z.offset
        decode = (lambda raw, s=sc, o=off: raw * s + o)
        encode = (lambda phys, s=sc, o=off: int(round((phys - o) / s))
                  if s else int(round(phys)))

        data_width = z.elemsize if not z.signed else -z.elemsize

        x_axis = AxisDef(
            name=self.x.units if self.x else "x",
            unit=self.x.units if self.x else "",
            scale=self.x.scale if self.x else 1.0,
            offset=self.x.offset if self.x else 0.0,
        ) if self.x else AxisDef(name="x")

        y_axis = AxisDef(
            name=self.y.units if self.y else "y",
            unit=self.y.units if self.y else "",
            scale=self.y.scale if self.y else 1.0,
            offset=self.y.offset if self.y else 0.0,
        ) if self.y else AxisDef(name="y")

        return MapDef(
            name        = self.name,
            description = self.desc or _DESCRIPTIONS.get(self.name, ""),
            rows        = z.rows,
            cols        = z.cols,
            data_width  = data_width,
            data_addr   = z.addr,
            x_axis_addr = self.x.addr if self.x else 0,
            y_axis_addr = self.y.addr if self.y else 0,
            x_axis      = x_axis,
            y_axis      = y_axis,
            decode      = decode,
            encode      = encode,
            confidence  = "CONFIRMED",
            notes       = f"XDF-confirmed offset for {self.pn}",
        )


def _parse_axis(ax: dict) -> XDFAxis:
    scale, offset = _parse_math(ax.get("math", "1.0 * X"))
    return XDFAxis(
        addr     = ax["addr"],
        elemsize = ax["elemsize"],
        cols     = ax["cols"],
        rows     = ax["rows"],
        signed   = ax.get("signed", False),
        scale    = scale,
        offset   = offset,
        units    = ax.get("units", ""),
    )


class XDFLoader:
    """
    Loads XDF table definitions from the JSON reference file.

    Provides lookup by part number and table name, and can produce
    a complete MapDef list for a given ECU variant.
    """

    def __init__(self, path: str = _JSON_PATH):
        with open(os.path.normpath(path)) as f:
            raw = json.load(f)
        self._tables: List[XDFTable] = []
        for entry in raw:
            name = _NAME_MAP.get(entry["name"], entry["name"])
            axes = entry.get("axes", {})
            self._tables.append(XDFTable(
                name = name,
                desc = entry.get("desc", _DESCRIPTIONS.get(name, "")),
                pn   = entry["pn"],
                z    = _parse_axis(axes["z"]) if "z" in axes else None,
                x    = _parse_axis(axes["x"]) if "x" in axes else None,
                y    = _parse_axis(axes["y"]) if "y" in axes else None,
            ))

        # Build index: pn → {name → XDFTable}
        self._by_pn: Dict[str, Dict[str, XDFTable]] = {}
        for t in self._tables:
            self._by_pn.setdefault(t.pn, {})[t.name] = t

    def part_numbers(self) -> List[str]:
        return sorted(self._by_pn.keys())

    def tables_for(self, pn: str) -> List[XDFTable]:
        return list(self._by_pn.get(pn, {}).values())

    def get(self, pn: str, name: str) -> Optional[XDFTable]:
        return self._by_pn.get(pn, {}).get(name)

    def make_maps(self, pn: str,
                  names: Optional[List[str]] = None) -> List[MapDef]:
        """
        Build a MapDef list for the given part number.

        If names is None, returns all maps except pure axis tables.
        Axis tables (SNM16ZUUB, SRL12ZUUB, TVUB, LAMFA_X, LAMFA_Y,
        VARDEF, MLOFS) are incorporated into the maps that reference them
        rather than shown as standalone entries.
        """
        _SKIP = {
            "SNM16ZUUB", "SNM16GKUB", "SRL12ZUUB", "SRL12GKUB",
            "SRL12GKUW", "TVUB", "LAMFA_X", "LAMFA_Y", "VARDEF",
            "MLOFS", "KRKTE",
        }
        tables = self.tables_for(pn)
        if names:
            tables = [t for t in tables if t.name in names]
        else:
            tables = [t for t in tables if t.name not in _SKIP]

        maps = [t.to_mapdef() for t in tables]

        # Sort by name for consistent display order
        _ORDER = ["KFZW", "KFZW2", "KFZWOP", "KFZWMS", "KFZWMN",
                  "KFMIRL", "KFMIOP", "LDRXN", "LDRXN_1_A", "LDRXNZK",
                  "MLHFM", "KFKHFM", "LAMFA", "KFLBTS", "KFLDRL"]
        def sort_key(m):
            try:
                return _ORDER.index(m.name)
            except ValueError:
                return len(_ORDER) + hash(m.name) % 100

        maps.sort(key=sort_key)
        return maps
