"""
meseventool/patches.py
======================
Click-box ECU patches — detectable features that can be toggled on/off.

Two patch types:
  PatchDef       — replaces a fixed byte sequence at a needle-located site
  ScalarPatchDef — reads/writes a single numeric value at a needle-located site

Both self-discover their address by needle search — no hardcoded offsets,
works across all ME7.x variants.

Philosophy (same as HachiROM/DigiTool):
  - Never permanently destroy stock data — always reversible
  - Show current state: STOCK | PATCHED | UNKNOWN | MISSING
  - Group logically: Emissions | Performance | Immobiliser | Comfort | Diagnostics
  - Confidence tracks whether patch is verified on real hardware

Patches marked CONFIRMED are tested on real ROM files.
PROVISIONAL patches are derived from published documentation.
UNCONFIRMED patches need real-ROM validation before use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Sequence, List, Set, TYPE_CHECKING

from .rom import ROMImage
from .needle import Searcher

if TYPE_CHECKING:
    from .profiles import ROMProfile

# Platform trait wildcard — import lazily to avoid circular dependency
_ANY = "*"


# ── Enums ──────────────────────────────────────────────────────────────────────

class PatchState(Enum):
    STOCK          = auto()   # ROM contains stock bytes
    PATCHED        = auto()   # ROM contains patch bytes
    UNKNOWN        = auto()   # neither stock nor patch pattern matched
    MISSING        = auto()   # needle not found in this ROM variant
    NOT_APPLICABLE = auto()   # patch cannot apply to this ECU platform
                               # e.g. a boost patch on an NA profile


class PatchCategory(Enum):
    EMISSIONS   = "Emissions"
    PERFORMANCE = "Performance"
    IGNITION    = "Ignition"
    FUELLING    = "Fuelling"
    IMMOBILISER = "Immobiliser"
    COMFORT     = "Comfort"
    DIAGNOSTICS = "Diagnostics"
    # Legacy aliases kept for backward compat with test code
    BOOST       = "Performance"
    SPEED       = "Performance"


# ── Result ─────────────────────────────────────────────────────────────────────

@dataclass
class PatchResult:
    patch:  "PatchDef"
    state:  PatchState = PatchState.UNKNOWN
    addr:   int        = 0
    detail: str        = ""


# ── PatchDef ───────────────────────────────────────────────────────────────────

@dataclass
class PatchDef:
    """
    A toggleable byte-level ECU patch.

    needle/mask locate the patch site; stock_bytes and patch_bytes define the
    toggle.  offset is the byte offset from needle hit start to modifiable bytes.

    Platform filtering — leave applies_to empty (default) to apply to all:
      applies_to: set of platform tags that must ALL be present in the profile.
      Tags: "turbo" "na" "narrowband" "wideband" "mpi" "fsi" "me7.5" "me7.1"
            "1.8t" "2.0t" "2.7t" "v6"

    Legacy fields (still accepted, auto-translated to applies_to):
      requires_induction / requires_lambda / requires_fuel / requires_family
    """
    name:        str
    description: str
    category:    PatchCategory | str
    needle:      Sequence[int]
    mask:        Sequence[int]
    offset:      int
    stock_bytes: bytes
    patch_bytes: bytes
    warning:     str       = ""
    confidence:  str       = "UNCONFIRMED"
    notes:       str       = ""
    applies_to:  Set[str]  = field(default_factory=set)
    # Legacy requirement lists — translated to applies_to in __post_init__
    requires_induction: List[str] = None   # type: ignore
    requires_lambda:    List[str] = None
    requires_fuel:      List[str] = None
    requires_family:    List[str] = None

    def __post_init__(self):
        assert len(self.needle) == len(self.mask), \
            f"Patch '{self.name}': needle/mask length mismatch"
        assert len(self.stock_bytes) == len(self.patch_bytes), \
            f"Patch '{self.name}': stock/patch bytes length mismatch"
        if self.requires_induction is None: self.requires_induction = []
        if self.requires_lambda    is None: self.requires_lambda    = []
        if self.requires_fuel      is None: self.requires_fuel      = []
        if self.requires_family    is None: self.requires_family    = []
        # Migrate legacy lists into applies_to tag set
        _tag_map = {
            "turbo": "turbo", "na": "na", "biturbo": "turbo",
            "narrowband": "narrowband", "nb": "narrowband",
            "wideband": "wideband",     "wb": "wideband",
            "mpi": "mpi", "fsi": "fsi", "tfsi": "tfsi",
            "me7": "me7.5", "me7.5": "me7.5", "me7.1": "me7.1",
        }
        merged = set(self.applies_to)
        for lst in (self.requires_induction, self.requires_lambda,
                    self.requires_fuel, self.requires_family):
            for r in lst:
                merged.add(_tag_map.get(r.lower(), r.lower()))
        self.applies_to = merged

    def check_applicable(self, profile) -> bool:
        return profile.patch_applies(self)

    def detect(self, rom: ROMImage,
               searcher: Optional[Searcher] = None,
               profile=None) -> PatchResult:
        """
        Locate patch site and return current state.
        NOT_APPLICABLE returned immediately when profile supplied and tags mismatch.
        """
        if profile is not None and not self.check_applicable(profile):
            return PatchResult(self, PatchState.NOT_APPLICABLE, 0,
                               f"N/A: {profile.induction}/"
                               f"{profile.o2_system}/{profile.fuel_system}")

        s   = searcher or Searcher(rom)
        hit = s.search_one(list(self.needle), list(self.mask))
        if hit is None:
            return PatchResult(self, PatchState.MISSING, 0,
                               "Needle not found — variant may differ")

        addr = hit.file_offset + self.offset
        if addr + len(self.stock_bytes) > rom.size:
            return PatchResult(self, PatchState.MISSING, addr,
                               "Patch site outside ROM bounds")

        current = bytes(rom.data[addr : addr + len(self.stock_bytes)])
        if current == self.stock_bytes:
            return PatchResult(self, PatchState.STOCK,   addr, "Stock")
        elif current == self.patch_bytes:
            return PatchResult(self, PatchState.PATCHED, addr, "Patched")
        else:
            return PatchResult(self, PatchState.UNKNOWN, addr,
                               f"Modified: {current.hex().upper()}")

    def apply(self, rom: ROMImage, result: PatchResult) -> bool:
        """Write patch_bytes at the discovered address. Returns True on success."""
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                  PatchState.NOT_APPLICABLE):
            return False
        rom.write(result.addr, self.patch_bytes)
        return True

    def revert(self, rom: ROMImage, result: PatchResult) -> bool:
        """Write stock_bytes at the discovered address."""
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                  PatchState.NOT_APPLICABLE):
            return False
        rom.write(result.addr, self.stock_bytes)
        return True


# ── ScalarPatchDef ─────────────────────────────────────────────────────────────

@dataclass
class ScalarPatchDef:
    """
    A single numeric value readable/writable at a needle-located site.

    Used for RPM limits, boost targets, injector corrections.
    Same platform requirement fields as PatchDef.
    """
    name:       str
    description:str
    category:   PatchCategory | str
    needle:     Sequence[int]
    mask:       Sequence[int]
    offset:     int
    size:       int
    big_endian: bool  = True
    scale:      float = 1.0
    offset_val: float = 0.0
    unit:       str   = ""
    min_val:    float = 0.0
    max_val:    float = 65535.0
    warning:    str   = ""
    confidence: str   = "UNCONFIRMED"
    notes:      str   = ""
    applies_to:         Set[str]  = field(default_factory=set)
    requires_induction: List[str] = None   # type: ignore
    requires_lambda:    List[str] = None
    requires_fuel:      List[str] = None
    requires_family:    List[str] = None

    def __post_init__(self):
        if self.requires_induction is None: self.requires_induction = []
        if self.requires_lambda    is None: self.requires_lambda    = []
        if self.requires_fuel      is None: self.requires_fuel      = []
        if self.requires_family    is None: self.requires_family    = []
        _tag_map = {
            "turbo": "turbo", "na": "na",
            "narrowband": "narrowband", "wideband": "wideband",
            "mpi": "mpi", "fsi": "fsi", "tfsi": "tfsi",
            "me7": "me7.5", "me7.5": "me7.5", "me7.1": "me7.1",
        }
        merged = set(self.applies_to)
        for lst in (self.requires_induction, self.requires_lambda,
                    self.requires_fuel, self.requires_family):
            for r in lst:
                merged.add(_tag_map.get(r.lower(), r.lower()))
        self.applies_to = merged

    def check_applicable(self, profile) -> bool:
        return profile.patch_applies(self)

    def _find_addr(self, rom: ROMImage,
                   searcher: Optional[Searcher] = None) -> int:
        s   = searcher or Searcher(rom)
        hit = s.search_one(list(self.needle), list(self.mask))
        if hit is None:
            return 0
        return hit.file_offset + self.offset

    def read(self, rom: ROMImage,
             searcher: Optional[Searcher] = None) -> Optional[float]:
        """Read current physical value. Returns None if needle missing."""
        addr = self._find_addr(rom, searcher)
        if addr == 0 or addr + self.size > rom.size:
            return None
        raw = int.from_bytes(rom.data[addr : addr + self.size],
                              'big' if self.big_endian else 'little')
        return raw * self.scale + self.offset_val

    def write(self, rom: ROMImage, value: float,
              searcher: Optional[Searcher] = None) -> bool:
        """Write a physical value. Rejects out-of-range values."""
        if value < self.min_val or value > self.max_val:
            return False
        addr = self._find_addr(rom, searcher)
        if addr == 0 or addr + self.size > rom.size:
            return False
        raw = round((value - self.offset_val) / self.scale)
        raw = max(0, min((1 << (self.size * 8)) - 1, raw))
        rom.write(addr, raw.to_bytes(self.size,
                                      'big' if self.big_endian else 'little'))
        return True


@dataclass
class OffsetPatchDef:
    """
    A byte-level patch located by an anchor string rather than a C167 needle.

    Used for DATA patches — cal table values at known stable offsets — where
    needle-based detection is fragile because the surrounding code varies across
    ROM variants.

    anchor_bytes   : byte string to search for in the ROM (e.g. EROTAN string).
    anchor_offset  : signed offset from the start of anchor_bytes to the patch
                     site.  Negative = before the anchor.
    stock_bytes    : expected bytes at the patch site in stock form.
    patch_bytes    : bytes written when the patch is applied.

    Example — O2 monitor threshold in DL ROM:
        anchor_bytes  = b'06A906032DL'   (EROTAN string at 0x0111E7)
        anchor_offset = -16              (threshold is 16 bytes before EROTAN)
        stock_bytes   = bytes([0x8D, 0x80])
        patch_bytes   = bytes([0x80, 0x73])

    Multiple patches per anchor are not supported — use one OffsetPatchDef per
    patch site if the same anchor has multiple dependent patches.
    """
    name:          str
    description:   str
    category:      PatchCategory | str
    anchor_bytes:  bytes
    anchor_offset: int
    stock_bytes:   bytes
    patch_bytes:   bytes
    warning:       str      = ""
    confidence:    str      = "UNCONFIRMED"
    notes:         str      = ""
    applies_to:    Set[str] = field(default_factory=set)

    def __post_init__(self):
        assert len(self.stock_bytes) == len(self.patch_bytes), \
            f"OffsetPatch '{self.name}': stock/patch bytes length mismatch"
        assert self.anchor_bytes, \
            f"OffsetPatch '{self.name}': anchor_bytes must not be empty"

    def check_applicable(self, profile) -> bool:
        if not self.applies_to:
            return True
        return bool(self.applies_to & set(profile.platforms))

    def _find_addr(self, rom: ROMImage) -> int:
        """Return file offset of patch site, or 0 if anchor not found."""
        anchor_pos = bytes(rom.data).find(self.anchor_bytes)
        if anchor_pos < 0:
            return 0
        addr = anchor_pos + self.anchor_offset
        if addr < 0 or addr + len(self.stock_bytes) > rom.size:
            return 0
        return addr

    def detect(self, rom: ROMImage,
               searcher=None,
               profile=None) -> PatchResult:
        if profile is not None and not self.check_applicable(profile):
            return PatchResult(self, PatchState.NOT_APPLICABLE, 0, "N/A")

        addr = self._find_addr(rom)
        if addr == 0:
            return PatchResult(self, PatchState.MISSING, 0,
                               "Anchor string not found")

        current = bytes(rom.data[addr : addr + len(self.stock_bytes)])
        if current == self.stock_bytes:
            return PatchResult(self, PatchState.STOCK,   addr, "Stock")
        elif current == self.patch_bytes:
            return PatchResult(self, PatchState.PATCHED, addr, "Patched")
        else:
            return PatchResult(self, PatchState.UNKNOWN, addr,
                               f"Modified: {current.hex().upper()}")

    def apply(self, rom: ROMImage, result: PatchResult) -> bool:
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                 PatchState.NOT_APPLICABLE):
            return False
        rom.write(result.addr, self.patch_bytes)
        return True

    def revert(self, rom: ROMImage, result: PatchResult) -> bool:
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                 PatchState.NOT_APPLICABLE):
            return False
        rom.write(result.addr, self.stock_bytes)
        return True


@dataclass
class MultiOffsetPatchDef:
    """
    A patch affecting multiple non-contiguous byte sites, all located relative
    to a single anchor string.

    Used for OBD readiness flag tables where the same logical patch clears
    several scattered bytes across a data table.

    sites : list of (anchor_offset: int, stock_byte: int, patch_byte: int)
            Each tuple names one byte site relative to anchor_bytes.

    Detect logic:
        STOCK       — all sites contain their stock_byte
        PATCHED     — all sites contain their patch_byte
        UNKNOWN     — mixed (some patched, some not)
        MISSING     — anchor not found in ROM
    """
    name:          str
    description:   str
    category:      PatchCategory | str
    anchor_bytes:  bytes
    sites:         List[tuple]   # [(anchor_offset, stock_byte, patch_byte), ...]
    warning:       str      = ""
    confidence:    str      = "UNCONFIRMED"
    notes:         str      = ""
    applies_to:    Set[str] = field(default_factory=set)

    def check_applicable(self, profile) -> bool:
        if not self.applies_to:
            return True
        return bool(self.applies_to & set(profile.platforms))

    def _find_anchor(self, rom: ROMImage) -> int:
        """Return file offset of anchor string start, or -1 if not found."""
        return bytes(rom.data).find(self.anchor_bytes)

    def detect(self, rom: ROMImage,
               searcher=None,
               profile=None) -> PatchResult:
        if profile is not None and not self.check_applicable(profile):
            return PatchResult(self, PatchState.NOT_APPLICABLE, 0, "N/A")

        anchor_pos = self._find_anchor(rom)
        if anchor_pos < 0:
            return PatchResult(self, PatchState.MISSING, 0,
                               "Anchor string not found")

        stock_count   = 0
        patched_count = 0
        for anchor_off, stock_b, patch_b in self.sites:
            addr = anchor_pos + anchor_off
            if addr < 0 or addr >= rom.size:
                continue
            b = rom.data[addr]
            if b == stock_b:
                stock_count   += 1
            elif b == patch_b:
                patched_count += 1

        total = len(self.sites)
        # Use first site address as the representative addr
        first_addr = anchor_pos + self.sites[0][0] if self.sites else 0

        if stock_count == total:
            return PatchResult(self, PatchState.STOCK,   first_addr, "Stock")
        elif patched_count == total:
            return PatchResult(self, PatchState.PATCHED, first_addr, "Patched")
        else:
            return PatchResult(self, PatchState.UNKNOWN, first_addr,
                               f"Mixed: {stock_count} stock, {patched_count} patched")

    def apply(self, rom: ROMImage, result: PatchResult) -> bool:
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                 PatchState.NOT_APPLICABLE):
            return False
        anchor_pos = self._find_anchor(rom)
        if anchor_pos < 0:
            return False
        for anchor_off, _stock_b, patch_b in self.sites:
            addr = anchor_pos + anchor_off
            if 0 <= addr < rom.size:
                rom.write(addr, bytes([patch_b]))
        return True

    def revert(self, rom: ROMImage, result: PatchResult) -> bool:
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                 PatchState.NOT_APPLICABLE):
            return False
        anchor_pos = self._find_anchor(rom)
        if anchor_pos < 0:
            return False
        for anchor_off, stock_b, _patch_b in self.sites:
            addr = anchor_pos + anchor_off
            if 0 <= addr < rom.size:
                rom.write(addr, bytes([stock_b]))
        return True


# ── C167 helper constants ──────────────────────────────────────────────────────
XX = 0x00   # wildcard in needle/mask
MM = 0xFF   # must-match


# ── Patch catalogue ────────────────────────────────────────────────────────────

ALL_PATCHES: list[PatchDef | OffsetPatchDef | MultiOffsetPatchDef] = [

    # ── Immobiliser ───────────────────────────────────────────────────────────

    PatchDef(
        name        = "Immobiliser Disable (Bench)",
        description = ("Patches the immobiliser seed/key routine to always "
                       "return TRUE. Engine starts without a valid key signal "
                       "from the instrument cluster. BENCH TESTING ONLY."),
        category    = PatchCategory.IMMOBILISER,
        needle      = [0xD7, 0x40, XX, XX,   # EXTP #seg, #1
                       0xF2, 0xF0, XX, XX,   # MOV  r0, immo_status
                       0x20, 0xF0,           # AND  r0, r0  (set flags)
                       0xDB, 0x00],          # RETS
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM,
                       MM, MM],
        offset      = 8,
        stock_bytes = bytes([0x20, 0xF0]),     # AND r0, r0 — return as-is
        patch_bytes = bytes([0xE0, 0x01]),     # MOV r0, #1 — always success
        confidence  = "PROVISIONAL",
        warning     = "⚠ BENCH TESTING ONLY. Do not drive.",
        notes       = "Variant 1 of ME7RomTool -seedkey patch (360trev).",
    ),

    PatchDef(
        name        = "Immobiliser Disable Variant 2",
        description = ("Second immo defeat variant for ECUs where variant 1 "
                       "needle is absent."),
        category    = PatchCategory.IMMOBILISER,
        needle      = [0xF2, 0xF0, XX, XX,   # MOV  r0, immo_word
                       0x42, 0xF0, 0x01, 0x00,  # CMP r0, #1
                       0x3D, XX,             # JMPR cc_NE, fail
                       0xE6, 0xF0, 0x01, 0x00],  # MOV r0, #1
        mask        = [MM, MM, XX, XX,
                       MM, MM, MM, MM,
                       MM, XX,
                       MM, MM, MM, MM],
        offset      = 8,
        stock_bytes = bytes([0x3D]),    # JMPR cc_NE — jump on not-equal
        patch_bytes = bytes([0x0D]),    # JMPR cc_UC — always skip fail
        confidence  = "UNCONFIRMED",
        warning     = "⚠ BENCH TESTING ONLY.",
    ),

    # ── Emissions ─────────────────────────────────────────────────────────────

    PatchDef(
        name        = "Rear O2 Sensor Delete",
        description = ("Disables post-cat oxygen sensor diagnostic. Suppresses "
                       "P0141/P0140 when rear O2 (B1S2) is removed or a decat fitted. "
                       "The front lambda sensor still controls closed-loop fuelling "
                       "normally — this only affects the post-cat monitoring circuit. "
                       "The rear sensor is always a conventional NB binary-switch type "
                       "regardless of what front sensor the ECU uses."),
        category    = PatchCategory.EMISSIONS,
        needle      = [0xD7, 0x40, XX, XX,   # EXTP  #seg, #1
                       0xF3, 0xF4, XX, XX,   # MOVBZ r4, LSUKATS (rear O2 byte)
                       0x49, 0xF4,           # CMPB  rl4, r4
                       0x8D, XX,             # JMPR  cc_Z, ok
                       0xE6, 0xF4, XX, XX],  # MOV   r4, #fault_flag
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM,
                       MM, XX,
                       MM, MM, XX, XX],
        offset      = 10,
        stock_bytes = bytes([0x8D]),    # conditional jump (fault if not OK)
        patch_bytes = bytes([0x0D]),    # unconditional jump (always OK)
        confidence  = "PROVISIONAL",
        warning     = "Disables OBD-II rear O2 monitoring (P0140/P0141).  "
                      "For 2.7T biturbo: also apply Rear O2 Delete Bank 2.",
        # No applies_to restriction — rear post-cat O2 patch applies to all
        # 1.8T and 06B profiles regardless of front sensor type.
    ),

    PatchDef(
        name        = "Secondary Air Pump Delete",
        description = ("Disables secondary air injection monitoring. "
                       "Suppresses P0410/P0411 when pump is removed."),
        category    = PatchCategory.EMISSIONS,
        needle      = [0x9A, XX, XX, XX,     # JNB  bitfield.bit, target
                       0xE6, 0xF0, XX, XX,   # MOV  r0, #LSBRKUM
                       0xF6, 0xF0, XX, XX],  # MOV  word_XXXX, r0
        mask        = [MM, XX, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM, XX, XX],
        offset      = 0,
        stock_bytes = bytes([0x9A]),    # JNB — conditional
        patch_bytes = bytes([0x0D]),    # JMPR cc_UC — always skip
        confidence  = "UNCONFIRMED",
        warning      = "Disables P0410/P0411.",
        requires_fuel = ["MPI"],
    ),

    PatchDef(
        name        = "EGR Delete",
        description = ("Disables EGR system monitoring. Suppresses P0400/P0401 "
                       "when EGR valve is blocked or removed."),
        category    = PatchCategory.EMISSIONS,
        needle      = [0xE6, 0xF0, XX, XX,   # MOV  r0, #CWEGRAKTION
                       0x20, 0xF0,           # AND  r0, r0
                       0x8D, XX,             # JMPR cc_Z, skip_egr
                       0xE6, 0xF0, XX, XX],  # MOV  r0, #egr_active
        mask        = [MM, MM, XX, XX,
                       MM, MM,
                       MM, XX,
                       MM, MM, XX, XX],
        offset      = 6,
        stock_bytes = bytes([0x8D]),
        patch_bytes = bytes([0x0D]),
        confidence  = "UNCONFIRMED",
        warning      = "Disables P0400/P0401.",
        requires_fuel = ["MPI"],
    ),

    PatchDef(
        name        = "Decel Fuel Cut Disable (DFCO)",
        description = ("Disables deceleration fuel cut. On stock ECUs fuel is "
                       "cut when throttle closes above ~1500 RPM. Disabling "
                       "smooths engine braking and prevents lean surge on "
                       "aggressive lifts with modified intake."),
        category    = PatchCategory.PERFORMANCE,
        needle      = [0x9A, XX, XX, XX,     # JNB  CWKONFZ.DFCO_bit
                       0xF2, 0xF0, XX, XX,   # MOV  r0, NMOT
                       0x42, 0xF0, XX, XX],  # CMP  r0, #dfco_rpm
        mask        = [MM, XX, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM, XX, XX],
        offset      = 0,
        stock_bytes = bytes([0x9A]),    # JNB — enters DFCO if bit set
        patch_bytes = bytes([0x0D]),    # JMP — always skip DFCO
        confidence  = "UNCONFIRMED",
    ),

    # ── Performance ───────────────────────────────────────────────────────────

    PatchDef(
        name        = "Vmax Speed Limiter Disable",
        description = ("Removes the 250 km/h electronic speed limiter. "
                       "Stock limit enforced by fuel cut at vehicle speed "
                       "threshold. Patch makes the comparison unreachable."),
        category    = PatchCategory.PERFORMANCE,
        needle      = [0xF2, 0xF0, XX, XX,   # MOV  r0, VFZGKL (speed)
                       0x42, 0xF0, XX, XX,   # CMP  r0, #vmax_limit
                       0x9D, XX,             # JMPR cc_NE
                       0xE6, 0xF0, XX, XX],  # MOV  r0, #fuel_cut_flag
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, XX,
                       MM, MM, XX, XX],
        offset      = 4,
        stock_bytes = bytes([0x42, 0xF0, 0xFA, 0x00]),  # CMP r0, #250 (approx)
        patch_bytes = bytes([0x42, 0xF0, 0xFF, 0xFF]),  # CMP r0, #65535 — never fires
        confidence  = "PROVISIONAL",
        notes       = "Stock comparison value varies by market/tune.",
    ),

    # ── Diagnostics ───────────────────────────────────────────────────────────

    PatchDef(
        name        = "CEL O2 Readiness Suppress",
        description = ("Suppresses the O2 sensor readiness bit in OBD-II "
                       "mode 01. Prevents 'not ready' CEL after rear O2 "
                       "delete. Does not affect fault code storage."),
        category    = PatchCategory.DIAGNOSTICS,
        needle      = [0xE6, 0xF0, XX, XX,   # MOV  r0, #CWSASY
                       0xA2, 0xF0, XX, XX,   # CMPB rl0, DKWSASY
                       0x8D, XX],            # JMPR cc_Z, ready
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, XX],
        offset      = 8,
        stock_bytes = bytes([0x8D]),   # conditional — CEL if not ready
        patch_bytes = bytes([0x0D]),   # always "ready"
        confidence  = "UNCONFIRMED",
    ),

    # ── Dual-bank rear O2 (2.7T biturbo, V6) ─────────────────────────────────

    PatchDef(
        name        = "Rear O2 Sensor Delete — Bank 2",
        description = ("Disables the Bank 2 post-cat oxygen sensor diagnostic. "
                       "Required in addition to the Bank 1 patch on V6 biturbo "
                       "engines (AGB/ARE/AZZ 2.7T) which have two separate "
                       "catalyst monitors.  Suppresses P0161/P0160."),
        category    = PatchCategory.EMISSIONS,
        needle      = [0xD7, 0x40, XX, XX,   # EXTP  #seg, #1
                       0xF3, 0xF4, XX, XX,   # MOVBZ r4, LSUKATS_B2 (bank 2 rear O2)
                       0x49, 0xF4,           # CMPB  rl4, r4
                       0x8D, XX,             # JMPR  cc_Z, ok_b2
                       0xE6, 0xF4, XX, XX],  # MOV   r4, #fault_flag_b2
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM,
                       MM, XX,
                       MM, MM, XX, XX],
        offset      = 10,
        stock_bytes = bytes([0x8D]),
        patch_bytes = bytes([0x0D]),
        confidence  = "UNCONFIRMED",
        warning     = "Disables OBD-II Bank 2 rear O2 monitoring (P0160/P0161).",
        applies_to  = {"dual_bank"},   # only shown for V6/V8 multi-bank profiles
    ),

    # ── EVAP ──────────────────────────────────────────────────────────────────

    PatchDef(
        name        = "EVAP Purge Delete",
        description = ("Disables EVAP (evaporative emissions) purge valve "
                       "monitoring.  Suppresses P0441/P0442 when the charcoal "
                       "canister or purge valve is removed.  Common on race builds "
                       "running a vented catch tank instead of the OEM system."),
        category    = PatchCategory.EMISSIONS,
        # TEV (Tankreinigungsventil) enable check — bit in configuration codeword
        needle      = [0x9A, XX, XX, XX,     # JNB   CWKONFZ.TEV_bit, skip_evap
                       0xE6, 0xF0, XX, XX,   # MOV   r0, #TEV_state
                       0x46, 0xF0, XX, XX],  # CMP   r0, #tev_active_mask
        mask        = [MM, XX, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM, XX, XX],
        offset      = 0,
        stock_bytes = bytes([0x9A]),   # JNB — enters EVAP monitor if bit set
        patch_bytes = bytes([0x0D]),   # JMP — always skip EVAP monitor
        confidence  = "UNCONFIRMED",
        warning     = "Disables OBD-II EVAP monitoring (P0441/P0442).",
    ),

    # ── Knock protection ──────────────────────────────────────────────────────

    PatchDef(
        name        = "Knock Retard Disable",
        description = ("Disables the ignition retard response to knock sensor "
                       "events.  Timing will NOT pull back under knock.  "
                       "USE WITH EXTREME CAUTION — only for engine-out dyno "
                       "calibration on a fresh build where knock must be "
                       "diagnosed separately.  Catastrophic if used on the road."),
        category    = PatchCategory.IGNITION,
        # EXTP + MOVBZ r4, ERKSP + CMP r4, #max — the knock retard accumulator load.
        # Changing the CMP operand to #0 means the comparison always reads zero
        # retard → the retard application branch never triggers.
        needle      = [0xD7, 0x40, XX, XX,   # EXTP  #seg, #1
                       0xF2, 0xF4, XX, XX,   # MOVBZ r4, [R4+d16]  (ERKSP load)
                       0x46, 0xF4, XX, XX,   # MOVBZ r4, [R4+d16]  (compare load)
                       0x9D, XX],            # JMPR  cc_Z, skip_retard
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, XX],
        offset      = 8,
        stock_bytes = bytes([0x46, 0xF4]),   # MOVBZ r4, [R4+d16]
        patch_bytes = bytes([0x42, 0xF4]),   # MOVBZ r4, [R4+d16] → zeroed path
        confidence  = "CONFIRMED",
        applies_to  = {"1.8t"},
        warning     = "⚠ DYNO/BENCH USE ONLY. Engine damage will result from "
                      "detonation without protection. Never use on the road.",
        notes       = ("Confirmed on 06A906032DL (AWW 150hp).  "
                       "15 needle hits across full ROM — all in ERKSP function.  "
                       "applies_to={'1.8t'} — 2.7T uses a separate needle (R6 not R4)."),
    ),

    PatchDef(
        name        = "Knock Retard Disable (2.7T)",
        description = ("Disables ignition retard response to knock events on the "
                       "2.7T biturbo (S4 B5 / Allroad / A6 C5).  Same functional "
                       "effect as the 1.8T variant but uses R6 register (not R4).  "
                       "USE WITH EXTREME CAUTION — dyno/bench only."),
        category    = PatchCategory.IGNITION,
        # C167 instruction sequence (each instruction is 4 bytes):
        #   D7 40 pp qq = EXTP #page, #1  (extend page pointer for next instruction)
        #   F2 F4 aa bb = MOVBZ R15, [R4+#bbaa]  (load ERKSP accumulator → R15)
        #   F6 F4 cc dd = MOVBZ R6,  [R4+#ddcc]  (load compare value → R6)
        #
        # The address bytes (aa bb / cc dd) vary per software version — wildcarded.
        # stock_bytes = F6 F4 (opcode of the second MOVBZ — bytes 8-9 in the needle).
        # patch_bytes = F2 F4 by analogy to 1.8T's 46→42 bit-2 transformation.
        # NOTE: patch_bytes UNCONFIRMED — needs validation on a known-patched 2.7T ROM.
        needle      = [0xD7, 0x40, XX, XX,   # EXTP  #seg, #1
                       0xF2, 0xF4, XX, XX,   # MOVBZ R15, [R4+d16]  (ERKSP load)
                       0xF6, 0xF4, XX, XX],  # MOVBZ R6,  [R4+d16]  (compare load)
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM, XX, XX],
        offset      = 8,
        stock_bytes = bytes([0xF6, 0xF4]),   # MOVBZ R6, [R4+d16] opcode
        patch_bytes = bytes([0xF2, 0xF4]),   # analogous zero path — UNCONFIRMED
        confidence  = "UNCONFIRMED",
        applies_to  = {"2.7t"},
        warning     = "⚠ DYNO/BENCH USE ONLY. patch_bytes UNCONFIRMED — derived "
                      "by analogy to 1.8T, not validated on a known-patched 2.7T ROM.",
        notes       = ("Needle confirmed: 12–28 hits per 8D0907551 ROM, all in "
                       "ERKSP function 0x03BC00-0x03E600.  "
                       "The 0x9D byte in the original attempt was the high displacement "
                       "byte of MOVBZ, not a JMPR opcode — needle corrected to 12 bytes.  "
                       "patch_bytes=F2F4 by 0xF6→0xF2 bit-2 analogy to 1.8T 0x46→0x42."),
    ),

    # ── Confirmed needle patches — 2.7T/V8 corpus validated ─────────────────

    PatchDef(
        name        = "Vmax Speed Limiter Disable (2.7T ME7.1)",
        description = ("Raises the top speed limiter from 250 km/h (stock) to "
                       "~655 km/h (0xFFFF in 0.01 km/h units) by patching the "
                       "VMAX immediate value loaded into R13 before the speed "
                       "comparison.  The C167 code loads #25000 (0x61A8) into "
                       "R13 for the 250 km/h limit; patching to 0xFFFF removes "
                       "the limiter in practice.  Does not affect the electronic "
                       "speed signal or instrument cluster reading."),
        category    = PatchCategory.PERFORMANCE,
        # C167: MOV R13, #25000  followed by  MOV R14, #imm  +  DA 00 9C 6C
        # Bytes 6-7 (the R14 immediate) vary between SW versions → masked out.
        # Bytes 2-3 (the speed value) are kept in the mask so the needle only
        # hits the real VMAX code site (other uses of MOV R13 exist with small
        # speed values like 0x003C that would be false positives if wildcarded).
        # Limitation: after patching a8 61 → ff ff, the needle no longer matches
        # the patched form — STOCK is detectable but PATCHED shows as MISSING.
        needle      = [0xE6, 0xFD, 0xA8, 0x61, 0xE6, 0xFE, 0x9A, 0x02,
                       0xDA, 0x00, 0x9C, 0x6C],
        mask        = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00, 0x00,
                       0xFF, 0xFF, 0xFF, 0xFF],
        offset      = 2,                    # patch bytes 2-3 (the VMAX immediate)
        stock_bytes = bytes([0xA8, 0x61]),  # 0x61A8 LE = 25000 = 250.00 km/h
        patch_bytes = bytes([0xFF, 0xFF]),  # 0xFFFF LE = 65535 = 655.35 km/h
        confidence  = "CONFIRMED",
        notes       = ("Validated on all 18 8D0907551 (S4 B5), all 12 4B0907551 "
                       "(A6 C5), and 10/20 4Z7907551 (early Allroad ME7.1) ROMs. "
                       "4Z7907551 R/S/T/AA/N/Q (ME7.1.1) and all 4D1907558 (RS4 V8) "
                       "use a different code structure and are NOT covered — "
                       "for those use VAVMX/VMAX table edit in TunerPro instead."),
        applies_to  = {"me7.1", "2.7t"},
    ),

    PatchDef(
        name        = "Vmax Speed Limiter Disable (2.7T ME7.1.1 / V8 RS4)",
        description = ("Raises the top speed limiter from 250 km/h to ~655 km/h "
                       "for the later ME7.1.1 Allroad (4Z7907551 N/Q/R/S/T/AA) "
                       "and all V8 RS4 / S8 variants (4D1907558).  "
                       "Same mechanism as the ME7.1 patch but the code uses a "
                       "different suffix instruction sequence (DA 00 9A 10) "
                       "instead of the ME7.1 form (E6 FE xx xx DA 00 9C 6C)."),
        category    = PatchCategory.PERFORMANCE,
        # C167: MOV R13, #25000  +  CLR Rx  +  DA 00 9A 10  +  (varies)
        # The post-VMAX bytes DA 00 9A 10 are stable across ME7.1.1 variants.
        # Bytes 8-11 vary (the instruction after the 9A 10 branch target) → masked.
        needle      = [0xE6, 0xFD, 0xA8, 0x61, 0xDA, 0x00, 0x9A, 0x10,
                       0x00, 0x00, 0x00, 0x00],
        mask        = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF,
                       0x00, 0x00, 0x00, 0x00],
        offset      = 2,
        stock_bytes = bytes([0xA8, 0x61]),  # 25000 = 250.00 km/h
        patch_bytes = bytes([0xFF, 0xFF]),
        confidence  = "CONFIRMED",
        notes       = ("Validated on 7 × 4D1907558 (RS4 B5 / S8 D2 V8) and "
                       "10 × 4Z7907551 N/Q/R/S/T/AA (ME7.1.1 Allroad). "
                       "Does NOT hit ME7.1 files (confirmed zero false positives). "
                       "Together with the ME7.1 VMAX patch this gives 57/57 1MB "
                       "corpus coverage (100%)."),
        applies_to  = {"me7.1.1", "2.7t"},
    ),

    # ── Confirmed offset-based patches (DL / 06A906032DL verified) ──────────

    OffsetPatchDef(
        name          = "Rear O2 Monitor Threshold",
        description   = ("O2 monitor pass/fail threshold table immediately "
                         "before the EROTAN component string. Patching these "
                         "two bytes effectively disables the rear O2 readiness "
                         "check — the monitor always passes regardless of sensor "
                         "state. Part of the 'O2 Delete Rev2' tune."),
        category      = PatchCategory.EMISSIONS,
        anchor_bytes  = b"06A906032DL",
        anchor_offset = -16,          # 0x0111E7 - 16 = 0x0111D7 on DL
        stock_bytes   = bytes([0x8D, 0x80]),
        patch_bytes   = bytes([0x80, 0x73]),
        confidence    = "CONFIRMED",
        notes         = ("Confirmed on 06A906032DL 1.8L R4/5VT (AWW 150hp). "
                         "Anchor = EROTAN string. Threshold at anchor-16. "
                         "Other part-numbers must be validated individually."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    MultiOffsetPatchDef(
        name          = "Rear O2 OBD Readiness Flags",
        description   = ("Clears 7 OBD readiness flag bytes that track whether "
                         "the rear O2 monitor has run and passed. Setting these "
                         "to 0x00 disables the monitor reporting entirely — MIL "
                         "will not illuminate for a missing/failed rear O2. "
                         "Part of the 'O2 Delete Rev2' tune alongside the "
                         "threshold patch above."),
        category      = PatchCategory.EMISSIONS,
        anchor_bytes  = b"40/1/ME7.5",
        # Offsets relative to anchor at 0x010005 on DL ROM:
        # flag_addr - 0x010005 for each of the 7 readiness bytes
        sites         = [
            (0x074C, 0x03, 0x00),  # 0x010751
            (0x074E, 0x03, 0x00),  # 0x010753
            (0x0767, 0x03, 0x00),  # 0x01076C
            (0x076D, 0x03, 0x00),  # 0x010772
            (0x0781, 0x03, 0x00),  # 0x010786
            (0x0784, 0x03, 0x00),  # 0x010789
            (0x078C, 0x03, 0x00),  # 0x010791
        ],
        confidence    = "CONFIRMED",
        notes         = ("Confirmed on 06A906032DL 1.8L R4/5VT (AWW 150hp). "
                         "Anchor = '40/1/ME7.5' in version string at 0x010005. "
                         "All 7 flag bytes: stock=0x03, patched=0x00. "
                         "Offsets will differ for other software versions."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    # ── Confirmed ESKONF patches — 2.7T/V8 corpus validated ─────────────────
    #
    # ESKONF (Endstufen Konfig) tells the ECU which physical outputs are wired.
    # Clearing LSHHK/HSH2/HSH bits disables post-cat O2 heater circuit diagnosis
    # so removing rear sensors does not trigger P0141/P0161.
    #
    # Three format variants across the 57-ROM corpus (all anchors exclude patch targets):
    #   newer:    block "0f 01 05 0d fe 08 19"  — anchor b'\x0f\x01\x05' (57/57 1MB ROMs)
    #   older-06: block "06 02 a8 0d fe 28 28"  — anchor b'\xee\x24\x06\x02\xa8' (20 ROMs)
    #   older-05: block "05 02 a8 0d fe 28 28"  — anchor b'\xee\x24\x05\x02\xa8' (16 ROMs)
    # Files often carry both a newer and an older block simultaneously.
    # Applying both newer + matching older patch is safe (idempotent on overlapping bytes).

    MultiOffsetPatchDef(
        name          = "ESKONF Rear O2 Heater Disable (newer — 0F 01 05)",
        description   = ("Clears LSHHK (rear O2 heater), HSH2 and HSH bit-pairs in the "
                         "newer-format ESKONF block '0f 01 05 0d fe 08 19'.  Required "
                         "when removing rear O2 sensors to prevent heater circuit DTCs.  "
                         "Covers all 57 standard 1MB ROMs in the s4wiki corpus."),
        category      = PatchCategory.EMISSIONS,
        anchor_bytes  = bytes([0x0F, 0x01, 0x05]),   # bytes 0-2 of block — never patch targets
        sites         = [
            (+3, 0x0D, 0xCD),   # b3 LSHHK: 0x0D → 0xCD  (bits 7:6 → 11 = NOT INSTALLED)
            (+5, 0x08, 0xC8),   # b5 HSH2:  0x08 → 0xC8
            (+6, 0x19, 0xD9),   # b6 HSH:   0x19 → 0xD9
        ],
        confidence    = "CONFIRMED",
        notes         = ("All 57 standard 1MB ROMs: STOCK correctly detected. "
                         "Stock block: 0f 01 05 0d fe 08 19.  "
                         "Anchor b'\x0f\x01\x05' appears exactly once per file and "
                         "never contains any patch-target byte."),
        applies_to    = {"me7.1", "2.7t", "dual_bank"},
    ),

    MultiOffsetPatchDef(
        name          = "ESKONF Rear O2 Heater Disable (older-06 — 06 02 A8)",
        description   = ("Same logical function as the newer-format patch, for ECUs "
                         "with the older '06 02 a8 0d fe 28 28' ESKONF block.  "
                         "Applies to 8D0907551M/G/N/Q/T and 4B0907551AA/R."),
        category      = PatchCategory.EMISSIONS,
        # 2 bytes before block (ee 24) + block bytes 0-2 (06 02 a8) — none are patch targets
        anchor_bytes  = bytes([0xEE, 0x24, 0x06, 0x02, 0xA8]),
        sites         = [
            (+5, 0x0D, 0xCD),   # b3 LSHHK
            (+7, 0x28, 0xE8),   # b5 HSH2
            (+8, 0x28, 0xE8),   # b6 HSH
        ],
        confidence    = "CONFIRMED",
        notes         = ("20 ROMs with '06 02 a8 0d' block; 10 others show UNKNOWN "
                         "from a false-positive '06 02 a8 FE' sequence at the same "
                         "anchor position — those files are fully covered by the newer patch."),
        applies_to    = {"me7.1", "2.7t", "dual_bank"},
    ),

    MultiOffsetPatchDef(
        name          = "ESKONF Rear O2 Heater Disable (older-05 — 05 02 A8)",
        description   = ("Older ESKONF format with '05 02 a8 0d fe 28 28' block prefix.  "
                         "Applies to 8D0907551H/J/K/L, early 4Z7907551K/M, 4B0907551S/T."),
        category      = PatchCategory.EMISSIONS,
        anchor_bytes  = bytes([0xEE, 0x24, 0x05, 0x02, 0xA8]),
        sites         = [
            (+5, 0x0D, 0xCD),
            (+7, 0x28, 0xE8),
            (+8, 0x28, 0xE8),
        ],
        confidence    = "CONFIRMED",
        notes         = ("16 ROMs with '05 02 a8 0d' block verified STOCK."),
        applies_to    = {"me7.1", "2.7t", "dual_bank"},
    ),



]  # end ALL_PATCHES


# ── Scalar patch catalogue ─────────────────────────────────────────────────────

ALL_SCALAR_PATCHES: list[ScalarPatchDef] = [

    ScalarPatchDef(
        name        = "Hard Rev Limit",
        description = ("Hard fuel-cut RPM limit. Stock is 6860 RPM on most "
                       "AWP variants. Raise carefully — valve float starts "
                       "around 7400+ on stock springs."),
        category    = PatchCategory.PERFORMANCE,
        # The hard limit is stored as a 16-bit big-endian raw value near the
        # soft limiter table NMAXKF.  ZWGRU caller sequence references NMXDS.
        needle      = [0xD7, 0x40, XX, XX,   # EXTP  #seg, #1
                       0xF2, 0xF4, XX, XX,   # MOV   r4, NMXDS (hard limit)
                       0x42, 0xF4, XX, XX],  # CMP   r4, #something
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM, XX, XX],
        offset      = 6,
        size        = 2,
        big_endian  = False,
        scale       = 0.75,          # raw * 0.75 = RPM
        unit        = "RPM",
        min_val     = 4000.0,
        max_val     = 8500.0,
        confidence  = "UNCONFIRMED",
        notes       = "Scale 0.75 RPM/count — confirm on real ROM.",
        warning     = "High RPM sustained operation requires forged internals.",
    ),

    ScalarPatchDef(
        name        = "Idle Target RPM",
        description = ("Warm idle target speed for closed-loop idle control. "
                       "Stock ~780 RPM on AWP. Raising slightly improves idle "
                       "stability with cam upgrades."),
        category    = PatchCategory.PERFORMANCE,
        needle      = [0xD7, 0x40, XX, XX,   # EXTP
                       0xF2, 0xF4, XX, XX,   # MOV  r4, LLRN (idle rpm target)
                       0x60, 0xF4],          # ADD  r4, r4
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM],
        offset      = 6,
        size        = 2,
        big_endian  = False,
        scale       = 0.75,
        unit        = "RPM",
        min_val     = 600.0,
        max_val     = 1200.0,
        confidence  = "UNCONFIRMED",
    ),

    ScalarPatchDef(
        name        = "Knock Threshold",
        description = ("Minimum knock sensor signal level before the ECU "
                       "considers it a knock event and begins timing retard. "
                       "Stock value is conservative to protect marginal fuel "
                       "quality.  Raising slightly on premium fuel / E85 can "
                       "allow the ignition map to hold timing longer.  "
                       "Lower = more sensitive (more retard, safer).  "
                       "Higher = less sensitive (more timing, more risk)."),
        category    = PatchCategory.IGNITION,
        # KLOPF — knock threshold stored as 16-bit value near knock window setup
        needle      = [0xD7, 0x40, XX, XX,   # EXTP  #seg, #1
                       0xF2, 0xF4, XX, XX,   # MOV   r4, KLOPF (knock threshold)
                       0x46, 0xF4, XX, XX,   # CMP   r4, knock_window
                       0xDB, 0x00],          # RETS
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM],
        offset      = 6,
        size        = 2,
        big_endian  = False,
        scale       = 1.0,
        unit        = "counts",
        min_val     = 100.0,
        max_val     = 800.0,
        confidence  = "UNCONFIRMED",
        notes       = "Raw count units. Confirm scaling on real ROM before adjusting.",
        warning     = "Raising threshold reduces knock protection. Premium fuel required.",
    ),

    ScalarPatchDef(
        name        = "Injector Dead Time (Battery 14V)",
        description = ("Injector opening dead time at 14V battery voltage. "
                       "Affects fuel delivery accuracy at all loads. "
                       "Must be calibrated to match your injectors — "
                       "wrong value causes lean/rich conditions especially at idle. "
                       "Stock AWP injectors: ~0.75ms at 14V.  "
                       "Larger aftermarket injectors typically need 0.6-0.9ms."),
        category    = PatchCategory.FUELLING,
        # TINHVL (Einspritzventil Haltezeit) — dead time table indexed by voltage
        # The 14V entry is typically in the middle of a ~6-entry table
        needle      = [0xD7, 0x40, XX, XX,   # EXTP  #seg, #1
                       0xF2, 0xF4, XX, XX,   # MOV   r4, TINHVL+4  (14V entry)
                       0xF6, 0xF4, XX, XX,   # MOV   word_XXXX, r4
                       0xDB, 0x00],          # RETS
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM],
        offset      = 6,
        size        = 2,
        big_endian  = False,
        scale       = 0.004,    # approx: raw * 0.004 = ms (confirm on real ROM)
        unit        = "ms",
        min_val     = 0.3,
        max_val     = 2.0,
        confidence  = "UNCONFIRMED",
        notes       = "Scale approx 0.004ms/count — confirm against known good injector "
                      "spec before use. See TINHVL table in maps for full voltage curve.",
        warning     = "Wrong dead time causes fuelling errors across the entire RPM range.",
    ),

    ScalarPatchDef(
        name        = "Soft Rev Limiter Entry",
        description = ("RPM at which the soft rev limiter begins reducing torque "
                       "demand ahead of the hard fuel-cut. Stock AWP: ~6520 RPM. "
                       "Should be set ~200-300 RPM below the hard cut."),
        category    = PatchCategory.PERFORMANCE,
        needle      = [0xD7, 0x40, XX, XX,   # EXTP  #seg, #1
                       0xF2, 0xF4, XX, XX,   # MOV   r4, NMXSB (soft limiter entry)
                       0x42, 0xF4, XX, XX,   # CMP   r4, word_XXXX
                       0x8D, XX],            # JMPR  cc_C, below_soft_limit
        mask        = [MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, MM, XX, XX,
                       MM, XX],
        offset      = 6,
        size        = 2,
        big_endian  = False,
        scale       = 0.75,
        unit        = "RPM",
        min_val     = 4000.0,
        max_val     = 8000.0,
        confidence  = "UNCONFIRMED",
        notes       = "Scale 0.75 RPM/count. Set 200-300 RPM below hard cut.",
    ),

]  # end ALL_SCALAR_PATCHES

# Legacy aliases
PATCH_REGISTRY  = ALL_PATCHES
SCALAR_REGISTRY = ALL_SCALAR_PATCHES


# ── Registry helpers ───────────────────────────────────────────────────────────

def get_patches_by_category() -> dict[PatchCategory, list[PatchDef]]:
    result: dict[PatchCategory, list[PatchDef]] = {}
    for p in ALL_PATCHES:
        cat = p.category if isinstance(p.category, PatchCategory) else PatchCategory.DIAGNOSTICS
        result.setdefault(cat, []).append(p)
    return result


def detect_all(rom: ROMImage,
               searcher: Optional[Searcher] = None,
               profile: Optional["ROMProfile"] = None) -> list[PatchResult]:
    """
    Run detection for every PatchDef and return results.

    If a profile is supplied, patches that don't apply to that platform
    are returned as NOT_APPLICABLE without running the needle search.
    """
    s = searcher or Searcher(rom)
    return [p.detect(rom, s, profile) for p in ALL_PATCHES]
