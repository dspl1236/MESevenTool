#!/usr/bin/env python3
"""
SGO Extract — unpack ODIS SGO flash containers to flat ECU images.

Thin CLI wrapper around ``meseventool.sgo``.  Supports the four older Bosch
engine families carried by MESevenTool:

    motronic7   Bosch Motronic ME7.x      (GEHEIM record coding)
    edc15       Bosch EDC15 diesel        (plain XOR-FF)
    edc16-1m    Bosch EDC16 diesel 1 MiB  (32-bit LFSR)
    edc16-2m    Bosch EDC16 diesel 2 MiB  (32-bit LFSR)

The decode primitives are a faithful port of lsdlsd88/TCU-FRF-SGO-UNPACKER
(MIT); see THIRD_PARTY_NOTICES.md.

Usage:
    python tools/sgo_extract.py file.sgo [file2.sgo ...]
    python tools/sgo_extract.py --family edc16-1m file.sgo
"""

import argparse
import os
import sys

# Allow running straight from a checkout without `pip install -e .`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from meseventool.sgo import FAMILIES, extract_sgo  # noqa: E402


def extract(sgo_path, out_path=None, family="auto"):
    """Decode ``sgo_path`` to a .bin and return the output path (library helper)."""
    result = extract_sgo(sgo_path, family=family)
    if out_path is None:
        base = sgo_path[:-4] if sgo_path.lower().endswith(".sgo") else sgo_path
        out_path = base + ".bin"
    with open(out_path, "wb") as f:
        f.write(result.image)
    print(f"  {os.path.basename(sgo_path)} -> {os.path.basename(out_path)} "
          f"[{result.family}] ({len(result.image) // 1024} KB)")
    return out_path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Unpack ODIS SGO flash containers.")
    parser.add_argument("sgo", nargs="+", help="one or more .sgo files")
    parser.add_argument("--family", default="auto",
                        choices=["auto", *FAMILIES],
                        help="decoder family (default: auto-detect)")
    args = parser.parse_args(argv)
    rc = 0
    for sgo in args.sgo:
        try:
            extract(sgo, family=args.family)
        except Exception as e:  # noqa: BLE001 — CLI: report and continue
            print(f"  ERROR {sgo}: {e}")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
