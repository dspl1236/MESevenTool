# Whole-tool review — October 2026

Five focused reviews of the codebase, each reading the real code and running
it where possible. Findings are grouped by severity for the tool's purpose:
detect the ECU from its ROM, apply patches safely, and let the stock ECU run
as a standalone.

Tick items off as they are fixed. "Confirmed" means the reviewer reproduced
it by running code; "plausible" means it was read from the source only.

---

## A. Stop-ship: can brick an ECU or silently corrupt a file

- [x] **A1. Checksum module does not implement the ME7 algorithm**
  (`meseventool/checksum.py:188-221`, confirmed). It sums the last 64 KB and
  stores `[sum, ~sum]` at `cal_page + 0xFFF8`. The vendored reference
  (`reference/me7romtool/fixsums.c`) instead needle-locates a region table
  (1–3 start/end ranges) and the storage address; none of those needles exist
  in `needle.py`. The code itself notes the real 06A906032DL checksum is at
  `0x0FFFE0`. On every real ROM, `verify()` reports BAD and `fix()` writes
  8 meaningless bytes while leaving the real checksum stale.
  *Fixed Oct 2026: rebuilt from `fixsums.c` + ME7Sum, all three layers
  needle-located; `fix(adam.bin)` reproduces `me7sum`'s output byte for
  byte. See `docs/checksum_port_handoff.md`.*
- [x] **A2. Multipoint "fix" overwrites the CRC32 polynomial table**
  (`checksum.py:278-291`, confirmed). It uses `NEEDLE_CRC32`, which in the
  reference locates the 256-entry CRC lookup table, not the multipoint block
  list (`needle_4/4aa/4b`). Fed a standard CRC table, `fix()` changed 510
  bytes of it. The walk also has no entry count (`:300-337`) and wrote 252
  bytes past a 2-entry table. Blocks use `zlib.crc32`; the reference uses the
  16-bit word sum.
- [x] **A3. Fallback checksum scan is dead code** (`checksum.py:249-251`,
  confirmed). The standard-offset branch returns unconditionally, so the scan
  that would find `0x0FFFE0` never runs.
- [x] **A4. `MapDef.write` has no bounds check and grows the ROM**
  (`meseventool/maps.py:137-141`, confirmed). Slice-assigning past the end of
  a `bytearray` appends. A 256 KB ROM with a map at `0x3FFFC` becomes
  `0x40004` bytes; saving gives an invalid-size file. Use `rom.write()`.
  *Fixed Oct 2026: `MapDef.write` bounds-checks and goes through `rom.write()`.*
- [x] **A5. `rom.write()` with a negative offset inserts bytes**
  (`meseventool/rom.py:174-180`, confirmed). Only `end > size` is checked.
  Reject `offset < 0`. *Fixed Oct 2026.*
- [x] **A6. Fallback map widths are wrong for several maps**
  (`maps.py:197-199, 292-336, 490-503`, confirmed against
  `reference/xdf_tables.json`). KFLBTS, LAMFA and KFDLULS (1.8T) and KFDLULS
  (2.7T) are declared U16 but the XDF says U8. Reads show garbage; a write
  clobbers the bytes after the map. Hits every part number without an exact
  XDF match (e.g. 06A906032HN, every 2.7T PN except 8D0907551M/557P).
  *Fixed Oct 2026: all four are U8; `tests/test_maps.py` now checks every
  fallback map's width and shape against `xdf_tables.json`.*

## B. Wrong patch on the wrong ECU

- [ ] **B1. Universal fixed-address patches fire on 256 KB AGU ROMs**
  (`patches.py:1491-1559`, `applies_to=set()`, confirmed). On
  `PROFILE_AGU_ME71` (cal page at `0x30000`) address `0x0181A2` is code.
  Gate on ROM size or family.
- [ ] **B2. 4B0906018 codeword labels are shifted one byte**
  (`patches.py:1434, 1448, 1462`). XDF and `docs/me7_stable_codeword_block.md`
  put CDHSVE=`0x0181A1`, CDKAT=`0x0181A2`, CDKVS=`0x0181A3`. The 4B0 entries
  call `0x0181A1` "CDKAT", `0x0181A2` "CDKVS", `0x0181A3` "CDKVS2" (not a real
  name). So "Catalyst Monitor Disable CDKAT (4B0906018)" clears CDHSVE, and
  `0x0181A2` is written by two entries with different meanings. Needs an
  18CM ROM to settle which is right; the universal entry matches the docs.
- [ ] **B3. Two CDNWS entries at `0x0181AF` with different stock bytes**
  (`patches.py:1606-1654`, confirmed). Both are gated `{me7.5, 1.8t}`; after
  applying either, both show PATCHED, and reverting through the other writes
  the wrong stock byte (0x03 vs 0x02).
- [ ] **B4. IMMO-OFF ME7.1.1 gated backwards** (`patches.py:1804`, confirmed).
  `applies_to={"me7.1"}`; the "prefix check" the comment mentions doesn't
  exist. Applicable on 2.7T/VR6 ME7.1, not on the 4Z7/4D1 ME7.1.1 ECUs it was
  written for.
- [ ] **B5. Three patches can never be offered** (`patches.py:791, 1365,
  1603`, confirmed). `applies_to={"me7.1","me7.1.1","2.7t"}` is an AND-set and
  no profile carries both `me7.1` and `me7.1.1`. Split into two entries.
- [ ] **B6. ESKONF "newer" excludes the ROMs it claims** (`patches.py:951`).
  Requires `me7.1`, so NOT_APPLICABLE on ME7.1.1 4Z7 and V8.
- [ ] **B7. Readiness Flags patch is DL-specific but gated to all ME7.5 1.8T**
  (`patches.py:891`, confirmed). The anchor matches every fw40 ROM; the notes
  admit the offsets differ per version.
- [ ] **B8. 2.7T Knock Retard alt-needle is too generic** (`patches.py:741`,
  confirmed on a synthetic site). Three `MOV R4,mem` in a row reports PATCHED
  and `revert()` writes a store into foreign code.
- [ ] **B9. CDEHFM reports PATCHED on stock DL/RN/LP** (`patches.py:1561`),
  which already hold 0x00.

## C. Detection: wrong profile, wrong family

- [ ] **C1. Unreachable profiles** (`profiles.py:258-285, 599`, confirmed).
  `PROFILE_AMU` and `PROFILE_AUQ` share prefixes with `PROFILE_AWP`, listed
  first, so they're never returned. `8N0906032` in AUQ looks like a typo.
- [ ] **C2. ME7.1.1 ROMs land on ME7.1 profiles** (confirmed). 022906032
  CS/CP/EG/BN/GE and 4D0907559E (all ME7.1.1 in `known_roms`) get the `me7.1`
  tag, so the ME7.1.1 Vmax patch ("confirmed on 022906032CS/EG") is
  NOT_APPLICABLE on R32 ROMs.
- [ ] **C3. Known ROMs with no profile:** 8L0906018 (5 entries), 8E0906018,
  4D0907560.
- [ ] **C4. DPP fallback is meaningless** (`profiles.py:627-651`, confirmed).
  Every profile's DPP1 range overlaps; with no version string any 2.7T/VR6/V8
  ROM falls to the ME7.5 1.8T profile.
- [ ] **C5. Engine-code scan takes the first run with any 3-letter code**
  (`ecu_id.py:183-196`, confirmed). Codes like `ACK`, `APP`, `AUG`, `BES`
  collide with ordinary text; an early spurious hit beats the real descriptor
  and blocks the part-number-suffix fallback.
- [ ] **C6. Part-number vote prefers the suffix-less base** (`ecu_id.py:156-
  162`, confirmed). `06A906032` and `06A906032DL` are different keys; the
  base often wins, which defeats part-number gating.
- [ ] **C7. `identify_from_filename` only matches `0[6-9][A-Z]…`**
  (`ecu_id.py:245`, confirmed). `8D0907551M_oem.bin`, `4Z7907551AA.bin`,
  `022906032CP.bin` return nothing.
- [ ] **C8. Version-string regex hard-codes `40|42|43|44`** (`ecu_id.py:48`).
  A `41/1/ME7.1/…` string is missed and degrades ME7.1 vs ME7.5 detection.
- [ ] **C9. `is_me75`/`is_me71` are size-based** (`ecu_id.py:103-110`). 1 MB
  ME7.1/ME7.1.1 ROMs report `is_me75=True`. Only used in tests today.
- [x] ~~Unknown ROMs were offered every ME7.5-tagged patch~~ — fixed:
  `profile.unknown` makes everything NOT_APPLICABLE and the GUI loads no maps.
- [x] ~~`get_profile()` ignored the part number for gating~~ — fixed.

## D. Patch mechanics

- [ ] **D1. "Apply to both sites" patches only write the first hit**
  (`patches.py:1186-1209` universal Vmax — comment says `all_hits=True`, it
  isn't; scalars `:1860` Hard Rev Limit and `:1963` NKILL, confirmed).
  `ScalarPatchDef.write` uses `search_one`. Leaves an inconsistent limiter
  pair.
- [ ] **D2. Two scalars resolve to the same byte** (`patches.py:1928` Hard Rev
  Limit alt path and `:1999` Fuel Cut Resume, confirmed). One name is wrong.
- [x] **D3. `write_u16/u32` silently truncate out-of-range values**
  (`rom.py:182-198`, confirmed). A bad scaling result becomes a plausible
  wrong value. *Fixed Oct 2026: `write_u16/u32` raise `ValueError` instead.*
- [ ] **D4. `dpp1_to_file` double-corrects** (`needle.py:222-234`,
  `dpp.py:26-35`, plausible). Subtracts a page and masks; correct only
  because ME7 always has dpp0 = dpp1 − 1.
- [ ] **D5. Form-1 DPP needle is not valid C167** (`needle.py:154-180`). It
  never matches; every DPP test exercises only this fake form, so the real
  Form-2 path is untested.
- [ ] **D6. `rom.read()` past end returns short data** while `read_u16/u32`
  raise (`rom.py:153-155`).

## E. GUI: losing or mis-saving work

- [x] **E1. Save / Save As / close-Save write a stale checksum with no warning**
  (`app/main.py:1243-1266, 1317-1330`, confirmed). No save path calls
  `verify()`. (Moot until A1 is fixed, then essential.)
  *Fixed Oct 2026: Save and Save As verify first and ask before writing a
  ROM whose checksums are bad or unverified.*
- [ ] **E2. Opening another ROM while dirty discards edits silently**
  (`main.py:1159-1175`, confirmed).
- [ ] **E3. Analysis exception leaves the window half-switched**
  (`main.py:1172-1175` vs `1222-1227`, confirmed). `self._rom/_searcher/
  _profile` are replaced before the `try`; on failure the widgets still
  describe the old ROM while Save writes the new one. Assign after success.
- [ ] **E4. Failed patch apply leaves the checkbox out of sync**
  (`main.py:1297-1298`, confirmed). Call `refresh_states()` on failure.
- [ ] **E5. `refresh_states` never updates scalar spinners; scalar writes
  don't refresh at all** (`main.py:471-486, 1300-1310`).
- [ ] **E6. Close accepts even when the save failed or was cancelled**
  (`main.py:1325-1330`, confirmed). Edits are lost.
- [ ] **E7. Save As doesn't retarget later Saves** (`rom.py:212-216`,
  `main.py:1254-1264`, confirmed). The next Ctrl+S overwrites the original
  file, often the stock dump.
- [ ] **E8. Cell display `.2f` is coarser than the raw step** (`main.py:767,
  825-831`, confirmed for KFMIOP/KFLBTS/LAMFA). Re-committing the displayed
  text shifts the raw value by up to ±3 counts. Unedited cells round-trip
  exactly.
- [ ] **E9. `_parse_math` drops the additive offset** in `"scale * X+ offset"`
  form (`xdf.py:120-134`, confirmed). IAT axes read 0…191 instead of −48…143.
- [ ] **E10. XDF map order is non-deterministic** (`xdf.py:296-302`,
  confirmed). `hash(name) % 100` changes per process; the GUI's map buttons
  shuffle between runs.
- [ ] **E11. 512 KB ECUFlash extracts aren't rebased** — XDF/fallback offsets
  are 1 MB-based, so they're `0x80000` too high on a 512 KB file
  (`xdf.py` docstring vs `maps.py`; plausible).

## F. Build and packaging

- [ ] **F1. CI build ignores the spec and bundles no data files**
  (`.github/workflows/ci.yml:35-51` vs `meseventool_gui.spec:8-11`). The EXE
  has no `reference/xdf_tables.json`; `XDFLoader()` raises, `profiles.py:197`
  swallows it, and every ROM silently gets the PROVISIONAL fallback map set,
  including the ones with confirmed XDF offsets. "Verify EXE" only checks the
  file exists.
- [ ] **F2. CI lints only `meseventool/`, not `app/`.**

## G. KWPBridge live data (plausible; `kwpbridge` not installed here)

- [ ] **G1.** `kwpbridge_running()` and `KWPClient.connect()` run on the UI
  thread every 1–2 s (`kwp.py:168-189`, `main.py:954-956`); a TCP timeout
  stalls the UI each tick while KWPBridge is absent.
- [ ] **G2.** After a drop, `_poll` builds a new `KWPClient` without
  disconnecting the old one; a client leaks per reconnect.
- [ ] **G3.** `KWPMonitor.stop()` is never called on close.
- [ ] **G4.** `LiveValues` cell indices are hard-coded to group 0 and nothing
  maps them to ROM axis units yet.

## H. Tests that can't catch the above

- ~~The checksum tests build ROMs with the same invented formula the checker
  uses, so they're tautological. No multipoint coverage.~~ *Fixed Oct 2026:
  `tests/synthetic_rom.py` embeds the real needles and tables;
  `tests/test_checksum_real.py` runs against the real corpus when present.*
- All 149 skipped tests are the real-ROM tests; they have never run in CI
  because the corpus isn't in the repo. They are the only tests that would
  have caught A1/A2.
- `CONFIRMED` is documented as "tested on real ROM files", but these entries
  cite no patched reference: P1681, both CDNWS ME7.5 entries, MAF Delete
  LP/18CM and SL DSG, Knock Retard 2.7T, SAP CDSLS 4B0, KRMXN, Overrev
  Protection, NKILL, Knock Retard 1.8T.

---

## Suggested order

1. **A1–A3** (rebuild checksums from `fixsums.c`, validate on one real stock
   dump) — nothing saved by the tool is flashable until this is done.
2. **A4–A6, D3** — bounds and width bugs that corrupt files.
3. **B1–B5, C1–C2** — patches on the wrong ECU, and the detection order that
   causes it.
4. **E1–E7** — losing or mis-saving work.
5. **F1** — the shipped EXE silently lacks the XDF data.
6. The rest.
