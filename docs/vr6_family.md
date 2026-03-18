# ME7 VR6 Engine Families — Reference & Compatibility Notes

This document covers the VR6 engine families that use ME7.x ECU management,
clarifies which are in scope for MESevenTool, and documents ROM analysis results.

---

## The VR6 Motronic Family Tree

The VR6 engine spanned three distinct ECU generations. Understanding which
generation an ECU belongs to is critical — they are not interchangeable.

### Generation 1: Pre-ME7 (OUT OF SCOPE for MESevenTool)

| Engine | Displacement | Valves | Cars | ECU PN | ECU Family |
|---|---|---|---|---|---|
| AAA | 2.8L | 12v | Golf MK3, Corrado, Passat B3/B4, Vento | 021906258xx | Bosch M2.7 |
| ABV | 2.9L | 12v | Corrado VR6 | 021906258xx | Bosch M2.9.1 |
| ACC | 2.8L | 12v | Sharan/Alhambra | 021906258xx | Bosch M2.9.1 |

These ECUs use a **Siemens SAB80C515/535 (8-bit i8051 derivative)** processor.
ROM is a 27C256 or 27C512 EPROM (32–64KB), directly socketed and replaceable.
Completely different toolchain, instruction set, and map structure from ME7.
The Corrado files on chiptuning.pw (021906258B, 021906258CP) confirm: M2.9 processor,
64KB EPROM images. Same era as Audi M2.3.2 (5-cylinder turbo).

**Not in scope for MESevenTool.** Could be a future separate tool.

---

### Generation 2: ME7.1 — 24V Narrow-Angle VR6 (IN SCOPE)

| Engine | Displacement | Valves | Cars | ECU PN | Firmware |
|---|---|---|---|---|---|
| BDF | 2.8L | 24v | Golf MK4, Bora, Passat B5 syncro | 06A906032AG/AK/L/T | fw6228 |
| BFH | 3.2L | 24v | Golf R32 MK4 | 06A906032JA/HT | fw???? |

**These use the same C167CR processor and 121-pin connector as the 2.7T S4.**
ME7.1 variant. Same Bosch function framework. Same codeword block at `0x018194`.
The 80-pin `06A906032` part number prefix is shared with the 1.8T ME7.5 family,
but the firmware version (fw6228 vs fw4019/4013) and code structure are distinct.

#### Key differences from 1.8T ME7.5

- **Dual bank O2** — CWKONLS = 0x64 (vs 0x03 single bank in 1.8T)
- **No turbo/boost management** — BGRLP, BGSRM functions absent or stub
- **Variable intake** — uses DROSALK/variable intake solenoid
- **No MAP sensor** — load calculated from MAF only (no ps_w boost sensor)
- **6-cylinder injection/ignition** — different output driver mapping
- **KL15 on pin 21** — different from 1.8T (which has it on pin 3)

#### ROM analysis: Bora 2.8 VR6 ME7.1 fw6228 (0261206618)

- **512KB** file (512KB of active code, no padding to 1MB)
- **~104KB free** (20% — much less than 1.8T's 35–47%)
- **Codeword block confirmed** at 0x018194 — structure shared with all ME7 families
- **12 of 33 MESevenTool patches** apply (7 STOCK, 5 PATCHED in this tuned file)

Patches that DO work on VR6 ME7.1:
| Patch | Status in this file | Notes |
|---|---|---|
| KRMXN Zero (knock retard cal) | STOCK | Same KRMXN table structure |
| ESKONF Rear O2 Heater newer | STOCK | 0F 01 05 pattern present |
| CDKAT universal (cat monitor) | PATCHED | Already disabled |
| CDLSH (O2 heater diag) | PATCHED | Already disabled |
| CDLSHV (O2 interchange diag) | PATCHED | Already disabled |
| CDLSV (O2 voltage diag) | STOCK | Present, patchable |
| CDEHFM (MAF diag) | STOCK | Present, patchable |

Patches that do NOT apply:
- Vmax: fw6228 VR6 has no speed limiter code (NA road car, no electronically governed limit)
- MAF Delete: not applicable (no Alpha-N redirect; load is always MAF-based)
- 1.8T knock retard code patches: different instruction sequence at that function
- P1681: ME7.1.1 only; this is ME7.1

---

### Generation 3: ME7.1.1 — Larger Platform (DIFFERENT ARCHITECTURE)

| Engine | Displacement | Valves | Cars | ECU PN | Notes |
|---|---|---|---|---|---|
| BUB | 3.2L | 24v | Golf R32 MK5, A3 3.2, TT 3.2, Cayenne | 022906032GP | Different HW |
| BHK | 3.2L | 24v | Touareg 3.2 | varies | |

The `022906032` prefix ECUs have a **different hardware architecture** from `06A906032`.
Analysis of our A3 3.2 BUB file (022906032GP, fw ME7.1.1/5/S1103A):
- Startup bytes `5C 5C 53 32...` — not C167 DPP initialisation sequence
- Codeword block at 0x018194 contains garbage (the block structure is absent or relocated)
- 0 of 33 patches hit in any state
- 760KB "free" — likely the entire 1MB is usable but flash is mostly erased

The `S1103A` in the version string may indicate a Siemens/Continental ECU module
(Bosch-licensed ME7.1.1 firmware running on Siemens hardware), or a different
Bosch sub-variant. Either way it does not share the MESevenTool patch structure.

**Not in scope for MESevenTool without dedicated reverse engineering work.**

---

## Summary: What MESevenTool can do for VR6

| VR6 Family | ME7 version | ECU PN prefix | In scope | Patches work |
|---|---|---|---|---|
| 12V AAA/ABV (M2.7/M2.9) | Pre-ME7 | 021906258xx | ❌ | 0/33 |
| 24V 2.8 BDF (ME7.1) | ME7.1 | 06A906032 | ✅ | ~12/33 |
| 24V 3.2 BFH R32 MK4 | ME7.1 | 06A906032JA/HT | ✅ expected | TBD |
| 24V 3.2 BUB MK5/A3/TT | ME7.1.1 | 022906032 | ⚠️ different HW | 0/33 |

Confirmed working patches for 24V ME7.1 VR6 (from fw6228 BDF analysis):
**Emissions codeword block, KRMXN knock retard, ESKONF heater.**
Confirmed NOT working: Vmax, MAF Delete, 1.8T-specific code patches.

---

## Files acquired

| File | PN | Engine | Firmware | Status |
|---|---|---|---|---|
| `Bora_2.8_VR6_ME7_0261206618.bin` | 0261206618 | BDF 2.8 24V | fw6228 ME7.1 | Confirmed ME7.1, partially tuned |
| `A3_3.2_VR6_250hp_0261201522.bin` | 022906032GP | BUB 3.2 | ME7.1.1/S1103A | Different arch, 0 patches hit |

Still needed for complete coverage:
- `06A906032AG` or `AK` — BDF 2.8 24V stock ROM (untuned baseline)
- `06A906032JA` or `HT` — BFH 3.2 R32 MK4 stock ROM

---

## Notes for tuning VR6 ME7.1 with MESevenTool

The following patches are applicable and have been verified against fw6228 BDF:

1. **Emissions codeword patches** — CDLSH, CDLSHV, CDLSV, CDKAT at the same
   fixed addresses as all other ME7 variants. The codeword block is fully present.

2. **KRMXN Zero** — the 16× 0x14 anchor is confirmed present. Zeroing the max
   knock retard table works the same way as on the 2.7T.

3. **ESKONF** (newer 0F 01 05 variant) — confirmed present. Disables dual rear
   O2 heater diagnosis. The VR6 CWKONLS = 0x64 (dual bank), different from
   1.8T single-bank 0x03 — confirming it monitors both banks.

4. **Vmax** — not applicable. No speed limiter in VR6 NA firmware.

5. **MAF Delete** — not applicable. Would require VR6-specific needle work if
   turbocharging (common build: MK4 R32 turbo). The load calculation path differs.
