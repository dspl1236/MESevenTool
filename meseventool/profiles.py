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

from .maps import MapDef, make_awp_maps, make_v6_biturbo_maps
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

        Routing:
          - Biturbo V6/V8 (me7.1, dual_bank)  → make_v6_biturbo_maps
          - N/A profiles (na)                  → make_awp_maps (shared base, no boost)
          - 1.8T/2.0T turbo (me7.5/me7.1 mpi) → XDF-confirmed make_awp_maps
        If xdf_pn is given and matches a known XDF part number, uses confirmed
        offsets from reference/xdf_tables.json.
        """
        # V6/V8 biturbo — different calibration structure
        if self.dual_bank or "2.7t" in self.platforms or "v8" in self.platforms:
            return make_v6_biturbo_maps(xdf_pn or "")

        # Try XDF confirmed offsets first (for exact PN match)
        if xdf_pn:
            try:
                from .xdf import XDFLoader
                loader = XDFLoader()
                if xdf_pn in loader.part_numbers():
                    return loader.make_maps(xdf_pn)
            except Exception:
                pass

        # Fall back to AWP map set (confirmed for 06A906032DL, provisional for others)
        return make_awp_maps(xdf_pn or "")

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

PROFILE_VR6_ME71 = ROMProfile(
    name          = "ME7.1 — 2.8/3.2 VR6 N/A (022906032 / 021906018)",
    description   = "Naturally aspirated VR6: Golf IV 2.8L AAA/AES (021906018R/M), "
                    "Golf IV 2.8L ABV/AHG (022906032E/B/C/CS/BM), "
                    "Golf V R32 3.2L (022906032EG/CE/CD/CP).  "
                    "Also: Jetta IV VR6, Passat B5 2.8L, T4 Transporter VR6.  "
                    "NB O2.  MPI (sequential).  No boost maps — N/A engine.  "
                    "Dual-bank lambda on 024-family 30V engines (R32).  "
                    "Part numbers: 022906032 (Golf4/Jetta4 VR6, R32) "
                    "and 021906018 (Golf3-era VR6 on ME7).",
    part_prefixes = ["022906032", "021906018", "022906019"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1",
    variants      = [
        "AAA 2.8 174hp",    # Golf3/Golf4 VR6 (021906018R — ME7.1 early)
        "AES 2.8 174hp",    # T4 Transporter VR6 (021906256H — same family)
        "AHG 2.8 174hp",    # Golf4 VR6 Golf4 (022906032E)
        "AZZ 2.8 197hp",    # Golf4 VR6 later (022906032CS/BM)
        "BDE 2.8 197hp",    # Jetta4 VR6 (022906032CS)
        "BDF 2.8 174hp",    # variant
        "AXYP 3.2 240hp",   # Golf4 R32 (022906032CP — ME7.1.1 fw6428)
        "BFH 3.2 250hp",    # Golf5 R32 (022906032CE/CD/EG — ME7.1.1 fw6432)
        "BMX 2.0 150hp",    # Golf4 2.0 8v ABA on 022 board (placeholder)
    ],
    dpp1_min      = 0x0205,
    dpp1_max      = 0x0205,
    induction     = "na",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    dual_bank     = False,   # True for R32 30V — set per-variant if needed
    notes         = "VR6 N/A family.  Boost patches irrelevant.  "
                    "DPP1=0x0205 confirmed on Golf4 VR6 and R32 corpus ROMs.  "
                    "ME7.1 fw6228/6428 (2.8L) and ME7.1.1 fw6428/6432 (R32).  "
                    "vmecuhn may be blank on older Golf3-era 021906018 ROMs — "
                    "Bosch number (0261206xxx) is the reliable key.",
)

PROFILE_V5_ME75 = ROMProfile(
    name          = "ME7.5 — 2.3 V5 N/A (071906018)",
    description   = "Naturally aspirated 2.3L V5: Passat B5 and Golf IV 2.3 20V.  "
                    "071-906-018 prefix.  NB O2.  MPI.  No boost maps.  "
                    "PLACEHOLDER — structure ready, no patches or maps yet.",
    part_prefixes = ["071906018"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.5",
    variants      = ["AGZ 2.3 V5 170hp", "AQN 2.3 V5 170hp", "AZX 2.3 V5 170hp"],
    dpp1_min      = 0x0200,
    dpp1_max      = 0x0210,
    induction     = "na",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "V5 N/A.  Boost patches irrelevant.  No content yet.",
)

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

PROFILE_V6_27T_ME71 = ROMProfile(
    name          = "ME7.1 — 2.7T V6 Biturbo early (AGB/ARE/BES — 8D0/4B0/early 4Z7)",
    description   = "2.7T V6 biturbo, ME7.1 software: S4 B5 (8D0907551), "
                    "A6 C5 tip (4B0907551), early Allroad (4Z7907551 up to M). "
                    "Version string: '40/1/ME7.1/'.  Twin KKK K03/K04 turbos. "
                    "NB O2 per bank.  DPP1=0x0205.",
    part_prefixes = ["8D0907551", "4B0907551", "4Z7907551"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1",
    variants      = ["AGB 2.7T 250hp", "ARE 2.7T 265hp",
                     "BES 2.7T 250hp", "APX 2.7T 256hp"],
    dpp1_min      = 0x0205,
    dpp1_max      = 0x0205,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    dual_bank     = True,
    notes         = "Twin turbo V6.  DPP1=0x0205 confirmed across 34 corpus ROMs.",
)

PROFILE_V6_27T_ME711 = ROMProfile(
    name          = "ME7.1.1 — 2.7T V6 Biturbo later (4Z7907551 N/Q/R/S/T/AA)",
    description   = "2.7T V6 biturbo, ME7.1.1 software: later Allroad variants "
                    "(4Z7907551 N/Q/R/S/T/AA).  Version string: '42/1/ME7.1.1/'. "
                    "Same hardware as ME7.1 but updated software with K-box logging "
                    "support and revised ESKONF layout.  DPP1=0x0205.",
    part_prefixes = ["4Z7907551"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1.1",
    variants      = ["AGB 2.7T 250hp", "ARE 2.7T 265hp", "BCY 2.7T 265hp"],
    dpp1_min      = 0x0205,
    dpp1_max      = 0x0205,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    dual_bank     = True,
    notes         = "Confirmed on 10 × 4Z7907551 N/Q/R/S/T/AA corpus ROMs. "
                    "DPP1=0x0205.  ME7.1.1 VMAX needle applies to this profile.",
)

# Legacy alias — keep for any code that references PROFILE_V6_2_7T by name
PROFILE_V6_2_7T = PROFILE_V6_27T_ME71

PROFILE_V8_RS4 = ROMProfile(
    name          = "ME7.1.1 — 4.2T V8 Biturbo (BCY/AKH/AQJ — 4D1907558 family)",
    description   = "RS4 B5 / S8 D2 / A8 4.2l V8 biturbo.  "
                    "ME7.1.1 (updated ME7.1 with K-box logging support).  "
                    "DPP1=0x0205, C167 architecture identical to 2.7T.",
    part_prefixes = ["4D1907558"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1.1",
    variants      = ["BCY 4.2T 380hp", "AKH 4.2T 340hp", "AQJ 4.2T 340hp"],
    dpp1_min      = 0x0205,
    dpp1_max      = 0x0205,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    dual_bank     = True,
    notes         = "V8 biturbo RS4.  K-box logging patch at 0x35FD2/0x77DE4/0x78CB6 "
                    "(s4wiki documented).  6 stock ROMs in corpus.",
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

PROFILE_V8_D2 = ROMProfile(
    name          = "ME7.1 — 4.2 V8 N/A (4D0907558/559 — S6/S8/A8 D2)",
    description   = "Naturally aspirated 4.2 V8: S6 C4, S8 D2, A8 D2.  "
                    "4D0-907-558 and 4D0-907-559 prefixes.  NB O2.  MPI.  "
                    "fw8000 (ME7.1) and fw8001 (ME7.1.1).  "
                    "No boost maps — N/A engine.  PLACEHOLDER.",
    part_prefixes = ["4D0907558", "4D0907559"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1",
    variants      = ["ACQ 4.2 290hp", "AKH 4.2 340hp", "ABZ 4.2 300hp",
                     "AUW 4.2 310hp", "ART 4.2 360hp"],
    dpp1_min      = 0x0205,
    dpp1_max      = 0x0205,
    induction     = "na",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    dual_bank     = True,    # V8 has B1+B2 lambda system
    notes         = "V8 N/A.  Boost patches irrelevant.  DPP1=0x0205.  "
                    "fw8000 = ME7.1, fw8001 = ME7.1.1.  No maps yet.",
)

PROFILE_V8_RS6 = ROMProfile(
    name          = "ME7.1.1 — 4.2T V8 biturbo RS6 (4D1907558F — C5)",
    description   = "RS6 C5 4.2 biturbo 450hp.  4D1-907-558 prefix.  "
                    "ME7.1.1 fw8542.  Twin KKK turbos.  NB O2.  MPI.  "
                    "Same C167 architecture as RS4/Allroad.  PLACEHOLDER.",
    part_prefixes = ["4D1907558"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1.1",
    variants      = ["BCY 4.2T 450hp", "AZR 4.2T 450hp"],
    dpp1_min      = 0x0205,
    dpp1_max      = 0x0205,
    induction     = "turbo",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    dual_bank     = True,
    notes         = "RS6 C5 biturbo.  fw8542 ME7.1.1.  No maps yet.",
)

PROFILE_W12 = ROMProfile(
    name          = "ME7.1.1 — 6.0 W12 (4E0910018 — A8 D3)",
    description   = "Audi A8 D3 6.0L W12 450hp.  4E0-910-018 prefix.  "
                    "ME7.1.1 fw12460.  Unique W12 engine architecture.  "
                    "N/A but 12-cylinder.  NB O2.  MPI.  PLACEHOLDER.",
    part_prefixes = ["4E0910018", "4E0906018"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1.1",
    variants      = ["BHT 6.0 W12 450hp", "BSB 6.0 W12 450hp"],
    dpp1_min      = 0x0205,
    dpp1_max      = 0x0205,
    induction     = "na",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    dual_bank     = True,
    notes         = "W12 6.0 unique engine.  fw12460 ME7.1.1.  No maps yet.",
)

PROFILE_V6_24_NA = ROMProfile(
    name          = "ME7.1 — 2.4 V6 N/A (3B0907552 — Passat/A6)",
    description   = "VW Passat B5 / Audi A6 C5 2.4 V6 170hp.  "
                    "3B0-907-552 prefix.  ME7.1 fw6009.  NB O2.  MPI.  "
                    "No boost maps — N/A engine.  PLACEHOLDER.",
    part_prefixes = ["3B0907552"],
    rom_size      = 0x080000,   # 512KB
    ecu_hw        = "ME7.1",
    variants      = ["ACK 2.4 V6 170hp", "ALF 2.4 V6 170hp", "APS 2.4 V6 170hp"],
    dpp1_min      = 0x0190,
    dpp1_max      = 0x01C0,
    induction     = "na",
    o2_system     = "narrowband",
    fuel_system   = "mpi",
    notes         = "2.4 V6 N/A Passat/A6.  512KB ROM.  No maps yet.",
)


PROFILE_UNKNOWN = ROMProfile(
    name          = "Unknown ME7.x",
    description   = "ROM not matched to any known profile.  "
                    "Checksum, DPP, and ECU ID extraction still available.",
    part_prefixes = [],
    rom_size      = 0x100000,
    notes         = "Drop a known ROM to improve detection.",
)

PROFILE_V8_D2 = ROMProfile(
    name          = "ME7.1 — 4.2 V8 N/A (4D0907558/559 — S6/S8 D2)",
    description   = "Naturally aspirated 4.2 V8: S6 D2, S8 D2. "
                    "4D0907558 / 4D0907559 prefixes. NB O2. MPI. "
                    "No boost maps. DPP1=0x0205. fw8000.",
    part_prefixes = ["4D0907558", "4D0907559"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1",
    variants      = ["ACQ 4.2 299hp", "AKH 4.2 300hp", "AHC 4.2 300hp"],
    dpp1_min      = 0x0205, dpp1_max = 0x0205,
    induction     = "na", o2_system = "narrowband", fuel_system = "mpi",
    dual_bank     = True,
    notes         = "V8 N/A. fw8000. 4D0907558S confirmed (CRC 0x509e389d).",
)

PROFILE_V8_RS6 = ROMProfile(
    name          = "ME7.1.1 — RS6 C5 4.2TT biturbo (4D1907558F)",
    description   = "RS6 C5 4.2 V8 biturbo 450hp. "
                    "4D1907558F prefix. NB O2. MPI. Dual-bank lambda. "
                    "fw8542. ME7.1.1.",
    part_prefixes = ["4D1907558"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1.1",
    variants      = ["BCY 4.2TT 450hp"],
    dpp1_min      = 0x0205, dpp1_max = 0x0205,
    induction     = "turbo", o2_system = "narrowband", fuel_system = "mpi",
    dual_bank     = True,
    notes         = "RS6 C5. fw8542 ME7.1.1. 4D1907558F confirmed.",
)

PROFILE_W12 = ROMProfile(
    name          = "ME7.1.1 — A8 D3 6.0 W12 (4E0910018)",
    description   = "Audi A8 D3 6.0L W12 450hp. "
                    "4E0910018 prefix. NB O2. MPI. fw12460. ME7.1.1.",
    part_prefixes = ["4E0910018", "4E0906018"],
    rom_size      = 0x100000,
    ecu_hw        = "ME7.1.1",
    variants      = ["BHT 6.0 W12 450hp"],
    dpp1_min      = 0x0205, dpp1_max = 0x0210,
    induction     = "na", o2_system = "narrowband", fuel_system = "mpi",
    dual_bank     = True,
    notes         = "A8 D3 W12. fw12460. 4E0910018 confirmed (CRC 0x5f33eaa6).",
)

PROFILE_V6_24_NA = ROMProfile(
    name          = "ME7.1 — 2.4 V6 N/A (3B0907552J — Passat/A6)",
    description   = "Naturally aspirated 2.4 V6: Passat B5, A6 C5. "
                    "3B0907552 prefix. NB O2. MPI. fw6009. "
                    "PLACEHOLDER — no patches or maps yet.",
    part_prefixes = ["3B0907552"],
    rom_size      = 0x080000,
    ecu_hw        = "ME7.1",
    variants      = ["AGA 2.4 165hp", "ALF 2.4 165hp", "AML 2.4 165hp"],
    dpp1_min      = 0x0190, dpp1_max = 0x01B0,
    induction     = "na", o2_system = "narrowband", fuel_system = "mpi",
    notes         = "V6 2.4 N/A. 512KB extract. No content yet.",
)


ALL_PROFILES: List[ROMProfile] = [
    PROFILE_AWP,
    PROFILE_AMU,
    PROFILE_AUQ,
    PROFILE_AGU_ME71,
    PROFILE_06B,
    PROFILE_VR6_ME71,      # Golf4/Jetta4 VR6 2.8, R32 3.2
    PROFILE_V5_ME75,       # Passat/Golf V5 2.3
    PROFILE_BGU_FSI,
    PROFILE_V6_27T_ME71,
    PROFILE_V6_27T_ME711,
    PROFILE_V8_RS4,
    PROFILE_NA_V6,
    PROFILE_V8_D2,         # S6/S8 D2 4.2 V8 NA (4D0907558/559)
    PROFILE_V8_RS6,        # RS6 C5 4.2TT biturbo (4D1907558F)
    PROFILE_W12,           # A8 D3 6.0 W12 (4E0910018)
    PROFILE_V6_24_NA,      # Passat/A6 2.4 V6 NA (3B0907552J)
]

PROFILES = ALL_PROFILES   # legacy alias


def detect_profile(ecu_id: ECUIdentity, dpp: DPPValues) -> ROMProfile:
    """Return the best matching profile, falling back to UNKNOWN.

    Match priority:
      1. part_prefixes match + ecu_hw matches version_string (most specific)
      2. part_prefixes match (any ecu_hw — first in ALL_PROFILES wins)
      3. DPP1 range match filtered by ME7 hw version in version_string
      4. DPP1 range match (unfiltered)
      5. UNKNOWN
    """
    vs = getattr(ecu_id, "version_string", "") or ""
    hw_hint = None
    for tag in ("ME7.1.1", "ME7.5", "ME7.1", "ME71"):
        if tag.replace(".", "").lower() in vs.replace(".", "").lower():
            hw_hint = tag.replace("ME71", "ME7.1")
            break

    # Pass 1: prefix match + ecu_hw agrees with version_string
    if hw_hint:
        for profile in ALL_PROFILES:
            if profile.matches(ecu_id, dpp) and profile.ecu_hw == hw_hint:
                return profile

    # Pass 2: prefix match regardless of ecu_hw
    for profile in ALL_PROFILES:
        if profile.matches(ecu_id, dpp):
            return profile

    if dpp.dpp1:
        # Use ECU version string to narrow DPP matches:
        # "ME7.5" → prefer ME7.5 profiles; "ME7.1.1" → ME7.1.1 profiles etc.
        vs = getattr(ecu_id, "version_string", "") or ""
        hw_hint = None
        for tag in ("ME7.1.1", "ME7.5", "ME7.1", "ME71"):
            if tag.replace(".", "").lower() in vs.replace(".", "").lower():
                hw_hint = tag.replace("ME71", "ME7.1").replace("ME7.1.1", "ME7.1.1")
                break

        if hw_hint:
            for profile in ALL_PROFILES:
                if profile.dpp1_min <= dpp.dpp1 <= profile.dpp1_max:
                    # Exact match beats prefix — "ME7.1.1" != "ME7.1"
                    if profile.ecu_hw == hw_hint:
                        return profile
            # Fallback: prefix match (e.g. "ME7.1" matches "ME7.1" profiles)
            for profile in ALL_PROFILES:
                if profile.dpp1_min <= dpp.dpp1 <= profile.dpp1_max:
                    if hw_hint.startswith(profile.ecu_hw):
                        return profile

        for profile in ALL_PROFILES:
            if profile.dpp1_min <= dpp.dpp1 <= profile.dpp1_max:
                return profile

    return PROFILE_UNKNOWN


def get_profile(part_number: str) -> ROMProfile:
    ecu = ECUIdentity(vmecuhn=part_number)
    return detect_profile(ecu, DPPValues())
