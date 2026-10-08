"""
tools/checksum_probe.py — show everything the checksum module finds in a ROM.

Usage: python tools/checksum_probe.py <rom.bin> [<rom.bin> ...]

Prints, per ROM: the main-checksum regions and stored pair, every multipoint
block (bad ones always, the first four for context), and the chained CRC32
regions with their stored constants.  Pure read-only; nothing is written.
See docs/checksum_port_handoff.md for how each layer was validated.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from meseventool.rom import ROMImage              # noqa: E402
from meseventool.checksum import ChecksumManager  # noqa: E402
from meseventool.ecu_id import identify           # noqa: E402


def probe(path: str) -> None:
    rom = ROMImage.load(path)
    ident = identify(rom)
    print(f"== {path}")
    print(f"ID: {ident.vmecuhn} {ident.ssecuhn} {ident.version_string}")
    r = ChecksumManager(rom).verify()

    m = r.main
    if m.found:
        for i, (s, e) in enumerate(m.regions):
            print(f"main region {i + 1}: 0x{s:05X}-0x{e:05X}")
        print(f"main stored @0x{m.offset:05X}: 0x{m.stored:08X} ~0x{m.stored_c:08X}"
              f"  calc 0x{m.calc:08X}  {'OK' if m.all_ok else 'BAD'}")
    else:
        print(f"main: NOT FOUND ({m.note})")

    mp = r.multi
    if mp.found:
        print(f"multipoint table @0x{mp.table_offset:05X}, {mp.count} blocks")
        for b in mp.blocks:
            if b.index <= 4 or not b.ok:
                print(f"  blk {b.index:2d}: 0x{b.start:06X}-0x{b.end:06X} "
                      f"stored=0x{b.stored_sum:08X} calc=0x{b.calc_sum:08X} "
                      f"{'OK' if b.ok else 'BAD'}")
        print(f"  multipoint: {mp.n_ok} ok, {mp.n_bad} bad")
    else:
        print(f"multipoint: {'not present' if not mp.note else 'NOT VERIFIED: ' + mp.note}")

    c = r.crc
    if c.found:
        if c.pre_block:
            print(f"crc32 pre-block 0x{c.pre_block[0]:05X}-0x{c.pre_block[1]:05X} (seeds the chain)")
        for b in c.blocks:
            where = f"@0x{b.offset:05X} stored=0x{b.stored:08X}" if b.offset is not None else "(no stored value)"
            print(f"  crc {b.index}: 0x{b.start:05X}-0x{b.end:05X} calc=0x{b.calc:08X} {where} "
                  f"{'OK' if b.ok else 'BAD'}")
    else:
        print(f"crc32: {'not present' if not c.note else 'NOT VERIFIED: ' + c.note}")
    print(f"ALL OK: {r.all_ok}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for p in sys.argv[1:]:
        probe(p)
