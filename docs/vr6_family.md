# ME7 Narrow-Angle Engine Families — VR6, VR5, AFP, V8

All narrow-angle VW Group engines using ME7.x ECU management, plus the V8 4.2L
which shares the same C167 hardware generation. Covers ECU hardware families,
firmware versions, known part numbers, and MESevenTool patch compatibility.

---

## Quick reference: ECU PN prefix → architecture

```
021906258xx  →  M2.7 / M2.9.1       VR6 12V pre-ME7 (MK3, Corrado)         OUT OF SCOPE
071906018xx  →  M3.8.3              VR5 10V pre-ME7 (AGZ)                   OUT OF SCOPE
8D0907557xx  →  M3.8.2 / M3.8.3    Audi 1.8 / 2.8 V6 pre-ME7              OUT OF SCOPE
4D0907551xx  →  M3.8.2              Audi A4/A6/A8 2.8 V6 30V pre-ME7       OUT OF SCOPE

021906018xx  →  ME7.1  fw6228       AFP VR6 12V (MK4 Golf/Jetta)            ✅ CONFIRMED
066906032xx  →  ME7.1  fw5423       AQN/AZX VR5 20V                         ✅ CONFIRMED
06A906032xx  →  ME7.1/ME7.5         BDF/BFH 24V VR6 + 1.8T                  ✅ CONFIRMED
4D0907558/9  →  ME7.1  fw8000       Audi S6/S8 4.2L V8                      ✅ CONFIRMED
4D1907558xx  →  ME7.1.1 fw8542      Audi RS6 C5 4.2TT                       ✅ CONFIRMED
8E0907560x   →  ME7.1.1 C1105B      Audi S4 B7 4.2L V8                      ✅ CONFIRMED

022906032 fw6228  →  ME7.1  C167    BDF 24V (some Passat spec)               ✅
022906032 fw6428  →  ME7.1.1 C167   Passat B5.5 2.8L V6 AMX (022CS)         ✅ CONFIRMED
022906032 fw6432  →  ME7.1.1 C167   Golf R32/TT 3.2 BUB (022EG/GE)          ✅ CONFIRMED
022906032 C1103A  →  ME7.1.1 hybrid Touareg 3.2 (022FT)                     ⚠️ partial
022906032 S1103A  →  different arch  A3 3.2 late / TT 3.2 late (022GP)      ❌ out of scope
```

---

## Pre-ME7 engines (not in scope)

### VR6 12V Gen 1 — AAA / ABV (Motronic M2.7 / M2.9.1)

- Corrado, Golf MK3, Passat B3/B4 — ECU `021906258xx`
- SAB80C515 8-bit processor, 27C256/27C512 EPROM (32–64KB)
- Confirmed from chiptuning.pw Corrado files: "M2.9" version string

### VR5 10V Gen 1 — AGZ (Motronic M3.8.3)

- Golf MK4/Bora 1997–2000, ECU `071906018xx`, cable throttle
- Confirmed: 256KB ROM, M3.8.3 version string
- Replaced by the AQN 20V in 2000

### Audi 2.8L V6 30V (AHA/ACK) — Motronic M3.8.2

- A4 B5, A6 C5 2.8 30V — ECU `4D0907551F` and `8D0907557xx`
- Confirmed: 128KB ROM, M3.8.2 version string
- Not related to the narrow-angle VR6 engine family

---

## AFP — VR6 12V MK4 (021906018xx) — ME7.1 fw6228  ✅ CONFIRMED

### Summary

The AFP replaced the pre-ME7 AAA in the MK4 Golf/Jetta from 1999.5. Despite being
a 12-valve engine it got a full ME7.1 upgrade — same C167 hardware, OBD-II, and
coil-on-plug. **It shares the same fw6228 firmware base as the BDF 24V VR6.**
Different calibration dataset, same Bosch function framework.

ECU prefix: `021906018xx` — different from both `06A906032` (1.8T/24V VR6) and
`066906032` (VR5). Different PCB layout for the 12V engine.

### Confirmed files

| PN | Bosch | Firmware | CWKONLS | Notes |
|---|---|---|---|---|
| 021906018R | 0261206814 | ME7.1/fw6228 Dst03o 2000 | 0x04 | Golf, lightly modified |
| 021906018Q | 0261206618 | ME7.1/fw F1031 2006 | 0x64 | Jetta, clean stock, dual-bank |

CWKONLS=0x04 on the Golf variant vs 0x64 on the Jetta is a dataset calibration
difference — the Golf file appears to have been lightly modified at some point.
The Jetta file matches the dual-bank config of the BDF 24V.

### Factory-disabled features

- **CDNWS=0x00** — no cam phasing on the 12V head (fixed timing)
- **CDSLS varies** — SAP was not fitted in some markets; Jetta had SAP

### Patch compatibility

| Patch | Status |
|---|---|
| KRMXN Knock Retard Zero | ✅ STOCK (confirmed both files) |
| ESKONF (0F 01 05) | ✅ STOCK |
| Codeword block (CDLSH/V/V, CDKAT, CDEHFM) | ✅ Available |
| CDNWS VVT disable | Not needed (already 0x00 from factory) |
| Vmax | Not present in this firmware — AFP 12V has no electronic speed limiter |
| MAF Delete | Not applicable |

---

## AQN / AZX — VR5 20V (066906032xx) — ME7.1 fw5423  ✅ CONFIRMED

### Summary

The 20-valve VR5 (2000+), produced by deleting one cylinder from the VR6 block.
Drive-by-wire, VVT, 170hp. Engine AQN (Golf/Bora) and AZX (Passat B5).
ECU prefix `066906032xx`. ME7.1 with C167. Not to be confused with the earlier
AGZ 10V VR5 which runs M3.8.3.

### Confirmed file

| PN | Bosch | Firmware | CWKONLS | Notes |
|---|---|---|---|---|
| 066906032AK | 0261207375 | ME7.1/fw5423 2001 | 0x00 | Golf AQN, lightly tuned |

CWKONLS=0x00 is unique to the VR5 — single-bank 5-cylinder configuration.

### Patch compatibility

| Patch | Status |
|---|---|
| KRMXN Zero | ✅ STOCK |
| ESKONF (0F 01 05) | ✅ STOCK |
| Vmax (2.7T ME7.1) | ✅ STOCK — VR5 has an electronic speed limiter |
| Codeword block patches | ✅ Available |
| CDNWS VVT disable | CDNWS=0x07 (multi-mode) — binary 0x01→0x00 does not apply directly |

---

## BDF / BFH — VR6 24V (06A906032xx) — ME7.1 fw6228  ✅ CONFIRMED

### Summary

- **BDF** 2.8L 24V: Golf MK4, Bora, Passat B5 syncro — `06A906032AG/AK/L/T`
- **BFH** 3.2L 24V (R32 MK4): `06A906032JA/HT` — no ROM yet, expected same architecture

Shares the `06A906032` prefix with the 1.8T ME7.5 family but runs **ME7.1** with
fw6228. Same C167 hardware. CWKONLS=0x64 (dual-bank O2, both cylinder banks).
No MAP sensor, no boost management, variable intake solenoid on pin 121.

KL15 on pin 21 (vs pin 3 on 1.8T ME7.5) — different harness.

### Confirmed file

| PN | Bosch | Firmware | Notes |
|---|---|---|---|
| 0261206618 | — | ME7.1/fw6228 1999 | Bora BDF, partially tuned |

### Patch compatibility

~12 of 34 patches confirmed: KRMXN, ESKONF, all codeword block patches.
Vmax, MAF Delete, boost patches: not applicable.

---

## Golf R32 / TT 3.2 — BUB engine (022906032EG/GE) — ME7.1.1 fw6432  ✅ CONFIRMED

### Summary

The 3.2L 24V VR6 in MK5 Golf R32, Audi A3 3.2, TT 3.2 (BUB engine code).
Uses `022906032` prefix with C167 startup (`fa 00 10 7e`). **Confirmed proper
Bosch ME7.1.1 — full codeword block present, 14 patches hit.**

| PN | Car | Firmware | CWKONLS | Notes |
|---|---|---|---|---|
| 022906032EG | Golf R32 MK4 | ME7.1.1/fw6432 Dst22o 2003 | 0x05 | Clean stock |
| 022906032GE | Audi TT 3.2 | ME7.1.1/fw6432 Dst41o 2003 | 0x05 | Same fw, different cal |

CWKONLS=0x05 — unique to the 6-cyl 022 family. CDNWS=0x01 — VVT present.

### Patch compatibility

| Patch | Status |
|---|---|
| KRMXN Zero | ✅ STOCK |
| Vmax (ME7.1.1) | ✅ STOCK — R32 has 250km/h limiter |
| CDNWS VVT disable | ✅ STOCK — cam phasing present, patchable |
| SAP, EVAP, CDLSH/V/V, CDKAT | ✅ STOCK |

---

## Passat B5.5 2.8V6 — AMX engine (022906032CS) — ME7.1.1 fw6428  ✅ CONFIRMED

### Summary

The DOHC 30-valve 2.8L V6 (AMX engine, 193hp) in Passat B5.5. Uses `022906032`
prefix with C167 startup (`fa 00 10 7e`). ME7.1.1/fw6428 — a distinct firmware
branch between fw6228 (BDF) and fw6432 (R32). Has VVT.

| PN | Bosch | Firmware | CWKONLS | Notes |
|---|---|---|---|---|
| 022906032CS v0005 | 0261207881 | ME7.1.1/fw6428 Dst01o 2002 | 0x05 | Stock |
| 022906032CS v0006 | 0261207881 | ME7.1.1/fw6428 Dst02o 2003 | 0x05 | Minor rev |

0005→0006: 83-byte difference, date code + calibration table rev. Both are
genuine production revisions from the same ECU. CDSLS=0x06 (non-binary SAP mode).

---

## Touareg 3.2 (022906032FT) — C1103A partial  ⚠️

Startup: `0e 03 3e 01` — different from C167 pattern. Likely Continental/Bosch hybrid.
12 of 34 patches hit. Codeword patches work; needle patches variable.

---

## A3 3.2 late / TT 3.2 late (022906032GP) — S1103A  ❌

Startup: `5c 5c 53 32` — completely different architecture. 0/34 patches.
Out of scope without dedicated RE work.

---

## V8 4.2L family — ME7.1 / ME7.1.1  ✅ CONFIRMED

### fw8000 — S6/S8 first-generation (ME7.1)

- `4D0907558` — S6 C5 4.2L V8 5V (163hp version)
- `4D0907559G` — S8 D2 4.2L 360hp
- Firmware ME7.1/fw8000.07, same startup as BDF (`8e 02 0e 01`)
- CWKONLS=0x71 (V8 dual-bank config). CDNWS=0x01 — VVT active, patchable
- ~10 patches + Vmax (ME7.1 variant)

### fw8001 — S6 revised (ME7.1.1)

- `4D0907559E` — S6 C5 4.2L revised
- Firmware ME7.1.1/fw8001.07. CDNWS=0x00 (already disabled)
- C167 startup (`fa 00 cc 76`)

### fw8542 — RS6 C5 4.2TT (ME7.1.1)

- `4D1907558F` (and B/C/-0002) — RS6 480hp Euro, 450hp US
- BCY twin-turbo engine. ME7.1.1/fw8542.05
- **No VVT** (CDNWS=0x00 factory — fixed cam timing on the TT engine)
- **No SAP** (CDSLS=0x00 factory — never fitted Euro spec)
- **No EVAP** (CDTES=0x00 factory)
- CWKONLS=0x00 (different O2 bank config vs naturally-aspirated V8)
- Vmax STOCK, knock retard STOCK, O2/cat patches STOCK

### C1105B — S4 B7 4.2L V8 (ME7.1.1)

- `8E0907560x` — Audi S4 B7, 2004+
- CDNWS=0x00 already. 12 patches hit.

---

## Files corpus status

| File | PN | Firmware | S/P/M | Engine |
|---|---|---|---|---|
| `021906018R_Golf_AFP_12V_fw6228.bin` | 021906018R | ME7.1 fw6228 | 9/7/13 | AFP 12V VR6 |
| `021906018Q_Jetta_AFP_12V_fw6228.bin` | 021906018Q | ME7.1 fw F1031 | 7/6/13 | AFP 12V VR6 |
| `066906032AK_Golf4_VR5_AQN_fw5423.bin` | 066906032AK | ME7.1 fw5423 | 14/3/10 | VR5 20V AQN |
| `Bora_2.8_VR6_ME7_0261206618.bin` | 0261206618 | ME7.1 fw6228 | 7/5/13 | BDF 24V VR6 |
| `022906032CS_0005_fw6428.bin` | 022906032CS | ME7.1.1 fw6428 | 12/3/16 | Passat 2.8V6 |
| `022906032CS_0006_fw6428.bin` | 022906032CS | ME7.1.1 fw6428 | 12/3/16 | Passat 2.8V6 |
| `022906032EG_Golf4_R32_3.2_fw6432.bin` | 022906032EG | ME7.1.1 fw6432 | 14/1/16 | Golf R32 MK4 |
| `022906032GE_TT_3.2_fw6432.bin` | 022906032GE | ME7.1.1 fw6432 | 14/1/16 | Audi TT 3.2 |
| `022906032FT_Touareg_3.2_C1103A.bin` | 022906032FT | ME7.1.1 C1103A | 12/1/18 | Touareg 3.2 |
| `4D0907558_S6_fw8000.bin` | 4D0907558 | ME7.1 fw8000 | 6/7/11 | S6 4.2 V8 |
| `4D0907559G_S8_fw8000.bin` | 4D0907559G | ME7.1 fw8000 | 6/7/11 | S8 4.2 360hp |
| `4D0907559E_S6_fw8001.bin` | 4D0907559E | ME7.1.1 fw8001 | 7/6/17 | S6 4.2 revised |
| `8E0907560_S4_4.2_C1105B.bin` | 8E0907560 | ME7.1.1 C1105B | 12/3/16 | S4 B7 4.2 V8 |

Not yet acquired: AFP 021906018S (common dealer part), BFH R32 MK4 (06A906032JA/HT)
