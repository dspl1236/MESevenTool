"""
tools/checksum_probe.py — run the me7romtool checksum needles against a ROM.

Usage: python tools/checksum_probe.py <rom.bin>

Prints the main-checksum regions and stored value, and the multipoint table
with per-block verification. See docs/checksum_port_handoff.md.
"""
import sys, struct
sys.path.insert(0, __import__('os').path.join(__import__('os').path.dirname(__file__), '..'))
from meseventool.rom import ROMImage
from meseventool.needle import Searcher, XXXX, MASK
from meseventool.ecu_id import identify

X, M = XXXX, MASK
# needle_2b: region count (byte at +27)
N2B = [0x88,0x90,0x88,0x80,0x88,0x70,0x88,0x60, 0xDA,X,X,X, 0xF3,0xF8,X,X, 0x49,0x81, 0xEA,0x30,X,X, 0xF3,0xFA,X,X, 0x49,X, 0x9D,0x27, 0xF2,0xF8,X,X, 0xF2,0xF9,X,X, 0xE0,0x07, 0x0D,0x0A]
M2B = [M,M,M,M,M,M,M,M, M,X,X,X, M,M,X,X, M,M, M,M,X,X, M,M,X,X, M,X, M,M, M,M,X,X, M,M,X,X, M,M, M,M]
# needle_2: regions
N2 = [0xF6,0x8E,X,X, 0xF6,0x8E,X,X, 0xF7,0x8E,X,X, 0xD7,0x50,X,X, 0xF2,X,X,X, 0xF2,X,X,X, 0xF6,X,X,X, 0xF6,X,X,X, 0xE1,0x18, 0xF7,X,X,X, 0xD7,0x50,X,X, 0xF2,X,X,X, 0xF2,X,X,X, 0xF6,X,X,X, 0xF6,X,X,X, 0xDB,0x00]
M2 = [M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,X,X,X, M,X,X,X, M,X,X,X, M,X,X,X, M,M, M,X,X,X, M,M,X,X, M,X,X,X, M,X,X,X, M,X,X,X, M,X,X,X, M,M]
# needle_3: stored main checksum
N3 = [0xF2,0xF4,X,X, 0xF2,0xF5,X,X, 0xD7,0x50,X,X, 0x22,0xF4,X,X, 0x32,0xF5,X,X, 0x3D,X, 0xE6,0xF4,X,X, 0xE6,0xF5,X,X, 0xDC,0x45, 0xA9,0x64, 0x77,0xF6,0x08,0x00, 0xE6,0xF4,X,X, 0xE6,0xF5,X,X, 0xDC,0x45, 0xB9,0x64, 0x0D,0x0E]
M3 = [M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,X, M,M,X,X, M,M,X,X, M,M, M,M, M,M,M,M, M,M,X,X, M,M,X,X, M,M, M,M, M,M]
N3B = [0xF6,0xF8,X,X, 0xF6,0xF9,X,X, 0xF0,0x48, 0xF0,0x59, 0x22,0xF4,X,X, 0x32,0xF5,X,X, 0xEA,0x80,X,X, 0x0D,X, 0xF2,0xF4,X,X, 0xF2,0xF5,X,X, 0xD7,0x50,X,X, 0x22,0xF4,X,X, 0x32,0xF5,X,X, 0x3D,X]
M3B = [M,M,X,X, M,M,X,X, M,M, M,M, M,M,X,X, M,M,X,X, M,M,X,X, M,X, M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,X]
# needle_4b: multipoint count (u16 at +42)
N4B = [0x98,0x4A, 0xA8,0x5A, 0xF6,0xF4,X,X, 0xF6,0xF5,X,X, 0xF6,0x8E,X,X, 0xF6,0x8E,X,X, 0xF2,0xF2,X,X, 0x66,0xF2,0xFF,0x47, 0x76,0xF2,0xFF,0x40, 0xF6,0xF2,X,X, 0xF2,0xF4,X,X, 0x46,0xF4,X,X, 0xEA,0x90,X,X]
M4B = [M,M, M,M, M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,M,M,M, M,M,M,M, M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X]
N4C = [0xF3,0xF8,X,X, 0x43,0xF8,X,X, 0xEA,0x30,X,X, 0xF3,0xFA,X,X, 0x49,0xA1, 0xEA,0x20,X,X, 0xF7,0x8F,X,X, 0x46,0xF6,0x00,0x10, 0xEA,0x30,X,X, 0xF2,0xF6,X,X, 0x66,0xF6,0xFF,0x00, 0x46,0xF6,X,X, 0xEA,0xE0,X,X, 0xF0,0x46]
M4C = [M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,M, M,M,X,X, M,M,X,X, M,M,M,M, M,M,X,X, M,M,X,X, M,M,M,M, M,M,X,X, M,M,X,X, M,M]
# needle_4: multipoint table (seg +58, off +54)
N4 = [0x98,0x24, 0xA8,0x34, 0x00,0xA2, 0x10,0xB3, 0x26,0xFA,0xFF,0xFF, 0x36,0xFB,0xFF,0xFF, 0x3D,0x08, 0xE6,0xF4,X,X, 0xE0,0x05, 0xF6,0xF4,X,X, 0xF6,0xF5,X,X, 0xDB,0x00, 0xE6,0xF4,X,X, 0xE6,0xF5,X,X, 0xF6,0xF4,X,X, 0xF6,0xF5,X,X, 0xDB,0x00, 0xE6,0xF4,X,X, 0xE6,0xF5,X,X, 0xF6,0xF4,X,X, 0xF6,0xF5,X,X, 0xDB,0x00]
M4 = [M,M, M,M, M,M, M,M, M,M,M,M, M,M,M,M, M,M, M,M,X,X, M,M, M,M,X,X, M,M,X,X, M,M, M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,M, M,M,X,X, M,M,X,X, M,M,X,X, M,M,X,X, M,M]
N4AA = [0x9A,0x89,X,X, 0xF6,0x8E,X,X, 0x0D,X, 0xE0,0x84, 0xF6,0xF4,X,X, 0xF2,0xF4,X,X, 0x5C,0x24, 0xD7,0x60,X,X, 0xD4,0xA4,X,X, 0xD4,0xB4,X,X, 0xCC,0x00, 0xF6,0xFA,X,X, 0xF6,0xFB,X,X]
M4AA = [M,M,X,X, M,M,X,X, M,X, M,M, M,M,X,X, M,M,X,X, M,M, M,M,X,X, M,M,X,X, M,M,X,X, M,M, M,M,X,X, M,M,X,X]

rom = ROMImage.load(sys.argv[1]); d = bytes(rom.data); size = rom.size
u16 = lambda o: d[o] | d[o+1] << 8
u32 = lambda o: struct.unpack_from('<I', d, o)[0]
def file_off(page, off): return ((page * 0x4000 + (off & 0x3FFF)) & 0xFFFFF) & (size - 1)
def wsum(s, e):
    t = 0
    for i in range(s // 2, e // 2 + 1): t += u16(2 * i)
    return t & 0xFFFFFFFF
S = Searcher(rom)
ident = identify(rom); print("ID:", ident.vmecuhn, ident.ssecuhn, ident.version_string)
for name, n, m in [("2b", N2B, M2B), ("2", N2, M2), ("3", N3, M3), ("3b", N3B, M3B), ("4b", N4B, M4B), ("4c", N4C, M4C), ("4", N4, M4), ("4aa", N4AA, M4AA)]:
    hits = S.search(n, m); print(f"needle_{name}: {len(hits)} hit(s) at {[hex(h.file_offset) for h in hits[:4]]}")
h = S.search_one(N2B, M2B); nreg = {0xA2:1,0xA4:2,0xA6:3}.get(d[h.file_offset+27], 0) if h else 0
print("region count byte:", hex(d[h.file_offset+27]) if h else None, "->", nreg)
h = S.search_one(N2, M2); regions = []
if h:
    a = h.file_offset; seg = u16(a+14); seg2 = u16(a+40)
    lo_t, hi_t = file_off(seg, u16(a+18)), file_off(seg, u16(a+22))
    elo_t, ehi_t = file_off(seg, u16(a+44)), file_off(seg, u16(a+48))
    print(f"needle_2 seg=0x{seg:X}/0x{seg2:X} start tbl lo=0x{lo_t:X} hi=0x{hi_t:X} end tbl lo=0x{elo_t:X} hi=0x{ehi_t:X}")
    total = 0
    for i in range(nreg):
        s = (u16(hi_t+i*8) << 16 | u16(lo_t+i*8)); e = (u16(ehi_t+i*8) << 16 | u16(elo_t+i*8))
        sf, ef = s & 0xFFFFF & (size-1), e & 0xFFFFF & (size-1)
        ws = wsum(sf, ef); total = (total + ws) & 0xFFFFFFFF; regions.append((sf, ef))
        print(f"  region {i+1}: phys 0x{s:X}-0x{e:X} file 0x{sf:X}-0x{ef:X} sum=0x{ws:08X}")
    print(f"  main calc = 0x{total:08X}  ~ = 0x{~total & 0xFFFFFFFF:08X}")
h = S.search_one(N3, M3)
if h:
    a = h.file_offset; p = file_off(u16(a+10), u16(a+14))
    print(f"needle_3 stored @0x{p:X}: 0x{u32(p):08X} ~0x{u32(p+4):08X}")
h = S.search_one(N3B, M3B)
if h:
    a = h.file_offset; seg = u16(a+36); lo, hi = file_off(seg, u16(a+40)), file_off(seg, u16(a+44))
    print(f"needle_3b seg=0x{seg:X} lo=0x{lo:X} hi=0x{hi:X}: norm=0x{u16(hi)<<16|u16(lo):08X} comp=0x{u16(hi+4)<<16|u16(lo+4):08X}")
cnt = None
h = S.search_one(N4B, M4B)
if h: cnt = u16(h.file_offset+42); print("mp count (4b):", cnt)
else:
    h = S.search_one(N4C, M4C)
    if h: cnt = u16(h.file_offset+44); print("mp count (4c):", cnt)
h = S.search_one(N4, M4)
if h and cnt:
    a = h.file_offset; tbl = file_off(u16(a+58), u16(a+54)); print(f"mp table @0x{tbl:X} (seg 0x{u16(a+58):X} off 0x{u16(a+54):X})")
    good = bad = 0
    for j in range(cnt):
        b = tbl + j*16; s, e, st, sc = u32(b), u32(b+4), u32(b+8), u32(b+12)
        sf, ef = s & 0xFFFFF & (size-1), e & 0xFFFFF & (size-1)
        ws = wsum(sf, ef) if sf < ef else 0
        ok = (ws == st) and ((~ws & 0xFFFFFFFF) == sc); good += ok; bad += (not ok)
        if j < 4 or not ok: print(f"  blk {j+1:2d}: 0x{sf:06X}-0x{ef:06X} stored=0x{st:08X} calc=0x{ws:08X} {'OK' if ok else 'BAD'}")
    print(f"  multipoint: {good} ok, {bad} bad of {cnt}")
