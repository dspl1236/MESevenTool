# ME7 Narrow-Angle Engine Families — VR6, VR5, AFP Reference

This document covers all narrow-angle Volkswagen Group engines that use ME7.x ECU
management: the 12-valve VR6 (AFP), 24-valve VR6 (BDF/BFH), 20-valve VR5 (AQN/AZX),
and the later 3.2 MK5/A3 variant. It documents ECU hardware families, ME7 version,
known part numbers, and MESevenTool compatibility status.

---

## Engine & ECU Family Map

| Engine | Disp | Valves | Code | Cars | ECU PN prefix | ME7 version | In scope |
|---|---|---|---|---|---|---|---|
| AAA/ABV | 2.8–2.9L | 12v | AAA/ABV | MK3/Corrado | 021906258xx | M2.7/M2.9.1 | ❌ pre-ME7 |
| AFP | 2.8L | 12v | AFP | MK4/Jetta MK4 | 021906018xx | ME7.1 | ✅ |
| BDF | 2.8L | 24v | BDF | MK4/Bora/Passat B5 | 06A906032xx | ME7.1 | ✅ |
| BFH | 3.2L | 24v | BFH | Golf R32 MK4 | 06A906032JA/HT | ME7.1 | ✅ (no ROM yet) |
| AGZ | 2.3L | 10v | AGZ | MK4/Bora (early) | 071906018xx | M3.8.3 | ❌ pre-ME7 |
| AQN | 2.3L | 20v | AQN | MK4/Bora/Beetle | 066906032xx | ME7.1 | ✅ (no ROM yet) |
| AZX | 2.3L | 20v | AZX | Passat B5 | 066906032xx | ME7.1 | ✅ (no ROM yet) |
| BUB | 3.2L | 24v | BUB | MK5 R32/A3/TT | 022906032xx | ME7.1.1 (diff HW) | ⚠️ |

---

## Gen 0 — Pre-ME7: AAA/ABV (12V) and AGZ (VR5 10V)

These run **Bosch M2.7, M2.9.1, and M3.8.3** respectively — 8-bit processors,
EPROM-based, no OBD-II. Not in scope. Documented only to avoid confusion.

- **AAA/ABV (12V VR6)**: MK3 Golf/Corrado/Passat B3. ECU `021906258xx`.
  Bosch M2.7/M2.9.1, 64KB EPROM. Confirmed by Corrado files from chiptuning.pw.
- **AGZ (10V VR5)**: MK4 Golf/Bora 1998–2000. ECU `071906018xx`.
  Bosch M3.8.3, cable throttle. Predates ME7.

---

## Gen 1 — ME7.1: AFP (VR6 12V MK4)

### What it is

The AFP is the **updated 12-valve 2.8L VR6** fitted to the Golf/Jetta MK4 from 1999.5
onwards, replacing the AAA. Despite being 12-valve — the same cylinder count as the
pre-ME7 AAA — the AFP got a complete ECU upgrade to **ME7.1** with the full Bosch
C167CR processor and OBD-II compliance. This is the first 12V VR6 on ME7.

Key changes from AAA:
- Plastic intake manifold (vs aluminium on AAA)
- Different cam profile
- OBD-II compliant (ME7.1 vs M2.9.1)
- Coil-on-plug ignition (no distributor)

### ECU hardware

| Part number | Bosch number | Notes |
|---|---|---|
| 021906018A–T (various) | 0261206xxx | ME7.1, MK4 Golf/Jetta/GTI |
| 021906018S | — | Common replacement part |
| 021906018AA+ | 0261206xxx | Later suffix variants |

**Important:** The AFP uses the `021906018` prefix — completely different from the
`06A906032` family used for the 24V BDF/BFH and the 1.8T ME7.5 engines. Different
connector layout, different board ID. Not cross-flashable with 06A ECUs.

The AFP is **ME7.1** (not ME7.5). Same C167CR processor and 121-pin connector
hardware generation as the 2.7T S4 and BDF 24V VR6. The codeword block at
`0x018194` is expected to be present. No ROM files have been acquired yet —
this is a documentation/research placeholder.

### Expected patch compatibility

Based on the hardware generation and ME7.1 code framework:
- **Codeword patches** (CDLSH/CDLSHV/CDLSV/CDKAT at 0x018190+): ✅ Expected
- **KRMXN Zero** (knock retard table): ✅ Expected — ME7.1 shared function
- **ESKONF** (rear O2 heater, 0F 01 05 pattern): ✅ Expected
- **Vmax**: Not applicable — NA engine, no speed limiter in same code path
- **MAF Delete / Alpha-N**: Not applicable without dedicated VR6 needle work
- **1.8T boost patches** (BGRLP, N75): ❌ Not applicable

### Status

No ROM files acquired. `021906018xx` files are uncommon in public archives.
The MK4 12V VR6 community is smaller than 1.8T or 24V VR6.
**Files to acquire:** `021906018S` or `021906018T` stock ROM.

---

## Gen 1 — ME7.1: BDF (VR6 24V MK4) — confirmed

See main analysis in previous session. Covered fully via the Bora fw6228 file.

ECU prefix: `06A906032AG/AK/L/T`. Firmware fw6228. 12/33 patches confirmed.
Codeword block fully present and matching expected structure.

---

## Gen 1 — ME7.1: AQN/AZX VR5 (2.3L 20V)

### What it is

The VR5 is a **five-cylinder variant of the VR6** block — one cylinder deleted from
the 2.8 VR6, giving 2324cc. The 20-valve version (AQN/AZX) launched in 2000 with
drive-by-wire throttle and VVT, producing 170hp. It is genuinely ME7.1.

The AQN and AZX are mechanically near-identical:
- **AQN**: Golf MK4, Bora, New Beetle
- **AZX**: Passat B5 (3B/3BG)

Both share the same ECU prefix and Bosch firmware.

### ECU hardware

| Part number | Bosch number | Application |
|---|---|---|
| 066906032AG | 0261207375 | MK4 Golf/Bora AQN 170hp |
| 066906032xx (various) | 0261207xxx | AQN/AZX variants |

**The `066` prefix** is distinct from both `06A` (1.8T) and `021` (AFP).
Different physical board layout for the 5-cylinder engine — different injector
and ignition output count (5 vs 6), different firing order.

ME7.1 hardware. C167CR processor. The codeword block at `0x018194` is
expected to be present — same Bosch function framework as BDF and AFP.

### Expected patch compatibility

Same reasoning as AFP. Emissions codeword patches, KRMXN, ESKONF all expected
to work. 5-cylinder-specific output mapping means ignition/injection patches
that assume 6 cylinders would not apply.

### AGZ (10V VR5) — NOT ME7

The earlier AGZ (1997–2000) runs Bosch **M3.8.3** with cable throttle.
ECU prefix `071906018xx`. Different generation, not in scope.
The AGZ→AQN swap requires throttle pedal change (cable to DBW) and coil packs.

### Status

No ROM files acquired. `066906032AG` files are rare publicly. The VR5 community
is smaller than VR6. NefMoto forum confirms `066906032F` (AZX variant) exists
as a community interest item but no XDF/DAMOS were available there either.
**Files to acquire:** `066906032AG` (AQN 170hp) stock ROM.

---

## Gen 2 — ME7.1.1: BUB (3.2L MK5/A3/TT) — different architecture

Already confirmed: `022906032GP`, version `ME7.1.1/5/S1103A`. Zero patches hit.
Different startup pattern, codeword block absent/relocated. Out of scope.

---

## Summary: ECU PN prefix → hardware generation

```
021906258xx  →  M2.7/M2.9.1  (12V VR6 pre-ME7, MK3/Corrado)
071906018xx  →  M3.8.3       (VR5 10V pre-ME7)
021906018xx  →  ME7.1        (AFP 12V VR6 MK4)          ← NEW
066906032xx  →  ME7.1        (AQN/AZX VR5 20V)          ← NEW
06A906032xx  →  ME7.1/ME7.5  (BDF/BFH 24V VR6 + 1.8T)
022906032xx  →  ME7.1.1      (BUB 3.2 MK5/A3/TT, diff HW)
```

All three `021906018`, `066906032`, and `06A906032` families run ME7.1 on the
same Bosch C167CR hardware. The connector is shared (121-pin). The codeword
block at `0x018194` is common to all. Once ROM files are acquired, the existing
MESevenTool detection infrastructure should handle them with minimal new work.

---

## Files status

| Family | Files | Status |
|---|---|---|
| AFP 12V VR6 (021906018) | 0 | Not yet acquired |
| BDF 24V VR6 (06A906032xx) | 1 (tuned) | ✅ fw6228 confirmed |
| BFH 3.2 R32 MK4 (06A906032JA/HT) | 0 | Not yet acquired |
| AQN/AZX VR5 (066906032) | 0 | Not yet acquired |
| BUB 3.2 MK5 (022906032) | 1 | ⚠️ different arch, confirmed out-of-scope |
