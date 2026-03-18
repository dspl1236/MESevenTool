# MESevenTool

ROM analysis and patch tool for Bosch ME7.x engine ECUs (VAG / Audi-VW group).

**34 confirmed patches | 5 confirmed scalars | 415 tests passing**

---

## Supported ECU families

| Platform | ME7 version | ECU PN prefix |
|---|---|---|
| 1.8T ME7.5 | ME7.5 | `06A906032xx`, `4B0906018xx`, `8N0906018xx` |
| 2.7T biturbo | ME7.1 / ME7.1.1 | `8D0907551xx`, `4B0907551xx`, `4Z7907551xx`, `4D1907558xx` |
| AFP VR6 12V | ME7.1 fw6228 | `021906018xx` |
| BDF/BFH VR6 24V | ME7.1 fw6228 | `06A906032AG/AK/JA/HT` |
| VR5 20V AQN/AZX | ME7.1 fw5423 | `066906032xx` |
| Golf R32 / Audi TT 3.2 | ME7.1.1 fw6432 | `022906032EG/GE` |
| Passat B5.5 2.8V6 | ME7.1.1 fw6428 | `022906032CS` |
| Touareg 3.2 | ME7.1.1 C1103A | `022906032FT` |
| S6/S8 4.2 V8 | ME7.1 fw8000 | `4D0907558/9xx` |
| RS6 4.2TT | ME7.1.1 fw8542 | `4D1907558xx` |
| S4 B7 4.2 V8 | ME7.1.1 C1105B | `8E0907560x` |

---

## Patches

### Performance
- **Vmax Speed Limiter Disable** — 3 variants covering all ME7.1, ME7.1.1, and ME7.5
- **Knock Retard Disable — KRMXN Zero** — zeroes the max retard table across all ME7.1/ME7.5
- **Knock Retard Code Disable** — disables the retard code path (2.7T ME7.1)
- **Knock Retard Disable** — alternative path (ME7.5 1.8T)
- **5th-Gear Torque Mode Disable** — fixed `0x00881D`, universal 1.8T

### Emissions
- **Rear O2 full delete** — CDLSH + CDLSHV + CDLSV (fixed universal) + ESKONF (3 variants) + monitor threshold (2 offset variants) + OBD readiness flags
- **Catalyst monitor disable (CDKAT)** — universal + 4B0906018-specific
- **SAP disable (CDSLS)** — fixed + needle airflow table zero (2.7T)
- **EVAP disable** — 2 variants
- **Rear O2 sensor diag disable** — needle (2.7T ME7.1/ME7.1.1)
- **Knock sensor monitor disable (CDKVS/CDKVS2)** — 4B0906018
- **MAF sensor diag disable (CDEHFM)** — required with MAF Delete on SL DSG / 4B

### Fuelling
- **MAF Delete / Alpha-N redirect** — 5 variants covering all ME7.5 1.8T sub-families

### Diagnostics
- **P1681 IMMO databus CEL disable** — ME7.1.1 ECU swap aid
- **VVT cam position monitor disable (CDNWS)** — fixed `0x0181AF`, ME7.1/ME7.1.1

### Scalar patches (read/write)
- Hard rev limit, overrev protection, emergency RPM cut (NKILL), fuel cut resume — all ME7.5 1.8T

---

## Usage

```python
from meseventool.rom import ROMImage
from meseventool.needle import Searcher
from meseventool.patches import ALL_PATCHES, PatchState

rom = ROMImage.load("myfile.bin")
searcher = Searcher(rom)

for patch in ALL_PATCHES:
    result = patch.detect(rom, searcher)
    if result.state == PatchState.STOCK:
        print(f"Patchable: {patch.name}")
    elif result.state == PatchState.PATCHED:
        print(f"Already applied: {patch.name}")
```

---

## Documentation

- [`docs/patch_catalogue.md`](docs/patch_catalogue.md) — full patch reference with addresses, notes, and per-ECU applicability
- [`docs/vr6_family.md`](docs/vr6_family.md) — VR6/VR5/AFP/V8 family taxonomy and confirmed file corpus
- [`docs/ecu_compatibility.md`](docs/ecu_compatibility.md) — cross-flash compatibility matrix
- [`docs/me7_stable_codeword_block.md`](docs/me7_stable_codeword_block.md) — codeword block reference
- [`docs/rom_space_and_adc.md`](docs/rom_space_and_adc.md) — free code space and ADC channel mapping per ECU

---

## Running tests

```bash
python3 -m pytest tests/ -q
# 415 passed
```

Tests require ROM files in `/mnt/user-data/uploads/`, `/home/claude/s4wiki_stock/`,
and `/home/claude/chiptuning_stock/`. Tests skip gracefully when ROM files are absent.
