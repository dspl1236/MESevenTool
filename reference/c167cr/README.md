# Infineon C167CR Reference

Extracted from: *C167CR Derivatives 16-Bit Single-Chip Microcontroller User's Manual V3.1, March 2000* (Infineon Technologies)

The C167CR is the CPU in all Bosch ME7.x ECUs (ME7.1, ME7.1.1, ME7.5). Understanding
its memory model and instruction encoding is essential for writing reliable patch needles.

---

## Memory Architecture

The C167CR uses a **segmented 24-bit address space** (up to 16MB), accessed via a
16-bit data bus. The address space is divided into 256 **segments** of 64KB each.

### Address Notation

Addresses are written as `SS'XXXXH` where `SS` is the segment number and `XXXX` is
the 16-bit offset. In ME7 practice:

- **Segment 0** (`00'xxxxH`): Internal RAM, SFR area, and lower ROM
- **Segment 1** (`01'xxxxH`): Extended ROM/Flash — 1MB ME7 images map here

A flat file offset in a 1MB ME7 `.bin` corresponds to linear address `00'0000H–0F'FFFFH`
in the C167's physical address space, with segment 0 as code segment and DPPs
mapping data pages into the cal region.

### Data Page Addressing

All data access uses the **DPP (Data Page Pointer)** scheme. The 16MB address space
is divided into 1024 **data pages** of 16KB each.

- `DPP0` (SFR `FE00H`, 8-bit addr `00H`) — reset value `0000H` (page 0)
- `DPP1` (SFR `FE02H`, 8-bit addr `01H`) — reset value `0001H` (page 1)
- `DPP2` (SFR `FE04H`, 8-bit addr `02H`) — reset value `0002H` (page 2)
- `DPP3` (SFR `FE06H`, 8-bit addr `03H`) — reset value `0003H` (page 3, always = internal RAM/SFR)

A 16-bit `mem` address `AAAAh` maps to physical address:
```
page = DPPn where n = AAAA[15:14]
physical = (page << 14) | (AAAA & 0x3FFF)
```

**In ME7 ROMs**, the firmware sets DPP1=0x0200 early in init, meaning `mem` addresses
`4000H–7FFFH` map to physical page 0x200 = address `0x80'0000H` (the calibration region
in a 1MB flash). This is why we search for `D7 40 06 02` (EXTP page=0x0206, count=1)
as an anchor — it's the C167 addressing the calibration data page by page number.

### Internal RAM and SFR Area

Located at data page 3 (`00'F600H–00'FFFFH`):

| Address Range | Contents |
|---|---|
| `00'F600H–00'EFFFH` | XRAM (2KB, on-chip extension) |
| `00'F000H–00'F5FFH` | Reserved / X-Peripherals |
| `00'F000H` | Start of SFR / IRAM area |
| `00'F600H–00'FBFFH` | Internal RAM (2KB IRAM) |
| `00'FC00H–00'FCDFH` | General-purpose registers (register banks) |
| `00'FCE0H–00'FCFEH` | PEC source/destination pointers |
| `00'FD00H–00'FDFFH` | Upper RAM — bit-addressable, system stack |
| `00'FE00H–00'FEFFH` | SFR area (standard registers, 512 bytes) |
| `00'FF00H–00'FFFFH` | SFR area (continued, 512 bytes) |

**Runtime variables** in ME7 firmware are in the `00'FD00H–00'FDFFH` and IRAM region.
When you see a needle like `F2 F4 XX XX` (`MOV R4, [mem]`) with the `XX XX` bytes being
a 16-bit address in the `F6xx` range, that's reading from IRAM — a runtime sensor value.

---

## Key Instructions for Needle Writing

The C167 has a CISC instruction set. Instructions are 2 or 4 bytes. All multi-byte
values are **little-endian**.

### EXTP / EXTPR — Extend Data Page

```
D7 40 PP PP   EXTP  #page, #1    ; next 1 instruction uses page PP instead of DPPs
D7 80 PP PP   EXTP  #page, #2    ; next 2 instructions
D7 C0 PP PP   EXTP  #page, #3    ; next 3 instructions
D7 00 PP PP   EXTP  #page, #4    ; next 4 instructions
```

Where `PP PP` is the 10-bit page number in little-endian word format.

**ME7 cal region access pattern** (the core of our needle search):
```
D7 40 06 02   EXTP  #0x0206, #1   ; override DPP for 1 instruction → cal page
F2 Fn XX XX   MOV   Rn, [mem]     ; read from cal (address XX XX on page 0x206)
```

`page 0x206 = 0x0206 << 14 = 0x81800H` — this is ~0x018000 in the 1MB flat file
(accounting for the segment offset). This matches exactly where we find the
`0x018194` codeword block in every ME7 ROM.

### MOV — Data Move

```
F2 Fn XX XX   MOV  Rn, mem        ; load word from 16-bit address into Rn (4 bytes)
E6 Fn XX XX   MOV  Rn, #imm16     ; load 16-bit immediate into Rn (4 bytes)
F0 nm         MOV  Rn, Rm         ; register-to-register (2 bytes)
```

Register encoding in opcode byte `Fn`: lower nibble = register number (R0=F0, R13=FD...).

**VMAX needle** `E6 FD A8 61` = `MOV R13, #0x61A8` = load 25000 (250km/h × 100) into R13.
The `FD` = register R13, `A8 61` = 0x61A8 = 25000 in little-endian.

### JMPA — Conditional Jump Absolute

```
EA cc XX XX   JMPA  cc, addr      ; jump to addr if condition cc is true
```

Condition codes: `cc=0` = unconditional (`JMP`), `cc=1` = Z, `cc=2` = NZ, etc.

### CMP / CMPD — Compare

```
E0 Fn XX XX   CMPD1 Rn, #imm     ; compare Rn with immediate, decrement Rn by 1
60 nm         CMP   Rn, Rm       ; compare registers
```

### JNEI / JNEB — Jump if Not Equal Immediate

```
9A nn XX XX   JNEI  Rn, #imm, rel ; jump if Rn != imm (2-byte relative offset)
```

This is common in ME7 for table-driven dispatch: compare a config byte to a constant,
branch if not equal.

---

## SFR Register Map

Full register table ordered by physical address (from C167CR UM Table 22-4):

### Core CPU Registers (SFR area 0xFE00–0xFE1F)

| Name    | Physical Addr | 8-bit Addr | Description                    | Reset  |
|---------|--------------|------------|--------------------------------|--------|
| DPP0    | FE00H        | 00H        | Data Page Pointer 0 (10 bits)  | 0000H  |
| DPP1    | FE02H        | 01H        | Data Page Pointer 1 (10 bits)  | 0001H  |
| DPP2    | FE04H        | 02H        | Data Page Pointer 2 (10 bits)  | 0002H  |
| DPP3    | FE06H        | 03H        | Data Page Pointer 3 (10 bits)  | 0003H  |
| CSP     | FE08H        | 04H        | Code Segment Pointer (8 bits)  | 0000H  |
| MDH     | FE0CH        | 06H        | Multiply/Divide High Word      | 0000H  |
| MDL     | FE0EH        | 07H        | Multiply/Divide Low Word       | 0000H  |
| CP      | FE10H        | 08H        | Context Pointer (register bank)| FC00H  |
| SP      | FE12H        | 09H        | System Stack Pointer           | FC00H  |
| STKOV   | FE14H        | 0AH        | Stack Overflow Pointer         | FA00H  |
| STKUN   | FE16H        | 0BH        | Stack Underflow Pointer        | FC00H  |
| ADDRSEL1| FE18H        | 0CH        | Address Select Register 1      | 0000H  |
| ADDRSEL2| FE1AH        | 0DH        | Address Select Register 2      | 0000H  |
| ADDRSEL3| FE1CH        | 0EH        | Address Select Register 3      | 0000H  |
| ADDRSEL4| FE1EH        | 0FH        | Address Select Register 4      | 0000H  |

### Timers and Peripherals (partial)

| Name    | Physical Addr | 8-bit Addr | Description                    |
|---------|--------------|------------|--------------------------------|
| T2      | FE40H        | 20H        | GPT1 Timer 2                   |
| T3      | FE42H        | 21H        | GPT1 Timer 3                   |
| T4      | FE44H        | 22H        | GPT1 Timer 4                   |
| T5      | FE46H        | 23H        | GPT2 Timer 5                   |
| T6      | FE48H        | 24H        | GPT2 Timer 6                   |
| T0      | FE50H        | 28H        | CAPCOM Timer 0                 |
| T1      | FE52H        | 29H        | CAPCOM Timer 1                 |
| ADDAT   | FEA0H        | 50H        | A/D Converter Result           |
| S0TBUF  | FEB0H        | 58H        | Serial Ch0 Transmit Buffer     |
| S0RBUF  | FEB2H        | 59H        | Serial Ch0 Receive Buffer      |
| S0BG    | FEB4H        | 5AH        | Serial Ch0 Baud Rate Generator |

### System Control SFRs (0xFF00–0xFFFF)

| Name    | Physical Addr | 8-bit Addr | Description                    | Reset  |
|---------|--------------|------------|--------------------------------|--------|
| P0L     | FF00H        | 80H        | Port 0 Low (lower PORT0)       | 00H    |
| P0H     | FF02H        | 81H        | Port 0 High (upper PORT0)      | 00H    |
| P1L     | FF04H        | 82H        | Port 1 Low (lower PORT1)       | 00H    |
| P1H     | FF06H        | 83H        | Port 1 High (upper PORT1)      | 00H    |
| BUSCON0 | FF0CH        | 86H        | Bus Configuration Register 0   | 0000H  |
| MDC     | FF0EH        | 87H        | Multiply/Divide Control        | 0000H  |
| PSW     | FF10H        | 88H        | Program Status Word            | 0000H  |
| SYSCON  | FF12H        | 89H        | System Configuration Register  | —      |
| BUSCON1 | FF14H        | 8AH        | Bus Configuration Register 1   | 0000H  |
| BUSCON2 | FF16H        | 8BH        | Bus Configuration Register 2   | 0000H  |
| BUSCON3 | FF18H        | 8CH        | Bus Configuration Register 3   | 0000H  |
| BUSCON4 | FF1AH        | 8DH        | Bus Configuration Register 4   | 0000H  |
| ZEROS   | FF1CH        | 8EH        | Constant 0x0000 (read only)    | 0000H  |
| ONES    | FF1EH        | 8FH        | Constant 0xFFFF (read only)    | FFFFH  |
| T2CON   | FF40H        | A0H        | GPT1 Timer 2 Control           | 0000H  |
| T3CON   | FF42H        | A1H        | GPT1 Timer 3 Control           | 0000H  |
| T4CON   | FF44H        | A2H        | GPT1 Timer 4 Control           | 0000H  |
| T5CON   | FF46H        | A3H        | GPT2 Timer 5 Control           | 0000H  |
| T6CON   | FF48H        | A4H        | GPT2 Timer 6 Control           | 0000H  |
| T01CON  | FF50H        | A8H        | CAPCOM Timer 0/1 Control       | 0000H  |
| TFR     | FFACH        | D6H        | Trap Flag Register             | 0000H  |
| WDTCON  | FFAEH        | D7H        | Watchdog Timer Control         | —      |
| S0CON   | FFB0H        | D8H        | Serial Channel 0 Control       | 0000H  |
| P2      | FFC0H        | E0H        | Port 2 Register                | 0000H  |
| P3      | FFC4H        | E2H        | Port 3 Register                | 0000H  |
| P4      | FFC8H        | E4H        | Port 4 Register (7 bits)       | 00H    |
| P6      | FFCCH        | E6H        | Port 6 Register (8 bits)       | 00H    |
| P7      | FFD0H        | E8H        | Port 7 Register (8 bits)       | 00H    |
| P8      | FFD4H        | EAH        | Port 8 Register (8 bits)       | 00H    |

---

## Needle Design Rules

Derived from the memory model and instruction set above:

1. **EXTP anchors are reliable** — `D7 40 XX XX` (EXTP page, #1) is unique in any function
   because it necessarily precedes a memory access to a specific calibration page. The
   page number `XX XX` identifies exactly which data page is being accessed, so it can
   distinguish closely-spaced calibration regions.

2. **Register numbers in opcode bytes are variable** — `F2 Fn XX XX` has `Fn` where
   n = register number (0–15). Use a mask byte `0xF0` on the opcode byte to match any
   register while requiring the `F2` prefix (MOV Rn, mem). This is why our needles use
   mask `0xFF FF 0x00 0x00` on `F2 Fn` bytes — we know it's a MOV but don't care which
   register.

3. **Little-endian immediates** — `E6 FD A8 61` = `MOV R13, #25000`. The value 25000
   = 0x61A8 is stored `A8 61` (low byte first). When searching for a known constant
   (like VMAX = 25000), search for its LE encoding.

4. **DPP1=0x0206 is the ME7.5 cal page** — any `D7 40 06 02` instruction is addressing
   the calibration region. Combined with the subsequent `F2 Fn XX XX` offset, the
   `XX XX` bytes are the offset within that 16KB page, which maps to flat file offset
   `0x018000 + XX XX`.

5. **The 0x018194 codeword block is anchored at data page 0x0206 offset 0x0194** —
   i.e., physical address `0x0206 << 14 | 0x0194 = 0x819194` — all ME7 firmware
   accesses the emissions codewords via EXTP+MOV sequences referencing this region.
   This is why the block is stable across all ME7.x variants regardless of SW version.

---

## Source

Infineon Technologies, *C167CR Derivatives 16-Bit Single-Chip Microcontroller User's Manual*, V3.1, March 2000.

The Instruction Set Manual referenced in Chapter 23 (separate document: "Instruction Set Manual for the C166 Family") contains the full opcode encoding tables. The key opcode bytes used in MESevenTool needles are documented in `needle_opcodes.md`.
