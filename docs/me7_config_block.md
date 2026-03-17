# ME7 Stable Configuration Block — `0x018194–0x0181C4`

## Summary

The 49-byte codeword block at flat ROM offset `0x018194`–`0x0181C4` is
**address-stable across all known ME7.x variants** on the Infineon C167 platform.
The same named variables appear at the same offsets regardless of SW version,
engine displacement, or model year.

Validated against:
| Family | ECU | SW versions | Status |
|---|---|---|---|
| ME7.5 1.8T | 06A906032DL, GG, GH, RT, SK, SL, SM | 7 variants | ✓ confirmed |
| ME7.1 2.7T | 8D0907551 A–T, 4B0907551, 4Z7907551 | 57 ROMs | ✓ confirmed |
| ME7.1.1 V8 | 4D1907558 A–F, EU3 | 7 ROMs | ✓ confirmed |

## Why It's Stable

The C167 firmware references these codewords via **literal 16-bit SFR-style
addresses** compiled into the code region. Because the firmware binary is
fixed across all variants (only the calibration tables change per tune), the
linker places this block at a fixed address in every build. It is part of the
**EEPROM shadow / diagnostic configuration area**, not a calibration table.

## Codeword Map

All offsets are flat ROM file offsets (base = 0x000000 in a 1MB image).

```
Offset      Name        Bytes  Description
─────────────────────────────────────────────────────────────────────
0x018194    CDAGR         1    EGR diagnosis enable (0=off, 1=on)
0x018195    CDAGRL        1    EGR leak diagnosis
0x018196    CDATR         1    Catalyst temperature diagnosis
0x018197    CDATS         1    Catalyst temperature sensor diagnosis
0x018198    CDBKVP        1    Brake vacuum pump diagnosis
0x018199    CDDSBKV       1    Double secondary air valve diag
0x01819A    CDDST         1    Double secondary air temperature diag
0x01819B    CDEGFE        1    EGR flow efficiency diagnosis
0x01819C    CDEHFM        1    HFM/MAF sensor diagnosis
0x01819D    CDGGGTS       1    Throttle position sensor diagnosis
0x01819E    CDHSH         1    Upstream O2 sensor diagnosis (B1)
0x01819F    CDHSHE        1    Upstream O2 sensor heater (B1)
0x0181A0    CDHSV         1    Upstream O2 sensor voltage diag
0x0181A1    CDHSVE        1    Upstream O2 sensor voltage extended
0x0181A2    CDKAT         1    Catalytic converter diagnosis (0=off, 1=on)
0x0181A3    CDKVS         1    Knock sensor diagnosis
0x0181A4    CDLASH        1    Lambda control adaptive (short-term)
0x0181A5    CDLATP        1    Lambda control adaptive (part load)
0x0181A6    CDLATV        1    Lambda control adaptive (full load)
0x0181A7    CDLDP         1    Load calculation diagnosis
0x0181A8    CDLLR         1    Lambda limit diagnosis
0x0181A9    CDLSA         1    Lambda signal amplitude diagnosis
0x0181AA    CDLSH         1    **Rear O2 sensor diagnosis** (0=off, 1=on)
0x0181AB    CDLSHV        1    Rear O2 interchange diagnosis
0x0181AC    CDLSV         1    Rear O2 sensor voltage diagnosis
0x0181AD    CDLSVV        1    Rear O2 sensor voltage extended
0x0181AE    CDMD          1    Mixture formation diagnosis
0x0181AF    CDNWS         1    Secondary air system diagnosis
0x0181B0    CDSLS         1    **SAP pump diagnosis** (0=off, 1=on)
0x0181B1    CDTANKL       1    Tank leak diagnosis (EVAP)
0x0181B2    CDTES         1    EVAP purge diagnosis
0x0181B3    CDWVERAD      1    Wheel speed diagnosis
0x0181B4    CWADRES       1    CAN address configuration
0x0181B5    CWDLSU        1    Wideband lambda sensor config (0=NB, 1=WB)
0x0181B6    CWERFIL       1    Fuel filter config
0x0181B7    CWGRABH       1    Brake intervention config
0x0181B8    CWKMMILSCT    1    MIL activation config
0x0181B9    CWKONABG      1    Output diagnosis enable
0x0181BA    CWKONFLS      1    Flash programming enable
0x0181BB    CWKONLS       1    **O2 sensor count** (0x33=dual bank, 0x03=single)
0x0181BC    CWLSHA        1    Lambda adaptive long-term enable
0x0181BD    CWMDAPP       1    MAP sensor application config
0x0181BE    CWOBD         1    OBD mode (0x03=OBD-II)
0x0181BF    CWSCTMDE      1    SCT mode
0x0181C0    CWSLS         1    Secondary air system config
0x0181C1    CWTF          1    Tank flush config
0x0181C2    CWUHR         1    CAN baud rate (0x04=500kbps)
0x0181C3    NSWO1         1    O2 readiness warm-up RPM threshold (low)
0x0181C4    NSWO2         1    O2 readiness warm-up RPM threshold (high)
```

## Emissions Delete Patches

Because these addresses are stable, all emissions codewords can be patched
**without anchor search** — simple absolute-address writes:

| Target | Address | Stock → Patch | Effect |
|---|---|---|---|
| Rear O2 sensor diag | `0x0181AA` | `0x01 → 0x00` | Suppress P0136/P0141 etc. |
| Rear O2 interchange | `0x0181AB` | `0x01 → 0x00` | Suppress P0141/P0161 |
| SAP pump diag | `0x0181B0` | `0x01 → 0x00` | Suppress P0410/P1411 |
| EVAP purge diag | `0x0181B2` | `0x01 → 0x00` | Suppress P0441/P0446 |
| Cat efficiency diag | `0x0181A2` | `0x01 → 0x00` | Suppress P0420/P0430 |
| Dual-bank O2 count | `0x0181BB` | `0x33 → 0x11` | Single bank only |

Note: for 2.7T biturbo (dual bank), CWKONLS = 0x33 stock. Patching to 0x11
disables bank 2 O2 monitoring. Combined with the ESKONF heater disable
(anchor-based, see patches.py), this fully silences rear O2 codes on both banks.

## Cross-Reference to XDF

All addresses above are confirmed against `reference/xdf_map_8D0907551M.json`
(8D0907551M-20190711.xdf, mesim translator). The XDF names match the
Bosch ME7 Funktionsrahmen variable names verbatim.

## Source

Derived by cross-referencing:
1. XDF parse of `8D0907551M-20190711.xdf` (s4wiki)
2. Byte-for-byte verification in `8D0907551M-0001.bin` (physical chip read)
3. Cross-validation across 64 ROMs from the s4wiki stock corpus
4. Three-family stability check: 06A906032 (ME7.5), 8D0907551 (ME7.1), 4D1907558 (ME7.1.1)
