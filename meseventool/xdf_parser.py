"""
xdf_parser.py — TunerPro XDF file parser for ME7.x address extraction.

Parses XDF definition files and returns a flat list of named map items
with their ROM addresses, dimensions, and scaling. Used to validate
patch addresses and build the anchor-based patch catalogue.

Ground truth XDF: 8D0907551M-20190711.xdf (s4wiki, mesim translator)
Confirmed against real ROM: all 476 items verified byte-for-byte.
"""

from __future__ import annotations
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Optional
import json, os


@dataclass
class XDFItem:
    name:     str
    addr:     int          # flat ROM offset (base_offset already applied)
    rows:     int
    cols:     int
    bits:     int          # element size in bits (8 or 16)
    tag:      str          # XDFTABLE | XDFCONSTANT
    category: str = ""


def parse_xdf(path: str, base_offset: int = 0) -> list[XDFItem]:
    """Parse a TunerPro XDF file and return all addressable items."""
    tree = ET.parse(path)
    root = tree.getroot()

    # Read base offset from XDF header if present
    xdf_header = root.find('XDFHEADER')
    if xdf_header is not None:
        b = xdf_header.findtext('baseoffset')
        if b:
            base_offset += int(b, 16) if b.startswith('0x') else int(b)

    items: list[XDFItem] = []

    for tag in ('XDFTABLE', 'XDFCONSTANT', 'XDFFUNC'):
        for elem in root.findall(f'.//{tag}'):
            title = elem.findtext('title') or elem.get('uniqueid', '?')

            # Find z-axis EMBEDDEDDATA (data address)
            z_ed = None
            for ax in elem.findall('.//XDFAXIS'):
                if ax.get('id') in ('z', None):
                    ed = ax.find('EMBEDDEDDATA')
                    if ed is not None and ed.get('mmedaddress'):
                        z_ed = ed
                        break
            if z_ed is None:
                z_ed = elem.find('.//EMBEDDEDDATA[@mmedaddress]')
            if z_ed is None:
                continue

            raw_addr = z_ed.get('mmedaddress', '')
            if not raw_addr:
                continue

            addr = int(raw_addr, 16) + base_offset
            rows = int(z_ed.get('mmedrowcount', 1))
            cols = int(z_ed.get('mmedcolcount', 1))
            bits = int(z_ed.get('mmedelementsizebits', 8))

            items.append(XDFItem(
                name=title, addr=addr,
                rows=rows, cols=cols, bits=bits,
                tag=tag,
            ))

    items.sort(key=lambda x: x.addr)
    return items


def load_json_map(path: str) -> list[XDFItem]:
    """Load a pre-parsed XDF map from JSON (faster than re-parsing XDF)."""
    with open(path) as f:
        data = json.load(f)
    return [XDFItem(**d) for d in data]


def find_by_name(items: list[XDFItem], name: str) -> Optional[XDFItem]:
    """Case-insensitive name lookup."""
    name_upper = name.upper()
    for item in items:
        if item.name.upper() == name_upper:
            return item
    return None


def find_containing(items: list[XDFItem], addr: int) -> Optional[XDFItem]:
    """Find the XDF item that contains a given ROM address."""
    for item in items:
        size = item.rows * item.cols * item.bits // 8
        if item.addr <= addr < item.addr + size:
            return item
    return None


# Pre-built map path (checked in to reference/)
_MAP_PATH = os.path.join(os.path.dirname(__file__),
                         '..', 'reference', 'xdf_map_8D0907551M.json')

def load_8D0907551M_map() -> list[XDFItem]:
    """Load the validated 8D0907551M address map (476 items)."""
    return load_json_map(os.path.normpath(_MAP_PATH))
