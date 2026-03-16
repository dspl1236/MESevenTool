"""
meseventool/profiles.py
=======================
Per-variant ROM profiles for ME7.x ECUs.

A ROMProfile carries enough metadata to:
  - Identify the ROM from its part number or DPP1 value
  - Drive patch applicability filtering in the UI
  - Select the right map set and scaling constants
  - Warn the user when a patch is irrelevant for this hardware

Key attributes added for future-proofing
-----------------------------------------
induction      : "turbo" | "na"
  Turbocharged ECUs have boost maps (LDRXN, LDRXS, N75), overboost
  protection, and knock pull that are meaningless on N/A.
  N/A ECUs have throttle-body fuelling and no wastegate.

o2_system      : "narrowband" | "wideband"
  Narrowband (NB): single-wire or 4-wire NTK/Bosch NB sensor; lambda
  control uses a switching strategy, LSUK thresholds around 0.5V.
  Wideband (WB):  5-wire LSU 4.2 or LSU 4.9; continuous lambda signal;
  different diagnostic needles; can target lambda ≠ 1.0 in closed-loop.
  ME7.5 AWP/AUM = NB.  ME7.5.10+ (BKG, BWT) = WB.
  Patches that touch rear O2 heater logic differ between the two.

fuel_system    : "mpi" | "fsi" | "tfsi"
  MPI:  port injection, KFKC fuelling maps
  FSI:  direct injection, very different fuel pressure maps, piezo injectors
  TFSI: direct + port hybrid
  Map names, scalings, and injector patches are completely different.

platforms      : set of platform tag strings
  Used by PatchDef.applies_to for coarse applicability filtering.
  Tags are short lowercase strings: "1.8t", "2.0t", "2.7t", "v6", "na",
  "turbo", "nb", "wb", "mpi", "fsi", "me7.5", "me7.1" etc.
  A patch with applies_to={"1.8t", "turbo"} will only be offered for
  profiles that have both tags in their platforms set.
  Empty applies_to means "applies to everything" (universal patches).

This design means:
  - All existing 1.8T patches work as-is (applies_to stays empty for now)
  - When we add N/A profiles, we add {"na"} to their platforms and N/A-
    specific patches get applies_to={"na"}
  - Wideband-specific O2 patches get applies_to={"wb"}
  - FSI patches get applies_to={"fsi"}
  - The UI calls profile.patch_applies(patch) and dims / hides as needed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Set

from .maps import MapDef, make_awp_maps
from .ecu_id import ECUIdentity
from .dpp import DPPValues


@dataclass
class ROMProfile:
    name:          str
    description:   str       = ""
    part_prefixes: List[str] = field(default_factory=list)
    rom_size:      int       = 0x80000
    ecu_hw:        str       = "ME7.5"
    variants:      List[str] = field(default_factory=list)
    dpp1_min:      int       = 0
    dpp1_max:      int       = 0xFFFF
    notes:         str       = ""

    # ── New capability / hardware classification fields ─────────────────────
    induction:     str       = "turbo"         # "turbo" | "na"
    o2_system:     str       = "narrowband"    # "narrowband" | "wideband"
    fuel_system:   str       = "mpi"           # "mpi" | "fsi" | "tfsi"
    platforms:     Set[str]  = field(default_factory=set)
    # platforms is auto-populated from induction/o2_system/fuel_system/ecu_hw
    # in __post_init__ so profiles don't need to repeat themselves.

    def __post_init__(self):
        # Build the platforms tag set from structured fields
        # Callers can also add extra tags manually after construction.
        auto = set()
        auto.add(self.induction)            # "turbo" or "na"
        auto.add(self.o2_system)            # "narrowband" or "wideband"
        auto.add(self.fuel_system)          # "mpi", "fsi", "tfsi"
        auto.add(self.ecu_hw.lower())       # "me7.5", "me7.1", etc.
        # engine displacement tag from variants list
        for v in self.variants:
            v_lower = v.lower()
            for tag in ("1.8t", "2.0t", "2.7t", "3.0t", "v6", "v8", "2.5"):
                if tag in v_lower:
                    auto.add(tag)
                    break
        self.platforms = self.platforms | auto

    def patch_applies(self, patch) -> bool:
        """
        Return True if the given PatchDef/ScalarPatchDef should be
        offered for this profile.

        A patch with an empty applies_to set is universal.
        A patch with a non-empty applies_to must have ALL its tags present
        in this profile's platforms set.
        """
        applies_to = getattr(patch, 'applies_to', set())
        if not applies_to:
            return True
        return applies_to.issubset(self.platforms)

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
        return make_awp_maps()

    def summary(self) -> str:
        return (f"{self.name}  [{self.ecu_hw}]  "
                f"({', '.join(self.variants[:3])})")


# ── Profile definitions ────────────────────────────────────────────────────────
#
# induction / o2_system / fuel_system are set explicitly where they differ
# from the defaults (turbo / narrowband / mpi).  The platforms set is built
# automatically by __post_init__.

PROFILE_AWP = ROMProfile(
    name          = "ME7.5 — 1.8T AWP/AUM/AUQ/BAM",
    description   = "06A-906-032 family.  The most common ME7.5 platform: "
                    "Golf IV, Jetta IV, TT 8N, A4 B5/B6.  Narrowband O2.  "
                    "Port injection.  512 KB ROM.",
    part_prefixes = ["06A906032"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.5",
    variants      = ["AWP 180hp", "AUM 150hp", "AUQ 180hp", "BAM 190hp",
                     "AVC 150hp", "AZG 150hp", "AGN 125hp"],
    dpp1_min      = 0x01F0,
    dpp1_max      = 0x0210,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "Primary target platform for MESevenTool.",
)

PROFILE_AMU = ROMProfile(
    name          = "ME7.5 — 1.8T 225hp (AMU/APX/BFV)",
    description   = "High-power 225hp 1.8T.  Audi TT Quattro 225, S3 8L.  "
                    "Narrowband O2.  Port injection.  Higher base boost.",
    part_prefixes = ["06A906032", "8N0906018"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.5",
    variants      = ["AMU 225hp", "APX 225hp", "BFV 225hp"],
    dpp1_min      = 0x01F8,
    dpp1_max      = 0x0208,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
)

PROFILE_AUQ = ROMProfile(
    name          = "ME7.5 — 1.8T 180hp Roadster (AUQ)",
    description   = "AUQ for TT Roadster 8N and some A4 B6.  NB O2.  MPI.",
    part_prefixes = ["06A906032", "8N0906032"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.5",
    variants      = ["AUQ 180hp"],
    dpp1_min      = 0x01F5,
    dpp1_max      = 0x0205,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
)

PROFILE_AGU_ME71 = ROMProfile(
    name          = "ME7.1 — 1.8T 150hp (AGU/AEB/ANB)",
    description   = "Earlier ME7.1 platform: A3 8L, Golf IV, Passat B5.  "
                    "256 KB ROM — cal page at 0x30000.  NB O2.  MPI.",
    part_prefixes = ["06A906018", "8D0906018"],
    rom_size      = 0x40000,
    ecu_hw        = "ME7.1",
    variants      = ["AGU 150hp", "AEB 150hp", "ANB 150hp", "AQY 115hp"],
    dpp1_min      = 0x00F0,
    dpp1_max      = 0x0110,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "256 KB ROM — cal page at 0x30000, not 0x70000.",
)

PROFILE_06B = ROMProfile(
    name          = "ME7.5 — 1.8T 06B platform (AWM/AUG/AWT)",
    description   = "06B-906-018 family: A6 C5, Passat B5.5, A4 B5/B6.  "
                    "Same ME7.5 codebase as 06A; different connector.  NB O2.",
    part_prefixes = ["06B906018"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.5",
    variants      = ["AWM 170hp", "AUG 150hp", "AWT 163hp", "AVJ 130hp"],
    dpp1_min      = 0x01F8,
    dpp1_max      = 0x0208,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "Same ME7.5 codebase as 06A; different connector pinout.",
)

# ── Placeholder profiles — no patches or maps yet, structure ready ─────────────

PROFILE_BGU_FSI = ROMProfile(
    name          = "ME7.5 — 2.0T FSI (BWT/BWA/AXX)",
    description   = "2.0T FSI direct injection.  Golf V GTI, A3 8P, Jetta V.  "
                    "Completely different fuelling maps from MPI.  "
                    "PLACEHOLDER — no patches or maps implemented yet.",
    part_prefixes = ["06F906056"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.5",
    variants      = ["BWT 200hp", "BWA 200hp", "AXX 200hp", "BPY 200hp"],
    dpp1_min      = 0x0200,
    dpp1_max      = 0x0220,
    induction     = "turbo",
    o2_system     = "wideband",    # WB — note: different O2 patch needles
    fuel_system   = "fsi",
    notes         = "FSI direct injection.  No patches or maps yet.",
)

PROFILE_V6_2_7T = ROMProfile(
    name          = "ME7.1 — 2.7T V6 Biturbo (AGB/ARE/APX/AZZ)",
    description   = "2.7T V6 biturbo: A4 B5/B6, A6 C5, Allroad.  "
                    "Twin turbo, NB O2 per bank, different boost maps.  "
                    "PLACEHOLDER — no patches or maps implemented yet.",
    part_prefixes = ["4B0906018", "078906018"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.1",
    variants      = ["AGB 250hp", "ARE 265hp", "AZZ 265hp"],
    dpp1_min      = 0x0180,
    dpp1_max      = 0x01A0,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "Twin turbo V6.  No patches or maps yet.",
)

PROFILE_NA_V6 = ROMProfile(
    name          = "ME7.1 — 2.8 V6 N/A (ACK/ALG/AQD/AMX)",
    description   = "Naturally aspirated 2.8 V6: A4 B5/B6, A6 C5, Passat.  "
                    "No boost maps.  Port injection.  Narrowband O2.  "
                    "PLACEHOLDER — no patches or maps implemented yet.",
    part_prefixes = ["078906018"],
    rom_size      = 0x80000,
    ecu_hw        = "ME7.1",
    variants      = ["ACK 193hp", "ALG 193hp", "AQD 193hp", "AMX 193hp",
                     "BBJ 193hp"],
    dpp1_min      = 0x0190,
    dpp1_max      = 0x01B0,
    induction     = "na",          # N/A — no boost patches apply
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "N/A V6.  Boost patches irrelevant.  No content yet.",
)

PROFILE_UNKNOWN = ROMProfile(
    name          = "Unknown ME7.x",
    description   = "ROM not matched to any known profile.  "
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
    PROFILE_BGU_FSI,
    PROFILE_V6_2_7T,
    PROFILE_NA_V6,
]

PROFILES = ALL_PROFILES   # legacy alias


def detect_profile(ecu_id: ECUIdentity, dpp: DPPValues) -> ROMProfile:
    """Return the best matching profile, falling back to UNKNOWN."""
    for profile in ALL_PROFILES:
        if profile.matches(ecu_id, dpp):
            return profile
    if dpp.dpp1:
        for profile in ALL_PROFILES:
            if profile.dpp1_min <= dpp.dpp1 <= profile.dpp1_max:
                return profile
    return PROFILE_UNKNOWN


def get_profile(part_number: str) -> ROMProfile:
    ecu = ECUIdentity(vmecuhn=part_number)
    return detect_profile(ecu, DPPValues())
