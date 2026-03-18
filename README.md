# MESevenTool

[![CI](https://github.com/dspl1236/MESevenTool/actions/workflows/ci.yml/badge.svg)](https://github.com/dspl1236/MESevenTool/actions/workflows/ci.yml)

Python library and analysis tool for Bosch ME7.x ECU ROM files — VAG 1.8T (ME7.5) and 2.7T biturbo (ME7.1/ME7.1.1).

**28 confirmed code/cal patches · 5 confirmed RPM scalar reads · 388 tests · corpus-verified against 57 stock 2.7T ROMs and 13 1.8T ROMs.**

---

## What it does

MESevenTool finds, verifies, and applies ECU patches **without hardcoded addresses**. Every patch is located at runtime by searching for C167 machine-code needle sequences that are stable across all firmware variants of the same family. Load any supported `.bin` and the tool automatically resolves the right byte locations.

### Core capabilities

| Capability | Detail |
|---|---|
| **Needle search** | Masked C167 bytecode patterns — locates patches in any firmware variant |
| **Patch detection** | Reports STOCK / PATCHED / MISSING / UNKNOWN per patch for any ROM |
| **Patch application** | Apply or revert any confirmed patch programmatically |
| **Scalar reads** | Read/write numeric ECU values (RPM limits) from code-immediate sites |
| **ECU identification** | Part number, firmware version string, engine code from ROM |
| **ROM I/O** | Load, mutate, and save 1 MB ME7 `.bin` files |
| **XDF parsing** | Parse TunerPro `.xdf` definition files for map cross-reference |
| **DPP extraction** | C167 DPP0–DPP3 address segment extraction from startup code |
| **Checksum** | ME7 main + multipoint CRC32 verify and correct |
| **KWP2000** | Basic ECU communication scaffolding (in progress) |

---

## Supported ECU families

### ME7.5 — 1.8T Turbo

| Part number | Engine | Power | Firmware |
|---|---|---|---|
| 06A906032DL | AWP | 180 hp | fw4019 |
| 06A906032HN | AWP | 180 hp | fw4019 (Unitronic Stage 2) |
| 06A906032RN | AWP | 180 hp | fw4013 |
| 06A906032LP | AWP | 180 hp | fw4013 |
| 06A906032SL | — | — | X505R (DSG auto) |
| 4B0906018CM | AWM | 170 hp | fw4012 (A6/Passat) |

All five MAF Delete variants, the full RPM limiter scalar stack, all emissions patches, and VMAX are confirmed across these files.

### ME7.1/ME7.1.1 — 2.7T Biturbo

Corpus of **57 stock ROMs** across four body variants:

| Family | Files | ME7 version |
|---|---|---|
| 8D0907551x (A4 B5) | 18 | ME7.1 + ME7.1.1 |
| 4B0907551x (A6 C5) | 12 | ME7.1 + ME7.1.1 |
| 4Z7907551x (allroad) | 20 | ME7.1 + ME7.1.1 |
| 4D1907558x (A8 D2 V8) | 7 | ME7.1.1 only |

---

## Patch catalogue — 28 CONFIRMED

### Emissions (15)

| Patch | Target | Method |
|---|---|---|
| Rear O2 Monitor Threshold | ME7.5 DL/HN | OffsetPatchDef — anchor on ECU PN string |
| Rear O2 Monitor Threshold (LP fw4013) | ME7.5 LP | OffsetPatchDef — anchor "06A906032LP" |
| Rear O2 OBD Readiness Flags | ME7.5 1.8T | MultiOffsetPatchDef — anchor "40/1/ME7.5" |
| ESKONF Rear O2 Heater Disable (newer 0F 01 05) | 2.7T ME7.1 all | MultiOffsetPatchDef — all 57 corpus files |
| ESKONF Rear O2 Heater Disable (older-06) | 2.7T ME7.1 earlier | MultiOffsetPatchDef — 17/57 corpus files |
| ESKONF Rear O2 Heater Disable (older-05) | 2.7T ME7.1 earlier | MultiOffsetPatchDef — 13/57 corpus files |
| SAP MSLUB Airflow Table Zero | 2.7T ME7.1 (not 4D1) | OffsetPatchDef — MISSING on V8 (no SAP) |
| SAP Diagnosis Disable CDSLS (4B0906018) | 1.8T A6/Passat | FixedAddr 0x0181B0 |
| SAP Diagnosis Disable (ME7.5 1.8T) | ME7.5 DL only | OffsetPatchDef — SAP-equipped ECUs |
| EVAP Purge Diagnosis Disable (ME7.5 1.8T) | ME7.5 DL only | OffsetPatchDef — SAP-equipped ECUs |
| Rear O2 Sensor Diagnosis Disable | 2.7T all | OffsetPatchDef — CDLSH, anchor on PN |
| Catalyst Monitor Disable CDKAT (4B0906018) | 1.8T A6/Passat | FixedAddr 0x0181A1 |
| Knock Sensor Monitor Disable CDKVS (4B0906018) | 1.8T A6/Passat | FixedAddr 0x0181A2 |
| Knock Sensor Variant Disable CDKVS2 (4B0906018) | 1.8T A6/Passat | FixedAddr 0x0181A3 |
| EVAP Diagnosis Disable (4B0906018) | 1.8T A6/Passat | FixedAddr 0x0181B2 |

### Fuelling (5)

MAF Delete redirects the load calculation from the MAF sensor to the Alpha-N throttle-angle table, enabling MAF-off / Alpha-N operation. Five variants cover all known 1.8T ME7.5 firmware builds:

| Variant | Target firmware | Stock bytes → patch bytes |
|---|---|---|
| ME7.5 06A (DL/HN fw4019) | DL, HN | FA18/FA19 → FA22/FA23 |
| ME7.5 RN/LP (fw4013) | RN | FA48/FA49 → FA22/FA23 |
| ME7.5 LP/18CM (fw4013/4012) | LP, 18CM | FA34/FA35 → FA22/FA23 |
| ME7.5 SL DSG (X505R) | SL | FA4A/FA4B → FA22/FA23 |
| ME7.5 fw4013 alt (FA1E/1F) | 20th Anniversary, rn_base | FA48/FA49 → FA1E/FA1F |

### Ignition (2)

| Patch | Target | Notes |
|---|---|---|
| Knock Retard Disable | ME7.5 1.8T | Code patch — prevents retard value being written to RAM |
| Knock Retard Code Disable (2.7T ME7.1) | 2.7T ME7.1 | F6 F4 → F2 F4 at KRRA accumulator store. 30/57 corpus (ME7.1 only; ME7.1.1 uses different instruction at this site) |

### Performance (5)

| Patch | Target | Notes |
|---|---|---|
| Knock Retard Disable — KRMXN Zero | 2.7T ME7.1/ME7.1.1 | Cal approach — zero KRMXN max-retard table. Unique 16× `0x14` anchor; all 57 corpus files |
| Vmax Speed Limiter Disable (2.7T ME7.1) | 2.7T ME7.1 | `E6 FD A8 61` 3-hit needle |
| Vmax Speed Limiter Disable (2.7T ME7.1.1 / V8 RS4) | 2.7T ME7.1.1 | ATOMIC prefix variant |
| Vmax Speed Limiter Disable (ME7.5 — all variants) | ME7.5 1.8T all | Code-immediate, **2 hits/file — apply twice** |
| 5th-Gear Torque Mode Disable | ME7.5 1.8T | FixedAddr 0x00881D — byte 0x0F → 0x00 |

### Diagnostics (1)

| Patch | Target | Notes |
|---|---|---|
| P1681 Immobiliser Databus CEL Disable | 2.7T ME7.1.1 | JMPR UC codeword — suppresses DTC P1681 |

---

## RPM limiter scalars — 5 CONFIRMED

All five scalars use the constant `0x4A` low byte. Only the high byte varies by firmware version and tune level. Scale: **0.75 RPM per raw bit**, `size = 2`, little-endian.

| Scalar | DL/LP (fw4019) | RN (fw4013) | 18CM (fw4012) | Unitronic S2 | Hits/file |
|---|---|---|---|---|---|
| Hard Rev Limit | 7160 RPM | 7352 RPM | 6968 RPM | 7544 RPM | **2** |
| Hard Rev Limit — alt path | 7160 RPM | 7160 RPM | 6776 RPM | 7352 RPM | 1 |
| Overrev Protection | 8180 RPM | 8180 RPM | 7988 RPM | 8372 RPM | 1 *(MT only)* |
| Emergency RPM Cut (NKILL) | 10424 RPM | 10424 RPM | 10424 RPM | 10808 RPM | **2** |
| Fuel Cut Resume RPM | 7160 RPM | 7160 RPM | 6776 RPM | 7352 RPM | 1 |

Hard Rev Limit and NKILL have two identical call sites per ROM — both sites must be written for a change to take effect.

---

## Python API

```python
from meseventool.rom import ROMImage
from meseventool.needle import Searcher
from meseventool.patches import ALL_PATCHES, ALL_SCALAR_PATCHES, PatchState

# Load ROM
rom = ROMImage.load("my_ecu.bin")
s   = Searcher(rom)

# Detect all patches
for patch in ALL_PATCHES:
    result = patch.detect(rom, s)
    print(f"{result.state.name:8}  {patch.name}")

# Apply a patch (handle multi-hit patches with a loop)
vmax = next(p for p in ALL_PATCHES if "ME7.5" in p.name and "Speed" in p.name)
for _ in range(3):
    r = vmax.detect(rom, Searcher(rom))
    if r.state == PatchState.STOCK:
        vmax.apply(rom, r)
    else:
        break

# Read an RPM scalar
hard_rev = next(p for p in ALL_SCALAR_PATCHES if "Hard Rev Limit (ME7.5" in p.name)
print(f"Hard rev limit: {hard_rev.read(rom, s):.0f} RPM")

# Fix checksums and save
from meseventool.checksum import fix_checksums
fix_checksums(rom)
rom.save("my_ecu_patched.bin")
```

### Detection state meanings

| State | Meaning |
|---|---|
| `STOCK` | Patch is present and unmodified — safe to apply |
| `PATCHED` | Already applied |
| `MISSING` | Needle not found — patch does not apply to this ROM variant |
| `UNKNOWN` | Needle found but bytes match neither stock nor patched state |

---

## Architecture

```
meseventool/
  rom.py          ROMImage — load/save/read/write flat .bin
  needle.py       Searcher — C167 masked pattern search engine
  patches.py      PatchDef, OffsetPatchDef, MultiOffsetPatchDef,
                  FixedAddressPatchDef, ScalarPatchDef — full patch catalogue
  profiles.py     ROMProfile — per-variant platform tags and detection
  ecu_id.py       ECU identification from ROM version strings
  maps.py         MapDef — calibration table definitions
  checksum.py     ME7 main + multipoint CRC32 verify and correct
  dpp.py          C167 DPP0–DPP3 address segment extraction
  kwp.py          KWP2000 ECU communication scaffolding
  xdf.py          TunerPro XDF export
  xdf_parser.py   TunerPro XDF import / cross-reference

tests/            388 unit + corpus tests (pytest)
docs/             Technical notes on codeword block, O2 classification
reference/        8D XDF, C167 datasheet, ME7RomTool C source
tools/            sgo_extract.py — SGO archive extractor
```

### Patch type hierarchy

```
PatchDef             — needle → fixed offset → stock/patch bytes
OffsetPatchDef       — anchor string → offset → single byte/word
MultiOffsetPatchDef  — anchor string → multiple independent byte offsets
FixedAddressPatchDef — absolute ROM address (address is rock-solid across all variants)
ScalarPatchDef       — needle → numeric read/write with scale factor
```

---

## Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -v
```

388 tests: needle search, patch detect/apply/revert, scalar reads at known RPM values, ECU ID extraction, XDF parsing, checksum verify/correct, platform filtering, multi-hit apply loops. Corpus-backed tests skip automatically if ROM files are absent.

---

## Adding a new patch

```python
# Add to ALL_PATCHES in meseventool/patches.py:
PatchDef(
    name          = "My New Patch",
    description   = "What it does and why",
    category      = PatchCategory.EMISSIONS,
    needle        = bytes([0xF6,0xF4, 0x00,0x00, 0xDB,0x00]),
    mask          = bytes([0xFF,0xFF, 0x00,0x00, 0xFF,0xFF]),
    offset        = 2,
    stock_bytes   = b'\x01',
    patch_bytes   = b'\x00',
    confidence    = "CONFIRMED",   # "UNCONFIRMED" until corpus-verified
    notes         = "Confirmed STOCK in: X. Confirmed PATCHED in: Y.",
    applies_to    = {"me7.5", "1.8t"},
),
```

`"CONFIRMED"` requires at least one corpus file showing `STOCK` and one showing `PATCHED` for the needle, with no spurious hits in unrelated families. `"UNCONFIRMED"` patches are rejected at catalogue import time.

---

## Credits

Needle approach and checksum algorithm derived from [ME7RomTool_Ferrari](https://github.com/360trev/ME7RomTool_Ferrari) by 360trev and nyet — MIT licence.

Stock ROM corpus from [files.s4wiki.com](https://files.s4wiki.com) — S4wiki community.

Community tuning reference from [NefMoto](http://nefariousmotorsports.com) and [s4wiki.com/wiki/Tuning](https://s4wiki.com/wiki/Tuning).
