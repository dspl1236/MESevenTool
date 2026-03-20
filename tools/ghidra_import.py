"""
tools/ghidra_import.py
======================
Import confirmed map addresses from a Ghidra JSON symbol export and
patch them into meseventool/known_roms.py (or print the Python snippet
to add manually).

Ghidra export workflow:
  1. Open the 1MB ROM in Ghidra
     Language: Infineon C167CR (or generic x86 / generic CPU as fallback)
     Base address: 0x80000  ← CRITICAL (C167 maps flash from 0x80000)
  2. Auto-analyze
  3. Export: File → Export Program → Format = "Symbol Table" (ASCII)
     OR: Script → ExportSymbolsScript (produces JSON)
  4. Run this script:
       python tools/ghidra_import.py symbols.json --pn 06A906032DL

Output: Python KnownROM entries ready to paste into known_roms.py,
        AND a maps.py snippet with confirmed data_addr values.

Address conversion:
  Ghidra exports C167 virtual addresses (0x80000–0xFFFFF).
  File offset = C167_addr - 0x80000.
  This script applies that conversion automatically.

Known map symbol names from s4wiki / ME7RomTool naming:
  KFZW   — ignition timing
  MLHFM  — MAF linearisation
  LDRXN  — N75 duty cycle
  KFMIRL — torque request
  KFMIOP — optimal torque
  KFLBTS — lambda target
  LAMFA  — lambda adaptation
  KFDLULS— boost duty upper limit
  LDRMAX — max boost pressure
  KFPED  — pedal map
"""

from __future__ import annotations
import argparse
import json
import sys
import re
from pathlib import Path

C167_BASE  = 0x80000    # C167 flash start address
FILE_LIMIT = 0x100000   # 1MB max

# Map symbol names → metadata (rows, cols, data_width, scale, unit)
# These are the common ME7.5 1.8T names confirmed from s4wiki / XDF files.
MAP_META: dict[str, dict] = {
    "KFZW":    {"rows": 12, "cols": 16, "width": -1, "scale": 0.75,    "unit": "°BTDC"},
    "MLHFM":   {"rows": 1,  "cols": 512,"width":  2, "scale": 0.1,     "unit": "kg/h"},
    "LDRXN":   {"rows": 9,  "cols": 8,  "width":  1, "scale": 1/2.55,  "unit": "%"},
    "KFMIRL":  {"rows": 16, "cols": 16, "width":  2, "scale": 0.023438,"unit": "%"},
    "KFMIOP":  {"rows": 16, "cols": 11, "width":  2, "scale": 0.001526,"unit": "%"},
    "KFLBTS":  {"rows": 12, "cols": 16, "width":  2, "scale": 0.007813,"unit": "λ"},
    "LAMFA":   {"rows": 15, "cols": 6,  "width":  2, "scale": 0.007813,"unit": "λ"},
    "KFDLULS": {"rows": 8,  "cols": 8,  "width":  2, "scale": 5.0,     "unit": "hPa"},
    "KFPED":   {"rows": 10, "cols": 10, "width":  2, "scale": 0.023438,"unit": "%"},
    "LDRMAX":  {"rows": 1,  "cols": 16, "width":  2, "scale": 5.0,     "unit": "hPa"},
    "KFNWSOL": {"rows": 12, "cols": 16, "width":  2, "scale": 0.75,    "unit": "°BTDC"},
}


def c167_to_file(addr: int) -> int:
    """Convert C167 virtual address to flat file offset."""
    if addr < C167_BASE:
        raise ValueError(f"Address 0x{addr:06X} below C167 flash base 0x{C167_BASE:06X}")
    off = addr - C167_BASE
    if off >= FILE_LIMIT:
        raise ValueError(f"Address 0x{addr:06X} above 1MB flash end")
    return off


def parse_ghidra_json(path: str) -> dict[str, int]:
    """
    Parse a Ghidra JSON symbol export.
    Returns {symbol_name: file_offset}.

    Supports two common Ghidra export formats:
      1. List of {"name": "...", "address": "0x12345"}
      2. Dict of {"name": {"address": "0x12345", ...}}
    """
    raw = json.loads(Path(path).read_text())
    symbols: dict[str, int] = {}

    if isinstance(raw, list):
        for entry in raw:
            name = entry.get("name", "")
            addr_s = entry.get("address", entry.get("addr", ""))
            if not name or not addr_s:
                continue
            try:
                addr = int(str(addr_s), 16)
                symbols[name] = c167_to_file(addr)
            except (ValueError, TypeError):
                pass
    elif isinstance(raw, dict):
        for name, info in raw.items():
            if isinstance(info, dict):
                addr_s = info.get("address", info.get("addr", ""))
            else:
                addr_s = str(info)
            try:
                addr = int(str(addr_s), 16)
                symbols[name] = c167_to_file(addr)
            except (ValueError, TypeError):
                pass

    return symbols


def parse_ghidra_text(path: str) -> dict[str, int]:
    """
    Parse a Ghidra text/ASCII symbol export (File → Export → Symbol Table).
    Format: lines of:  Name  Address  ...
    """
    symbols: dict[str, int] = {}
    for line in Path(path).read_text().splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name, addr_s = parts[0], parts[1]
        try:
            addr = int(addr_s, 16)
            symbols[name] = c167_to_file(addr)
        except (ValueError, TypeError):
            pass
    return symbols


def generate_map_snippet(symbols: dict[str, int], pn: str) -> str:
    """Generate Python MapDef entries for confirmed symbols."""
    lines = [f"# Confirmed map addresses from Ghidra — {pn}"]
    found = 0
    for sym_name, file_off in sorted(symbols.items()):
        meta = MAP_META.get(sym_name)
        if meta is None:
            continue
        found += 1
        w     = meta['width']
        rows  = meta['rows']
        cols  = meta['cols']
        scale = meta['scale']
        unit  = meta['unit']
        w_str = f"S{abs(w)*8}" if w < 0 else f"U{abs(w)*8}"
        lines.append(
            f"        MapDef(name=\"{sym_name}\", rows={rows}, cols={cols}, "
            f"data_width={'S8' if w==-1 else ('U16' if w==2 else 'U8')}, "
            f"data_addr=0x{file_off:06X}, "
            f"decode=lambda x: x * {scale}, "
            f"encode=lambda x: int(round(x / {scale})), "
            f"confidence=\"CONFIRMED\", "
            f"notes=\"Ghidra confirmed for {pn}\"),"
        )
    if not found:
        lines.append("# No known map symbols found in export")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="Import Ghidra symbol export → MESevenTool map addresses"
    )
    ap.add_argument("symbols", help="Path to Ghidra symbol export (JSON or text)")
    ap.add_argument("--pn", default="", help="ECU part number (e.g. 06A906032DL)")
    ap.add_argument("--format", choices=["json", "text", "auto"], default="auto",
                    help="Symbol file format")
    args = ap.parse_args()

    # Auto-detect format
    fmt = args.format
    if fmt == "auto":
        fmt = "json" if args.symbols.endswith(".json") else "text"

    print(f"Importing symbols from: {args.symbols}  (format: {fmt})")
    try:
        symbols = (parse_ghidra_json if fmt == "json" else parse_ghidra_text)(args.symbols)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(symbols)} symbols")

    # Show recognised map symbols
    recognised = {k: v for k, v in symbols.items() if k in MAP_META}
    if recognised:
        print(f"\nRecognised map symbols ({len(recognised)}):")
        for name, off in sorted(recognised.items()):
            meta = MAP_META[name]
            print(f"  {name:<15} file=0x{off:06X}  C167=0x{off + C167_BASE:06X}"
                  f"  {meta['rows']}×{meta['cols']}")
    else:
        print("\nNo recognised map symbols. Check symbol naming matches MAP_META keys.")
        print("Expected names:", list(MAP_META.keys()))

    # Output snippet
    print(f"\n{'='*70}")
    print("Python snippet for maps.py / known_roms.py:")
    print(f"{'='*70}")
    print(generate_map_snippet(symbols, args.pn))


if __name__ == "__main__":
    main()
