# "Standalone swap" preset — scope (November 2026)

Goal: one preset in the patch panel that turns a stock ME7 calibration into a
tolerant controller for an engine swap or race car: no immobiliser, no
emissions hardware, missing cluster/ABS/climate nodes, optional MAF-less
load. Stock firmware stays (Bosch knock control, cold start, DBW safety),
so this is the Option A route next to HaniCore's full-replacement route
(`github.com/MartinHani/HaniCore`), and it produces the list of "what has to
be neutralised" that a seed-tune exporter for HaniCore would need anyway.

Scoped against the catalogue as of v0.2.0 and the 06A906032HS/LP XDFs
(585 named codewords, DAMOS-derived) in `D:\ME7_corpus\s4wiki\defs`.

## 1. What the catalogue already covers

| Need on a swap car | Existing entry | Status | Note |
|---|---|---|---|
| Start without the cluster's immobiliser | IMMO-OFF ME7.5 06A/06B/4B0; 06A VDO fw4013; ME7.1 2.7T; ME7.1.1 | **PROVISIONAL** — needle confirmed, no bench run | The one entry the preset cannot ship without proving. See §4. |
| No immobiliser CEL | P1681 Databus CEL Disable | CONFIRMED, **ME7.1.1 only** | 1.8T ME7.5 equivalent is the `CDTWFS` fault path (§2). |
| No catalyst | CDKAT (per-build address) | CONFIRMED | |
| No rear O2 | CDLSH / CDLSHV / CDLSV (per-build); ESKONF heater (2.7T); Rear O2 Monitor Threshold; Rear O2 OBD Readiness Flags | CONFIRMED | Readiness flags entry is review B7 (DL-specific offsets, gated too wide) — exclude from the preset until B7 is resolved. |
| No secondary air pump | SAP CDSLS (06a/4b0); SAP MSLUB table (2.7T) | CONFIRMED | |
| No EVAP / tank venting | EVAP CDTES (06a/4b0) | CONFIRMED | Leak-diagnosis pump path (`CDTLDP`) not covered — §2. |
| No VVT solenoid | CDNWS (06a / 4b0 / me71 / me711) | CONFIRMED | |
| No MAF (alpha-N) | MAF Delete / Alpha-N (5 firmware variants) + CDEHFM | CONFIRMED | Only if the build is one of the five; otherwise leave MAF in. |
| Speed limiter | Vmax (universal, 2.7T, ME7.1.1) | CONFIRMED | |
| Gearbox torque model with a different box | 5th-Gear Torque Mode Disable | CONFIRMED | ME7.5 1.8T only. |
| Rev limits | Hard Rev Limit, alt path, NKILL, Overrev | CONFIRMED | Scalars, user-set, not part of the bundle. |

Everything above is gated to the ECU/build it was validated on (review B/C,
A7), so the preset can be a *selection* of these: applying it means
"apply every member that `detect()` reports STOCK on this ROM", and the
panel shows which members do not apply to this build.

## 2. What is missing, and where the XDF says it lives

The 06A XDFs expose a second codeword area the tool has never used: the
**"Codewort Tester" fault-path enables** at `0x013C40–0x013D52` (one byte per
diagnostic path, `CDT*`), plus configuration codewords scattered through the
calibration. These are what a car with half its sensors needs.

Fault paths to silence (06A906032HS addresses; same names exist in LP, and
in 8D0907551M for 2.7T — layout per build must be verified like A7):

| Codeword | HS addr | Fault path | Why a swap needs it |
|---|---|---|---|
| `CDTVFZ` | 0x013D4E | vehicle speed | no VSS / no cluster |
| `CDTBREMS` | 0x013C58 | brake switch | no brake switch wired |
| `CDTKUPPL` | 0x013CDE | clutch pedal sender | no clutch switch |
| `CDTCINS` | 0x013C6A | CAN timeout, instruments | no cluster |
| `CDTCAS` | 0x013C60 | CAN timeout, ABS/ASC | no ABS |
| `CDTCKLA` | 0x013C6C | CAN timeout, climate | no climate control |
| `CDTCGE` | 0x013C64 | CAN timeout, gearbox | manual or non-CAN box |
| `CDTTMKI` | 0x013D3A | coolant temp from cluster | no cluster |
| `CDTWFS`, `CDTWFSRC`, `CDTSGEEW` | 0x013D50/52, 0x013D1C | immobiliser paths | with IMMO-OFF |
| `CDTEPCLE` | 0x013C9A | EPC lamp output stage | no EPC lamp |
| `CDTMILE`, `CDTMFA` | 0x013D08/06 | MIL output / MIL-foreign | no MIL |
| `CDTSLS`, `CDTSLPE`, `CDTSLV`, `CDTSLVE` | 0x013D1E–24 | secondary air | with SAP delete |
| `CDTTES*`, `CDTTEVE*`, `CDTLDP`, `CDTLDPE`, `CDTTANKL` | 0x013CE8–EA, 0x013D2A–34 | EVAP, leak pump, empty tank | with EVAP delete |
| `CDTENWS`, `CDTENWSE`, `CDTNWSE`, `CDTNWKW` | 0x013C96–98, 0x013D0C–0E | cam control / cam-crank assignment | VVT solenoid removed |
| `CDTKS1–4` | 0x013CD6–DC | knock sensors | **keep** unless a sensor is physically absent |
| `CDTUBR` | 0x013D40 | main-relay voltage | relay wiring changed |
| `CDTKPE` | 0x013CC6 | fuel pump relay output | pump driven elsewhere |
| `CDTDVE*` | 0x013C80–8C | DBW throttle checks | **keep** — safety |

Configuration codewords (same source):

| Codeword | HS addr | Meaning | Swap use |
|---|---|---|---|
| `CWCANKBI` | 0x0101AA | auto-detect cluster CAN message | off without a cluster |
| `CWCAUVW` | 0x0101AD | Audi/VW CAN output | off on a non-VAG bus |
| `CWMSRCAN` | 0x0101D0 | MSR/ASR over CAN | off without ABS |
| `CW_CAN_R/S_0..3`, `CWGC_0..3` | 0x0132AC–BF | CAN receive/send config, gearbox coding | per installation |
| `CWKUPPL` | 0x011439 | clutch codeword | no clutch switch |
| `CWGGVFZG` | 0x010A6D | vehicle-speed source | no VSS |
| `CWGGPBKV` | 0x01244C | brake-booster function | no booster sensor |
| `CWKOC`, `CWKOCAN` | 0x0123D1/D2 | A/C compressor control / over CAN | no A/C |
| `CWFGR*` | 0x014512.., 0x018996 | cruise control | off |
| `CWNOMIL`, `CWFLC` | 0x01844D, 0x0109E4 | MIL control | off without a lamp |
| `CWNOSCAT` | 0x0183D2 | disable scan-tool comms | **never** (kills KWP) |
| `CW_NOROMCHKRESET` | (HS) | no reset on ROM check failure | research item for on-the-fly tuning, §5 |

Values for each (which bit, 0 vs 1) must be read from the XDF description
and checked against stock bytes before any entry is written; the names
alone do not say. Two facts from the XDF already change the design:

- The `CDT*` entries are **16-bit** ("Fehlerpfadcode"), not single-byte
  switches like the 0x018194 block. They hold the fault-path code the path
  reports, so "silencing" one is probably writing 0, and that needs a
  stock-byte survey plus a bench confirmation per entry.
- `CW_NOROMCHKRESET` is an 8-bit codeword at HS 0x011C67 with no
  description in the XDF; its meaning has to come from the stock bytes
  and a bench test, not assumed from the name.

## 3. Shape of the feature

- **`PatchCategory.SWAP`** and a preset object: an ordered list of patch
  names with a per-member `required` flag. Apply = for each member whose
  `detect()` is STOCK, `apply()`; report members that are NOT_APPLICABLE
  (wrong build) or MISSING. Revert = reverse order.
- **Variants:** "swap, keep MAF" and "swap, alpha-N" (adds the MAF delete
  members); "race, no cluster/ABS" adds the CAN-timeout paths.
- **New codeword entries** for the `CDT*` paths and the CW config words
  above, as `FixedAddressPatchDef` with `codeword`/`layouts`, which means
  first extending `codewords.LAYOUTS` with the 0x013Cxx block per build
  (HS and LP for 06a; 551M for me71; the ME7.1.1 XDFs for me711). Expect
  a second A7-style layout study: these blocks move per build too.
- **Checksums:** the existing fix covers all three layers; the preset ends
  with Fix Checksums and the Save warning already in place.
- **Panel:** one "Standalone swap" button with a preview list (member,
  state, will-apply / N/A / already applied) before anything is written.

## 4. What must be proven before this ships

1. **IMMO-OFF on a bench ECU.** Every immobiliser entry is PROVISIONAL.
   The preset is useless without it, and wrong without proof: a bench
   ME7.5 (06A906032, 4B0906018) with a K-line cable, start without a
   cluster, confirm injection enable. This is the gating item.
2. **The 0x013Cxx layout per build** (same method as A7: XDFs + stock
   bytes across the corpus; the corpus has 68 06A, 32 06B/4B0, 13 2.7T,
   8+8 VR6 images).
3. **Codeword semantics**: for each `CDT*`/`CW*` entry, the XDF description
   plus a stock-byte survey, then one bench ECU with the sensor unplugged
   to confirm the fault stays away. A fault path left enabled is a CEL, not
   a danger; a config word set wrong (CAN send/receive, `CWNOSCAT`) can
   brick communication, so those stay out until bench-proven.

Estimate: the catalogue-only preset (§1 members, no new codewords) is a
day of GUI work. The `CDT*` layer is a week: layout study, ~25 entries,
corpus tests, one bench session.

## 5. "Flash on the fly" for tuning

Three levels, in increasing effort:

1. **Fast reflash cycle (realistic now).** Save → Fix Checksums → flash
   over KWP2000 (VAGFlasher's ME7 path; `requestDownload`/`transferData`
   with security access). A full 1 MB write is minutes; writing only the
   calibration sectors (the 64 KB region holding the maps) is tens of
   seconds. The tool-side work is a "Save and flash" button that hands
   the file to VAGFlasher with the sector list. No ECU-side change.
2. **Live map editing (what HaniCore has).** Requires the firmware to read
   its maps from RAM and accept writes over the K-line. On stock Bosch
   firmware that is a code patch: relocate the hot maps to a RAM mirror,
   hook the table-lookup routine, add a `writeMemoryByAddress` handler or
   reuse ME7's existing one (KWP2000 service 0x3D exists on ME7 and is
   what ME7Logger-style tools use for RAM). This is the "free space and
   spare resources" research from earlier, now with a concrete purpose.
   It is weeks of C167 work per build and the main reason HaniCore chose
   to own the firmware.
3. **HaniCore + LibreTune.** Already does live tuning and K-line updates
   with the tune preserved; the price is leaving Bosch's calibration.
   Our contribution there is the seed-tune exporter (stock maps →
   LibreTune tune) and the boot-mode first flash.

Recommendation: ship level 1 with the swap preset (it is mostly plumbing
between two tools you already have), and treat level 2 as a research
branch whose first milestone is "KFZW served from RAM on a bench ECU".
`CW_NOROMCHKRESET` in the HS XDF is worth reading first: if the stock
firmware really has a switch to tolerate a failed ROM check, iteration
without a checksum fix becomes possible on the bench.
