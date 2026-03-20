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

    # ── ME7.1 — S4 B5 2.7T early 512KB variants (ME71 fw6001 calibration extracts) ─
    KnownROM(0xd4d20006, "8D0907551C",  "0261206108", "44/1/ME71/05/6001_01//prog16d/dat16d/180797",
             "ME7.1", 512,  "Audi S4 B5 2.7T AGB/ARE 265hp — 8D0907551C fw6001 512KB cal extract"),
    KnownROM(0x14f1d02d, "8D0907551E",  "0261206376", "44/1/ME71/05/6001_01//prog16d/dat16d/180797",
             "ME7.1", 512,  "Audi S4 B5 2.7T AGB/ARE 265hp — 8D0907551E fw6001 512KB cal extract"),
    KnownROM(0x8a5d93cb, "8D0907551G",  "0261206776", "40/1/ME7.1/5/6001.02//22m/DstT2o/011197",
             "ME7.1", 1024, "Audi S4 B5 2.7T ARE 265hp — fw6001 rev2"),
    KnownROM(0x743acc24, "4B0907551L",  "0261206562", "42/1/ME7.1/5/6005.01//X22kb/Dstf1o/291099",
             "ME7.1", 1024, "Audi S4 B5/A6 C5 2.7T 265hp — 4B0907551L fw6005"),

    # ── ME7.1 — V8 4.2 Audi A6/S6 D2 ────────────────────────────────────────
    KnownROM(0x9fd0c125, "4D0907558",   "0261206372", "42/1/ME7.1/5/8000.07//X22fc/Dsttbg/",
             "ME7.1", 1024, "Audi S6 D2 4.2 V8 fw8000 — 4D0907558"),
    KnownROM(0x70ec5b6f, "4D0907559G",  "0261206096", "42/1/ME7.1/5/8000.07//X22fc/Dsts3g/",
             "ME7.1", 1024, "Audi S8 D2 4.2 V8 360hp — 4D0907559G fw8000"),

    # ── ME7.1 — Passat/A6 2.4 V6 NA ─────────────────────────────────────────
    KnownROM(0x546215f8, "3B0907552J",  "0261206122", "42/1/ME7.1/5/6009.01//F21dd/Dstj1g/031198",
             "ME7.1", 512,  "VW Passat / Audi A6 2.4 V6 170hp — 3B0907552J fw6009 N/A"),

    # ── ME7.1.1 — V8 4.2 S6/S8 D2 / RS6 ─────────────────────────────────────
    KnownROM(0xeb2f6e4f, "4D0907559E",  "0261206846", "42/1/ME7.1.1/5/8001.07//23h/Dst03o/",
             "ME7.1.1", 1024, "Audi S6 D2 / S8 D2 4.2 V8 — 4D0907559E fw8001 ME7.1.1"),
    KnownROM(0x24114441, "4D1907558F",  "0261208728", "42/1/ME7.1.1/5/8542.05//25K/Dst01o/",
             "ME7.1.1", 1024, "Audi RS6 C5 4.2TT 450hp — 4D1907558F fw8542 ME7.1.1"),

    # ── ME7.1.1 — A8 6.0 W12 ─────────────────────────────────────────────────
    KnownROM(0x5f33eaa6, "4E0910018",   "0261208203", "43/1/ME7.1.1/5/12460.01//25E/Dst05o/020304",
             "ME7.1.1", 1024, "Audi A8 D3 6.0 W12 450hp — 4E0910018 fw12460"),

    # ── ME7.5 — 06A 1.8T additional ──────────────────────────────────────────
    KnownROM(0x56371171, "06A906032BB", "0261206268", "40/1/ME7.5/5/4013.00//PST_SER/DST_S",
             "ME7.5", 512,  "Audi A3 8L 1.8T AWD 150hp — 06A906032BB fw4013 Bosch 512KB"),
    KnownROM(0xfad9a671, "06A906032BJ", "0261206892", "40/1/ME7.5/5/4019.02//24b/Dst02o/220201",
             "ME7.5", 1024, "Audi A3 8L 1.8T AUQ 180hp — 06A906032BJ fw4019"),
    KnownROM(0xa94cc076, "06A906032FC", "0261207204", "40/1/ME7.5/5/4013.00//24b/Dst01o/210101",
             "ME7.5", 1024, "Audi A3 8L 1.8T AUM 150hp — 06A906032FC fw4013 Bosch"),
    KnownROM(0x2301ab9c, "06A906032HN", "0261207440", "40/1/ME7.5/5/4019.02//24C/Dst02o/221001",
             "ME7.5", 1024, "Audi A3 8L 1.8T AUM 150hp — 06A906032HN fw4019"),

    # ── ME7.5 — 4B0/8E A4/A6 B5/B6 additional ───────────────────────────────
    KnownROM(0xbe9ea0ad, "4B0906018CH", "0261207216", "40/1/ME7.5/5/4012.01//24b/Dst01o/111100",
             "ME7.5", 1024, "Audi A4 B5 / A6 C5 1.8T AWT 150hp — 4B0 fw4012"),
    KnownROM(0x862853ee, "4B0906018CM", "0261207435", "40/1/ME7.5/3/4012.31//24E/Dst04o/180102",
             "ME7.5", 1024, "Audi A4 B5 / A6 C5 1.8T AWT 150hp — 4B0 fw4012 AT variant"),
    KnownROM(0xe972c32c, "4B0906018DC", "0261207636", "40/1/ME7.5/5/4016.31//24b/Dst01o/220402",
             "ME7.5", 1024, "Audi A6 C5 1.8T AWM 170hp — 4B0 fw4016"),
    KnownROM(0xfcbd8753, "8E0909518AA", "0261207934", "40/1/ME7.5/5/4016.32//24E/Dst02o/260303",
             "ME7.5", 1024, "Audi A4 B6 1.8T BFB 163hp — 8E fw4016"),
    KnownROM(0x5d4d6059, "8E0909518AH", "0261207941", "40/1/ME7.5/5/4016.32//24E/Dst02o/180902",
             "ME7.5", 1024, "Audi A4 B6 1.8T BEX 192hp — 8E fw4016"),
    KnownROM(0x14cc1816, "8E0909518M",  "0261207778", "40/1/ME7.5/5/4016.32//24E/Dst02o/300102",
             "ME7.5", 1024, "Audi A4 B6 1.8T AMB 163hp — 8E fw4016"),

    # ── ME7.5 — TT 8L / S3 8N additional ────────────────────────────────────
    KnownROM(0x3dea5688, "8L0906018Q",  "0261206790", "40/1/ME7.5/5/4019.00//24b/Dst02o/220900",
             "ME7.5", 1024, "Audi TT 8L 1.8T AUQ 180hp — 8L fw4019"),
    KnownROM(0xe632dbcd, "8N0906018AE", "0261207030", "",
             "ME7.5", 512,  "Audi TT 8N 1.8T APX 225hp — 8N fw"),
    KnownROM(0xbd1059e9, "8N0906018AN", "0261207418", "40/1/ME7.5/5/4018.00//22I/Dst04o/280801",
             "ME7.5", 512,  "Audi TT 8N 1.8T AUQ 180hp — 8N fw4018"),
    KnownROM(0xe0d18364, "8N0906018CH", "0261208269", "40/1/ME7.5/5/4018.20//24B/Dst05o/140103",
             "ME7.5", 1024, "Audi S3 8N 1.8T AMK 225hp — 8N fw4018"),

    # ── ME7.5 — 8E0909518 A4 B6/B7 additional revisions ─────────────────────
    KnownROM(0x9c691ff8, "8E0909518G",  "0261206879", "40/1/ME7.5/5/4012.31//24E/Dst02o/",
             "ME7.5", 1024, "Audi A4 B6 1.8T AMB 163hp — 8E fw4012"),
    KnownROM(0x8a31de62, "8E0909518AF", "0261207939", "40/1/ME7.5/5/4012.31//24E/Dst03o/",
             "ME7.5", 1024, "Audi A4 B6 1.8T BEX/AMB 170hp — 8E fw4012"),
    KnownROM(0x6ac132ee, "8E0909518AK", "0261208230", "40/1/ME7.5/5/4012.31//24E/Dst03o/",
             "ME7.5", 1024, "Audi A4 B6/B7 1.8T BFB 163hp — 8E fw4012"),
    KnownROM(0x686907f6, "8E0909518AS", "0261208500", "40/1/ME7.5/5/4016.32//24E/Dst03o/",
             "ME7.5", 1024, "Audi A4 B6/B7 1.8T BFB 163hp — 8E fw4016"),

    # ── ME7.5 — TT 8N additional ─────────────────────────────────────────────
    KnownROM(0x66b79df8, "8N0906018AQ", "0261207416", "40/1/ME7.5/5/4019.00//24C/Dst02o/",
             "ME7.5", 1024, "Audi TT 8N 1.8T AUQ 180hp — 8N fw4019"),

    # ── ME7.5 — S3 8L / TT additional ────────────────────────────────────────
    KnownROM(0x55b84996, "06A906032CL", "0261206552", "42/1/ME7.5/3/4019.20//F22ib/Dst01o/",
             "ME7.5", 512,  "Audi A3 8L 1.8T AWD 150hp — 06A906032CL fw4019 VDO 512KB"),
    KnownROM(0xc5c57fd1, "8L0906018N",  "0261206796", "42/1/ME7.5/5/4018.20//F19x5/Dst01o/",
             "ME7.5", 512,  "Audi S3 8L 1.8T APY 210hp — 8L fw4018 512KB"),
    KnownROM(0x2906eb6e, "8N0906018H",  "0261206795", "40/1/ME7.5/5/4018.10//24b/Dst04o/",
             "ME7.5", 1024, "Audi TT 8N 1.8T BAM 225hp — 8N fw4018"),
    KnownROM(0xf5d4528a, "8N0906018BR", "0261208005", "40/1/ME7.5/5/4019.00//24C/Dst02o/",
             "ME7.5", 1024, "Audi TT 8N 1.8T BAM 225hp — 8N fw4019"),

    # ── ME7.5 — 4B0 A4/A6 additional ─────────────────────────────────────────
    KnownROM(0x5c28989b, "4B0906018R",  "0261206539", "40/1/ME7.5/5/4016.31//24b/Dst02o/",
             "ME7.5", 1024, "Audi A4 B5 / A6 C5 1.8T APU/ATW — 4B0 fw4016"),

    # ── ME7.1 — A6 C5 2.7T AJK / A6 D2 4.2 V8 ───────────────────────────────
    KnownROM(0x1807191e, "4B0907551G",  "0261206380", "42/1/ME7.1/5/6010.01//X22kb/Dstj1o/300799",
             "ME7.1", 1024, "Audi A6 C5 2.7T AJK 230hp — 4B0 fw6010"),
    KnownROM(0x7b521678, "4D0907560AE", "0261206843", "42/1/ME7.1.1/5/8001.02//23g/Dst0ao/140102",
             "ME7.1.1", 1024, "Audi A6 C5 / A8 D2 4.2 V8 ACQ/AKH — 4D0 fw8001 ME7.1.1"),

    # ── ME7.5 — 06A / 4B0 additional ─────────────────────────────────────────
    KnownROM(0x18f572a2, "06A906032AS", "0261206435", "42/1/ME7.5/5/4013.00//F21dx/Dst04o/260899",
             "ME7.5", 512,  "Audi A3 8L 1.8T ARZ 150hp — 06A906032AS fw4013 VDO 512KB"),
    KnownROM(0x4d90713d, "4B0906018P",  "0261206537", "42/1/ME7.5/3/4012.00//F22id/Dst01o/110599",
             "ME7.5", 512,  "Audi A4 B5 1.8T APU 150hp — 4B0 fw4012 512KB"),
    KnownROM(0x8b5a5e39, "8E0909518AN", "0261208285", "40/1/ME7.5/5/4016.32//24E/Dst05o/120903",
             "ME7.5", 1024, "Audi A4 B6/B7 1.8T BFB 190hp — 8E fw4016"),

    # ── ME7.5 — S3 8L second cal revision ────────────────────────────────────
    KnownROM(0x42633d75, "8L0906018K",  "0261206442", "42/1/ME7.5/5/4018.20//F19x4/Dst01t/100699",
             "ME7.5", 512,  "Audi S3 8L 1.8T APY/BAM 210hp — 8L fw4018 512KB rev2"),

    # ── ME7.1 / ME7.1.1 — VR6 T4/Phaeton ────────────────────────────────────
    # T4 California uses the 022906032 VR6 family but with different trim level
    KnownROM(0x00e5a2e6, "022906032B",  "0261206239", "42/1/ME7.1/3/6428.AA//X22i9/Dstm1g/071099",
             "ME7.1",   1024, "VW T4 California 2.8 VR6 AMV 204hp — fw6428 ME7.1"),
    # Phaeton 3.2 VR6 — version string shows ME7.1.1 fw6432
    KnownROM(0xa525b453, "022906032BN", "0261207688", "42/1/ME7.1.1/3/6432.D1//24F/Dst0oo/100204",
             "ME7.1.1", 1024, "VW Phaeton 3.2 VR6 AYT 241hp — fw6432 ME7.1.1"),

    # ── ME7.1.1 — Touareg 4.2 V8 ─────────────────────────────────────────────
    KnownROM(0x5adb84f3, "4D0907560BR", "0261208009", "42/1/ME7.1.1/3/8542.01//25D/DstA4o/060503",
             "ME7.1.1", 1024, "VW Touareg 4.2 V8 AXQ 310hp — 4D0 fw8542 ME7.1.1"),

    # ── ME7.5 — 06A late production (fw4013/fw4518/X505R DSG) ─────────────────
    # fw4518 is Motronic ME7.5 for automatic/CVT applications (Beetle auto, Sharan)
    # X505R is the DSG (Direct Shift Gearbox) firmware variant
    KnownROM(0x58f96103, "06A906032CL", "0261206552", "42/1/ME7.5/3/4019.20//F22ic/Dst01o/050600",
             "ME7.5",   512,  "VW Jetta 1.8T AWD 150hp — 06A906032CL fw4019 VDO 512KB rev2"),
    KnownROM(0xe96baffe, "06A906032FT", "0261207341", "42/1/ME7.5/120/4518.KE//24b/DstE3o/010403",
             "ME7.5",  1024, "VW New Beetle 1.8T AWP 180hp — fw4518 auto"),
    KnownROM(0x7b5d481f, "06A906032GQ", "0261207349", "42/1/ME7.5/120/4518.KE//24b/Dst53o/010403",
             "ME7.5",  1024, "VW New Beetle 1.8T AWW/AUM 150hp — fw4518 auto"),
    KnownROM(0x269bf66a, "06A906032LP", "0261207955", "42/1/ME7.5/120/4013.00//24D/Dst03o/100103",
             "ME7.5",  1024, "VW Jetta 1.8T AWP 180hp — fw4013 Bosch late 1MB"),
    KnownROM(0xbc658efd, "06A906032LQ", "0261207956", "42/1/ME7.5/120/4013.00//24D/Dst03o/100103",
             "ME7.5",  1024, "VW Golf4 1.8T AWW/AWD 150hp — fw4013 Bosch late 1MB"),
    KnownROM(0x39292d94, "06A906032LT", "0261207957", "40/1/ME7.5/3/4013.00//24B/Dst01o/250103",
             "ME7.5",  1024, "VW Golf4 1.8T AWP 180hp — fw4013 Bosch LT"),
    KnownROM(0x4749483d, "06A906032QJ", "0261208686", "42/1/ME7.5/381/4518.SA//22L/DstA2o/010804",
             "ME7.5",  1024, "VW Sharan 1.8T AWC 150hp — fw4518 auto (Sharan-specific)"),
    # X505R = DSG Direct Shift Gearbox firmware — twin-clutch automatic
    KnownROM(0xb1bcd707, "06A906032SK", "0261208528", "40/1/ME7.5/120/X505R//24D/Dst03o/020603",
             "ME7.5",  1024, "VW Golf4/Bora 1.8T AWP/AUM — fw X505R DSG"),
    KnownROM(0xf7253a01, "06A906032SL", "0261208529", "40/1/ME7.5/120/X505R//24D/Dst03o/020603",
             "ME7.5",  1024, "VW Bora 1.8T AWP/AWW — fw X505R DSG rev2"),

    # ── ME7.5 — 4B0 Passat B5/B5.5 additional ────────────────────────────────
    KnownROM(0xcdf3841b, "4B0906018CC", "0261206871", "40/1/ME7.5/5/4016.31//24b/Dst01o/280201",
             "ME7.5",  1024, "VW Passat B5 1.8T AWT 163hp — 4B0 fw4016"),
    KnownROM(0x2612cf54, "4B0906018DA", "0261207931", "40/1/ME7.5/3/4016.31//24E/Dst06o/120302",
             "ME7.5",  1024, "VW Passat B5.5 1.8T AWM 170hp — 4B0 fw4016"),
    KnownROM(0xa641b12c, "4B0906018DF", "0261207639", "40/1/ME7.5/5/4016.31//24b/Dst01o/070202",
             "ME7.5",  1024, "VW Passat B5.5 1.8T AWT 163hp — 4B0 fw4016 DF"),
    KnownROM(0x3fd5ed14, "4B0906018DH", "0261207928", "40/1/ME7.5/3/4016.31//24G/Dst04o/130602",
             "ME7.5",  1024, "VW Passat B5.5 1.8T 163hp — 4B0 fw4016 DH"),
    KnownROM(0x20e8a04e, "4B0906018DP", "0261208291", "40/1/ME7.5/3/4012.31//24H/Dst02o/121002",
             "ME7.5",  1024, "VW Passat B5.5 1.8T AWM 170hp — 4B0 fw4012 DP late"),

    # ── ME7.1 — A6 C5 2.7T additional 4B0 variant ────────────────────────────
    KnownROM(0xbd291747, "4B0907551N",  "0261206637", "40/1/ME7.1/5/6010.02//22N/DstL2o/291000",
             "ME7.1", 1024, "Audi A6 C5 2.7T ARE/AGB 265hp — 4B0907551N fw6010"),

    # ── ME7.1.1 — S4 B6/RS4 B7 4.2 V8 N/A (8H0910560 family) ───────────────
    # 8H0 = S4 Cabriolet / RS4 B7 body.  4.2L V8/5V N/A engine (BBK/BHF/BNS).
    # fw C1105B is specific to the B6/B7 platform — completely different from
    # RS4 B5 fw8542.  DPP1=0x0205.  ME7.1.1.
    KnownROM(0x4517d56e, "8H0910560A",  "0261208462", "42/1/ME7.1.1/5/C1105B//25F/E5f9ka1/020205",
             "ME7.1.1", 1024, "Audi S4 B6 Cabriolet 4.2 V8 BBK 344hp — 8H0 fw C1105B"),
    KnownROM(0x2c2ec95a, "8H0910560H",  "0261208776", "42/1/ME7.1.1/5/C1105B//25F/E5f8lh3/071004",
             "ME7.1.1", 1024, "Audi RS4 B7 4.2 V8 BNS 420hp — 8H0 fw C1105B rev2"),
    KnownROM(0x68cee08c, "8H0910560J",  "0261208777", "42/1/ME7.1.1/5/C1105B//25F/E5f8la3/071004",
             "ME7.1.1", 1024, "Audi RS4 B7 4.2 V8 BNS 420hp — 8H0 fw C1105B rev3"),

    # ── ME7.1.1 — TT 3.2 VR6 additional (022906032GE) ────────────────────────
    KnownROM(0x0d3f657e, "022906032GE", "0261208651", "42/1/ME7.1.1/5/6432.06//24F/Dst4ao/100104",
             "ME7.1.1", 1024, "Audi TT 8N 3.2 VR6 250hp — fw6432 ME7.1.1 late"),

    # ── ME7.5 — A3 8L additional variants ────────────────────────────────────
    KnownROM(0x6f4778f9, "06A906032AF", "0261206269", "40/1/ME7.5/5/4013.00//PST_SER/DST_SER2",
             "ME7.5", 512,  "Audi A3 8L 1.8T AWD 150hp — 06A906032AF fw4013 Bosch 512KB"),
    KnownROM(0x9c3ced82, "06A906032R",  "0261206438", "42/1/ME7.5/5/4019.02//F21dx/Dst01o/",
             "ME7.5", 512,  "Audi A3 8L 1.8T AWD/AUM 150hp — 06A906032R fw4019 512KB"),

    # ── ME7.5 — A4 B6/B7 8E additional suffix ────────────────────────────────
    KnownROM(0x86381242, "8E0909518AL", "0261208228", "40/1/ME7.5/5/4016.32//24H/Dst03o/",
             "ME7.5", 1024, "Audi A4 B6/B7 1.8T BFB 163hp — 8E fw4016 AL"),

    # ── ME7.5 — S3 8N / TT 8N additional ────────────────────────────────────
    KnownROM(0x4d09cde6, "8N0906018BP", "0261208054", "40/1/ME7.5/5/4018.20//24B/Dst02o/",
             "ME7.5", 1024, "Audi S3 8N 1.8T AMK/BAM 225hp — 8N fw4018 BP"),
    KnownROM(0xbf493e72, "8N0906018CA", "0261208086", "",
             "ME7.5", 1024, "Audi TT quattro sport 240hp — 8N0906018CA"),
    KnownROM(0x2d78a9eb, "8N0906018CG", "0261208268", "40/1/ME7.5/5/4018.10//24B/Dst05o/",
             "ME7.5", 1024, "Audi TT 8N 1.8T BAM 225hp — 8N fw4018 CG"),
    KnownROM(0x3bb12a92, "8N0906018K",  "0261206894", "40/1/ME7.5/5/4018.00//22i/Dst03o/",
             "ME7.5", 512,  "Audi TT 8N 1.8T AMU/APX 225hp — 8N fw4018 K 512KB"),
    KnownROM(0x6bf0b9ee, "8N0906018T",  "0261206228", "42/1/ME7.5/5/4018.00//F22id/Dst01o/",
             "ME7.5", 512,  "Audi TT 8N 1.8T AMU 225hp — 8N fw4018 T 512KB"),

]

# ── Public interface ───────────────────────────────────────────────────────────

KNOWN_ROMS: Dict[int, KnownROM] = {r.crc32: r for r in _CATALOG}


def lookup_rom(crc32: int) -> Optional[KnownROM]:
    """Return the KnownROM entry for this CRC32, or None if not catalogued."""
    return KNOWN_ROMS.get(crc32)


def is_known_stock(crc32: int) -> bool:
    """Return True if this CRC32 matches a catalogued stock ROM."""
    return crc32 in KNOWN_ROMS
