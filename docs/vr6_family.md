# ME7 Narrow-Angle Engine Families — VR6, VR5, AFP Reference

This document covers all narrow-angle VW Group engines using ME7.x management,
clarifies hardware sub-families within the 022906032 connector prefix, and
documents ROM analysis results from acquired files.

---

## Engine & ECU Family Map

| Engine | Disp | Valves | Code | Cars | ECU PN prefix | ME7 | In scope |
|---|---|---|---|---|---|---|---|
| AAA/ABV | 2.8–2.9L | 12v | AAA/ABV | MK3/Corrado | 021906258xx | M2.7/M2.9.1 | ❌ pre-ME7 |
| AHA/ACK/ATX | 2.8L | 30v | AHA/ACK | A4 B5, A6 C5 | 4D0907551xx, 8D0907557xx | M3.8.2/3.8.3 | ❌ pre-ME7 |
| AGZ | 2.3L | 10v | AGZ | MK4/Bora (early) | 071906018xx | M3.8.3 | ❌ pre-ME7 |
| AFP | 2.8L | 12v | AFP | MK4/Jetta MK4 | 021906018xx | ME7.1 | ✅ (no ROM yet) |
| AQN | 2.3L | 20v | AQN | MK4/Bora/Beetle | 066906032xx | ME7.1 | ✅ CONFIRMED |
| AZX | 2.3L | 20v | AZX | Passat B5 | 066906032xx | ME7.1 | ✅ expected |
| BDF | 2.8L | 24v | BDF | MK4/Bora/Passat B5 | 06A906032xx | ME7.1 | ✅ CONFIRMED |
| BFH | 3.2L | 24v | BFH | Golf R32 MK4 | 06A906032JA/HT | ME7.1 | ✅ (no ROM yet) |
| BUB/BHK | 3.2L | 24v | BUB | Golf R32 MK5, A3 3.2, TT 3.2 | 022906032 fw6432 | ME7.1.1 C167 | ✅ CONFIRMED |
| — | 3.2L | 24v | — | Touareg 3.2, Cayenne | 022906032 C1103A | ME7.1.1 hybrid | ⚠️ partial |
| — | 3.2L | 24v | — | A3 3.2 late, some TT | 022906032 S1103A | ME7.1.1 diff arch | ❌ |

---

## Pre-ME7 Engines — NOT in scope

### Audi 2.8L V6 30V (AHA/ACK/ATX) — M3.8.2/M3.8.3

The **Audi A4 B5 2.8 V6** and **A6 C5 2.8 V6** use the DOHC 2.8L 30-valve V6 (not a
narrow-angle VR6). ECU: `4D0907551F` (A4/A6/allroad). File confirmed: M3.8.2, **128KB**,
pre-ME7. Not related to the VR6/VR5 family.

### AGZ VR5 10V — M3.8.3

File confirmed: **256KB**, M3.8.3 version string, cable throttle, pre-ME7.
ECU `071906018x`.

### AAA/ABV VR6 12V — M2.7/M2.9.1

64KB EPROM. Confirmed from earlier Corrado file analysis.

---

## AFP — ME7.1 VR6 12V MK4 (021906018xx)

No ROM files acquired yet. Architecture confirmed as ME7.1 C167 from community
sources. Part prefix `021906018x`. Full codeword patch coverage expected once ROM
is available.

---

## AQN/AZX VR5 20V — ME7.1 (066906032xx) — **CONFIRMED**

### File: 066906032AK, fw5423 ME7.1

Startup bytes: `fa 00 70 64 fa 82 04 00...` — **C167 DPP initialisation**, confirmed
Bosch ME7.1 architecture. Part number `066906032AK`.

Version string: `ME7.1/3/5423.A1//24C/Dst11o/130801`
- fw5423 = VR5 20V firmware baseline
- `/3/` = 5-cylinder variant designation
- Date code 130801 = August 2001

**Patch results: 14 STOCK, 3 PATCHED, 10 MISSING**

Patches confirmed STOCK (patchable):
- Knock Retard Disable (both KRMXN variants) ✅
- Vmax Speed Limiter Disable (ME7.1 variant) ✅ — VR5 AQN **has a Vmax**
- Vmax Speed Limiter Disable (ME7.5 code-immediate variant) ✅
- ESKONF Rear O2 Heater Disable (0F 01 05) ✅
- SAP Disable (CDSLS, both variants) ✅
- CDKAT x2, CDKVS, CDLSHV, CDLSV, CDEHFM ✅

Pre-patched in this file (lightly tuned): EVAP Purge, EVAP 4B0, CDLSH.

**Codeword block notes:**
- CWKONLS = 0x00 — VR5 is single-bank 5-cyl, no dual-bank O2 monitoring
  (compare: 1.8T = 0x03 single-bank; 24V VR6 = 0x64 dual-bank)
- CDTES = 0x00 — EVAP disabled
- CDLSH = 0x00 — rear O2 heater diag already off

---

## BDF 24V VR6 — ME7.1 (06A906032xx) — confirmed earlier

Firmware fw6228. 12+ patches confirmed. See previous session notes.

---

## 022906032 Family — Three Sub-Architectures

**This is the most important correction to the previous documentation.**
The `022906032` part prefix covers three distinct hardware implementations:

### Sub-family A: fw6432 — C167-based ME7.1.1 (IN SCOPE)

| Part | Bosch PN | Cars | Notes |
|---|---|---|---|
| 022906032EG | 0261208344 | Golf R32 MK4 | fw6432.06 |
| 022906032GE | 0261208651 | Audi TT 3.2 | fw6432.06 |

Startup bytes: `fa 00 10 7e fa 82 04 00...` — **C167 DPP init, confirmed Bosch ME7.1.1.**
Codeword block fully present at 0x018194, identical structure.

**Patch results: 14 STOCK, 1 PATCHED (5th gear already zeroed)**

Confirmed STOCK on both Golf R32 and TT:
- Knock Retard Disable (KRMXN) ✅
- Vmax (2.7T ME7.1.1 variant) ✅ — R32 has the Vmax! Maps to the 250km/h limiter.
- SAP Disable (both variants) ✅
- EVAP x2 ✅
- CDKAT x2, CDKVS, CDLSH/V/V, CDEHFM ✅

Golf R32 (022EG) and TT 3.2 (022GE) are the **same firmware fw6432**, different
calibration suffix only (`Dst22o` vs `Dst41o`, `Dst` = Datensatz/dataset index).
Both are proper C167 Bosch ME7.1.1. They are **in scope** for MESevenTool.

### Sub-family B: C1103A — Continental derivative, partial hits

| Part | Bosch PN | Cars | Notes |
|---|---|---|---|
| 022906032FT | 0261208619 | Touareg 3.2 4Motion | C1103A |

Startup bytes: `0e 03 3e 01 fe 02 ae 01...` — **different startup sequence** from
C167. Likely a Continental/Bosch hybrid ECU or Bosch ECU with alternative boot ROM.
Codeword block at 0x018190 partially present (anchor bytes differ).

**Patch results: 12 STOCK, 1 PATCHED** — most codeword patches and codeword-anchored
patches hit correctly. Needle-based patches are more variable.

Partially in scope. Emissions codeword patches work; code-search patches need verification.

### Sub-family C: S1103A — Different architecture (OUT OF SCOPE)

| Part | Bosch PN | Cars | Notes |
|---|---|---|---|
| 022906032GP | 0261201522 | Audi A3 3.2, TT 3.2 (late) | S1103A |

Startup bytes: `5c 5c 53 32 36 45 36 41...` — text header, completely different.
Codeword block at 0x018194 = random code bytes, not the ME7 structure.
**0/33 patches.** Not a C167 flat binary. Different architecture, out of scope.

---

## ECU PN prefix → hardware architecture (complete map)

```
021906258xx  →  M2.7/M2.9.1         (VR6 12V pre-ME7 MK3/Corrado)
4D0907551xx  →  M3.8.2              (Audi 2.8L V6 30V AHA/ACK pre-ME7)
8D0907557xx  →  M3.8.2/3.8.3       (Audi 1.8 pre-ME7)
071906018xx  →  M3.8.3              (VR5 10V AGZ pre-ME7)
021906018xx  →  ME7.1               (AFP VR6 12V MK4)              ← no ROM yet
066906032xx  →  ME7.1               (AQN/AZX VR5 20V)              ← CONFIRMED
06A906032xx  →  ME7.1/ME7.5         (BDF/BFH 24V VR6 + 1.8T)       ← CONFIRMED
022906032 fw6432  →  ME7.1.1 C167   (Golf R32 MK4, Audi TT 3.2)    ← CONFIRMED
022906032 C1103A  →  ME7.1.1 hybrid (Touareg 3.2)                  ← partial
022906032 S1103A  →  Different arch (A3 3.2 late, TT 3.2 late)     ← out of scope
```

---

## Files Corpus Status

| File | PN | Firmware | S/P/M | Notes |
|---|---|---|---|---|
| `066906032AK_Golf4_VR5_AQN_fw5423.bin` | 066906032AK | ME7.1 fw5423 | 14/3/10 | VR5 AQN 20V confirmed |
| `022906032EG_Golf4_R32_3.2_fw6432.bin` | 022906032EG | ME7.1.1 fw6432 | 14/1/16 | Golf R32 MK4 confirmed |
| `022906032GE_TT_3.2_fw6432.bin` | 022906032GE | ME7.1.1 fw6432 | 14/1/16 | Audi TT 3.2 confirmed |
| `022906032FT_Touareg_3.2_C1103A.bin` | 022906032FT | ME7.1.1 C1103A | 12/1/18 | Touareg, partial hits |
| `Bora_2.8_VR6_ME7_0261206618.bin` | 0261206618 | ME7.1 fw6228 | 7/5/13 | BDF 24V, tuned |
| `A3_3.2_VR6_250hp_0261201522.bin` | 022906032GP | ME7.1.1 S1103A | 0/0/20 | different arch |

Not acquired yet: AFP (021906018x), BFH R32 MK4 (06A906032JA/HT), BDF 24V stock untuned.
