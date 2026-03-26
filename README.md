# MESevenTool

[![CI](https://github.com/dspl1236/MESevenTool/actions/workflows/ci.yml/badge.svg)](https://github.com/dspl1236/MESevenTool/actions/workflows/ci.yml)
[![Download](https://img.shields.io/github/v/release/dspl1236/MESevenTool?label=Download&logo=windows)](https://github.com/dspl1236/MESevenTool/releases/latest/download/MESevenTool.exe)

ROM editor and patch tool for Bosch ME7.x ECUs (Bosch Motronic ME7.1, ME7.1.1, ME7.5).

**[⬇ Download MESevenTool.exe (Windows)](https://github.com/dspl1236/MESevenTool/releases/latest/download/MESevenTool.exe)**

**CPU:** Infineon C167CR (16-bit, little-endian) — all supported variants.

> **⚠ Work in Progress — Use at Your Own Risk**
>
> This tool is under active development. Features may be incomplete, map
> addresses may be unverified, and patches may not have been tested on all
> hardware variants. **Always read and back up your original ROM before making
> any changes.** Read it twice, compare the files, keep both copies safe.
>
> If you find a bug, incorrect address, or have a ROM dump to contribute,
> please [open an issue](https://github.com/dspl1236/MESevenTool/issues).

**ROM:** 256KB (ME7.1 early), 512KB (ECUFlash extract), or 1MB (ME7.5 full flash).  
**Memory map:** File offset 0x00000 = C167 address 0x80000. No mirroring.

---

## Supported Profiles

| Profile | Part prefix(es) | Engine | ROM | Notes |
|---------|----------------|--------|-----|-------|
| ME7.5 — 06A 1.8T | `06A906032`, `8N0906018`, `1C0906032` | AWP/AWW/AWD/AUM/AUQ/BAM/APH | 1MB | Golf4/Jetta4/TT/A3/S3/Beetle turbo |
| ME7.5 — 225hp 1.8T | `06A906032`, `8N0906018` | AMU/APX/BFV | 1MB | TT Quattro 225, S3 8L |
| ME7.5 — 180hp AUQ | `06A906032`, `8N0906032` | AUQ | 1MB | TT Roadster, some A4 B6 |
| ME7.5 — 06B/4B0 1.8T | `06B906018`, `4B0906018`, `8E0909518` | AWM/AUG/AWT/ATW/AMB | 512KB | A6/Passat/A4 longitudinal |
| ME7.5 — 2.0T FSI | `06F906056` | BWT/BWA/AXX/BPY | 1MB | Golf5 GTI, A3 8P (placeholder) |
| ME7.5 — 2.3 V5 | `071906018` | AGZ/AQN/AZX | 1MB | Passat/Golf V5 (placeholder) |
| ME7.1 — AGU/AEB early | `06A906018`, `8D0907557`, `8D0907559` | AGU/AEB/ANB/AQY | 256KB | A3 8L, Golf4, A4 B5 early |
| ME7.1 — 2.7T biturbo | `8D0907551`, `4B0907551`, `4Z7907551` | AGB/ARE/BES | 1MB | S4 B5, A6 C5, early Allroad |
| ME7.1.1 — 2.7T biturbo | `4Z7907551` | AGB/ARE/BCY | 1MB | Allroad N/Q/R/S/T/AA |
| ME7.1.1 — V8 biturbo | `4D1907558` | BCY/AKH/AQJ | 1MB | RS4 B5, S8 D2 |
| ME7.1 — 2.8 V6 N/A | `078906018` | ACK/ALG/AQD/AMX | 1MB | A4/A6/Passat 30V (placeholder) |
| **ME7.1 — VR6 N/A** | **`022906032`, `021906018`** | **AHG/AZZ/BDE/AXYP/BFH** | **1MB** | **Golf4/Jetta4 VR6, R32** |

---

## Known Stock ROMs — 25 Confirmed

CRC32 catalog covers OEM/unmodified ROM images. Used for stock detection and as
safe baseline before patching.

| CRC32 | Part number | Bosch number | Engine/Variant |
|-------|-------------|-------------|----------------|
| `0x1e1bc31a` | 06A906032DL | 0261206890 | Golf4/Jetta4 AWW 150hp fw4019 Bosch |
| `0x8bb14b75` | 06A906032DL | 0261206890 | Golf4/Jetta4 AWW 150hp fw4019 Bosch rev2 |
| `0x6262fb03` | 06A906032AR | 0261206436 | Golf4/Jetta4 ARZ 150hp fw4013 VDO |
| `0x9372b946` | 06A906032DS | 0261207080 | Bora 2.0 AZG 115hp fw4220 |
| `0xfab1a067` | 06A906032HP | 0261207441 | Bora/Golf4 AUM 180hp fw4019 |
| `0xa9b537b9` | 06A906032HS | 0261207446 | Golf4 AWP 180hp fw4019 Bosch |
| `0x5c0ceeae` | 4B0906018AG | 0261206453 | Passat B5 ATW 150hp 4B0 fw4016 |
| `0x386dcb34` | 4B0906018AT | 0261206532 | Passat B5 APU 150hp 4B0 fw4016 |
| `0xf7b8ce22` | 4B0906018B  | 0261206050 | Passat B5 APU 150hp 4B0 fw4017 |
| `0x9d9a16c4` | 4B0906018BF | 0261206525 | Passat B5 ANB 150hp 4B0 fw4016 |
| `0x28e1e3cc` | 8L0906018M  | 0261206797 | Audi TT 8L AMU 225hp fw4018 |
| `0x7815dae4` | 8D0907559C  | 0261206315 | Audi A4 B5 AGU 150hp 256KB |
| `0x5bbee924` | 06A906018AQ | 0261204678 | Audi A3 8L AGU 150hp 256KB rev1 |
| `0x6d8d38cb` | 06A906018AQ | 0261204678 | Audi A3 8L AGU 150hp 256KB rev2 |
| `0x85dd801e` | 06A906018R  | 0261204673 | VW Golf4 AGU 150hp 256KB |
| `0xb8c7dbce` | 8D0907551A  | 0261206110 | Audi S4 B5 ARE 265hp fw6005 |
| `0x6044f9dd` | 8D0907551D  | 0261206382 | Audi S4 B5 AGB/ARE 250hp fw6001 |
| `0x1c8e82c6` | 022906032E  | 0261206619 | VW Golf4 VR6 AHG 174hp fw6428 ME7.1 |
| `0x3fb4cfcf` | 022906032CS | 0261207881 | Golf4/Jetta4 VR6 AZZ/BDE 197hp ME7.1.1 |
| `0xbe9ea096` | 022906032CS | 0261207881 | Golf4/Jetta4 VR6 AZZ/BDE 197hp ME7.1.1 r2 |
| `0x6be5a4c5` | 022906032CP | 0261207885 | Golf4 R32 3.2L AXYP 240hp ME7.1.1 |
| `0xbc7b5d85` | 022906032EG | 0261208344 | Golf5/R32 3.2L BFH 250hp fw6432 ME7.1.1 |
| `0x01106d6c` | 021906018R  | 0261206814 | VW Golf4 VR6 174hp 512KB fw6228 ME7.1 |

---

## Patches — 41 Total (36 Original + 5 Immo)

### Categories

| Category | Count | Notes |
|----------|-------|-------|
| Emissions | 19 | O2 monitors, SAP, EVAP, catalyst, knock sensor |
| Performance | 5 | Vmax, knock retard, 5th-gear torque mode |
| Fuelling | 6 | MAF Delete / Alpha-N, MAF diagnosis |
| Ignition | 2 | Knock retard disable (1.8T and 2.7T) |
| Diagnostics | 4 | P1681, VVT cam position monitor (3 variants) |
| **Immobiliser** | **5** | **IMMO-OFF and SKC bypass — see below** |

All patches use **needle-based discovery** — no hardcoded file offsets. Works across
all ROM revisions within each firmware family.

### Immobiliser Patches

> **Important:** ROM reflashing does NOT break IMMO. The ECU's 95040/95080/95160
> EEPROM (SOIC-8) stores the SKC independently. Reflashing the same ECU with a
> different ROM leaves the EEPROM untouched and the car continues starting normally.
>
> These patches are only needed when **physically swapping a donor ECU** into a
> different car whose cluster SKC does not match the donor ECU's EEPROM.

| Patch | Platform | Confidence | Notes |
|-------|----------|------------|-------|
| IMMO-OFF — ME7.5 06A/06B/4B0 fw4013/4016/4017/4019 | `me7.5 mpi` | PROVISIONAL | Kill-branch NOP — injection-kill bypass |
| IMMO-OFF — ME7.5 VDO fw4013 variant | `me7.5 mpi` | PROVISIONAL | Alternate needle for VDO-sourced hw |
| IMMO-OFF — ME7.1 2.7T S4/A6 fw6001/6005 | `me7.1 2.7t` | PROVISIONAL | 8D0907551 family |
| IMMO-OFF — ME7.1.1 Allroad/RS4/VR6 R32 | `me7.1` | PROVISIONAL | 4Z7/4D1/022906032CS/CP/EG |
| IMMO SKC Accept-All — ME7.5 | `me7.5` | UNCONFIRMED | SKC comparison bypass (experimental) |

**PROVISIONAL** = needle structure confirmed from disassembly, bench validation pending.  
**UNCONFIRMED** = needle derived from documentation only.

The C167 CPU NOP is `0x00 0x00` (not the same as HD6303 `0x01` or 8051 `0x00`).
The injection-kill is a `JMPR cc_NE` (opcode `0xC1 0xF4`) replaced with two NOPs.

For **ME7.1.1** ECU swaps, also apply the **P1681 Immobiliser Databus CEL Disable**
patch (already CONFIRMED) to eliminate the fault DTC that logs even after the engine
starts.

---

## Checksum

Two independent checksum systems, both required:

1. **Main ROM checksum** — 16-bit LE word accumulation over the calibration page,
   stored as `[sum:u32][~sum:u32]` at `cal_page + 0xFFF8`.
2. **Multipoint CRC32** — N blocks each `[start:u32][end:u32][crc32:u32][~crc32:u32]`
   discovered by needle. Absent in some variants (OK).

MESevenTool verifies and corrects both before saving.

Calibration page offsets:
- 256KB ROM (ME7.1 early): `0x30000`
- 512KB ECUFlash extract: `0x70000`
- 1MB full flash: `0xF0000`

---

## ROM Architecture

```
C167 address  File offset   Content
0x80000       0x00000       Start of flash
0xF0000       0x70000       Calibration page (512KB) / 0xF0000 (1MB)
0xFFFFF       0xFFFFF       End of flash, reset vectors
```

No A15 mirroring — the full flash is live. XDF offsets are flat file offsets.

### Hardware variants

Two PCB sources exist for ME7.5 06A906032:

| Source | Bosch number prefix | MAF ADC | Examples |
|--------|-------------------|---------|---------|
| **Bosch** | `0 261 206 8xx` | AN0 (ch0) | DL, HN, A, B, C |
| **VDO** | `0 261 206 9xx` | AN14 | RN, LP, PL, HL, GL, SL |

Cross-flashing Bosch firmware onto VDO hardware (or vice versa) puts the MAF
signal on the wrong ADC channel → no load signal → won't run correctly.

---

## KWPBridge Integration

When KWPBridge is running and connected:
- ECU part number matched against loaded ROM — mismatch flagged as warning
- Live data channels: RPM, boost pressure, lambda (per bank for V6/V8),
  ignition advance, knock retard, MAF g/s, coolant temp, TPS

---

## Python API

```python
import zlib
from meseventool.rom import ROMImage
from meseventool.ecu_id import identify
from meseventool.dpp import extract_dpp
from meseventool.profiles import detect_profile
from meseventool.known_roms import lookup_rom, is_known_stock
from meseventool.patches import ALL_PATCHES, detect_all
from meseventool.checksum import ChecksumManager

# Load and identify
rom   = ROMImage.load("my_awp.bin")
ecu   = identify(rom)
dpp   = extract_dpp(rom)
prof  = detect_profile(ecu, dpp)
crc   = zlib.crc32(rom.data) & 0xffffffff

print(f"Part:    {ecu.vmecuhn}")
print(f"Bosch:   {ecu.bosch_number}")
print(f"Version: {ecu.version_string}")
print(f"Profile: {prof.name}")
print(f"Stock:   {is_known_stock(crc)}")
known = lookup_rom(crc)
if known:
    print(f"Known:   {known.label}")

# Check all patches
results = detect_all(rom, profile=prof)
for r in results:
    print(f"  {r.patch.name}: {r.state.name}")

# Verify checksum
cm = ChecksumManager(rom)
ok, msg = cm.verify()
print(f"Checksum: {'OK' if ok else 'BAD'} — {msg}")

# Fix checksum after editing
cm.fix()
rom.save("my_awp_patched.bin")
```

---

## Version History

| Version | Changes |
|---------|---------|
| v0.1.5 (current) | VR6 profile (022906032/021906018), V5 profile, KNOWN_ROMS catalog (25 entries), 5 immo patches (PROVISIONAL), ecu_id VR6 PN regex, 316 tests |
| v0.1.4 | P1681 scope fix, CDNWS 4B0906018CM patch, 427 tests |
| v0.1.3 | MAF Delete Alpha-N (5 variants), Fuel Cut Resume RPM scalar |
| v0.1.2 | 2.7T biturbo patches, ME7.1.1 Allroad variants, K-box logging |
| v0.1.1 | Vmax disable (ME7.5 + ME7.1), 5th-gear torque mode |
| v0.1.0 | Initial release: emissions patches, checksum, DPP, ECU ID |

---

## Known Limitations

| Area | Issue | Status |
|------|-------|--------|
| **CDKAT address conflict** | Two catalyst monitor patches target 0x0181A1 vs 0x0181A2 — one is wrong. Verify against DAMOS | Needs verification |
| **Profile ambiguity** | AWP/AMU/AUQ share `06A906032` prefix — first match wins. Profile ordering is load-bearing | Document / improve |
| **IMMO SKC Accept-All** | Patch bytes == stock bytes (deliberate no-op until bench validated) | UNCONFIRMED |
| **No atomic save** | `rom.save()` overwrites original without backup or temp-file rename | TODO |
| **Overlapping part prefixes** | `detect_profile()` first-match can pick wrong profile for shared prefixes | TODO |
| **No signed scalar patches** | `ScalarPatchDef` assumes unsigned values only | TODO |

---

## Ghidra Bridge (External)

MESevenTool does not embed Ghidra. The correct workflow is:

1. Open 1MB ROM in Ghidra: Language = **Infineon C167**, base = `0x80000`
2. Auto-analyze
3. Export confirmed symbol addresses to JSON (`File → Export → JSON`)
4. *(planned)* `tools/ghidra_import.py` will read the JSON and update `known_roms.py`
   map addresses for that specific part number

This keeps Ghidra external and MESevenTool lightweight.
