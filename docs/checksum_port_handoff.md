# Checksum rebuild — notes (October 2026)

`meseventool/checksum.py` is a port of the ME7 checksum algorithms from
`reference/me7romtool/fixsums.c` (layers 1–2) and ME7Sum (layer 3,
`nyetwurk/ME7Sum`, `FindMainCRC*`/`DoMainCRCs`).  Status: **done and
validated**; `fix(adam.bin)` reproduces `me7sum`'s `adamfixed.bin` byte for
byte.  This file records what was validated and how, for the next person
who touches it.  Review items A1–A3 and E1 in `review_findings_2026-10.md`
are closed by this work.

`tools/checksum_probe.py <rom.bin>` prints everything the module finds in a
ROM (read-only).  `tests/test_checksum_real.py` runs the checks below when
the corpus is present (`$MESEVENTOOL_ROM_DIR`, `/mnt/user-data/uploads`, or
the archive path in that file).

## ROMs used

From `Z:\Archive\Google Drive\home flashing\ME7` (also in Google Drive
`home flashing/ME7`):

| File | ECU | Firmware | Notes |
|---|---|---|---|
| `032rn.bin` | 06A906032RN | 42/1/ME7.5/120/4013.00 | crc32 `0x99e4ee7c`; multipoint block 1 stale by 1, so not pristine; CRC layer OK |
| `18CM.Bin` | 4B0906018CM | 40/1/ME7.5/3/4012.31 | crc32 `0x5193a0f3`; everything verifies; **no CRC32 layer** |
| `adam.bin` | 06A906032HN | 40/1/ME7.5/5/4019.02 | before `me7sum`; crc32 `0x89ef4e68` |
| `adamfixed.bin` | 06A906032HN | same | after `me7sum`; crc32 `0x2594ba5f` |

## Layer 1 — main checksum (`fixsums.c`)

All needles live in `checksum.py` with their operand offsets.

- **Region count** — `NEEDLE_MAIN_COUNT` (me7romtool `needle_2b`), byte at
  `+27`: `0xA2`→1, `0xA4`→2, `0xA6`→3.  All three ROMs: 2.
- **Region table** — `NEEDLE_MAIN_REGIONS` (`needle_2`).  EXTP page at
  `+14`; start-table lo/hi operands at `+18`/`+22`, end-table at `+44`/`+48`.
  File offset of an operand = `(page*0x4000 + (op & 0x3FFF)) & 0xFFFFF`.
  Entry *i* is 8 bytes apart: `u16(hi + 8i) << 16 | u16(lo + 8i)`, then
  `& 0xFFFFF`.  All three ROMs: `0x00000–0x0FBFF` and `0x20000–0xFFFFF`.
- **Sum** — `for i in range(start//2, end//2 + 1): sum += u16(2*i)` mod
  2^32, i.e. inclusive of the word containing `end`.
- **Stored** — `NEEDLE_MAIN_STORE` (`needle_3`): page `+10`, offset `+14`
  → `[sum u32][~sum u32]`.  All three ROMs: `0xFFFE0`.  (`needle_3b` agrees
  and is not needed.)
- Region 2 contains the stored pair.  That is fine: `lo(x)+hi(x)+lo(~x)+hi(~x)`
  is always `2*0xFFFF`, so a consistent pair is a fixed point.  `fix()`
  iterates (max 3 passes) so a *corrupted* pair also converges.
- Confirmed exact: RN `0x43D04E38`, 18CM `0x00903D56`, HN `0x43C5BB56`
  (before) / `0x43C6CC9A` (after).

## Layer 2 — multipoint block sums (`fixsums.c`)

- **Count** — `NEEDLE_MULTI_COUNT` (`needle_4b`): u16 at `+42`.  Fallback
  `NEEDLE_MULTI_COUNT_ALT` (`needle_4c`): u16 at `+44` (untested, no hits here).
  All three ROMs: 66.
- **Table** — `NEEDLE_MULTI_TABLE` (`needle_4`): page `+58`, offset `+54`
  → `0x1FBDE`.  Entries are 16 bytes `[start u32][end u32][sum u32][~sum u32]`,
  physical addresses (`& 0xFFFFF`).  Blocks 1–2 and 3–4 repeat `0x0–0x3FFF`
  and `0x4000–0x7FFF`; the rest step through the ROM in 16 KB blocks.
- **Sum** — same word sum as layer 1, **not CRC32**.  `0` when `start >= end`.
- Block 10 (`0x1C000–0x1FFFF`) contains the table and block 39
  (`0x90000–0x93FFF`) contains the layer-3 constants, so `fix()` loops until
  a pass writes nothing.
- `needle_4aa` (split hi/lo tables) from the reference is not ported: no
  hits on any ROM here.

## Layer 3 — chained main CRC32 (ME7Sum)

Not in me7romtool.  Resolved by reading ME7Sum: the four regions are not
CRC'd independently, they are **chained**.

- **Pre-block** — `NEEDLE_CRC_PRE`: `mov r12,#lo; mov r13,#seg; mov r14,#len`
  → 10 bytes at `0x183C8–0x183D1`.  Its CRC32 (zlib semantics) seeds region 1.
- **Regions** — `NEEDLE_CRC_START` (`mov r8,#lo; mov r9,#seg; mov r4,mem`)
  and `NEEDLE_CRC_END` (`addc r9,r11; mov r4,#lo; mov r5,#seg`), paired in
  order.  HN/RN: `0x10002–0x13FFE`, `0x14252–0x17F4E`, `0x18192–0x1FBDC`,
  `0x26A00–0x2FFFC` (inclusive).
- **Stored** — `NEEDLE_CRC_STORE` (`mov mem,r5; mov r4,#lo; mov r5,#seg;
  calls`): exactly three hits, `0x90B4E`, `0x90B54`, `0x90B5A`.  With four
  regions, region 3 has **no** stored value and region 4 uses the third slot.
- **Chain** — `c1 = crc32(pre); c1 = crc32(r1, seed=c1); c2 = crc32(r2,
  seed=c1); c3 = crc32(r3, seed=c2); c4 = crc32(r4, seed=c3)`; stored are
  `c1, c2, c4`.  Verified on adamfixed (`F32D6517 54B731DB 990BFF49`) and
  032rn (`F1E314F2 AF26BF31 4434C0EF`).
- Operand decode is ME7Sum's `FindData`: `hi<<16 | lo`, or `hi<<14` when
  `hi & 0xFE00` (page form); must land inside `0x800000 + size`.
- 18CM has no store hits and no pre-block: the layer is reported "not
  present", exactly as ME7Sum skips `DoMainCRCs` there.  Store hits without
  region hits (or ≠3 store hits) is reported "not verified" and never fixed.

## Fix order and acceptance

`fix()` runs CRC32 → multipoint → main, then returns a fresh `verify()`.
Layers whose needles are missing are never written.

The 36 bytes `me7sum` changed in `adam.bin`, all reproduced:

```
0x01FC46, 0x01FC4A              block 7  sum/~sum   (0x1FBDE + 6*16 + 8/12)
0x01FC56-58, 0x01FC5A-5C        block 8
0x01FC76-77, 0x01FC7A-7B        block 10 (contains the table)
0x01FE46-48, 0x01FE4A-4C        block 39 (contains the CRC constants)
0x090B4E-51, 0x090B54-57, 0x090B5A-5D   c1, c2, c4
0x0FFFE0-E2, 0x0FFFE4-E6        main sum/~sum
```

## Tests

- `tests/synthetic_rom.py` builds ROMs with the real needles and tables in
  the last 4 KB (two main regions, four multipoint blocks, no CRC layer) and
  computes the sums with independent loops.  Every synthetic checksum test
  (`test_checksum.py`, `test_integration.py`, `test_patches.py`) uses it.
  The only area a real ME7.5 layout leaves unchecked is `0xFC00–0x1FFFF`,
  which is where "patch outside the checksum" tests now put their needle.
- `tests/test_checksum_real.py`: 18CM and adamfixed verify on all layers,
  adam shows blocks 7/8/10 and three CRCs bad, `fix(adam) == adamfixed`,
  fix is idempotent, 032rn's CRC layer verifies.

## GUI

`app/main.py` shows all three layers in the ROM Info panel ("not verified"
in red when a needle is missing, "not present" when a layer is legitimately
absent), and Save / Save As verify first and ask before writing a file whose
checksums are not all OK.
