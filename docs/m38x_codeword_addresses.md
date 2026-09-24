# Motronic M3.8.x / M5.9.x codeword addresses (not used by MESevenTool)

This table records the addresses that were briefly shipped as MESevenTool
patches in v0.1.14–v0.1.16. They were removed because they target the older
Bosch Motronic M3.8.x / M5.9.x ECUs, not ME7:

- They were tagged `me7.1`, but M382/M383 are M3.8.x and M592 is M5.9.x
  firmware. `known_roms.py` already lists M5.9 / M3.8 as out of scope.
- `ROMImage.load` only accepts 256 KB, 512 KB and 1 MB images. M3.8 EPROM
  dumps (32 KB / 64 KB) can't be opened. M5.9 flash dumps (512 KB) load, but
  no profile matches the 4B090755x part numbers, and ME7 detection doesn't
  apply to them.
- MESevenTool has no M3.8 / M5.9 checksum handling, so a patched file would
  still need its checksum fixed elsewhere.
- None of the addresses have been checked against a real ROM dump.

Keep this as reference data for a tool that supports M3.x (e.g. M35Tool), or
for re-adding the patches once MESevenTool gains a proper M3.8 profile
(file size, `m3.8` platform tag, checksum).

---

## Removed entries — to port to another app

Everything below was removed from `meseventool/patches.py` (last present in
v0.1.16, commit `ff7d0ca`). Tick each one off once it exists in the app
that supports these ECUs. The addresses are in the tables further down. All
diagnosis patches write `0x01` → `0x00`.

**4B0907557B — M3.8.2 (AEB 1.8T 150hp)**
- [ ] Upstream O2 Heater Diagnosis Disable — CDHSV (4B0907557B M382)
- [ ] Downstream O2 Heater Diagnosis Disable — CDHSH (4B0907557B M382)
- [ ] Rear O2 Diagnosis Disable — CDLSH (4B0907557B M382)
- [ ] Front O2 Diagnosis Disable — CDLSV (4B0907557B M382)
- [ ] EVAP Purge Diagnosis Disable — CDTES (4B0907557B M382)
- [ ] Rev Limit NMAXDV + NMAXF (4B0907557B M382 AEB) — scalar

**4B0907557P — M5.9.2 (AEB 1.8T, later firmware)**
- [ ] Upstream O2 Heater Diagnosis Disable — CDHSV (4B0907557P M592)
- [ ] Downstream O2 Heater Diagnosis Disable — CDHSH (4B0907557P M592)
- [ ] Rear O2 Diagnosis Disable — CDLSH (4B0907557P M592)
- [ ] Front O2 Diagnosis Disable — CDLSV (4B0907557P M592)
- [ ] EVAP Purge Diagnosis Disable — CDTES (4B0907557P M592)

**4B0907558M — M5.9.2 (AEB 1.8T)**
- [ ] EVAP Purge Diagnosis Disable — CDTES (4B0907558M M592)
- [ ] CDHSV / CDHSH — *never added: addresses not recorded; get them from the datasheet*

**06A906018R — M3.8.3 (AGU 1.8T, Golf IV / A3 8L)**
- [ ] Upstream O2 Heater Diagnosis Disable — CDHSV (06A906018R M383)
- [ ] Downstream O2 Heater Diagnosis Disable — CDHSH (06A906018R M383)
- [ ] Rear O2 Diagnosis Disable — CDLSH (06A906018R M383)
- [ ] Front O2 Diagnosis Disable — CDLSV (06A906018R M383)
- [ ] EVAP Purge Diagnosis Disable — CDTES (06A906018R M383)

**06A906018CJ — M3.8.3**
- [ ] CDHSV / CDHSH — *never added: same addresses as 06A906018R per the datasheet*

**06A906018CG — M3.8.3 (AGU 1.8T)**
- [ ] Upstream O2 Heater Diagnosis Disable — CDHSV (06A906018CG M383)
- [ ] Downstream O2 Heater Diagnosis Disable — CDHSH (06A906018CG M383)
- [ ] Rear O2 Diagnosis Disable — CDLSH (06A906018CG M383)
- [ ] Front O2 Diagnosis Disable — CDLSV (06A906018CG M383)
- [ ] EVAP Purge Diagnosis Disable — CDTES (06A906018CG M383)
- [ ] Rev Limit NMAXDV + NMAXF (06A906018CG M383 AGU) — scalar

That's 21 diagnosis patches and 2 rev-limit scalars, plus 3 gaps that were
never implemented. When porting, keep what MESevenTool learned the hard way:
gate each patch on the ECU part number, check the stock value before
writing, and write NMAXF together with NMAXDV.

---

**Source:** *M38x M592 Function Datasheet.xlsx* (s4wiki.com), cross-referenced
against TunerPro XDF definitions. Addresses are flat file offsets. The
datasheet itself is not in this repo.

---

## Diagnosis codewords

All are single bytes: `0x01` = diagnosis active (stock), `0x00` = keine
Diagnose (disabled).

| Codeword | Meaning | 4B0907557B (M382) | 4B0907557P (M592) | 4B0907558M (M592) | 06A906018R (M383) | 06A906018CG (M383) |
|---|---|---|---|---|---|---|
| CDHSV | Upstream (pre-cat) O2 heater diagnosis | `0x07CD0` | `0x07866` | — | `0x0720A` | `0x07274` |
| CDHSH | Downstream (post-cat) O2 heater diagnosis | `0x07CD1` | `0x07867` | — | `0x0720B` | `0x07275` |
| CDLSH | Rear O2 sensor diagnosis | `0x07D00` | `0x07896` | — | `0x0723A` | `0x072A4` |
| CDLSV | Front O2 sensor diagnosis | `0x07D11` | `0x078A7` | — | `0x0724B` | `0x072B5` |
| CDTES | EVAP / tank-vent diagnosis (P0440–P0446) | `0x07D4A` | `0x078E0` | `0x0798C` | `0x07284` | `0x072EE` |

Notes:

- **06A906018CJ** uses the same CDHSV/CDHSH addresses as 06A906018R, per the
  datasheet.
- **4B0907558M**: the datasheet has CDTES only. There's no CDLSH/CDLSV for this
  ECU. CDHSV/CDHSH addresses were never recorded, although an earlier commit
  message claimed them.
- In the four ECUs with a full set, the block has a fixed layout relative
  to CDHSV: CDHSH `+0x01`, CDLSH `+0x30`, CDLSV `+0x41`, CDTES `+0x7A`.
  4B0907558M lacks CDLSH/CDLSV, so don't assume it shares this layout.

---

## Rev limit (NMAXDV / NMAXF)

| ECU | NMAXDV | NMAXF |
|---|---|---|
| 4B0907557B (M382, AEB 1.8T) | `0x0743A` | `0x074C6` |
| 06A906018CG (M383, AGU 1.8T) | `0x0693A` | `0x069EC` |

- **NMAXDV**: datasheet label *Drehzahlbegrenzung bei Fehlererkennung
  Geschwindigkeitssignal*, meaning the rev limit applied when a
  vehicle-speed-signal fault is detected. Exceeding it sets a DTC and the MIL.
  Whether it is also the normal limiter on these ECUs is unverified.
  Encoding: big-endian u16, 40 RPM per count.
- **NMAXF**: hard RPM cut-off. Encoding: big-endian u16, 0.25 RPM per count.
- OEM relationship: **NMAXF = NMAXDV + 300 RPM** (per the MED9.1 TFSI
  Funktionsrahmen p.491 and the Motronic 3.8.x / 5.9.x notes). Change both
  together.
