# ME7.x ECU Family Hardware Notes
# Generated from corpus analysis of 86 ROM files

## Engine / Turbo / Sensor Matrix

### 2.7T Biturbo Family (ME7.1 / ME7.1.1)

| ECU PN         | Engine | Market / Model    | Turbos | Injectors | Front O2 | Rear O2 | SAP | EGT | CDSLS | CWKONLS |
|----------------|--------|-------------------|--------|-----------|----------|---------|-----|-----|-------|---------|
| 8D0907551(all) | AGB/AZB/AZR | S4 B5        | K03×2 | ~269cc    | NB ×2   | NB ×2  | Most variants | No | 00-02 | 0x33 |
| 4B0907551(all) | AGB/AZB | A6 C5 2.7T    | K03×2 | ~269cc    | NB ×2   | NB ×2  | Most variants | No | 00-01 | 0x33 |
| 4B0907551 F/G/K | AGB  | A6 C5 later   | K03×2 | ~269cc    | NB ×2   | NB ×2  | Yes | No | 00 | 0x04 |
| 4Z7907551(all) | ARE   | allroad C5        | K03×2 | ~269cc    | NB ×2   | Config varies | Yes | No | 01 | 0x00 |
| 4D1907558(all) | BCY/AQJ | RS4 B5 / S8 D2 | K04×2 | ~300cc+   | NB ×2   | None   | No | YES | 00 | 0x00 |

Notes:
- CWKONLS=0x33: both banks, 3 O2 sensors each monitored
- CWKONLS=0x04: single-bank-style O2 config (later A6 C5 harness variant)
- CWKONLS=0x00: no rear O2 monitoring (allroad/RS4 different rear sensor config)
- CDSLS=0x02: early 8D variants (A, D), SAP variant 2 encoding, no MSLUB table
- Allroad adds: air suspension codewords CDDST, CDLSVV, CDDSBKV

### 1.8T 20V Family (ME7.5)

| ECU PN          | Engine | Model          | Turbos | Injectors | Front O2 | Rear O2 | SAP | CDLATP |
|-----------------|--------|----------------|--------|-----------|----------|---------|-----|--------|
| 06A906032DL     | AWD    | Golf IV 150hp  | K03s   | ~200cc    | WB (LSU4.2) | NB | Yes | 0x01 |
| 06A906032RN     | AWD?   | Golf IV 150hp  | K03s   | ~200cc    | WB      | NB      | Yes | 0x01 |
| 06A906032HN     | AWD    | Golf IV 150hp  | K03s   | ~200cc    | WB      | NB      | Yes | 0x01 |
| 06A906032LP     | AWP    | Golf GTI 180hp | K03s   | ~225cc    | WB      | NB      | Yes | 0x01 |
| 06A906032CL/CM  | AUM?   | variant        | K03s   | varies    | WB      | NB      | Yes | 0x01 |
| 4B0906018CM     | AWM    | Passat B5.5 170hp | K03s | ~200cc  | WB      | NB      | Yes | 0x01 |
| 8N0906018S      | BAM    | TT 225hp       | K04    | ~225cc    | WB      | NB      | Yes | 0x01 |

Notes:
- ALL 1.8T ME7.5 variants in corpus: CDLATP=0x01 = wideband upstream O2 (LSU4.2/4.9)
- The ATC 1.8T (narrowband front O2, CDLATP=0x00) is a DIFFERENT older ECU family
- Turbo variants: K03=150hp, K03s=180hp, K04=225hp -- same engine block, different mapping
- Injector sizing difference frozen in KRKTE + TVUB calibration constants

---

## ADC Channel Architecture

### Confirmed: Both ME7.1 (C167CR) and ME7.5 (ST10F27x) use ADC AUTO-SCAN mode

The ADC hardware runs independently, cycling through all 16 channels continuously.
An ISR fires after each conversion and stores the result to a RAM buffer:

**RAM buffer (both ME7.1 and ME7.5):**
```
RAM[0x80A2] = ADC ch0 result
RAM[0x80A4] = ADC ch1 result
...
RAM[0x80A2 + 2*N] = ADC chN result
...
RAM[0x80C2] = ADC ch14 result   ← EGT bank1 on RS4, spare on S4
RAM[0x80C4] = ADC ch15 result   ← EGT bank2 on RS4, totally unused on S4
```

Firmware confirmation:
- `CMP R4, #15` at 0x0783E4 in 8D0907551M: confirms 16-channel scan loop
- `MOV R4, ADCON` reads confirmed at 0x078E30+ (read result from ADC)
- 0 writes to ADCON: channel select is hardware auto-scan, not firmware-controlled
- ME7.5 (ST10): same pattern -- 70 ADCON reads, 0 writes

### 2.7T S4/A6: Spare ADC channels (ADC14/15 = EGT pins)

**ADC14 (RAM[0x80C2]):**
- 1 firmware reference at 0x079F36 in 8D0907551M
- Read for an overtemp gate comparison (EGT threshold check)
- Floating pin → random noise → gate never triggers → correct behavior
- RS4 (4D1): 4 references → active EGT processing, enrichment table, protection

**ADC15 (RAM[0x80C4]):**
- 0 firmware references in 8D → value scanned but never consumed
- RS4 (4D1): 8 references → second EGT bank processing

**PCB note:** The 8D/4B S4/A6 ECU PCB may have thermocouple signal conditioning
on these pins (to match the RS4 PCB layout) OR may have a simple direct ADC input.
This needs hardware verification (PCB inspection) before connecting a 0-5V source.

### 1.8T ME7.5: Spare ADC channels

**CO-Topf wire (MAF emissions test probe):**
- Physical wire in MAF housing connector, present in all Euro-market 1.8T cars
- Goes to an ADC channel (specific channel TBD -- not yet traced in firmware)
- 0-5V compatible, no signal conditioning
- HachiROM repurposes this as a configurable analog input
- MLCO calibration constant sets its zero offset

**Downstream O2 channels:**
- If rear O2 sensor removed: channel floats to ~0V (ECU PCB pulldown)
- Full lambda processing firmware active on this channel
- Wideband O2 controller (0-5V output) would need a voltage divider
  to stay within the NB lambda circuit input range (~0-1V typical)

---

## Variant-Specific Patch Applicability

### ESKONF Rear O2 Heater Disable (EE XX ZZ 02 A8 anchor)

| Variant | newer (0F 01 05) | older-06 (06 02 A8) | older-05 (05 02 A8) |
|---------|:---:|:---:|:---:|
| 8D all | ✓ 18/18 | ✓ 14/18 | ✓ 4/18 |
| 4B all | ✓ 12/12 | ✓ 6/12  | ✓ 6/12 |
| 4Z7 ME7.1 (B-M) | ✓ | ✓ 4/12 | ✓ 6/12 |
| 4Z7 ME7.1.1 (AA/N-T) | ✓ | — | — |
| 4D1 all | ✓ 7/7 | — | — |

Note: "newer" covers all variants universally. "older" patches provide
additional coverage on the same files (two pattern sites patched = more robust).

### SAP MSLUB Table Zero

| Variant | Coverage | Reason for gaps |
|---------|:--------:|-----------------|
| 8D (14/18) | ✓ | Early A/D variants (CDSLS=0x02) have different table encoding |
| 4B (8/12)  | ✓ | Later variants differ |
| 4Z7 (20/20)| ✓ | allroad always has SAP |
| 4D1 (0/7)  | — | V8 never had SAP — table absent |

---

## Field Diagnostics: MAF Disconnect Test (1.8T ME7.5)

### What happens when you unplug the MAF

On ME7.5 1.8T, physically disconnecting the MAF sensor causes the ECU to
throw **P0100/P0102** and switch its load calculation from MAF-based to the
**Alpha-N fallback map** — a throttle-position × RPM lookup stored in ROM.
The MAP sensor is **not** used as a load source in this fallback; on ME7.5
the MAP sensor feeds boost control (N75 target and boost cut logic), not
the primary load path.

The Alpha-N fallback map on 1.8T is at the address documented in
patch_catalogue.md under "Alpha/N MAF Error Filling" (12×6 RPM×TPS grid).
It is intentionally conservative — the ECU will run but not make full power
or correct fuelling across the rev range.

### Why this is a useful diagnostic

If the engine runs **noticeably better** with the MAF unplugged than with
it connected, the MAF signal is corrupted and its measured value is worse
than no signal at all. Two common causes:

**Boost leak upstream of the MAF (most common on modified cars):**
The MAF measures real airflow entering the intake — but some of that air
escapes through a split hose, loose intercooler pipe, or cracked boost
pipe before reaching the cylinders. The ECU commands fuelling for the
measured air mass, but the engine only burns a fraction of it. Result:
the car runs rich and makes less boost than commanded (pressure bleeds
off through the leak). Boost control starts hunting trying to compensate.
Disconnecting the MAF removes the corrupted signal — Alpha-N fuelling,
while imprecise, is at least consistent and not actively wrong.

**Failing MAF element:**
A degraded hot-wire or hot-film element can produce a plausible but
incorrect signal — too low at idle, too high at part throttle, or
non-linear across the sweep — without triggering a range fault. The
engine runs poorly throughout the rev range rather than just under boost.
Disconnecting forces Alpha-N and if the behaviour improves, the MAF
element itself is the culprit.

**How to use this test:**
1. Cold start and let idle stabilise
2. Note idle quality, part-throttle response, and boost behaviour
3. With engine off, unplug MAF connector
4. Restart — ECU will set P0100/P0102 immediately (expected)
5. Drive conservatively; compare feel to step 2
6. If better → follow up with boost leak test (pressurised intake) or
   substitute-test a known-good MAF element
7. If no change or worse → MAF is probably fine; look elsewhere

**What this test does NOT tell you:**
- It cannot distinguish a failing MAF from a boost leak — both produce
  the same qualitative result. A pressurised boost leak test is required
  to separate them.
- Alpha-N fuelling is not accurate enough for meaningful lambda or power
  comparison — do not draw conclusions from WOT runs in MAF-disconnected
  state.
- On cars with a wideband O2 installed, the wideband trace while connected
  vs disconnected is more informative than seat-of-the-pants feel.

### Relationship to MAF Delete patches

The MAF Delete patches in MESevenTool permanently redirect the load
calculation to Alpha-N (FA18/FA19→FA22/FA23 etc.) and require retuning
the Alpha-N map for the actual engine. The MAF disconnect test is the
untuned, stock-map version of the same thing — useful precisely because
it is temporary and reversible, not as a permanent fix.

### Platform note

This behaviour is specific to ME7.5 1.8T. On 2.7T ME7.1/ME7.1.1 (biturbo),
MAF disconnect behaviour is architecturally similar but the fallback map
addresses and DTC codes differ. The VR6 and V8 variants have their own
MAF fault handling paths — do not generalise this test across platforms
without verifying the firmware behaviour for that specific ECU family.
