# ST10F27x Application Note Reference

Source: STMicroelectronics AN2353 Rev 2 (September 2013)  
Covers: ST10F276 / ST10F275 / ST10F273 / ST10F272 / ST10F271  
Applies to: **ME7.5 ECUs** — 06A906032 (AWP/AUM/BAM), 4B0906018, 8E0906018 families

The ST10F27x is STMicroelectronics' licensed C167 implementation. ME7.5 ECUs use the
ST10F269 or ST10F275; ME7.1 ECUs (2.7T, older 1.8T) use the Infineon C167CR.
The instruction set and memory model are identical — differences are peripheral and
timing only. Needles and patch logic derived from one family apply directly to the other.

---

## CPU Clock / PLL

Port0 P0H.7:5 sampled at power-on reset selects the PLL multiplier:

| P0H.7 | P0H.6 | P0H.5 | Multiplier | ME7.5 XTAL | CPU clock |
|-------|-------|-------|-----------|------------|-----------|
| 1     | 1     | 1     | ×4        | 4 MHz      | 16 MHz    | ← **default ME7.5**
| 1     | 0     | 1     | ×8        | 4 MHz      | 32 MHz    |
| 0     | 1     | 1     | ×1        | 16 MHz     | 16 MHz    | direct drive

ME7.5 runs at **16 MHz** via ×4 PLL on a 4 MHz crystal.
ME7.1 2.7T (C167CR) also targets 16 MHz — timing constants are directly comparable.

**Implication:** Any timer-based period in the ROM (TVUB, injection pulse width, delay
loops) is in CPU clock ticks. At 16 MHz: 1 tick = 62.5 ns. Consistent across ME7.1
and ME7.5 when both run at 16 MHz. Verify BUSCON startup code if clock differs.

---

## External Memory Interface

ST10F27x external bus → STMicro M29Fxx series NOR Flash (see AN1155).

In ME7.5 ECUs:
- **Program flash**: internal ST10 Flash (256–512 KB)
- **Calibration flash**: external M29F400/M29F800 (512 KB or 1 MB) on external bus

BUSCON0 at SFR 0xFF04 configures external bus timing (read cycle length, ALE width,
WR strobe, data hold). The startup code sets BUSCON0 before any calibration access —
this is the first `MOV [0xFF04], #imm` after the reset vectors at 0x000000.

---

## ADC — MAF Signal Sampling

10-bit SAR ADC. Key parameters for MAF sampling:

| Parameter | Value |
|-----------|-------|
| Sample capacitance Cin | max 5 pF |
| Series input resistance R1 | max 1.5 kΩ |
| Input leakage IOZ1 | max ±200 nA |
| Recommended source impedance | < 1.5 kΩ |

The MLHFM table maps raw ADC counts → airflow (g/s). The ADC transfer is linear
after the input RC filter — MLHFM nonlinearity comes from the MAF sensor curve, not
ADC error. At very high airflow (top 5–10 cells), RC rolloff at high signal slew can
introduce ~2–3 LSB error, but this is below calibration sensitivity.

**MLHFM scaling note:** Scaling all cells by a fixed factor is equivalent to scaling
injector flow — valid because the ADC is not the bottleneck here.

---

## EA/VSTBY — Bench Flash Mode

- EA pin HIGH → boot from internal flash (normal ECU operation)
- EA pin LOW during reset → boot from external memory / bootstrap loader

ME7.5 ECUs: EA tied HIGH via pull-up. Pulling EA LOW during reset enters bootstrap
loader mode — used by bench flash tools (Galletto, FGTech, etc.) for direct flash write
without KWP2000 authentication. Relevant for the Teensy EPROM emulator project.

---

## Port0 at Reset

All Port0 pins have internal pull-ups active during reset only. The ECU PCB has fixed
resistors on P0H to permanently select clock config and bus width. After reset, Port0
reverts to normal GPIO.

---

## Oscillator

- **Wide-swing** (ST10F276/275/273): gm 8–35 mA/V
- **Low-power** (ST10F272/271): gm 0.7–6 mA/V
- ME7.5 ECUs typically use wide-swing for noise margin in automotive environment
- 4 MHz crystal; ceramic resonator acceptable for production cost, lower accuracy

---

## ST10F27x vs Infineon C167CR Comparison

| Feature           | Infineon C167CR    | ST10F27x           |
|-------------------|--------------------|--------------------|
| Instruction set   | Full C167          | **Identical**      |
| SFR addresses     | 0xFF00–0xFFFF      | **Identical**      |
| DPP model         | 16 KB pages        | **Identical**      |
| Reset vector      | 0x000000           | **Identical**      |
| Internal RAM      | 2 KB               | 2–16 KB (variant)  |
| Internal Flash    | None               | 256–512 KB         |
| External bus      | Yes                | Yes                |
| CAN               | On-chip            | Via L4969 SPI      |
| Used in           | ME7.1 2.7T/V8/W8  | ME7.5 1.8T/2.0T    |

**Bottom line:** The firmware binary format, memory map, and patch approach are
identical. Needle sequences and EXTP/MOV patterns from one family apply to the other.

