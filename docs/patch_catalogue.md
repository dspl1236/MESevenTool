# MESevenTool — Patch Catalogue

Complete listing of all confirmed patches and scalars as of the current build.
All entries are `confidence = "CONFIRMED"` — every one has corpus evidence.

---

## How needles work

Each patch is found by searching the ROM for a sequence of C167 instruction bytes
(the "needle") that is unique to the target code location. Wildcard mask bytes
(`0x00` in the mask) allow variable operands (RAM addresses, immediate values)
that shift between firmware versions. Once the needle hits, a fixed offset into
the match gives the patch site.

This means **no hardcoded addresses** — the same patch definition works on
fw4012, fw4013, fw4019 and every minor revision without modification.

---

## PatchDef types

| Type | How it works |
|---|---|
| `PatchDef` | Needle search → fixed byte offset → write stock/patch bytes |
| `OffsetPatchDef` | Search for anchor string → add integer offset → write byte |
| `MultiOffsetPatchDef` | Anchor string → list of independent offsets, each patched separately |
| `FixedAddressPatchDef` | Direct ROM address — used where the address is provably constant across all variants |
| `ScalarPatchDef` | Needle → read/write a 16-bit numeric value with scale factor |

---

## 28 Confirmed patches

### Diagnostics

#### P1681 Immobiliser Databus CEL Disable (ME7.1.1)
- **Target:** 2.7T ME7.1.1 (4Z7, late 8D, 4D1 RS4/S8)
- **Method:** PatchDef — JMPR UGE → JMPR UC in codeword check
- **Effect:** Suppresses DTC P1681 (immobiliser databus fault) when running ECU standalone
- **Confirmed:** 4Z7907551AA stock → 4Z7907551AA-disable-P1681 patched

---

### Emissions

#### Rear O2 Monitor Threshold / Rear O2 Monitor Threshold (LP fw4013)
- **Target:** ME7.5 1.8T
- **Method:** OffsetPatchDef — anchor on ECU part-number string ("06A906032DL" or "06A906032LP"), fixed offset to threshold byte
- **Effect:** Raises the secondary O2 voltage comparison threshold, allowing rear O2 removal without continuous fault
- **Confirmed:** DL stock vs DL tuned; LP stock separately anchored (different PN, offset -20 from standard)

#### Rear O2 OBD Readiness Flags
- **Target:** ME7.5 1.8T DL/HN (fw4019)
- **Method:** MultiOffsetPatchDef — anchor "40/1/ME7.5"; three independent codeword bytes
- **Effect:** Clears O2 monitor readiness bits so OBD never reports rear O2 as incomplete
- **Note:** DL/HN only; RN/LP/SL use different values at the same offsets

#### ESKONF Rear O2 Heater Disable (three variants)
- **Target:** 2.7T ME7.1 (all 57 corpus files)
- **Method:** MultiOffsetPatchDef — anchor on ESKONF codeword pattern
- **Effect:** Disables the rear O2 heater diagnostic circuit check
- **Three variants:** `0F 01 05` (newer, universal), `06 02 A8` (older, 17 files), `05 02 A8` (oldest, 13 files)

#### SAP MSLUB Airflow Table Zero (2.7T)
- **Target:** 2.7T ME7.1 (not 4D1 V8 — no SAP fitted)
- **Method:** OffsetPatchDef — anchor on SAP flow table header
- **Effect:** Zeros the SAP airflow contribution table, preventing SAP pump activation

#### SAP Diagnosis Disable (ME7.5 1.8T)
- **Target:** ME7.5 1.8T DL (06A906032DL) — SAP-equipped ECUs only
- **Method:** OffsetPatchDef — CDSLS codeword, anchor on PN string
- **Effect:** CDSLS → 0x00, disables secondary air pump diagnosis fault

#### EVAP Purge Diagnosis Disable (ME7.5 1.8T)
- **Target:** ME7.5 1.8T DL — EVAP-equipped ECUs only
- **Method:** OffsetPatchDef — CDTES codeword
- **Effect:** Disables EVAP canister purge diagnosis fault

#### 4B0906018 fixed-address patches (5 patches: CDSLS, CDKAT, CDKVS, CDKVS2, CDTES)
- **Target:** 4B0906018CM (A6/Passat 1.8T)
- **Method:** FixedAddressPatchDef — addresses 0x0181A1–0x0181B2
- **Effect:** Individual codeword byte writes — SAP, catalyst monitor, knock sensor monitor, knock sensor variant, EVAP diagnosis
- **Confirmed:** 18CM_stock → 18CM_uni2 / 18CM_evap

#### Rear O2 Sensor Diagnosis Disable (2.7T ME7.1/ME7.1.1)
- **Target:** 2.7T all 57 corpus files
- **Method:** OffsetPatchDef — CDLSH codeword, anchor on ECU PN string
- **Effect:** Disables rear O2 sensor fault diagnosis

---

### Fuelling

#### MAF Delete / Alpha-N load redirect (5 variants)
- **Target:** ME7.5 1.8T — all known firmware builds
- **Method:** PatchDef — needle finds the `FAxxx` load-source selector opcode in the MAF-to-load calculation code
- **Effect:** Redirects ECU load calculation from MAF (air mass) to Alpha-N (throttle angle × RPM), enabling MAF-off operation
- **Two-byte patch** changes load-source register reference:

| Variant | Needle stock | → Patch | Firmware |
|---|---|---|---|
| 06A fw4019 DL/HN | `FA18/FA19` | `FA22/FA23` | fw4019 |
| RN fw4013 | `FA48/FA49` | `FA22/FA23` | fw4013 |
| LP/18CM fw4013/4012 | `FA34/FA35` | `FA22/FA23` | fw4013/fw4012 |
| SL DSG X505R | `FA4A/FA4B` | `FA22/FA23` | X505R |
| fw4013 alt (20th/rn_base) | `FA48/FA49` | `FA1E/FA1F` | fw4013 |

---

### Ignition

#### Knock Retard Disable (ME7.5 1.8T)
- **Target:** ME7.5 1.8T
- **Method:** PatchDef — code needle
- **Effect:** Prevents timing retard from accumulating after knock events

#### Knock Retard Code Disable (2.7T ME7.1)
- **Target:** 2.7T ME7.1 — 30/57 corpus files (ME7.1 only; ME7.1.1 uses different code)
- **Method:** PatchDef — needle `F2 F4 xx xx F6 F4 xx xx F2 F4 xx xx 68 44`
  - `F6 F4` = `MOV [RAM], R4` — STORE retard to accumulator
  - Patch changes to `F2 F4` = `MOV R4, [RAM]` — LOAD instead of STORE
  - `68 44` (`SUB R4, R4`) is the unique discriminator distinguishing this site from other F6 F4 instances
- **Effect:** Retard accumulator is never written — knock events are detected but timing is not pulled
- **Coverage:** 8D A/B/D/G/H/J/L/M/N, 4B A/F/G/K/L/R/S/T, 4Z7 B–K

---

### Performance

#### Knock Retard Disable — KRMXN Zero (2.7T ME7.1/ME7.1.1)
- **Target:** 2.7T all 57 corpus files
- **Method:** OffsetPatchDef — anchor `0x14` × 16 (unique in all 57 corpus files)
- **Effect:** Zeros the KRMXN maximum knock retard table — limits retard to 0° per knock event while keeping knock detection active
- **Note:** Cal approach (safer than code patch). Does not affect knock detection, only the retard magnitude.

#### Vmax Speed Limiter Disable (2.7T ME7.1)
- **Target:** 2.7T ME7.1 (8D/4B/4Z7 early)
- **Method:** PatchDef — 3-hit needle `E6 FD A8 61 E6 FE 9A 02`
- **Effect:** Sets speed limit comparison to 0xFFFF (no limit)

#### Vmax Speed Limiter Disable (2.7T ME7.1.1 / V8 RS4)
- **Target:** 2.7T ME7.1.1 (4Z7 late, 4D1)
- **Method:** PatchDef — ATOMIC prefix variant needle

#### Vmax Speed Limiter Disable (ME7.5 — all variants)
- **Target:** ME7.5 1.8T — all firmware variants
- **Method:** PatchDef — code-immediate needle `E6 FD A8 61 E6 FE 9A 02 DA 00`
- **Effect:** Sets both speed limit immediates to `0xFFFF` (no limit)
- **⚠️ 2 hits per file** — apply twice: first `detect()` returns site 1, second returns site 2, third returns PATCHED

#### 5th-Gear Torque Mode Disable (ME7.5 1.8T universal)
- **Target:** ME7.5 1.8T — 06A906032 (Golf/Jetta/TT) and 4B0906018 (A6/Passat)
- **Method:** FixedAddressPatchDef — 0x00881D: `0x0F → 0x00`
- **Effect:** Index 5 of the 8-element gear-mode table — 5th gear stops using Mode 0x0F (economy torque cap) and uses Mode 0 instead. Removes steady-highway-speed power reduction.
- **Address rock-solid** across fw4012/4013/4019

---

## 5 Confirmed scalars — ME7.5 1.8T RPM limiter stack

All use `scale = 0.75 RPM/bit`, `size = 2`, `big_endian = False`. The constant `0x4A` low byte is the family signature — only the high byte changes.

### Hard Rev Limit
- **Needle:** `F7 F8 xx xx E1 08 [val] F4 xx 49 81 3D 08`
- **Hits:** 2 per file (two call sites, always identical value)
- **DL stock:** raw `0x254A` = **7160 RPM**
- **Applies to:** All MT and DSG variants

### Hard Rev Limit — alt path
- **Needle:** `48 42 EA 30 E0 03 24 8F xx xx E1 08 [val] F4`
- **Hits:** 1 per file
- **Stable prefix** `48 42 EA 30 E0 03 24 8F` is constant across all variants including SL DSG
- **DL stock:** raw `0x254A` = **7160 RPM**

### Overrev Protection RPM
- **Needle:** `F6 F4 xx xx 8A xx 02 xx [val] 16 xx F2 F4`
- **Hits:** 1 per file (MT only — absent in SL DSG X505R)
- **DL stock:** raw `0x2A9A` = **8180 RPM** (~1020 RPM above hard rev)

### Emergency RPM Cut — NKILL
- **Needle:** `F7 F8 xx xx E1 08 [val] F4 xx 49 81 3D 09`
- **Hits:** 2 per file (discriminated from Hard Rev by `3D 09` vs `3D 08`)
- **DL stock:** raw `0x364A` = **10424 RPM** (~3264 RPM above hard rev)

### Fuel Cut Resume RPM
- **Needle:** separate from Hard Rev (distinct surrounding code)
- **Hits:** 1 per file
- **DL stock:** **7160 RPM** (fuel resumption when RPM drops back)

---

## Confirmed corpus

| ROM | Firmware | Key patches confirmed |
|---|---|---|
| 06A906032DL (stock) | fw4019 | All 1.8T patches STOCK |
| 06A906032HN (Unitronic Stage 2) | fw4019 | 5th-gear, SAP, EVAP, MAF-del PATCHED |
| 06A906032RN (stock) | fw4013 | All 1.8T patches STOCK |
| 06A906032LP (stock) | fw4013 | All 1.8T patches STOCK |
| 06A906032SL (Revo DSG) | X505R | MAF-del, 5th-gear PATCHED |
| 4B0906018CM (stock) | fw4012 | All 4B patches STOCK |
| 4B0906018CM (Unitronic 2) | fw4012 | CDKAT/CDKVS/5th-gear PATCHED |
| 8D0907551M-0002 (stock) | fw6005 | All 2.7T patches STOCK |
| 4Z7907551AA (stock) | fw6010 | All 2.7T patches STOCK |
| 4Z7907551AA-disable-P1681 | fw6010 | P1681 PATCHED |
| 4D1907558 (RS4 V8) | fw6012 | 2.7T non-SAP coverage |

---

## Universal codeword block patches (5 new — added from chiptuning.pw corpus)

These patches use the stable ME7 codeword block at `0x018190–0x0181C4` via fixed addresses.
All addresses verified stable across all ME7.1, ME7.1.1, and ME7.5 variants.

### Rear O2 full-disable trio — apply all three together

| Patch | Address | Stock→Patch | Applies |
|---|---|---|---|
| Rear O2 Heater Diag Disable (CDLSH) | `0x0181AA` | `0x01→0x00` | Universal ME7 |
| Rear O2 Interchange Diag Disable (CDLSHV) | `0x0181AB` | `0x01→0x00` | Universal ME7 |
| Rear O2 Voltage Diag Disable (CDLSV) | `0x0181AC` | `0x01→0x00` | Universal ME7 |

**Confirmed STOCK** in all tested stock ROMs (DL/RN/LP/SL/18CM/8D/4B/4Z7).
**Confirmed PATCHED** (0x00) in: HN-630hp Unitronic, 20th Anniversary PL.
3 of 20 allroad 4Z7 corpus files already show 0x00 — pre-patched in that variant.

### Catalyst Monitor Disable (CDKAT) — universal ME7

- `0x0181A2` → `0x01→0x00`. Prevents P0420/P0430. No effect on engine operation.
- **Extends** the existing `4B0906018`-specific CDKAT to all ME7 families.
- Confirmed PATCHED in: 20th Anniversary PL tuned file.

### MAF Sensor Diagnosis Disable (CDEHFM) — SL DSG + 4B0906018 only

- `0x01819C` → `0x01→0x00`. Prevents P0100–P0104 when MAF is physically removed.
- **Only needed** for SL DSG and 4B0906018 — DL/RN/LP/HN already have `0x00` in stock.
- Apply together with the MAF Delete / Alpha-N patch on affected ECUs.

---

## New ECU families from chiptuning.pw corpus

### 2.0 8V ME7.5 — `06A906032DS` (Bora/Golf 2.0 8V NA)

ME7.5 was used for the NA 2.0 8V engine, not just the 1.8T. Same VDO fw4013 hardware as
RN/LP. 13 of our patches hit STOCK. Emissions patches (SAP/EVAP) appear pre-patched (5 PATCHED).
Rev limit reads 6008 RPM via scalar — lower than 1.8T. Confirms the 2.0 8V → Beetle cross-flash
was plausible at the hardware level.

### VR6 3.2 24v ME7 — `0261201522` (A3 3.2 / TT 3.2)

Zero of our 33 patches hit this family. Confirmed completely separate code structure from 1.8T ME7.5.
Needs its own needle corpus. This file is preserved as the first entry point for VR6 ME7 support.

### VR6 2.8 ME7 — `0261206618` (Bora VR6)

512KB file. 7 STOCK, 5 PATCHED — likely a pre-tuned file. RPM scalar returns garbage (not 1.8T code).
Some emissions codeword patches hit (fixed-address codeword block is shared with 2.8 VR6).
