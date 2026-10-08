# ME7 Emissions Codeword Block — Layouts by Software Build

> **Correction (October 2026).** This block is *not* one layout. The byte
> order depends on the Bosch software build named in the ROM's version string
> (e.g. `40/1/ME7.5/3/4019.20` → build 4019), and the "universal" addresses
> below are only right for the ME7.1 2.7T builds they were taken from.
> `meseventool/codewords.py` is the authoritative table; every codeword patch
> resolves its address through it and is withheld on unverified builds
> (review item A7). Evidence: files.s4wiki.com `defs/` XDFs (06A906032HS/LP,
> 8N0906018CB, 8D0907551M/F/G/H/K, 4Z7907551R/AA, 4D1907558; all BASEOFFSET
> 0) cross-checked against the stock bytes of ~290 corpus images.

## Layouts

| Layout | Builds (version-string field 5) | ECUs seen | CDKAT | CDLSH | CDLSHV | CDLSV | CDNWS | CDSLS | CDTES | CDEHFM |
|---|---|---|---|---|---|---|---|---|---|---|
| `me71`  | `40/1/ME7.1/5/` 6001, 6005, 6010, 6025 | 8D0907551 G/H/J/L/M/N/T/AA, 4B0907551 M/R/S/T/AA/AH/AL, 4Z7907551 –/D/E/K/L/M | 0x1A2 | 0x1AA | 0x1AB | 0x1AC | 0x1AF | 0x1B0 | 0x1B2 | 0x19C |
| `4b0`   | ME7.5 4012.xx, 4016.xx | 4B0906018 (not R), 06B906018, 8E0909518, 8E0906018 | same as `me71` (validated on 18CM tuned files; CDKVS=0x03 at 0x1A3) | | | | | | | |
| `06a`   | ME7.5 4013, 4018, 4019, 4518 (field 3 = 120) | 06A906032, 8N0906018, 8L0906018 | **0x1A3** | **0x1AB** | absent | 0x1AC | 0x1AF | 0x1B0 | 0x1B2 | 0x19C |
| `me711` | ME7.1.1 6030, 6011, 8001, 8542; ME7.1 6024 (RS4 K/Q) | 4Z7907551 N/Q/R/S/AA, 4D1907558 –/B/C/F, 4D0907559E, 4D0907560AE/AF, 8D0907551K/Q | **0x1A0** | **0x1A8** | 0x1A9 | 0x1AA | **0x1AD** | 0x1AE | 0x1B0 | 0x19A |

The `06a` layout inserts **CDHSVSA at 0x0181A2** (between CDHSVE and CDKAT)
and has no CDLSHV, so everything from CDKAT to CDLSVV sits one byte later
than in `me71` while CDNWS onward lines up again. The `me711` layout is the
whole `me71` block two bytes earlier (0x0181AF is CDTANKL there, 0x0181B2 is
CWADRES — the value 2 seen on every late Allroad is CWADRES, not CDTES).

Independent confirmation on 06A: two copies of the 06A906032DL v360227 dump
differ in exactly one byte, 0x0181A3, and the one with 0x00 is a catalyst
delete; the HN "no cat" and FC "SAI and rear O2 delete" tunes clear 0x1A3,
0x1A5 and 0x1AB (CDKAT, CDLASH, CDLSH in the `06a` layout).

**Unverified builds (no layout, codeword patches withheld):** early 2.7T
`42/1/ME7.1/5/` 6001/6005/6010 (8D0907551 A/B/D, 4B0907551 F/G/K/L — their
bytes fit none of the above), 8D0907551F (its XDF is shifted five bytes),
06A906032 X505R (SL/SK/SM: CDNWS-like 3 at 0x1B1) and 4220 (DS/MS),
4B0906018R, 4D1907558D, 4D0907560BR, every VR6 (022906032/021906018), the
Touareg/Phaeton and W12 builds, and the Golf 5 R32 S1103A builds, where
0x018194 holds code, not codewords.

---

The remainder of this document is the original ME7.1 2.7T (`me71`) map.

## Complete Codeword Map

All addresses confirmed from `8D0907551M-20190711.xdf` and cross-validated against
the three ECU families above. Values shown are from `8D0907551M-0001.bin`.

| Address  | Name       | Value | Meaning (stock) |
|----------|------------|-------|-----------------|
| 0x018194 | CDAGR      | 0x00  | AGR diagnosis disabled |
| 0x018195 | CDAGRL     | 0x00  | AGR diagnosis (lean) disabled |
| 0x018196 | CDATR      | 0x01  | ATR diagnosis enabled |
| 0x018197 | CDATS      | 0x01  | ATS diagnosis enabled |
| 0x018198 | CDBKVP     | 0x00  | — |
| 0x018199 | CDDSBKV    | 0x00  | — |
| 0x01819A | CDDST      | 0x00  | — |
| 0x01819B | CDEGFE     | 0x01  | EGR position feedback enabled |
| 0x01819C | CDEHFM     | 0x01  | HFM (MAF sensor) diagnosis enabled |
| 0x01819D | CDGGGTS    | 0x01  | — |
| 0x01819E | CDHSH      | 0x01  | Lambda sensor heater B1 diagnosis enabled |
| 0x01819F | CDHSHE     | 0x01  | Lambda sensor heater B1 after-cat enabled |
| 0x0181A0 | CDHSV      | 0x01  | Lambda sensor B1 voltage diagnosis enabled |
| 0x0181A1 | CDHSVE     | 0x01  | Lambda sensor B1 after-cat voltage enabled |
| 0x0181A2 | CDKAT      | 0x01  | **Catalyst diagnosis enabled** |
| 0x0181A3 | CDKVS      | 0x01  | — |
| 0x0181A4 | CDLASH     | 0x01  | Lambda sensor B1 enabled |
| 0x0181A5 | CDLATP     | 0x01  | Lambda sensor B1 phase enabled |
| 0x0181A6 | CDLATV     | 0x01  | Lambda sensor B1 voltage enabled |
| 0x0181A7 | CDLDP      | 0x01  | — |
| 0x0181A8 | CDLLR      | 0x01  | — |
| 0x0181A9 | CDLSA      | 0x01  | Lambda sensor B1 active enabled |
| 0x0181AA | CDLSH      | 0x01  | **Rear O2 sensor B1 heater diagnosis enabled** |
| 0x0181AB | CDLSHV     | 0x01  | **Rear O2 sensor B1 interchange enabled** |
| 0x0181AC | CDLSV      | 0x01  | Rear O2 sensor B1 voltage enabled |
| 0x0181AD | CDLSVV     | 0x00  | — |
| 0x0181AE | CDMD       | 0x01  | — |
| 0x0181AF | CDNWS      | 0x01  | NWS (secondary air) enabled — varies |
| 0x0181B0 | CDSLS      | 0x00  | **SAP diagnosis (0=disabled in 6sp M-box)** |
| 0x0181B1 | CDTANKL    | 0x01  | Tank leakage (EVAP) enabled |
| 0x0181B2 | CDTES      | 0x01  | EVAP purge diagnosis enabled |
| 0x0181B3 | CDWVERAD   | 0x00  | — |
| 0x0181B4 | CWADRES    | 0x02  | Address mode — varies by variant |
| 0x0181B5 | CWDLSU     | 0x00  | — |
| 0x0181B6 | CWERFIL    | 0x00  | — |
| 0x0181B7 | CWGRABH    | 0x00  | — |
| 0x0181B8 | CWKMMILSCT | 0x00  | — |
| 0x0181B9 | CWKONABG   | 0x01  | Output diagnosis enable |
| 0x0181BA | CWKONFLS   | 0x00  | — |
| 0x0181BB | CWKONLS    | 0x33  | **O2 sensor count (0x33=dual bank, 0x11=patched)** |
| 0x0181BC | CWLSHA     | 0x00  | — |
| 0x0181BD | CWMDAPP    | 0x00  | — |
| 0x0181BE | CWOBD      | 0x03  | OBD mode — stable across all families |
| 0x0181BF | CWSCTMDE   | 0x01  | — |
| 0x0181C0 | CWSLS      | 0x00  | — varies by variant |
| 0x0181C1 | CWTF       | 0x00  | — |
| 0x0181C2 | CWUHR      | 0x04  | — stable |
| 0x0181C3 | NSWO1      | 0x71  | — varies |
| 0x0181C4 | NSWO2      | 0xAF  | — stable across 2.7T |

## Emissions Delete Patch Addresses

These are the addresses to target for clean emissions deletes with no CEL:

| Codeword | Address  | Stock | Delete value | Effect |
|----------|----------|-------|--------------|--------|
| CDLSH    | 0x0181AA | 0x01  | 0x00         | Disable rear O2 heater diagnosis |
| CDLSHV   | 0x0181AB | 0x01  | 0x00         | Disable rear O2 interchange diagnosis |
| CDLSV    | 0x0181AC | 0x01  | 0x00         | Disable rear O2 voltage diagnosis |
| CDSLS    | 0x0181B0 | 0x01  | 0x00         | Disable SAP diagnosis |
| CDTES    | 0x0181B2 | 0x01  | 0x00         | Disable EVAP purge diagnosis |
| CDKAT    | 0x0181A2 | 0x01  | 0x00         | Disable catalyst diagnosis |
| CWKONLS  | 0x0181BB | 0x33  | 0x11         | Change dual-bank to single-bank O2 |

These are `OffsetPatchDef` candidates using the ESKONF block or adjacent codewords
as anchors, avoiding the address-float problem entirely by using content-addressable
lookup against the stable block values.

## Cross-Family Stability Table

78 of 159 single-byte codewords in the block are stable (same value) across at least
2 of the 3 tested ECU families. 37 are identical across all three (ALL):

Confirmed ALL-stable (value identical across 8D ME7.1, 4B ME7.1, 06A ME7.5):
`CDAGR`, `CDAGRL`, `CDBKVP`, `CDDSBKV`, `CDDST`, `CDGGGTS`, `CDHSH`, `CDHSHE`,
`CDHSV`, `CDHSVE`, `CDKAT`, `CDKVS`, `CDLASH`, `CDLATP`, `CDLATV`, `CDLDP`,
`CDLLR`, `CDLSA`, `CDLSH`, `CDLSHV`, `CDLSV`, `CDLSVV`, `CDMD`, `CDTANKL`,
`CDTES`, `CDWVERAD`, `CWDLSU`, `CWGRABH`, `CWKMMILSCT`, `CWKONFLS`, `CWMDAPP`,
`CWOBD`, `CWSCTMDE`, `CWTF`, `CWUHR`, `NSWO2`, `AccPedalThreshold`

## Source

- XDF: `8D0907551M-20190711.xdf` (TunerPro format, from s4wiki.com)
- Parsed map: `reference/xdf_tables.json` and `reference/xdf_map_8D0907551M.json`
- Validation: MESevenTool corpus analysis across 64 s4wiki stock ROMs (Oct 2020)
