"""
tests/synthetic_rom.py
======================
Shared builder for synthetic ROMs that carry a *real* ME7 checksum layout:
the me7romtool needles from ``meseventool.checksum`` are embedded in the
last 4 KB of the image, pointing at a main-region table, a multipoint table
and a stored sum/~sum pair.  ``ChecksumManager`` locates everything by
needle exactly as it does on a real ROM.  The sums are computed here with
plain loops so the tests are not circular.

Layout (T = size - 0x1000):
    T+0x000  region-count needle   (2 regions)
    T+0x040  region-table needle
    T+0x080  store needle
    T+0x0C0  multipoint-count needle (4 blocks)
    T+0x100  multipoint-table needle
    T+0x200  main region table      [s_lo s_hi e_lo e_hi] x 2 (8 B stride)
    T+0x300  multipoint table       [start end sum ~sum] x 4
    size-0x20 main [sum][~sum]

Main regions: 0x0-0xFBFF and (0x20000 | 0x10000 for 256 KB)-(size-1).
Multipoint blocks: 0x0-0x3FFF, 0x4000-0x7FFF, cal-cal+0x3FFF, cal+0x4000-cal+0x7FFF.
There is no CRC32 layer (as on 4B0906018CM).
"""
import struct
from typing import Optional

from meseventool.rom import ROMImage
from meseventool import checksum as C

PHYS_BASE = 0x800000


def main_sum_offset(size: int) -> int:
    return size - 0x20


def main_regions(size: int):
    second = 0x20000 if size >= 0x80000 else 0x10000
    return [(0x0, 0xFBFF), (second, size - 1)]


def multi_blocks(size: int):
    cal = ROMImage(data=bytearray(size)).cal_page_offset
    return [(0x0, 0x3FFF), (0x4000, 0x7FFF),
            (cal, cal + 0x3FFF), (cal + 0x4000, cal + 0x7FFF)]


def word_sum(data, start: int, end: int) -> int:
    total = 0
    for i in range(start // 2, end // 2 + 1):
        total += data[2 * i] | (data[2 * i + 1] << 8)
    return total & 0xFFFFFFFF


def _needle_bytes(needle, mask) -> bytearray:
    return bytearray(b if m else 0 for b, m in zip(needle, mask))


def _page_op(file_off: int):
    phys = PHYS_BASE + file_off
    return phys >> 14, phys & 0x3FFF


def embed_checksum_layout(data: bytearray) -> None:
    """Write needles and tables into ``data`` (no sums yet)."""
    size = len(data)
    T = size - 0x1000

    # Region count: 2
    n = _needle_bytes(C.NEEDLE_MAIN_COUNT, C.MASK_MAIN_COUNT)
    n[C.MAIN_COUNT_BYTE] = 0xA4
    data[T:T + len(n)] = n

    # Region table needle
    tbl = T + 0x200
    page, op = _page_op(tbl)
    n = _needle_bytes(C.NEEDLE_MAIN_REGIONS, C.MASK_MAIN_REGIONS)
    struct.pack_into('<H', n, C.MAIN_REGIONS_PAGE, page)
    struct.pack_into('<H', n, C.MAIN_REGIONS_SLO, op)
    struct.pack_into('<H', n, C.MAIN_REGIONS_SHI, op + 2)
    struct.pack_into('<H', n, C.MAIN_REGIONS_ELO, op + 4)
    struct.pack_into('<H', n, C.MAIN_REGIONS_EHI, op + 6)
    data[T + 0x40:T + 0x40 + len(n)] = n
    for i, (s, e) in enumerate(main_regions(size)):
        ps, pe = PHYS_BASE + s, PHYS_BASE + e
        struct.pack_into('<HHHH', data, tbl + i * 8,
                         ps & 0xFFFF, ps >> 16, pe & 0xFFFF, pe >> 16)

    # Store needle
    page, op = _page_op(main_sum_offset(size))
    n = _needle_bytes(C.NEEDLE_MAIN_STORE, C.MASK_MAIN_STORE)
    struct.pack_into('<H', n, C.MAIN_STORE_PAGE, page)
    struct.pack_into('<H', n, C.MAIN_STORE_OFF, op)
    data[T + 0x80:T + 0x80 + len(n)] = n

    # Multipoint count + table needles
    blocks = multi_blocks(size)
    n = _needle_bytes(C.NEEDLE_MULTI_COUNT, C.MASK_MULTI_COUNT)
    struct.pack_into('<H', n, C.MULTI_COUNT_OFF, len(blocks))
    data[T + 0xC0:T + 0xC0 + len(n)] = n
    mtbl = T + 0x300
    page, op = _page_op(mtbl)
    n = _needle_bytes(C.NEEDLE_MULTI_TABLE, C.MASK_MULTI_TABLE)
    struct.pack_into('<H', n, C.MULTI_TABLE_PAGE, page)
    struct.pack_into('<H', n, C.MULTI_TABLE_OFF, op)
    data[T + 0x100:T + 0x100 + len(n)] = n
    for j, (s, e) in enumerate(blocks):
        struct.pack_into('<II', data, mtbl + j * 16, PHYS_BASE + s, PHYS_BASE + e)


def write_checksums(data: bytearray) -> int:
    """Compute and store the multipoint sums then the main sum. Returns main sum."""
    size = len(data)
    mtbl = size - 0x1000 + 0x300
    for j, (s, e) in enumerate(multi_blocks(size)):
        ws = word_sum(data, s, e)
        struct.pack_into('<II', data, mtbl + j * 16 + 8, ws, ~ws & 0xFFFFFFFF)
    # The main pair lies inside region 2.  Once a sum/~sum pair is in place
    # its contribution is the constant 2 * 0xFFFF, so the second pass is
    # exact (the first replaces whatever fill bytes were there).
    off = main_sum_offset(size)
    total = 0
    for _ in range(2):
        total = 0
        for s, e in main_regions(size):
            total = (total + word_sum(data, s, e)) & 0xFFFFFFFF
        struct.pack_into('<II', data, off, total, ~total & 0xFFFFFFFF)
    return total


def make_rom_with_checksum(size: int = 0x80000, fill: int = 0xAA,
                           data: Optional[bytearray] = None) -> ROMImage:
    """
    Build a synthetic ROM with valid main and multipoint checksums.
    Pass ``data`` to embed the layout into an image you already prepared
    (e.g. with patch needles); its size is used.
    """
    if data is None:
        data = bytearray([fill]) * size
    embed_checksum_layout(data)
    write_checksums(data)
    return ROMImage(data=data)
