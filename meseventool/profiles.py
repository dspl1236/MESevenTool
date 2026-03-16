"""
meseventool/profiles.py
=======================
Per-variant ROM profiles for ME7.x ECUs.

A ROMProfile defines:
  - Which part numbers / DPP1 ranges identify this variant
  - ECU hardware family and engine code(s)
  - Which maps apply and whether addresses are confirmed
  - Helper to generate MapDef list for this variant

Detection order: part_number prefix → DPP1 range → UNKNOWN fallback.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .maps import MapDef, make_awp_maps
from .ecu_id import ECUIdentity
from .dpp import DPPValues


@dataclass
class ROMProfile:
    name:          str
    description:   str          = ""
    part_prefixes: List[str]    = field(default_factory=list)   # e.g. ["06A906032"]
    rom_size:      int          = 0x80000
    ecu_hw:        str          = "ME7.5"
    variants:      List[str]    = field(default_factory=list)   # engine codes
    dpp1_min:      int          = 0
    dpp1_max:      int          = 0xFFFF
    notes:         str          = ""

    def matches(self, ecu_id: ECUIdentity, dpp: DPPValues) -> bool:
        """Return True if this profile matches by part number prefix."""
        pn = (ecu_id.vmecuhn or ecu_id.ssecuhn or "").upper()
        if not pn:
            return False
        for prefix in self.part_prefixes:
            if pn.startswith(prefix.upper()):
                return True
        return False

    def make_maps(self) -> List[MapDef]:
        """Return MapDef list for this profile (addresses unresolved)."""
        # Default: use AWP maps as the base template
        return make_awp_maps()

    def summary(self) -> str:
        return (f"{self.name}  [{self.ecu_hw}]  "
                f"({', '.join(self.variants[:3])})")


# ── Profile definitions ────────────────────────────────────────────────────────

PROFILE_AWP = ROMProfile(
    name          = "ME7.5 — 1.8T 180hp (AWP)",
    description   = "06A-906-032 AWP/AUM/AVC/BAM/AUQ and related 1.8T 180hp variants. "
                    "The most common ME7.5 platform for Golf IV, Jetta, TT, A4.",
    part_prefixes = ["06A906032"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.5",
    variants      = ["AWP 180hp", "AUM 150hp", "AUQ 180hp", "BAM 190hp",
                     "AVC 150hp", "AZG 150hp", "AGN 125hp"],
    dpp1_min      = 0x01F0,
    dpp1_max      = 0x0210,
    notes         = "Primary target platform for MESevenTool.",
)

PROFILE_AMU = ROMProfile(
    name          = "ME7.5 — 1.8T 225hp (AMU/APX/BFV)",
    description   = "High-power 225hp 1.8T used in Audi TT Quattro 225 and S3.",
    part_prefixes = ["06A906032", "8N0906018"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.5",
    variants      = ["AMU 225hp", "APX 225hp", "BFV 225hp"],
    dpp1_min      = 0x01F8,
    dpp1_max      = 0x0208,
    notes         = "Higher boost and different fuelling vs AWP.",
)

PROFILE_AUQ = ROMProfile(
    name          = "ME7.5 — 1.8T 180hp Roadster (AUQ)",
    description   = "AUQ variant for TT Roadster and some A4 applications.",
    part_prefixes = ["06A906032", "8N0906032"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.5",
    variants      = ["AUQ 180hp"],
    dpp1_min      = 0x01F5,
    dpp1_max      = 0x0205,
)

PROFILE_AGU_ME71 = ROMProfile(
    name          = "ME7.1 — 1.8T 150hp (AGU/AEB/ANB)",
    description   = "Earlier ME7.1 used in A3 8L, Golf IV and Passat B5. "
                    "256 KB ROM; different map addresses from ME7.5.",
    part_prefixes = ["06A906018", "8D0906018"],
    rom_size      = 0x40000,
    ecu_hw        = "ME7.1",
    variants      = ["AGU 150hp", "AEB 150hp", "ANB 150hp", "AQY 115hp"],
    dpp1_min      = 0x00F0,
    dpp1_max      = 0x0110,
    notes         = "256 KB ROM — cal page at 0x30000, not 0x70000.",
)

PROFILE_06B = ROMProfile(
    name          = "ME7.5 — 1.8T 20v (06B platform)",
    description   = "06B-906-018 — A6 C5, Passat B5.5, A4 B5/B6 applications.",
    part_prefixes = ["06B906018"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.5",
    variants      = ["AWM 170hp", "AUG 150hp", "AWT 163hp", "AVJ 130hp"],
    dpp1_min      = 0x01F8,
    dpp1_max      = 0x0208,
    notes         = "Same ME7.5 codebase as 06A; different connector pinout.",
)

PROFILE_UNKNOWN = ROMProfile(
    name          = "Unknown ME7.x",
    description   = "ROM not matched to any known profile. "
                    "Checksum, DPP, and ECU ID extraction still available.",
    part_prefixes = [],
    rom_size      = 0x80000,
    notes         = "Drop a known ROM to improve detection.",
)

ALL_PROFILES: List[ROMProfile] = [
    PROFILE_AWP,
    PROFILE_AMU,
    PROFILE_AUQ,
    PROFILE_AGU_ME71,
    PROFILE_06B,
]

# Legacy alias used in some test/tool code
PROFILES = ALL_PROFILES


def detect_profile(ecu_id: ECUIdentity, dpp: DPPValues) -> ROMProfile:
    """Return the best matching profile, falling back to UNKNOWN."""
    # Part-number match first
    for profile in ALL_PROFILES:
        if profile.matches(ecu_id, dpp):
            return profile
    # DPP1-range fallback when part number is absent but dpp1 is set
    if dpp.dpp1:
        for profile in ALL_PROFILES:
            if profile.dpp1_min <= dpp.dpp1 <= profile.dpp1_max:
                return profile
    return PROFILE_UNKNOWN


def get_profile(part_number: str) -> ROMProfile:
    """Return profile by part number prefix (convenience wrapper)."""
    ecu = ECUIdentity(vmecuhn=part_number)
    return detect_profile(ecu, DPPValues())
