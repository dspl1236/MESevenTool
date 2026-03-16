# ME7.x Lambda / O2 Sensor Classification

## Key clarification: community "wideband" vs technical "wideband"

The VAG tuning community uses "wideband ECU" to mean two different things:

1. **Technical WB**: front O2 sensor is a 5-wire LSU 4.2/4.9 Bosch pump-cell
   sensor driven by a CJ125 controller chip.  The ECU reads pump current and
   reports lambda 0.7–1.3λ continuously.  Requires specific ECU hardware.

2. **Community WB**: the ECU supports running a *tuner-added* wideband
   controller (AEM X-Series, Innovate, etc.) OR simply that the ECU is
   later-generation and more tuneable than pre-2001 M3.8.3 units.

The user's source ("AUM, AUQ, AWP = wideband") is using definition 2.

## Evidence from VCDS label files (our data)

Block 043 readout units tell us the sensor type used:

| Engine | Block 043 field 3 | Conclusion |
|--------|-------------------|------------|
| AUM    | Lambda Voltage, B1 Sensor 2: 0.0...1.0 V | **NB** front O2 |
| AWP    | Lambda Sensor Voltage (B1-S1): 0.1...0.9 V | **NB** front O2 |
| BAM    | Lambda Voltage, Bank 1 Sensor 1: 0.0...1.0 V | **NB** front O2 |

A true wideband front circuit would show lambda ratio (λ) or pump current (mA),
not a 0–1 V binary voltage range.

## Confirmed classification

**Narrowband front O2 (all current profiles):**
- AGU, AEB, ANB (ME7.1)
- AUM, AWP, AUQ, BAM, AVC, AZG, AGN (ME7.5)
- AWM, AUG, AWT, AVJ (06B ME7.5)

**True wideband front O2 (not yet in our profiles):**
- BEX, BBU, BJX — later 1.8T, post-2004, need label verification
- BWT, BWA, AXX (2.0T FSI) — already classified WB in PROFILE_FSI

## The rear O2 sensor (post-cat, B1S2)

This is a conventional 4-wire NB sensor (Bosch LSF or equivalent) on **all**
variants listed above.  The rear O2 delete patch suppresses the post-cat
diagnostic — it is NOT gated by the front sensor type.

**Fix needed:** remove `requires_lambda=["narrowband"]` from the rear O2
delete patch.  It applies to every profile that has a post-cat sensor.

## 2.7T Biturbo (AGB/ARE/AZZ/APX) — dual bank

Two exhaust banks = two complete lambda systems:
- B1S1 (pre-cat bank 1) + B1S2 (post-cat bank 1)
- B2S1 (pre-cat bank 2) + B2S2 (post-cat bank 2)

The readiness flag structure in the BAM label already shows Bank 2 sensor
entries in the OBD framework (it's the same ECU base code).  For the 2.7T,
both banks are populated.

Rear O2 delete on a 2.7T requires **two patches** — one per bank.
Profile needs `dual_bank=True` to signal that Bank 2 patches are relevant.

## MAF sensor: Bosch HFM5 vs Hitachi

| Type | Part number prefix | MLHFM entries | Scale |
|------|-------------------|---------------|-------|
| Bosch HFM5 | 0 280 218 xxx | 512 × u16 | ~0.1 kg/h per count |
| Hitachi | 8E0 133 471 etc | 512 × u16 | different curve |

The raw count → kg/h characteristic is different.  MLHFM tables from a Bosch
MAF cannot be transplanted into an ECU calibrated for a Hitachi and vice versa.

Profile field needed: `maf_type: str = "bosch_hfm5"` (default).
Override to `"hitachi"` for affected variants when confirmed.
