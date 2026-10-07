# Checksum rebuild — handoff notes (October 2026)

State of the work to replace `meseventool/checksum.py` with a real port of
the ME7 checksum algorithms. Written for the session that picks this up.
Read `docs/review_findings_2026-10.md` items A1–A3 first for why.

`tools/checksum_probe.py <rom.bin>` runs every needle below against a ROM and
prints what it finds. It is the fastest way to re-establish state. It needs
no tool changes; it imports `meseventool` for `ROMImage` and `Searcher` only.

## Validated against real ROMs (all three agree)

ROMs used, from `Z:\Archive\Google Drive\home flashing\ME7` (same files are
in the user's Google Drive `home flashing/ME7` folder):

| File | ECU | Firmware | Notes |
|---|---|---|---|
| `032rn.bin` | 06A906032RN | 42/1/ME7.5/120/4013.00 | crc32 `0x99e4ee7c`; multipoint block 1 stale by 1, so probably not pristine |
| `18CM.Bin` | 4B0906018CM | 40/1/ME7.5/3/4012.31 | crc32 `0x5193a0f3`; everything verifies |
| `adam.bin` | 06A906032HN | 40/1/ME7.5/5/4019.02 | before `me7sum`; crc32 `0x89ef4e68` |
| `adamfixed.bin` | 06A906032HN | same | after `me7sum`; crc32 `0x2594ba5f` |

**Acceptance test for the port:** `fix()` on `adam.bin` must produce
`adamfixed.bin` byte for byte. They differ in exactly 36 bytes (list below).

### Layer 1 — main checksum (from `reference/me7romtool/fixsums.c`)

All offsets are into the needle hit. Needle/mask bytes are in
`tools/checksum_probe.py` (`N2B`, `N2`, `N3`, `N3B`), copied from
`reference/me7romtool/needles.c`.

- **Region count** — `needle_2b`, one hit. Byte at `+27`: `0xA2`→1,
  `0xA4`→2, `0xA6`→3 regions. All three ROMs: `0xA4` → 2.
- **Region table** — `needle_2`, one hit. EXTP page = u16 at `+14`. Start
  table: lo word operand at `+18`, hi word operand at `+22`. End table: lo at
  `+44`, hi at `+48` (same page). Each operand is a 16-bit mem address;
  file offset = `(page * 0x4000 + (operand & 0x3FFF)) & 0xFFFFF`. Region *i*
  reads `u16(hi_table + i*8) << 16 | u16(lo_table + i*8)`, then
  `& 0xFFFFF` for the file offset.
  All three ROMs: region 1 = `0x00000–0x0FBFF`, region 2 = `0x20000–0xFFFFF`.
- **Sum** — `CalcChecksumBlk`: `for i in range(start//2, end//2 + 1): sum +=
  u16(2*i)`, mod 2^32. Inclusive of the word containing `end`. The current
  `calc_sum_block` in `checksum.py` gets this wrong for even `end`.
- **Stored** — `needle_3`, one hit. Page = u16 at `+10`, offset = u16 at
  `+14` → file offset of `[sum u32][~sum u32]`. All three ROMs: `0xFFFE0`.
  `needle_3b` also hits (page `+36`, lo `+40`, hi `+44`) and agrees;
  the reference treats it as a fallback, verify-only.
- Confirmed exact: RN `0x43D04E38`, 18CM `0x00903D56`, HN `0x43C5BB56`.

### Layer 2 — multipoint block sums (from `fixsums.c`)

- **Count** — `needle_4b`, one hit: u16 at `+42`. All three ROMs: 66.
  Fallback `needle_4c`: u16 at `+44` (no hits here).
- **Table** — `needle_4`, one hit: page = u16 at `+58`, offset = u16 at
  `+54` → file offset. All three ROMs: `0x1FBDE` (page `0x207`, offset
  `0x3BDE`). Entries are 16 bytes: `[start u32][end u32][sum u32][~sum u32]`,
  addresses are physical (`& 0xFFFFF` → file). Blocks 1–2 and 3–4 cover the
  same ranges (`0x0–0x3FFF`, `0x4000–0x7FFF`); the rest step through the ROM
  in 16 KB blocks.
- **Sum** — same 16-bit word sum as layer 1, **not CRC32** (the current
  module uses `zlib.crc32`, which is wrong). `sum = 0` when `start >= end`.
- Fallback variant `needle_4aa` (split hi/lo tables, skip first 32 bytes,
  count − 2) is in the reference; no hits on these ROMs; untested.
- 18CM and adamfixed: 66/66 OK. adam.bin: blocks 7, 8, 10 bad (the tuned
  areas), which `me7sum` fixed.

### Layer 3 — CRC32 (NOT in me7romtool; `me7sum` does it) — UNRESOLVED

`adam.bin → adamfixed.bin` changes three 4-byte values at `0x090B4E`,
`0x090B54`, `0x090B5A` (each followed by a `RETS`, so they are embedded
constants, not a table). Decoded from the HN ROM at `0x90C32–0x91520`:

- CRC32 routine at `0x90C32` (matches `crc32_needle` in `needles.c`);
  polynomial table at file `0x2775A`, standard reflected table
  (`0x77073096, 0xEE0E612C, ...`). Update step is standard reflected CRC32.
  Running value lives in RAM `[0xF9E2]/[0xF9E4]`; it is seeded with ONES
  (`0x914E0`), so standard `zlib.crc32` semantics.
- Compare at `0x910F0`: computed value XOR `0xFFFFFFFF`, then
  `mov r4,#0x0B4E; mov r5,#0x0089; calls 0,0x7ED8` reads the stored u32 at
  far `0x890B4E` (file `0x90B4E`) and subtracts. Same pattern at `0x91188`
  (`0x890B54`) and `0x91210` (`0x890B5A`). So a needle for the stored
  location: `E6 F4 lo hi E6 F5 seg 00 DA 00 D8 7E` with the far pointer
  `seg:lo hi`, file offset `(seg << 16 | off) & 0xFFFFF`.
- Four chunked loops call the routine (`0x90ED6`, `0x90F74`, `0x91016`,
  `0x910B4`), each in `0xB0`-byte chunks from `r9:r8` up to a fixed end:

  | loop | start (`mov r8/r9`) | end immediate | file range as decoded |
  |---|---|---|---|
  | 1 | `0x810002` | `0x813FFE` | `0x10002–0x13FFE` |
  | 2 | `0x814252` | `0x817F4E` | `0x14252–0x17F4E` |
  | 3 | `0x818192` | `0x81FBDC` | `0x18192–0x1FBDC` |
  | 4 | `0x826A00` | `0x82FFFC` | `0x26A00–0x2FFFC` |

  A fifth call at `0x914F2` CRCs 10 bytes at `0x8183C8` (something else).
- **What was tried and did not match** the stored values (`0xF32D6517`,
  `0x54B731DB`, `0x990BFF49` in adamfixed): every contiguous range at
  256-byte granularity over the whole ROM, both inits, value and complement;
  and every concatenation of the four decoded ranges with ±2-byte shifts.
  So either the start/end decoding is off (the loop code at `0x90E96` is
  only partly decoded — check whether `r8` is reloaded from `[0xF5F2]`/
  `[0xF5F6]` between chunks and whether the chunk math is `end - 0xB0`), the
  regions skip bytes inside the range, or the stored values are for ranges
  that also include RAM-side data. **Next step:** disassemble `0x90E60–
  0x91120` properly (Ghidra with the C167 processor; `tools/ghidra_import.py`
  exists) rather than hand-decoding, or diff against `me7sum`'s source
  (nyet/me7sum on GitHub, `DoCRCs`), which implements exactly this.
- Multipoint block 39 (`0x90000–0x93FFF`) contains the stored CRCs, and main
  region 2 contains both, so **fix order must be CRC32 → multipoint → main**,
  then re-verify.

### Bytes `me7sum` changed in `adam.bin` (36 total)

```
0x01FC46, 0x01FC4A              block 7  sum/~sum   (0x1FBDE + 6*16 + 8/12)
0x01FC56-58, 0x01FC5A-5C        block 8
0x01FC76-77, 0x01FC7A-7B        block 10
0x01FE46-48, 0x01FE4A-4C        block 39 (re-summed after the CRCs changed)
0x090B4E-51, 0x090B54-57, 0x090B5A-5D   three CRC32 values
0x0FFFE0-E2, 0x0FFFE4-E6        main sum/~sum
```

## Plan for the module (not started — no code written yet)

1. New `checksum.py` keeping the public API (`ChecksumManager.verify/fix`,
   `ChecksumResult.main/multi/all_ok/summary`, `calc_sum_block`,
   `MainChecksumResult`, `MultiBlock`, `MultiChecksumResult`,
   `ChecksumChecker`, `verify_and_fix`, `_le16/_le32`) so `app/main.py` and
   `tests/test_core.py` keep working. Add a `crc` layer alongside `main` and
   `multi`. Drop `CAL_CKSUM_OFFSET`, `calc_crc32`-as-multipoint and the
   bogus `NEEDLE_CRC32` / `NEEDLE_MAIN_CKSUM` in `needle.py` (only
   `checksum.py` and `__init__.py` reference them).
2. `fix()` order: CRC32 → multipoint → main, then return a fresh `verify()`
   (the current code sets `all_ok` True by construction).
3. If a needle is missing, report **not verified**, never "OK". Refuse to
   fix a layer whose storage location wasn't found.
4. Tests: the synthetic builders in `tests/test_checksum.py:8`,
   `tests/test_integration.py:42`, `tests/test_patches.py:2351` and `:2566`
   all use the invented `cal_page + 0xFFF8` layout and must be replaced with
   one shared builder that embeds the needles and tables. Add real-ROM tests
   under the existing `/mnt/user-data/uploads` skip pattern: verify on 18CM
   and adamfixed, and `fix(adam) == adamfixed`.
5. GUI (`app/main.py`): warn on Save when `verify().all_ok` is False
   (review item E1), and show the CRC layer in the info panel.
