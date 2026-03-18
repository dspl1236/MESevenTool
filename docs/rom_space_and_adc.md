# MESevenTool — Free ROM Space & ADC Channel Reference

Analysis of erased (0xFF) flash space available for code injection, and
ADC channel assignments across all supported ECU families.

---

## Free ROM space by ECU

ME7 uses a 1 MB NOR flash chip. Bosch compiled one codebase for multiple
hardware variants — regions not used by a given variant remain as 0xFF.
**There is no space constraint for any practical code injection project.**

| ECU / Firmware | Free CODE | Largest block | Start addr | Notes |
|---|---|---|---|---|
| 06A906032DL (fw4019 Bosch MT) | **386 KB** | 386 KB | `0x09F7EE` | One contiguous block |
| 06A906032RN (fw4013 VDO MT)   | **308 KB** | 308 KB | `0x0B2F00` | One contiguous block |
| 06A906032LP (fw4013 VDO MT)   | **306 KB** | 306 KB | `0x0B35F2` | Same as RN |
| 06A906032SL (X505R VDO DSG)   | **321 KB** | 315 KB | `0x0AF360` | DSG variant |
| 4B0906018CM (fw4012 Bosch MT) | **306 KB** | 306 KB | `0x0B37E0` | A6/Passat |
| 8D0907551M  (fw6005 ME7.1)    | **454 KB** | 454 KB | `0x08E472` | Enormous — S4 B5 |
| 4B0907551AA (fw6005 ME7.1)    | **443 KB** | 443 KB | `0x0911EE` | A6 C5 |
| 4Z7907551B  (fw6005 ME7.1)    | **451 KB** | 451 KB | `0x08F192` | Allroad |
| 4D1907558D  (ME7.1.1 RS4/S8)  | **194 KB** | 194 KB | `0x0CF3EA` | V8 — less free |

### Cal area free space (also 0xFF)

Each ECU also has 25–30 KB free in the calibration area (`0x010000–0x07FFFF`)
— usable for extra map sets (KFZW, KFLDS, KFMIRL for octane switching etc):

| ECU | Free cal | Largest cal block |
|---|---|---|
| DL fw4019 | ~40 KB | 30 KB @ `0x028812` |
| RN fw4013 | ~32 KB | 26 KB @ `0x029A94` |
| 8D ME7.1  | ~12 KB | 6 KB @ `0x020322` |

### Scale reference

- noice's SpeedDensity function (topic 17703): **~286 bytes**
- NefMoto launch control + NLS script: **~4 KB**
- Multimap switch + 4 extra cal sets: **~5–8 KB total**
- 6-hour timed tune (timer + redirect logic): **~300 bytes code + extra cal sets**
- All of the above combined: **under 15 KB** — tiny fraction of available space

---

## ADC channel assignments

The C167 has 16 ADC channels (AN0–AN15). Channel selection is written to
ADCON (SFR at `F0A0h`) as `0xX000` where X = channel number (0–F).

**Critical:** The physical pin-to-channel mapping depends on the PCB — Bosch-sourced
ECUs (DL/HN) and VDO-sourced ECUs (RN/LP) route signals to different channels.
Do not assume DL channel assignments apply to RN or vice versa.

### ME7.5 1.8T — Bosch hardware (DL, HN, fw4019)
*Bosch part number prefix: `0 261 206 8xx`*

| ADC Ch | Signal | Variable | References | Notes |
|---|---|---|---|---|
| **8** | MAF voltage (MLHFM) | `ushfm_w` | 159 | Primary load input — by far the most-read |
| **1** | Boost MAP sensor | `uss_w` / `ps_w` | 11 | Post-turbo absolute pressure |
| **2** | IAT or coolant NTC | `ulf_w` / `tmot_w` | 10 | Non-linear thermistor |
| **4** | TPS / throttle angle | `ugdk_w` | 9 | Potentiometer 0–5V |
| **6** | Battery voltage ref | `ubat_w` | 1 | Occasional read |
| **12** | Front narrowband O2 | `ulavo_w` | 1 | Lambda upstream |
| **15** | Rear narrowband O2 | `ulsas_w` | 1 | Lambda downstream |
| **0,3,5,7,9,10,11,13,14** | — | — | 0 | **FREE in ROM code** |

**Best candidate for MAP sensor injection (speed density):** Channel 7.
Zero references in any DL/HN ROM. The rear O2 wire (`ulsas_w`, ch15) is
the practical hardware path — repin to 5V supply + MAP sensor output.
noice's implementation (topic 17703) used ch7 on his S3 ECU; the approach
is identical: 2-byte change to the ADC channel selector constant.

### ME7.5 1.8T — VDO hardware (RN, LP, PL, HL, fw4013)
*Bosch part number prefix: `0 261 206 8xx` (different sub-range)*

| ADC Ch | Signal | References | Notes |
|---|---|---|---|
| **14** | MAF voltage (MLHFM) | dominant | VDO board routes MAF to ch14, not ch8 |
| **12** | Boost MAP or O2 | several | |
| **1,2,4,6,8** | Various sensors | moderate | Same logical signals, different physical routing |
| **3,5,7,9,10,11,13** | — | **0** | **FREE in ROM code** |

⚠️ If you write speed-density code from a DL/HN bin and cross-flash to RN:
the ADC channel constant must be changed from ch7/ch8 to the equivalent
free channel on the VDO board. 2-byte edit.

### ME7.1 2.7T biturbo — all variants (8D, 4B, 4Z7, 4D1)

| ADC Ch | Signal | Notes |
|---|---|---|
| **8** | MAF voltage | Primary, same as DL Bosch board |
| **12** | O2 sensor (one of four) | 2.7T biturbo has 4 O2 sensors total |
| **1,2,4** | MAP, temps, TPS | Standard pattern |
| **3,5,6,7,9,10,11,13,14,15** | **FREE** | More free channels — less instrumented |

The 2.7T has a dedicated knock sensor controller (not ADC), so those
channels are not consumed. More free ADC than any 1.8T variant.

### 4D1 RS4/S8 V8 — ME7.1.1 (least free ROM)

| ADC Ch | Used | Notes |
|---|---|---|
| **1,2,4,6,8,10,12,14** | Yes | More channels used — extra sensors for V8 |
| **3,5,7,9,11,13,15** | **FREE** | Still 7 free channels |

Only 194 KB free code space (vs 450+ KB for other 2.7T) due to more complex
V8 engine management code.

---

## ECU cross-flash compatibility

### The fundamental rule: hardware revision must match firmware

The ROM firmware is compiled for a specific **PCB hardware revision**. The
hardware revision determines pin assignments, ADC routing, injector driver
configuration, and coil driver topology.

```
Bosch ECU (0 261 206 8xx)  ←→  DL, HN  firmware only
VDO ECU   (0 261 206 9xx)  ←→  RN, LP, PL, HL, GL, SL  firmware only
```

Cross-flashing Bosch firmware onto a VDO board (or vice versa) will appear
to flash successfully but the car will not run — the MAF is on the wrong
ADC channel and all sensor readings are garbage.

### Transmission — why AT bins won't work on MT hardware

The DSG/Tiptronic firmware (SL, GL) has fundamentally different torque
management code. The AT expects torque request signals from the gearbox
TCU over CAN; an MT has no TCU. The engine will start but torque delivery
will be erratic and the car may limp or cut out under load.

### The no-start problem — almost always IMMO, not firmware

Every ME7 ECU stores a **Secret Key Code (SKC)** in a 95040 EEPROM chip
on the PCB (separate from the main flash). This SKC is paired with:
- The instrument cluster
- The transponder in each key

**Flashing a new ROM does not change the SKC.** If you flash a DL ROM onto
an HN ECU, the car will start fine because the SKC in the physical EEPROM
chip hasn't changed.

**The car won't start when** you physically swap an ECU from a different car:
the donor ECU's EEPROM has a different SKC that doesn't match your cluster
and keys. This is why your MK4 VW experiment with a wrong ECU didn't start —
IMMO mismatch, not ROM mismatch.

Solutions:
1. EEPROM recode — read the target vehicle's EEPROM, write SKC into the donor
2. Cluster swap — match the cluster from the donor car
3. IMMO delete — code patch (P1681 etc.) for standalone / swap use

### PL (6-speed) vs HL (5-speed)

Both are VDO fw4013 hardware. The ROM code is identical. The difference is
in the **calibration data**:
- Gear ratio constants used for speed → gear calculation
- The 5th-gear torque mode table (our FixedAddr patch at `0x00881D`)
- VMAX speed calculation (wheel circumference assumed differs slightly)

Cross-flashing PL onto HL will run but the ECU will miscalculate which
gear you're in and may apply wrong torque corrections. The 5th-gear torque
map will also apply to 6th gear or not apply correctly. Fixable by cal
editing once you know the gear ratios.

### RN vs HN — the one you know doesn't work

RN (`06A906032RN`) is VDO hardware, fw4013.
HN (`06A906032HN`) is Bosch hardware, fw4019.
Different PCB, different ADC routing, different injector driver stage.
The binary is not interchangeable in any direction.

---

## ADC free channel summary table

Quick reference for code injection projects:

| ECU family | Most likely free channel | Practical access point |
|---|---|---|
| DL/HN Bosch fw4019 | Ch 7 | Rear O2 sensor wire (repin to 5V + MAP) |
| RN/LP/PL VDO fw4013 | Ch 7 or 13 | Same approach — rear O2 wire |
| 8D/4B/4Z7 ME7.1 2.7T | Ch 7 or 13 | Rear O2 sensor (one of the four) |
| 4D1 RS4/S8 V8 | Ch 7 | Rear O2 bank 2 downstream |

Using the MAF wire (replacing the MAF entirely) is the cleanest approach for
permanent speed-density builds — prj's recommendation in topic 17703. The
MAF ADC channel is already filtered and sampled correctly in the existing
firmware; you're just changing what sensor feeds it.

---

*Analysis generated from corpus of 57 × 2.7T stock ROMs and 13 × 1.8T ROMs.*
*ADC channel counts based on C167 ADCON write patterns in code area (0x080000+).*
*Free space = contiguous 0xFF regions ≥ 64 bytes in the 1 MB flash image.*
