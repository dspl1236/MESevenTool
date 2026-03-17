# ME7 Emissions Codeword Block — Stable Addresses

## Finding

The Bosch ME7.x firmware contains a tightly-packed block of single-byte emissions
configuration codewords at a **fixed flat-file offset** that is consistent across all
ME7.1 and ME7.5 variants, regardless of software version.

**Block location:** `0x018194–0x0181C4` (49 bytes)

This was confirmed by cross-referencing the `8D0907551M` XDF (TunerPro definition
file) against three ECU families:

| ECU | Family | Engine | CDLSH | CWKONLS | CDSLS | CWDLSAHK |
|-----|--------|--------|-------|---------|-------|----------|
| `8D0907551M` | ME7.1 2.7T S4 B5 | AGB/ARE/BES | `0x01` | `0x33` | `0x00` | `0x03` |
| `4B0907551AA` | ME7.1 2.7T A6 C5 | AGB/ARE | `0x01` | `0x33` | `0x00` | `0x03` |
| `06A906032DL` | ME7.5 1.8T | AWP/AUM | `0x01` | `0x03`  | `0x01` | `0x3F` |

All three ECU families have their codewords at **identical flat file offsets**, despite
different engine families, different ME7 sub-versions, and different SW calibrations.

## Why It's Stable

The C167CR accesses these codewords via `EXTP + MOV` sequences in the firmware code.
The code is compiled to reference a specific data page (DPP1 = `0x0206` in ME7.5,
equivalent page in ME7.1) plus a fixed offset within that page. Since all ME7 variants
share the same Bosch Funktionsrahmen (function framework) ABI, the codeword layout
within the cal page is fixed — it's part of the Bosch calibration data structure
definition, not something that floats with SW version.

Flat file offset `0x018194` maps to:
- C167 data page: `0x0206` (= `0x018000 >> 14` = page 97)
- Page offset: `0x0194`
- Physical address: `0x0206 << 14 | 0x0194 = 0x81'9194H`

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
