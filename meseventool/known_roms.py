"""
meseventool/known_roms.py
=========================
Catalogued ME7.x ROM CRC32 fingerprints.

Each entry maps a full-file CRC32 to a KnownROM descriptor carrying
enough metadata to identify the ROM without needing to disassemble it.

Built from the collection scan — all entries are confirmed stock reads.
Version string, DPP1, and profile name are extracted by the batch scanner;
label is manually verified from the filename/ECU PN.

Usage::

    from meseventool.known_roms import lookup_rom, KNOWN_ROMS

    entry = lookup_rom(crc32_of_file)
    if entry:
        print(entry.label, entry.vmecuhn)

CRC32 is computed over the **full** ROM file as-loaded by ROMImage.
For 1MB files this is the full 1MB. For 512KB ECUFlash extracts it is
the 512KB image. Do not compute CRC over only a partial window.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class KnownROM:
    crc32:    int    # full-file CRC32
    vmecuhn:  str    # VAG part number (may be blank for some VR6 older files)
    bosch:    str    # Bosch ECU number (0261xxxxxx)
    version:  str    # ME7.x version string from ROM
    ecu_hw:   str    # "ME7.5" | "ME7.1" | "ME7.1.1"
    size_kb:  int    # ROM file size in KB (512 or 1024)
    label:    str    # Human-readable description


# ── Catalog ────────────────────────────────────────────────────────────────────
#
# All entries confirmed from physical/digital ROM reads.
# Grouped by ECU hardware family then by part number.

_CATALOG: list[KnownROM] = [

    # ── ME7.5 — 06A906032 transverse 1.8T ───────────────────────────────────
    KnownROM(0x6262fb03, "06A906032AR", "0261206436", "42/1/ME7.5/3/4013.00//F21dx/Dst05g/020699",
             "ME7.5", 512,  "Golf4/Jetta4 1.8T ARZ 150hp — fw4013 VDO"),
    KnownROM(0x1e1bc31a, "06A906032DL", "0261206890", "40/1/ME7.5/3/4019.20//24b/Dst02o/090600",
             "ME7.5", 1024, "Golf4/Jetta4 1.8T AWW 150hp — fw4019 Bosch DL manual"),
    KnownROM(0x8bb14b75, "06A906032DL", "0261206890", "40/1/ME7.5/3/4019.20//24b/Dst03o/280800",
             "ME7.5", 1024, "Golf4/Jetta4 1.8T AWW 150hp — fw4019 Bosch DL manual (rev2)"),
    KnownROM(0x9372b946, "06A906032DS", "0261207080", "42/1/ME7.5/120/4220.AA//23f/Dst03o/191200",
             "ME7.5", 1024, "Bora 2.0 8v AZG 115hp — fw4220"),
    KnownROM(0xfab1a067, "06A906032HP", "0261207441", "40/1/ME7.5/5/4019.02//24b/Dst01o/210201",
             "ME7.5", 1024, "Bora/Golf4 1.8T AUM 180hp — fw4019 variant"),
    KnownROM(0xa9b537b9, "06A906032HS", "0261207446", "40/1/ME7.5/3/4019.20//24B/Dst06o/020501",
             "ME7.5", 1024, "Golf4 1.8T AWP 180hp — fw4019 Bosch HS"),

    # ── ME7.5 — 4B0906018 / 8L / 8E longitudinal 1.8T ──────────────────────
    KnownROM(0x5c0ceeae, "4B0906018AG", "0261206453", "42/1/ME7.5/3/4016.00//F22gm/Dst04g/280499",
             "ME7.5", 512,  "Passat B5 1.8T ATW 150hp — 4B0 fw4016"),
    KnownROM(0x386dcb34, "4B0906018AT", "0261206532", "42/1/ME7.5/3/4016.00//F22g6/Dst03g/120499",
             "ME7.5", 512,  "Passat B5 1.8T APU 150hp — 4B0 fw4016"),
    KnownROM(0xf7b8ce22, "4B0906018B",  "0261206050", "40/1/ME7.5/5/4017.00//PST_SER/DST_SER2",
             "ME7.5", 512,  "Passat B5 1.8T APU 150hp — 4B0 fw4017"),
    KnownROM(0x9d9a16c4, "4B0906018BF", "0261206525", "42/1/ME7.5/5/4016.00//F22gb/Dst06g/170899",
             "ME7.5", 512,  "Passat B5 1.8T ANB 150hp — 4B0 fw4016"),
    KnownROM(0x28e1e3cc, "8L0906018M",  "0261206797", "42/1/ME7.5/5/4018.10//F19x5/Dst01t/300999",
             "ME7.5", 512,  "Audi TT 8L 1.8T AMU 225hp — 8L fw4018"),

    # ── ME7.5 — Unknown profile (ABA 2.0 M3.8-era board) ────────────────────
    KnownROM(0x427bf20b, "",            "0261204634", "",
             "ME7.5", 512,  "VW Golf3/4 2.0 8v ABA 115hp — 0261204634 (M3.8 board)"),

    # ── ME7.1 — 8D0907551 S4 B5 2.7T biturbo ────────────────────────────────
    KnownROM(0xb8c7dbce, "8D0907551A",  "0261206110", "42/1/ME7.1/5/6005.01//X22k6/Dstc2g/310599",
             "ME7.1", 1024, "Audi S4 B5 2.7T ARE 265hp — fw6005"),
    KnownROM(0x6044f9dd, "8D0907551D",  "0261206382", "42/1/ME7.1/5/6001.01//X22k6/Dstt2t/260599",
             "ME7.1", 1024, "Audi S4 B5 2.7T AGB/ARE 250hp — fw6001"),

    # ── ME7.1 — 8D0907559 / 06A906018 early AGU/AEB 256KB ───────────────────
    KnownROM(0x7815dae4, "8D0907559C",  "0261206315", "",
             "ME7.1", 256,  "Audi A4 B5 1.8T AGU 150hp — 8D0907559C 256KB"),
    KnownROM(0x5bbee924, "06A906018AQ", "0261204678", "",
             "ME7.1", 256,  "Audi A3 8L 1.8T AGU 150hp — 06A906018AQ 256KB (rev1)"),
    KnownROM(0x6d8d38cb, "06A906018AQ", "0261204678", "",
             "ME7.1", 256,  "Audi A3 8L 1.8T AGU 150hp — 06A906018AQ 256KB (rev2)"),
    KnownROM(0x85dd801e, "06A906018R",  "0261204673", "",
             "ME7.1", 256,  "VW Golf4 1.8T AGU 150hp — 06A906018R 256KB"),

    # ── ME7.1 / ME7.1.1 — VR6 022906032 Golf4/Jetta4/R32 ───────────────────
    KnownROM(0x1c8e82c6, "022906032E",  "0261206619", "40/1/ME7.1/3/6428.AA//23d/DstE3o/110700",
             "ME7.1", 1024, "VW Golf4 2.8L VR6 AHG 174hp — fw6428 ME7.1"),
    KnownROM(0x3fb4cfcf, "022906032CS", "0261207881", "44/1/ME7.1.1/120/6428.AA//24F/Dst01o/260302",
             "ME7.1.1", 1024, "VW Golf4/Jetta4 2.8L VR6 AZZ/BDE 197hp — fw6428 ME7.1.1 rev1"),
    KnownROM(0xbe9ea096, "022906032CS", "0261207881", "44/1/ME7.1.1/120/6428.AA//24F/Dst02o/050603",
             "ME7.1.1", 1024, "VW Golf4/Jetta4 2.8L VR6 AZZ/BDE 197hp — fw6428 ME7.1.1 rev2"),
    KnownROM(0x6be5a4c5, "022906032CP", "0261207885", "",
             "ME7.1.1", 1024, "VW Golf4 R32 3.2L AXYP 240hp — fw6428 ME7.1.1"),
    KnownROM(0xbc7b5d85, "022906032EG", "0261208344", "42/1/ME7.1.1/3/6432.06//24F/Dst22o/250903",
             "ME7.1.1", 1024, "VW Golf5/R32 3.2L BFH 250hp — fw6432 ME7.1.1"),

    # ── ME7.1 — 021906018 Golf3-era VR6 on ME7 ──────────────────────────────
    KnownROM(0x01106d6c, "021906018R",  "0261206814", "42/1/ME7.1/120/6228.A5//19l/Dst03o/071100",
             "ME7.1", 512,  "VW Golf4 2.8L VR6 174hp — 021906018R fw6228 512KB"),

    # ── ME7.1 — 2.7T biturbo S4/A6/RS4/Allroad additional ───────────────────
    KnownROM(0xbd800d41, "8D0907551A",  "0261206110", "42/1/ME7.1/5/6005.01//X22ka/Dstc3g/300899",
             "ME7.1", 1024, "Audi S4 B5 ARE 265hp — fw6005 rev2"),
    KnownROM(0x73a2804b, "8D0907551L",  "0261207004", "40/1/ME7.1/5/6005.01//22m/DstD1o/110700",
             "ME7.1", 1024, "Audi S4 B5 2.7T 265hp — fw6005"),
    KnownROM(0xb88da125, "8D0907551F",  "0261206635", "40/1/ME7.1/5/6024.02//23g/DstW1o/160300",
             "ME7.1", 1024, "Audi RS4 B5 / S4 B5 2.7T 380/265hp — fw6024"),
    KnownROM(0x4553ebf9, "8D0907551K",  "0261207001", "40/1/ME7.1/5/6024.02//23g/DstW1o/051000",
             "ME7.1", 1024, "Audi RS4 B5 2001 2.7T 380hp — fw6024"),
    KnownROM(0x2b4a08eb, "4B0907551F",  "0261206378", "42/1/ME7.1/5/6010.01//X22k6/Dsta1g/270599",
             "ME7.1", 1024, "Audi A6 C5 2.7T ARE/AGB 265hp — 4B0 fw6010"),
    KnownROM(0xf384696d, "4Z7907551D",  "0261207137", "40/1/ME7.1/5/6025.02//22m/DstJ1o/110700",
             "ME7.1", 1024, "Audi A6 Allroad 2.7T ARE/AGB 265hp — 4Z7 fw6025 ME7.1"),
    KnownROM(0x509e389d, "4D0907558S",  "0261206204", "42/1/ME7.1/5/8000.01//X22fj/Dstaeg/040899",
             "ME7.1", 1024, "Audi A6 D2 4.2 V8 ACQ/AKH 299hp — 4D0 fw8000"),

    # ── ME7.1.1 — Allroad additional ─────────────────────────────────────────
    KnownROM(0xd6dafb3f, "4Z7907551N",  "0261207766", "42/1/ME7.1.1/5/6030.03//25A/DstP2o/200602",
             "ME7.1.1", 1024, "Audi A6 Allroad 2.7T AGB/ARE — 4Z7 fw6030 ME7.1.1"),

    # ── ME7.5 — 06A 1.8T additional ──────────────────────────────────────────
    KnownROM(0x5db81d16, "06A906032AC", "0261206580", "42/1/ME7.5/5/4013.00//F21dz/Dst04o/260899",
             "ME7.5", 512,  "Audi A3 8L 1.8T AWD 150hp — fw4013 VDO 512KB"),
    KnownROM(0x291eab26, "06A906032S",  "0261206197", "42/1/ME7.5/5/4019.02//F21dw/Dst01t/030599",
             "ME7.5", 512,  "Audi A3 8L 1.8T AWD 150hp — fw4019 VDO 512KB"),
    KnownROM(0x32c335f2, "06A906032DR", "0261206887", "40/1/ME7.5/3/4013.00//24b/Dst03o/190900",
             "ME7.5", 1024, "VW Bora 1.8T AUM 150hp — fw4013 Bosch 1MB"),

    # ── ME7.5 — 4B0/8L/8N additional ─────────────────────────────────────────
    KnownROM(0x04e60f05, "4B0906018AR", "0261206524", "42/1/ME7.5/5/4016.00//F22g9/Dst01g/310599",
             "ME7.5", 512,  "Audi A4 B5 1.8T APU 150hp — 4B0 fw4016 512KB"),
    KnownROM(0xadaa81b5, "8L0906018K",  "0261206442", "42/1/ME7.5/5/4018.20//F19x4/Dst03g/100699",
             "ME7.5", 512,  "Audi S3 8L 1.8T APY/BAM 210hp — 8L fw4018 512KB"),
    KnownROM(0x68d4e49c, "8N0906018F",  "0261206105", "",
             "ME7.5", 512,  "Audi TT 8N 1.8T AMU/APX 225hp — 8N"),
    KnownROM(0xadeda34c, "8N0906018AB", "0261207027", "",
             "ME7.5", 512,  "Audi TT 8N 1.8T AUQ 180hp — 8N"),
    KnownROM(0x419ad007, "8N0906018J",  "0261206794", "40/1/ME7.5/5/4018.20//24b/Dst03o/210900",
             "ME7.5", 1024, "Audi S3 8N / TT 8N 1.8T AMK/BAM 210hp — fw4018 1MB"),

    # ── ME7.1 — S4/RS4 B5 additional revisions ───────────────────────────────
    KnownROM(0x8d52019a, "8D0907551AA", "0261207453", "40/1/ME7.1/5/6005.01//22N/Dst43o/170501",
             "ME7.1", 1024, "Audi S4 B5 2.7T ARE 265hp — fw6005 late"),
    KnownROM(0xd872dd1a, "8D0907551M",  "0261207143", "40/1/ME7.1/5/6005.01//22m/DstC2o/010101",
             "ME7.1", 1024, "Audi S4 B5 2.7T ARE 265hp — fw6005 (8D0907551M)"),
    KnownROM(0x9aa99c89, "8D0907551Q",  "0261207141", "40/1/ME7.1/5/6024.02//23g/DstW1o/050901",
             "ME7.1", 1024, "Audi RS4 B5 2.7T 380hp — fw6024 (8D0907551Q)"),

    # ── ME7.1.1 — Allroad 4Z7 BEL ────────────────────────────────────────────
    KnownROM(0x6851136d, "4Z7907551R",  "",           "43/1/ME7.1.1/5/6011.02//A25an/Dst5Ao/131202",
             "ME7.1.1", 1024, "Audi A6 Allroad 2.7T BEL 250hp — 4Z7 fw6011 ME7.1.1"),

    # ── ME7.5 — A4/A6 4B0/8E longitudinal additional ─────────────────────────
    KnownROM(0x7d6fa42b, "4B0906018CG", "0261207215", "40/1/ME7.5/5/4016.31//24b/Dst02o/290901",
             "ME7.5", 1024, "Audi A4 B5/A6 C5 1.8T AWT 163hp — 4B0 fw4016"),
    KnownROM(0xc2f5ee1d, "4B0906018L",  "0261206320", "",
             "ME7.5", 512,  "Audi A6 C5 1.8T ANB 150hp — 4B0 fw"),
    KnownROM(0x6420eed7, "8E0906018B",  "0261206868", "40/1/ME7.5/5/4016.32//24e/Dst04o/190901",
             "ME7.5", 1024, "Audi A4 B6 1.8T AMB 163hp — 8E fw4016"),

    # ── ME7.5 — S3 8N / TT 8N additional ────────────────────────────────────
    KnownROM(0x3a86104d, "8N0906018AG", "0261207213", "40/1/ME7.5/5/4018.20//24b/Dst04o/090901",
             "ME7.5", 1024, "Audi S3 8N 1.8T AMK 210hp — 8N fw4018"),
    KnownROM(0x16cc590e, "8N0906018BH", "0261207751", "40/1/ME7.5/5/4018.20//24B/Dst01o/140502",
             "ME7.5", 1024, "Audi S3 8N 1.8T BAM 225hp — 8N fw4018"),

]

# ── Public interface ───────────────────────────────────────────────────────────

KNOWN_ROMS: Dict[int, KnownROM] = {r.crc32: r for r in _CATALOG}


def lookup_rom(crc32: int) -> Optional[KnownROM]:
    """Return the KnownROM entry for this CRC32, or None if not catalogued."""
    return KNOWN_ROMS.get(crc32)


def is_known_stock(crc32: int) -> bool:
    """Return True if this CRC32 matches a catalogued stock ROM."""
    return crc32 in KNOWN_ROMS
