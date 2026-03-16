# MESevenTool

[![CI](https://github.com/dspl1236/MESevenTool/actions/workflows/ci.yml/badge.svg)](https://github.com/dspl1236/MESevenTool/actions/workflows/ci.yml)

Bosch ME7.x ROM editor and analysis tool for VAG 1.8T/2.0T engines.

Primary target: **06A-906-032** (AWP · AUM · AUQ · BAM · AVC and related).  
Also supports **06B-906-018** (AWM · AUG · AWT) and **06A-906-018** ME7.1 variants.


> **🚧 Development status — not yet validated on real hardware**
>
> Map offsets are PROVISIONAL and patch needles are UNCONFIRMED until tested
> against a real ME7 `.bin`. The tool will open ROMs and display data, but
> **do not write to any ECU** until a real ROM has been loaded and the needle
> hits confirmed. All map cells showing data from this version should be
> treated as illustrative only.
>
> If you have a ME7.5 `.bin` (06A-906-032 family), loading it and reporting
> which needles hit is the most useful contribution you can make right now.

---

## Philosophy

**Click-box patching** — no hex editor, no hardcoded offsets.

Every patch and map location is discovered by searching for C167 machine-code
needle sequences that are stable across ROM versions. Drop any ME7 `.bin` and
the tool locates the right addresses automatically. Works across all ME7.x
variants without manual configuration.

---

## Features

| | |
|---|---|
| **Patches** | Rear O2 delete · Secondary air delete · EGR delete · Vmax remove · IMMO defeat (bench) · Rev limit raise · DFCO disable · more |
| **Scalars** | RPM limits · Injector scaling · MAF scaling — editable numeric fields |
| **Maps** | KFZW ignition · MLHFM MAF linearisation · LDRXN boost · KFKHFM · KFMIRL — editable table cells |
| **Checksum** | Full ME7 main + multipoint CRC32 verify and correct |
| **ECU ID** | VMECUHN · Bosch number · EROTAN · engine code extracted from ROM |
| **DPP** | C167 DPP0-DPP3 extraction from startup code |

---

## Quick start

```bash
pip install PyQt5
python -m app.main path/to/rom.bin
```

Or open a ROM from the toolbar after launching.

**Workflow:**
1. Open ROM
2. Check ECU ID and checksum status on the ROM Info tab
3. Toggle patches on the Patches tab — CONFIRMED patches are safe to apply
4. Edit map cells on the Maps tab, click **Write to ROM**
5. Click **Fix Checksums** in the toolbar
6. **Save ROM** — flash with your preferred tool

---

## ROM support

**Flash format:** ME7.5 uses a 1 MB NOR flash chip (Intel 28F800 or equivalent).
All XDF map offsets are flat file offsets into the 1 MB binary. There is no address-line
mirroring in ME7 — the full 1 MB is the active image. 512 KB files (ECUFlash/WinOLS
extracted cal regions) are also accepted for compatibility.

| Part number | Engine | Power | Status |
|---|---|---|---|
| 06A906032xx | AWP 1.8T | 180hp | PROVISIONAL |
| 06A906032xx | AWW 1.8T | 150hp | PROVISIONAL |
| 06A906032xx | AWD 1.8T | 150hp | PROVISIONAL |
| 06A906032xx | AUM 1.8T | 150hp | PROVISIONAL |
| 06A906032xx | AUQ 1.8T | 180hp | PROVISIONAL |
| 06A906032xx | BAM 1.8T | 190hp | PROVISIONAL |
| 06A906032xx | APH/AWV 1.8T | 150hp | PROVISIONAL |
| 06A906032xx | AJQ/ARY 1.8T | 180hp | PROVISIONAL |
| 06B906018xx | AWM 1.8T | 170hp | PROVISIONAL |
| 06A906018xx | AGU/AEB | 150hp | PROVISIONAL |

All offsets marked **PROVISIONAL** pending validation against real ROM files.
Once a `.bin` is loaded and the needles hit, they upgrade to **CONFIRMED**.

---

## Architecture

```
meseventool/
  rom.py        ROMImage — load/save/read/write flat .bin
  needle.py     Searcher — C167 machine-code masked pattern search
  dpp.py        DPP0-DPP3 extraction and address translation
  checksum.py   Main + multipoint CRC32 verify and correct
  ecu_id.py     ECU identification from ROM string table
  maps.py       MapDef — calibration table definitions
  patches.py    PatchDef + ScalarPatchDef — click-box ECU patches
  profiles.py   Per-variant ROM profiles and detection

app/
  main.py       PyQt5 GUI — ROM Info · Patches · Maps tabs

reference/
  me7romtool/   C reference implementation (360trev/nyet, MIT)
```

---

## Adding ROMs and patches

Drop a `.bin` in the root and run `python -m meseventool` — the tool reports
what it finds. All needle misses are logged.  To add a new patch:

```python
PatchDef(
    name        = "My Patch",
    description = "What it does",
    category    = PatchCategory.EMISSIONS,
    needle      = [0xE6, 0xF0, XX, XX, 0xDB, 0x00],
    mask        = [MASK, MASK, XX, XX, MASK, MASK],
    offset      = 2,
    stock_bytes = b'\x00\x00',
    patch_bytes = b'\x01\x00',
    confidence  = "UNCONFIRMED",
)
```

Add it to `ALL_PATCHES` in `patches.py`. The GUI picks it up automatically.

---

## Credits

Needle approach and checksum algorithm ported from
[ME7RomTool_Ferrari](https://github.com/360trev/ME7RomTool_Ferrari)
by 360trev and nyet — MIT licence.

VCDS label files © Ross-Tech LLC.
