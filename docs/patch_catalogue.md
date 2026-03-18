# MESevenTool Patch Catalogue

**34 confirmed patches | 5 confirmed scalars | all CONFIRMED against real ROM corpus**

Last updated: March 2026

---

## Codeword block overview

All `Fixed` address patches target the stable ME7 codeword block at `0x018190–0x0181C4`.
This block is identical in structure across all ME7.1, ME7.1.1, and ME7.5 variants —
and confirmed present in: 1.8T, 2.7T, VR5 20V, VR6 24V BDF, R32/TT 3.2 fw6432,
Passat 2.8V6 fw6428, V8 fw8000/fw8001/fw8542, AFP 12V VR6.

Setting a codeword byte from `0x01` to `0x00` disables that monitoring function.
Some ECUs ship with certain codewords already `0x00` from the factory when the
monitored hardware was never fitted to that market/variant.

---

## Performance patches (5)

### Vmax Speed Limiter Disable — three variants

All three are confirmed needle patches that zero the speed limiter comparison value.
The ME7.1 and ME7.1.1 variants have different instruction sequences at the limiter
function; both are required in the corpus to cover the full 2.7T/VR6/V8 family.

| Patch | Applies to | Notes |
|---|---|---|
| Vmax (2.7T ME7.1) | 8D0907551xx early | `0x01 8A nn nn` needle |
| Vmax (ME7.1.1 / V8 RS4) | 8D0907551 late, 4B, 4Z7, 4D1907558xx V8, R32, TT 3.2 fw6432, Passat 2.8V6 fw6428 | Updated instruction sequence |
| Vmax (ME7.5 — all variants) | All 06A906032xx, 4B0906018xx | Code-immediate variant, single needle |

### Knock Retard Disable — KRMXN Zero

Sets the maximum knock retard table (`KRMXN`) to all zeros, preventing the ECU
from retarding timing in response to knock events. Use when running aggressive
ignition maps that self-manage timing, or when the knock sensor has been removed.

| Patch | Applies to |
|---|---|
| KRMXN Zero (needle, 2.7T ME7.1/ME7.1.1) | All 2.7T S4/A6/allroad, all VR6 24V BDF, VR5 AQN, AFP 12V, V8 4.2, R32/TT fw6432 |

### 5th-Gear Torque Mode Disable

- **Fixed `0x00881D` → `0x0F` → `0x00`**
- Disables 5th-gear torque reduction. Applies universally to all ME7.5 1.8T.
- Pre-patched in many tuned files.

---

## Ignition patches (2)

### Knock Retard Disable (code injection)

Two needle variants that disable the knock retard *code path* (vs the table zero
above). Applied when needing to hard-disable the retard routine entirely rather
than just reducing its magnitude.

| Patch | Applies to |
|---|---|
| Knock Retard Disable (needle) | ME7.5 1.8T (all variants) |
| Knock Retard Code Disable (2.7T ME7.1) | 2.7T ME7.1 early firmware |

---

## Emissions patches (19)

### Rear O2 system — full delete (3 fixed + 2 needle + 1 offset)

The complete rear O2 delete requires patches from both the codeword block
and the cal area. The three fixed-address codewords are universal; the offset
and ESKONF patches target the monitoring thresholds and heater control.

| Patch | Type | Address | Applies to |
|---|---|---|---|
| CDLSH — Rear O2 Heater Diag Disable | Fixed | `0x0181AA` | All ME7 |
| CDLSHV — Rear O2 Interchange Diag Disable | Fixed | `0x0181AB` | All ME7 |
| CDLSV — Rear O2 Voltage Diag Disable | Fixed | `0x0181AC` | All ME7 |
| Rear O2 Monitor Threshold (DL fw4019) | Offset | `−16` from PN | 06A906032DL |
| Rear O2 Monitor Threshold (LP fw4013) | Offset | `−20` from PN | 06A906032LP |
| Rear O2 OBD Readiness Flags | Needle | `40/1/ME7.5` | ME7.5 1.8T |
| Rear O2 Sensor Diag Disable | Needle | `FF FF FF FF 00 00 01 01` | 2.7T ME7.1/ME7.1.1 |

**ESKONF (rear O2 heater — 3 variants):**

| Patch | Anchor bytes | Applies to |
|---|---|---|
| ESKONF newer (0F 01 05) | `0x0F 0x01 0x05` | All ME7.1/ME7.1.1/ME7.5 post-2000 |
| ESKONF older-06 | `0x06 0x02 0xA8` | Early 2.7T ME7.1 |
| ESKONF older-05 | `0x05 0x02 0xA8` | Early 2.7T ME7.1 |

### Catalyst monitor disable (2 fixed)

| Patch | Address | Applies to |
|---|---|---|
| CDKAT (universal ME7) | `0x0181A2` | All ME7 — preferred |
| CDKAT (4B0906018) | `0x0181A1` | 4B0906018 A6/Passat 1.8T only |

Note: The 4B0906018-specific variant exists at `0x0181A1` due to a one-byte
offset in that ECU's codeword layout. Use the universal version (`0x0181A2`)
for all other platforms.

### SAP (Secondary Air Pump) disable (2 fixed + 1 needle)

| Patch | Type | Applies to | Notes |
|---|---|---|---|
| CDSLS (ME7.5 1.8T) | Fixed `0x0181B0` | All ME7.5 1.8T | Standard |
| CDSLS (4B0906018) | Fixed `0x0181B0` | 4B0906018 A6/Passat | Same address, separate confirmation |
| SAP MSLUB Airflow Table Zero | Needle | 2.7T ME7.1 | Zeros the SAP airflow model to prevent P0410 |

The VR6 24V BDF, AFP 12V, and RS6 4.2TT ECUs have CDSLS already `0x00` from
factory — no SAP was fitted to those variants/markets.

### EVAP disable (2 fixed)

| Patch | Address | Applies to |
|---|---|---|
| EVAP Purge Diag Disable | `0x0181B2` | ME7.5 1.8T |
| EVAP Diag Disable (4B0906018) | `0x0181B2` | 4B0906018 (same address, confirmed separately) |

The RS6 4.2TT and some Euro-spec VR6/V8 variants already have CDTES=0x00 from factory.

### Knock / MAF sensor diagnosis disable (2 fixed)

| Patch | Address | Applies to | Notes |
|---|---|---|---|
| CDKVS — Knock Sensor Monitor | `0x0181A3` | 4B0906018 | Single sensor variant |
| CDKVS2 — Knock Sensor Variant | needle | 4B0906018 | Dual sensor variant |
| CDEHFM — MAF Sensor Diag Disable | `0x01819C` | SL DSG + 4B0906018 | Required with MAF Delete on these ECUs |

---

## Fuelling patches (6)

### MAF Delete / Alpha-N (5 needle variants)

Redirects the load calculation from MAF-based to throttle angle (Alpha-N) by
patching the load redirect call. Required when the MAF sensor is physically
removed. Five variants cover all known ME7.5 1.8T firmware sub-families:

| Patch | Firmware | Anchor |
|---|---|---|
| MAF Delete (06A fw4019) | DL/HN/HS Bosch | |
| MAF Delete (RN/LP fw4013) | RN/LP VDO | |
| MAF Delete (LP/18CM fw4013/4012) | LP/4B0906018 | |
| MAF Delete (SL DSG X505R) | SL auto | |
| MAF Delete (fw4013 alt FA1E/1F) | Some VDO variants | |

Always apply CDEHFM (`0x01819C`) alongside MAF Delete on SL DSG and 4B0906018 ECUs.

### MAF Sensor Diagnosis Disable (fixed `0x01819C`)

See Emissions section above. Required companion to MAF Delete on SL/4B variants.

---

## Diagnostics patches (2)

### P1681 Immobiliser Databus CEL Disable

- Needle patch, ME7.1.1 only.
- Disables the IMMO3 databus fault code that triggers when an ECU is swapped
  into a car where the cluster IMMO code doesn't match.
- Allows used ECU installation without cluster re-coding (the IMMO light may
  still flash but the CEL does not set).

### VVT Cam Position Monitor Disable — CDNWS (fixed `0x0181AF`)

**Who needs this:** Any ME7.1/ME7.1.1 engine with variable cam timing where
the cam position solenoids have been deleted, bypassed, or have failed.

**DTCs prevented:** P0010/P0011 (intake cam timing over-retarded/advanced, bank 1/2)
and P0020/P0021 (exhaust cam equivalent).

**Stock value = `0x01` (monitoring active) on:**
- 2.7T S4/A6/allroad — late variants (8D0907551M+, 4B0907551AA+, 4Z7907551x)
- VR6 24V BDF (06A906032AG/AK) — fw6228
- VR6 R32/TT 3.2 fw6432 (022906032EG/GE)
- Passat 2.8V6 AMX fw6428 (022906032CS)
- Touareg 3.2 C1103A (022906032FT)
- V8 4.2L fw8000 (4D0907558/559G)

**Already `0x00` from factory (patch not needed) on:**
- AFP 12V VR6 (021906018xx) — no cam phasing on the 12V head
- Early 2.7T (8D0907551A–F) — pre-VVT firmware calibration
- RS4 4.2 V8 (4D1907558xx) — different cam monitoring strategy
- V8 fw8001 (4D0907559E) and S4 B7 4.2 C1105B (8E0907560x) — already disabled
- RS6 4.2TT (4D1907558F fw8542) — fixed cam timing, no phasing hardware

---

## Scalar patches (5)

All 5 scalars apply to ME7.5 1.8T only. They are read/write operations on
16-bit values in the calibration area, not binary on/off patches.

| Scalar | Description | Typical stock value |
|---|---|---|
| Hard Rev Limit | Primary RPM cut | ~7200 RPM |
| Overrev Protection RPM | Secondary soft-limiter | ~7544 RPM |
| Hard Rev Limit (alt path) | Redundant limiter | matches primary |
| Emergency RPM Cut (NKILL) | Absolute safety cut | ~8500 RPM |
| Fuel Cut Resume RPM | Decel fuel cut re-entry | ~1200 RPM |

---

## ECU family coverage summary

| Platform | ME7 version | Patches applicable |
|---|---|---|
| 1.8T ME7.5 (06A906032xx) | ME7.5 | All 34 patches, all 5 scalars |
| 1.8T 4B0906018xx | ME7.5 | 28–30 patches (no 1.8T needle overlap) |
| 2.7T ME7.1 (early 8D) | ME7.1 | ~18 patches |
| 2.7T ME7.1.1 (late 8D/4B/4Z7) | ME7.1.1 | ~22 patches |
| AFP 12V VR6 (021906018xx) | ME7.1 fw6228 | ~14 patches (KRMXN, ESKONF, codewords) |
| BDF 24V VR6 (06A906032AG/AK) | ME7.1 fw6228 | ~14 patches |
| VR5 20V AQN/AZX (066906032xx) | ME7.1 fw5423 | ~14 patches + Vmax |
| Golf R32/TT 3.2 fw6432 (022906032EG/GE) | ME7.1.1 | ~14 patches + Vmax + CDNWS |
| Passat 2.8V6 fw6428 (022906032CS) | ME7.1.1 | ~12 patches + Vmax + CDNWS |
| V8 4.2 fw8000 (4D0907558/559G) | ME7.1 | ~10 patches + Vmax |
| V8 4.2 fw8001/fw8542 (4D0907559E/4D1907558xx) | ME7.1.1 | ~10 patches + Vmax |
| S4 B7 4.2 C1105B (8E0907560x) | ME7.1.1 | ~12 patches + Vmax |
