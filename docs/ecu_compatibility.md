# ME7.x ECU Interchangeability Matrix

Physical ECU swaps and ROM cross-flashing have different rules. This document covers both.

---

## The fundamental split: ROM flash vs physical ECU swap

**ROM flash** (reflash the existing ECU with a different `.bin` file):
- Does NOT touch the 95040 EEPROM chip that holds the SKC
- Does NOT break IMMO pairing — the car will continue starting normally
- Constraints are purely about hardware compatibility (PCB must match firmware)

**Physical ECU swap** (replace the ECU unit from a different car):
- The donor ECU has a different SKC in its EEPROM
- Your cluster/keys will not match the donor SKC → IMMO prevents starting
- Solution: EEPROM recode, cluster swap, or P1681 disable (ME7.1.1)

---

## ME7.5 1.8T — 06A906032 family (Golf / Jetta / TT / A3 / S3 / Beetle)

### Hardware revisions

Two completely different PCBs exist under the same part-number prefix:

| Hardware | Bosch part prefix | MAF ADC channel | Examples |
|---|---|---|---|
| **Bosch-sourced** | `0 261 206 8xx` | AN0 (ch0) via ASIC | DL, HN, A, B, C |
| **VDO-sourced** | `0 261 206 9xx` | AN14 (different routing) | RN, LP, PL, HL, GL, SL |

Cross-flashing Bosch firmware onto VDO hardware or vice versa = MAF on wrong ADC channel → no load signal → won't run correctly.

### Compatibility table — 06A906032 variants

| From → To | DL/HN | RN/LP | PL (6spd) | HL (5spd) | SL (DSG) | GL (AT) |
|---|---|---|---|---|---|---|
| **DL/HN** (Bosch fw4019) | ✅ | ❌ HW | ❌ HW | ❌ HW | ❌ HW+AT | ❌ HW+AT |
| **RN/LP** (VDO fw4013) | ❌ HW | ✅ | ⚠️ gear cal | ⚠️ gear cal | ❌ AT | ❌ AT |
| **PL (6-speed)** (VDO fw4013) | ❌ HW | ⚠️ gear cal | ✅ | ⚠️ gear cal | ❌ AT | ❌ AT |
| **HL (5-speed)** (VDO fw4013) | ❌ HW | ⚠️ gear cal | ⚠️ gear cal | ✅ | ❌ AT | ❌ AT |
| **SL (DSG/auto)** (VDO X505R) | ❌ HW+AT | ❌ AT | ❌ AT | ❌ AT | ✅ | ❌ |
| **GL (Tiptronic)** (VDO fw4013 AT) | ❌ HW+AT | ❌ AT | ❌ AT | ❌ AT | ❌ | ✅ |

**Key:**
- ✅ = Direct cross-flash, no issues
- ⚠️ gear cal = Same PCB, runs but gear detection miscalculates → wrong torque corrections. Fixable by editing gear ratio constants in cal area
- ❌ HW = Different PCB hardware — MAF on wrong ADC channel, won't run
- ❌ AT = Automatic gearbox firmware on manual car (or vice versa) — torque management mismatch, TCU CAN mismatch

### Why PL (6-speed) ↔ HL (5-speed) has issues

Both are VDO fw4013, identical code. The firmware estimates current gear by dividing RPM by vehicle speed and comparing to stored gear ratios. With a different final drive or gear count, the gear estimate is wrong. The consequences:
- 5th-gear torque mode table is applied at the wrong gear
- Speed-referenced boost corrections are slightly wrong
- Correctable with cal editing (change the gear ratio table)

---

## ME7.5 1.8T — 4B0906018 family (Audi A4 / A6 / Passat B5)

Completely different PCB from 06A906032. The 4B0906018 uses a different connector layout and different injector/coil driver configuration.

| Part number family | Engine | Trans | Notes |
|---|---|---|---|
| 4B0906018x MT | AWM 170hp, APU 150hp | Manual | |
| 4B0906018x AT | AWM/APU | Tiptronic/CVT | Different torque management |

- `4B0906018` ↔ `06A906032` = ❌ Different PCB entirely, different connector
- `4B0906018` MT ↔ AT variants = ❌ Same caveat as above

---

## ME7.1 / ME7.1.1 — 2.7T biturbo (Audi S4, A6, allroad, RS4, S8)

All 2.7T ECUs use the same 121-pin SKE connector and the same Bosch C167 dual-processor architecture. The code families split ME7.1 vs ME7.1.1.

### ME7.1 corpus (40 files)

| Body | Part numbers | Notes |
|---|---|---|
| A4 B5 S4 | 8D0907551A-Q | Early production |
| A6 C5 | 4B0907551A-M | Same firmware |
| allroad early | 4Z7907551A-M | Same firmware |

All ME7.1 within the same body/engine/trans spec are freely cross-flashable.
ME7.1 ↔ ME7.1.1 = ⚠️ different BGVMAX and P1681 codeword structure — may cause P1681 DTC when cross-flashing. Use P1681 disable patch.

### ME7.1.1 corpus (17 files)

| Body | Part numbers | Notes |
|---|---|---|
| A4 B5 S4 (late) | 8D0907551R+ | ATOMIC variant code |
| A6 C5 (late) | 4B0907551AH+ | |
| allroad late | 4Z7907551N+ | |
| RS4/S8 V8 | 4D1907558x | ME7.1.1 only — different knock, no SAP |

---

## Firmware version pairing

| Firmware | Hardware generation | Free code space | Used by |
|---|---|---|---|
| fw4019 | C2-2 (Bosch) | 386 KB @ `0x09F7EE` | DL, HN, S3 8N0 variants |
| fw4013 | C2-2 (VDO) | 308 KB @ `0x0B2F00` | RN, LP, PL, HL, SL, GL |
| fw4012 | C2-2 (Bosch) | 306 KB @ `0x0B37E0` | 4B0906018CM (Passat/A4/A6) |
| fw6005 | C4 (2.7T) | 454 KB @ `0x08E472` | All ME7.1 2.7T biturbo |

---

## The no-start diagnostic decision tree

When an ECU swap results in no-start:

```
1. Did you flash a new ROM to the same physical ECU?
   → YES: Not an IMMO issue. Check hardware compatibility (right PCB for that firmware).
   → NO (physical swap): Continue →

2. Does the donor ECU part number match what the car expects?
   → If connector doesn't fit: wrong ECU family entirely
   → If connectors match but no-start: →

3. IMMO mismatch (most common)
   → Donor ECU EEPROM has different SKC than your cluster/keys
   → Fix: EEPROM recode (read target car's EEPROM, write donor ECU's EEPROM to match)
   → Or: cluster + key set from same donor car
   → Or: P1681 disable patch (ME7.1.1 only, suppresses IMMO databus DTC)

4. ECU in wrong engine mode (manual firmware in auto car or vice versa)
   → Car may crank but not start, or start and limp
   → Fix: use correct transmission variant firmware
```

---

## What the Beetle experiment tells us

A MK4 2.0 8V Golf normally runs Simos 3.3 or Magneti Marelli — not ME7. If a ME7 ROM ran at all:
- The New Beetle used 1.8T AWP with ME7.5 (part numbers `06A906032xx`)
- Beetle ECU = ME7.5 VDO hardware (same connector style as Golf MK4)
- If IMMO wasn't an issue (matching cluster gen), it would start
- The car "ran decent" because: crank/cam sync worked (same 60-2 wheel), injectors fired in sequence, but MAF calibration for a 2.0 8V would give wrong load → rich/lean issues at load transitions

---

## New ECU families under consideration

| ECU | Engine | Status | Notes |
|---|---|---|---|
| `8N0906018AH` | AWU/BAM 225hp (S3 8L, TT 225) | Pending ROM | ME7.5 fw4019 Bosch hardware. All DL patches should apply. Confirmed in NefMoto topic 17703 (noice's ECU). |
| `06A906032JA` | 3.2 VR6 (R32 Golf MK4) | Pending ROM | ME7.1 NA variant. No boost management. Vmax/knock/emissions patches should apply; MAF Delete/boost patches do not. |
| `06A906032HT` | 3.2 VR6 (R32 Golf MK4) | Pending ROM | As above |
| `06A906032BH` | AGU/AEB 150hp (older Golf/A3) | Easy add | VDO fw4013, same family as RN/LP |


---

## VR6, VR5, AFP, and V8 families

### AFP 12V VR6 (021906018xx) — ME7.1 fw6228

All AFP files use the same `021906018` prefix. Not cross-flashable with `06A906032` family.

| From | To | Result |
|---|---|---|
| 021906018M (1999) | 021906018Q/R | ✅ Same fw6228 base, only cal difference |
| 021906018x | 06A906032xx | ❌ Wrong PCB — different connector, ADC mapping |

The AFP 12V has no VVT (CDNWS=0x00 from factory). CDSLS varies by market — some had SAP, some didn't.

### VR6 24V BDF (06A906032AG/AK/L/T) — ME7.1 fw6228

Shares the `06A906032` prefix with the 1.8T ME7.5 family but runs ME7.1 fw6228.
**Not cross-flashable with 1.8T ECUs** — different firmware version, different injection/ignition mapping.

KL15 on pin 21 (1.8T uses pin 3) — harness pinout differs.

### VR5 20V AQN/AZX (066906032xx) — ME7.1 fw5423

Separate `066` prefix, 5-cylinder output mapping. Not interchangeable with 6-cylinder VR6 or 4-cylinder 1.8T.

### 022906032 cross-flash matrix

The `022906032` prefix covers five different hardware sub-families — **do not cross-flash between them.**

| Sub-family | Firmware | Startup | Examples | Cross-flash |
|---|---|---|---|---|
| fw6428 C167 | ME7.1.1 | `fa 00 10 7e` | CS (Passat 2.8V6) | ⚠️ only within fw6428 |
| fw6432 C167 | ME7.1.1 | `fa 00 10 7e` | EG (R32), GE (TT 3.2) | ⚠️ only within fw6432 |
| C1103A | ME7.1.1 | `0e 03 3e 01` | FT (Touareg 3.2) | ❌ different hw |
| S1103A | ME7.1.1 | `5c 5c 53 32` | GP (A3 3.2 late) | ❌ different arch |

Golf R32 (022906032EG) and Audi TT 3.2 (022906032GE) share fw6432 and are cross-flashable with cal calibration differences only.

### V8 4.2L cross-flash

| From | To | Result |
|---|---|---|
| 4D0907558 (S6 fw8000) | 4D0907559G (S8 fw8000) | ✅ Same fw8000, dataset only differs |
| fw8000 | fw8001 | ⚠️ Same C167 hardware, different fw revision — verify codeword layout |
| 4D1907558xx (RS6 fw8542) | 4D0907558/9 | ❌ Different firmware branch |
| Any 4D | 8E0907560 (S4 B7 C1105B) | ❌ Different firmware generation |

---

## CDNWS VVT codeword — platform notes

On ME7.1/ME7.1.1 engines, CDNWS at `0x0181AF` is a binary VVT monitoring flag (0x01 = active).

On ME7.5 1.8T, the same address holds a **multi-mode configuration byte** with different semantics:
- `0x03` = standard mode, most VDO fw4013/fw4019 1.8T ECUs
- `0x02` = 4B0906018CM A6/Passat variant
- `0x01` = older Bosch fw4019/fw4013 early builds (CL, CM, AR)
- `0x00` = SL DSG, 2.0 8V

The 1.8T AWW/AWP/AUM engines have no cam position solenoid hardware — CDNWS on
1.8T ME7.5 does **not** control VVT monitoring and the CDNWS patch is not applicable
to the 1.8T platform.
