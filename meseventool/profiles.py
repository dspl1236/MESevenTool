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
from typing import List, Optional, Set

from .maps import MapDef, make_awp_maps
from .ecu_id import ECUIdentity
from .dpp import DPPValues


@dataclass
class ROMProfile:
    name:          str
    description:   str       = ""
    part_prefixes: List[str] = field(default_factory=list)
    rom_size:      int       = 0x100000
    ecu_hw:        str       = "ME7.5"
    variants:      List[str] = field(default_factory=list)
    dpp1_min:      int       = 0
    dpp1_max:      int       = 0xFFFF
    notes:         str       = ""

    # ── Hardware classification fields ──────────────────────────────────────
    induction:     str       = "turbo"         # "turbo" | "na"
    o2_system:     str       = "narrowband"    # "narrowband" | "wideband"
                                               # narrowband = binary NB front sensor (0-1V)
                                               # wideband   = 5-wire pump-cell LSU front sensor
                                               # NOTE: "wideband tuner" in community parlance
                                               # is NOT the same as this field. AUM/AWP/AUQ
                                               # all use NB front sensors despite community
                                               # calling them "wideband ECUs". See docs/.
    fuel_system:   str       = "mpi"           # "mpi" | "fsi" | "tfsi"
    maf_type:      str       = "bosch_hfm5"   # "bosch_hfm5" | "hitachi"
                                               # MLHFM table characteristic is NOT interchangeable
    dual_bank:     bool      = False           # True for V6/V8 with B1+B2 lambda systems
                                               # (2.7T biturbo, 2.8 VR6, etc.)
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
        auto.add(self.maf_type)             # "bosch_hfm5" or "hitachi"
        if self.dual_bank:
            auto.add("dual_bank")
        # engine displacement tag from variants list
        for v in self.variants:
            v_lower = v.lower()
            for tag in ("1.8t", "2.0t", "2.7t", "3.0t", "v6", "v8", "2.5"):
                if tag in v_lower:
                    auto.add(tag)
                    break
        self.platforms = self.platforms | auto

    def patch_applies(self, patch_or_induction=None,
                      lambda_req=None, fuel_req=None, family_req=None) -> bool:
        """
        Return True if a patch should be offered for this profile.

        Two calling conventions are supported:

        New (preferred) — pass the patch object:
            profile.patch_applies(patch)
            Uses patch.applies_to (a set of platform tags).
            Empty set → applies to all.

        Legacy — pass 4 requirement lists:
            profile.patch_applies(ind_list, lambda_list, fuel_list, family_list)
            Translates to tag checks against self.platforms.
        """
        # New-style: patch object with applies_to set
        if hasattr(patch_or_induction, 'applies_to'):
            applies_to = patch_or_induction.applies_to or set()
            return not applies_to or applies_to.issubset(self.platforms)

        # Legacy-style: 4 separate requirement lists
        # Map old field names to platform tags
        def _ok(req_list, mapping):
            if not req_list:
                return True
            for r in req_list:
                tag = mapping.get(r.lower(), r.lower())
                if tag in self.platforms:
                    return True
            return False

        ind_map  = {"turbo": "turbo", "na": "na", "biturbo": "turbo"}
        lam_map  = {"narrowband": "narrowband", "nb": "narrowband",
                    "wideband": "wideband",    "wb": "wideband"}
        fuel_map = {"mpi": "mpi", "fsi": "fsi", "tfsi": "tfsi"}
        fam_map  = {"me7": "me7.5", "me7.5": "me7.5", "me7.1": "me7.1"}

        return (
            _ok(patch_or_induction or [], ind_map) and
            _ok(lambda_req         or [], lam_map) and
            _ok(fuel_req           or [], fuel_map) and
            _ok(family_req         or [], fam_map)
        )

    def matches(self, ecu_id: ECUIdentity, dpp: DPPValues) -> bool:
        """Return True if this profile matches by part number prefix."""
        pn = (ecu_id.vmecuhn or ecu_id.ssecuhn or "").upper()
        if not pn:
            return False
        for prefix in self.part_prefixes:
            if pn.startswith(prefix.upper()):
                return True
        return False

    def make_maps(self, xdf_pn: Optional[str] = None) -> List[MapDef]:
        """
        Return MapDef list for this profile.

        If xdf_pn is given (e.g. "06A906032DL"), loads confirmed offsets
        from the XDF reference JSON for that specific part number.
        Otherwise falls back to the generic provisional AWP map set.
        """
        if xdf_pn:
            try:
                from .xdf import XDFLoader
                loader = XDFLoader()
                if xdf_pn in loader.part_numbers():
                    return loader.make_maps(xdf_pn)
            except Exception:
                pass
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
    name          = "ME7.5 — 1.8T 06A family (AWP/AWW/AWD/AUM/AUQ/BAM/APH/AWV/AJQ)",
    description   = "06A-906-032 transverse family — the most common ME7.5 platform.  "
                    "Golf IV, Jetta IV, New Beetle, TT 8N, A3 8L, A4 B5.  "
                    "Narrowband O2.  Port injection.  512 KB ROM.  "
                    "CL and CM are transmission variants of AWD — same ROM layout.  "
                    "DL/DM/GH are AWW variants.  8N0/1C0 prefixes are TT/Beetle Turbo S.",
    part_prefixes = ["06A906032", "8N0906018", "1C0906032"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.5",
    variants      = [
        # Golf/Jetta (transverse)
        "AWP 1.8T 180hp",   # 2002+ Golf/Jetta (primary US target)
        "AWW 1.8T 150hp",   # 2001 Golf/Jetta (DL/DM/GH ECUs)
        "AWD 1.8T 150hp",   # 2000 Golf/Jetta (CL/CM ECUs — CL=manual, CM=auto)
        "AUM 1.8T 150hp",   # various markets
        "AUQ 1.8T 180hp",   # various markets
        "BAM 1.8T 190hp",   # TT Roadster / S3
        "AVC 1.8T 150hp",
        "AZG 1.8T 150hp",
        "AGN 1.8T 125hp",
        # New Beetle
        "APH 1.8T 150hp",   # Beetle 1999-2000 (06A906032A/B/C/E/P/Q/R/S)
        "AWV 1.8T 150hp",   # Beetle 2001+ (06A906032DP/FD/GB/KQ/PT etc.)
        # Audi TT 8N
        "AJQ 1.8T 180hp",   # TT Quattro (8L0/8N0906018J etc.)
        "ARY 1.8T 180hp",   # TT — paired with AUQ, same ROM family
        "APP 1.8T 150hp",   # TT single variant (8N0997018HX)
    ],
    dpp1_min      = 0x01F0,
    dpp1_max      = 0x0210,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "Primary target platform for MESevenTool.  "
                    "CL=AWD manual, CM=AWD auto — same map layout.  "
                    "DL=AWW manual, DM/GH=AWW auto — DL is primary XDF reference.  "
                    "PassatWorld ECU list 2000-2002 US market validated against this profile.",
)

PROFILE_AMU = ROMProfile(
    name          = "ME7.5 — 1.8T 225hp (AMU/APX/BFV)",
    description   = "High-power 225hp 1.8T.  Audi TT Quattro 225, S3 8L.  "
                    "Narrowband O2.  Port injection.  Higher base boost.",
    part_prefixes = ["06A906032", "8N0906018"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.5",
    variants      = ["AMU 1.8T 225hp", "APX 1.8T 225hp", "BFV 1.8T 225hp"],
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
    rom_size      = 0x100000,
    ecu_hw        = "ME7.5",
    variants      = ["AUQ 1.8T 180hp"],
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
    part_prefixes = ["06A906018", "8D0906018", "8D0907557", "8D0907559", "8D0997557", "8D0997559"],
    rom_size      = 0x40000,
    ecu_hw        = "ME7.1",
    variants      = ["AGU 1.8T 150hp", "AEB 1.8T 150hp", "ANB 1.8T 150hp", "AQY 1.8T 115hp"],
    dpp1_min      = 0x00F0,
    dpp1_max      = 0x0110,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "256 KB ROM — cal page at 0x30000, not 0x70000.",
)

PROFILE_06B = ROMProfile(
    name          = "ME7.5 — 1.8T 06B/4B0 platform (AWM/AUG/AWT/ATW/AMB)",
    description   = "Longitudinal 1.8T family: A6 C5, Passat B5/B5.5, A4 B5/B6.  "
                    "06B-906-018 and 4B0-906-018 prefixes — same ME7.5 codebase, "
                    "different connectors for transverse vs longitudinal mounting.  "
                    "ATW (Passat 4B0) uses same ROM layout.  NB O2.",
    part_prefixes = ["06B906018", "4B0906018", "4B0997019", "4B0997020", "8E0909518"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.5",
    variants      = [
        "AWM 1.8T 170hp",   # A6 C5, Passat B5.5 (06B)
        "AUG 1.8T 150hp",   # A6 C5 (06B)
        "AWT 1.8T 163hp",   # A6 C5, Passat B5.5 (06B)
        "AVJ 1.8T 130hp",   # A6 C5 (06B)
        "ATW 1.8T 150hp",   # Passat B5 1999-2001 (4B0 prefix)
        "AMB 1.8T 163hp",   # A4 B6 2002 (8E0909518 prefix)
    ],
    dpp1_min      = 0x01F8,
    dpp1_max      = 0x0208,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "Same ME7.5 codebase as 06A; different connector pinout.  "
                    "ATW (4B0 Passat) and AMB (8E A4 B6) confirmed via PassatWorld ECU list.",
)

# ── Placeholder profiles — no patches or maps yet, structure ready ─────────────

PROFILE_BGU_FSI = ROMProfile(
    name          = "ME7.5 — 2.0T FSI (BWT/BWA/AXX)",
    description   = "2.0T FSI direct injection.  Golf V GTI, A3 8P, Jetta V.  "
                    "Completely different fuelling maps from MPI.  "
                    "PLACEHOLDER — no patches or maps implemented yet.",
    part_prefixes = ["06F906056"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.5",
    variants      = ["BWT 2.0T 200hp", "BWA 2.0T 200hp", "AXX 2.0T 200hp", "BPY 2.0T 200hp"],
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
                    "Twin turbo, NB O2 per bank (B1S1+B1S2 and B2S1+B2S2).  "
                    "Rear O2 delete requires two patches — Bank 1 and Bank 2.  "
                    "PLACEHOLDER — no patches or maps implemented yet.",
    part_prefixes = ["4B0906018", "078906018"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1",
    variants      = ["AGB 2.7T 250hp", "ARE 2.7T 265hp", "AZZ 2.7T 265hp"],
    dpp1_min      = 0x0180,
    dpp1_max      = 0x01A0,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    dual_bank     = True,
    notes         = "Twin turbo V6.  dual_bank=True — rear O2 patches need Bank1+Bank2.  "
                    "No patches or maps yet.",
)

PROFILE_NA_V6 = ROMProfile(
    name          = "ME7.1 — 2.8 V6 N/A (ACK/ALG/AQD/AMX)",
    description   = "Naturally aspirated 2.8 V6: A4 B5/B6, A6 C5, Passat.  "
                    "No boost maps.  Port injection.  Narrowband O2.  "
                    "PLACEHOLDER — no patches or maps implemented yet.",
    part_prefixes = ["078906018"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1",
    variants      = ["ACK 2.8 193hp", "ALG 2.8 193hp", "AQD 2.8 193hp",
                     "AMX 2.8 193hp", "BBJ 2.8 193hp"],
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
    rom_size      = 0x100000,
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
