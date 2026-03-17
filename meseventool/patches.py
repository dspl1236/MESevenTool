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
    all_hits:    bool     = False  # if True, apply/revert patches ALL needle hits
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
            # Also search with patch_bytes substituted in — handles already-patched ROMs
            # where the stock value has been replaced and the strict needle no longer matches.
            if self.patch_bytes != self.stock_bytes:
                patched_needle = list(self.needle)
                patched_mask   = list(self.mask)
                for i, b in enumerate(self.patch_bytes):
                    patched_needle[self.offset + i] = b
                    patched_mask[self.offset + i]   = 0xFF
                hit2 = s.search_one(patched_needle, patched_mask)
                if hit2 is not None:
                    addr2 = hit2.file_offset + self.offset
                    return PatchResult(self, PatchState.PATCHED, addr2, "Patched (alt needle)")
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
        """Write patch_bytes at the discovered address. Returns True on success.
        If all_hits=True, patches every needle occurrence in the ROM."""
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                  PatchState.NOT_APPLICABLE):
            return False
        if self.all_hits:
            s = Searcher(rom)
            hits = s.search(list(self.needle), list(self.mask))
            for h in hits:
                rom.write(h.file_offset + self.offset, self.patch_bytes)
        else:
            rom.write(result.addr, self.patch_bytes)
        return True

    def revert(self, rom: ROMImage, result: PatchResult) -> bool:
        """Write stock_bytes at the discovered address.
        If all_hits=True, reverts every needle occurrence in the ROM."""
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                  PatchState.NOT_APPLICABLE):
            return False
        if self.all_hits:
            s = Searcher(rom)
            hits = s.search(list(self.needle), list(self.mask))
            for h in hits:
                rom.write(h.file_offset + self.offset, self.stock_bytes)
        else:
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
class FixedAddressPatchDef:
    """Patch at a known fixed address in the ROM — no anchor search needed.

    Used when the target address is stable across all firmware versions
    (e.g. the ME7 codeword block which is always at 0x018194 in all variants).
    A sanity set of expected values is provided to confirm the site before patching.
    """
    name:          str
    description:   str
    category:      PatchCategory
    fixed_addr:    int               # ROM file offset of the byte(s) to patch
    stock_bytes:   bytes             # expected bytes at that address when stock
    patch_bytes:   bytes             # bytes to write when applying patch
    warning:       str    = ""
    confidence:    str    = "UNCONFIRMED"
    notes:         str    = ""
    applies_to:    set    = field(default_factory=set)

    # Stub fields for compatibility with PatchDef callers
    requires_induction: list = field(default_factory=list)
    requires_lambda:    list = field(default_factory=list)
    requires_fuel:      list = field(default_factory=list)
    requires_family:    list = field(default_factory=list)

    def check_applicable(self, profile=None) -> bool:
        if not self.applies_to or profile is None:
            return True
        # Use .platforms (same as PatchDef) — .tags doesn't exist on ROMProfile
        platforms = getattr(profile, 'platforms', set())
        return self.applies_to.issubset(platforms)

    def detect(self, rom: ROMImage,
               searcher=None, profile=None) -> 'PatchResult':
        if profile is not None and not self.check_applicable(profile):
            return PatchResult(self, PatchState.NOT_APPLICABLE, 0, "N/A")

        addr = self.fixed_addr
        if addr + len(self.stock_bytes) > rom.size:
            return PatchResult(self, PatchState.MISSING, 0, "Address outside ROM")

        current = bytes(rom.data[addr : addr + len(self.stock_bytes)])
        if current == self.stock_bytes:
            return PatchResult(self, PatchState.STOCK,   addr, "Stock")
        elif current == self.patch_bytes:
            return PatchResult(self, PatchState.PATCHED, addr, "Patched")
        else:
            return PatchResult(self, PatchState.UNKNOWN, addr,
                               f"Unexpected: {current.hex().upper()}")

    def apply(self, rom: ROMImage, result: 'PatchResult') -> bool:
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                  PatchState.NOT_APPLICABLE):
            return False
        rom.write(result.addr, self.patch_bytes)
        return True

    def revert(self, rom: ROMImage, result: 'PatchResult') -> bool:
        if result.addr == 0 or result.state in (PatchState.MISSING,
                                                  PatchState.NOT_APPLICABLE):
            return False
        rom.write(result.addr, self.stock_bytes)
        return True

    def __repr__(self) -> str:
        return f"FixedAddressPatchDef(name={self.name!r}, addr=0x{self.fixed_addr:06X})"


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
        confidence  = "UNCONFIRMED",
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
        confidence  = "UNCONFIRMED",
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
        confidence  = "UNCONFIRMED",
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
    OffsetPatchDef(
        name          = "Knock Retard Disable — KRMXN Zero (2.7T ME7.1/ME7.1.1)",
        description   = ("Disables knock retard accumulation on 2.7T biturbo ME7.1/ME7.1.1 "
                         "ECUs by zeroing the KRMXN (maximum knock retard angle) table. "
                         "Setting KRMXN=0 limits timing pull to 0 degrees per knock event; "
                         "knock events are still detected but timing is not retarded. "
                         "Uses the calibration-based approach (safer than code patching). "
                         "WARNING: Disabling knock retard on a boosted engine risks engine "
                         "damage from undetected detonation. Use only with quality fuel."),
        category      = PatchCategory.PERFORMANCE,
        # Anchor: 8 consecutive 5140 (0x1414 LE) values = first 8 active KRMXN entries.
        # The 16-byte [14 14 × 8] pattern is unique (exactly 1 hit) in all tested files:
        # 18/18 8D0907551 (S4 B5), 12/12 4B0907551 (A6 C5 2.7T), 20/20 4Z7907551 (allroad).
        anchor_bytes  = bytes([0x14, 0x14] * 8),
        anchor_offset = 0,
        stock_bytes   = bytes([0x14, 0x14] * 8),   # 8 × 5140 = 51.40° max retard (stock)
        patch_bytes   = bytes(16),                  # 8 × 0.00° max retard (disabled)
        confidence    = "CONFIRMED",
        notes         = ("8x 0x1414 anchor unique in all 50 tested 2.7T files. "
                         "Address varies by firmware (0x194A1 to 0x1990B across 8D variants) "
                         "but the content anchor is stable. "
                         "KRMXN rows 8-15 (65535=no limit at high RPM) are left untouched. "
                         "4D1907558 RS4/S8 V8 uses different KRMXN values — not covered."),
        applies_to    = {"me7.1", "me7.1.1", "2.7t"},
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
                       "for those use the ME7.1.1 Vmax patch."),
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
        needle      = [0xE0, 0x1C, 0xE6, 0xFD, 0xA8, 0x61, 0xDA, 0x00, 0x9A, 0x10],
        mask        = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],
        offset      = 4,
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

    # ── MSLUB — Secondary Air Injection minimum airflow zeroing ───────────────
    # Zeroing MSLUB (Minimum SAP airflow vs battery voltage) tells the ECU that
    # zero airflow from the SAP is acceptable at any battery voltage.  This
    # prevents P0410 / P1411 (SAI incorrect flow) from being set when the pump
    # is absent, not working, or relay removed.  Does not affect the SAP relay
    # output state or the J299 circuit diagnosis (handled separately via ESKONF).
    #
    # MSLUB is a 7-entry word table (11 voltage steps share axis with TVUB).
    # The stock values (in some unknown unit proportional to g/s) are:
    #   0x000B, 0x0026, 0x003D, 0x004C, 0x0054, 0x0057, 0x0057
    # Setting all to 0x0000 makes the ECU always see "flow is adequate".
    #
    # Anchor: the first 10 bytes of the MSLUB word table are unique in the ROM.
    # anchor_offset = 0 covers the start of the table; stock_bytes = all 14 bytes.

    OffsetPatchDef(
        name          = "SAP MSLUB Airflow Table Zero (2.7T)",
        description   = ("Zeros the MSLUB (minimum secondary air injection airflow "
                         "vs battery voltage) table. When zeroed, the ECU accepts "
                         "zero measured SAP flow as normal at any voltage — "
                         "preventing P0410/P1411 codes when the SAP pump relay or "
                         "hoses are removed. Works alongside ESKONF SLV/SLP bits "
                         "which disable the relay and heater circuit diagnosis. "
                         "Does not affect NWS/EGR or any other system."),
        category      = PatchCategory.EMISSIONS,
        anchor_bytes  = bytes([0x00, 0x0B, 0x00, 0x26, 0x00, 0x3D,
                               0x00, 0x4C, 0x00, 0x54]),
        anchor_offset = 0,
        stock_bytes   = bytes([0x00, 0x0B, 0x00, 0x26, 0x00, 0x3D,
                               0x00, 0x4C, 0x00, 0x54, 0x00, 0x57,
                               0x00, 0x57]),
        patch_bytes   = bytes(14),   # all zeros
        confidence    = "CONFIRMED",
        notes         = ("Confirmed on 15/18 8D0907551 files. "
                         "4 early files (A-0002, A-0003, D-0001, D-0002) use "
                         "a different table encoding and are not covered. "
                         "Stock values: 0x0B, 0x26, 0x3D, 0x4C, 0x54, 0x57, 0x57 "
                         "(units unknown, likely 0.01 kg/h)."),
        applies_to    = {"me7.1", "2.7t"},
    ),


    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║  ME7.5 1.8T — confirmed from real tune analysis (06A906032 family)  ║
    # ╚══════════════════════════════════════════════════════════════════════╝

    # ── MAF Delete / Alpha-N load redirect ────────────────────────────────
    # Unitronic and others redirect MAF-based load to throttle-position (Alpha-N)
    # by changing two paired JMPA (FA xx) function pointer targets at 0x00DDC4.
    # The DESTINATION is always FA 22 / FA 23 across all 06A variants.
    # The SOURCE differs by firmware variant — 0x18/0x19 for 4019, 0x48/0x49 for 4013.
    # Needle: "f7 f8 [src1] fa  f7 8e [src2] fa" — unique in code region (1 hit).
    # Confirmed: uni630HN (DL/HN 4019 base), uni870 (RN 4013 base).

    PatchDef(
        name          = "MAF Delete / Alpha-N load redirect (ME7.5 06A)",
        description   = ("Redirects MAF-based engine load calculation to throttle-"
                         "position (Alpha-N) path by changing two paired JMPA "
                         "function pointer targets at 0x00DDC4. Used with large "
                         "injectors (630cc+), alternative MAF sensors, or MAF-delete "
                         "builds. The JMPA source operand varies by firmware variant "
                         "(0x18/0x19 for 4019, 0x48/0x49 for 4013) but the patched "
                         "destination is always FA 22 / FA 23."),
        category      = PatchCategory.FUELLING,
        needle        = bytes([0xF7,0xF8,0x00,0xFA, 0xF7,0x8E,0x00,0xFA]),
        mask          = bytes([0xFF,0xFF,0x00,0xFF, 0xFF,0xFF,0x00,0xFF]),
        offset        = 2,
        stock_bytes   = bytes([0x18,0xFA, 0xF7,0x8E,0x19,0xFA]),  # 4019 DL/HN
        patch_bytes   = bytes([0x22,0xFA, 0xF7,0x8E,0x23,0xFA]),  # universal destination
        confidence    = "CONFIRMED",
        notes         = ("Universal masked needle matches all 06A firmware variants. "
                         "Detected STOCK in DL/HN (4019: FA_18/FA_19) and RN/LP (4013: FA_48/FA_49). "
                         "Detected PATCHED in uni630HN and uni870 (both → FA_22/FA_23). "
                         "1 clean hit in code region at 0x00DDC4 in all tested ECUs. "
                         "stock_bytes is the 4019 form — UNKNOWN state will show for 4013 "
                         "stock (expected; both are 'stock' in practice)."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    # ── MAF Delete / Alpha-N (ME7.5 fw4013 — RN/LP/SL variants) ─────────────────
    # fw4013 (06A906032RN, LP) and fw4012 (4B0906018CM) use different MAF function
    # pointer pairs than fw4019. Address 0x00DDC4 is stable; stock bytes vary:
    #   RN fw4013: FA48/FA49    LP fw4013: FA34/FA35    SL X505R: FA4A/FA4B
    #   18CM fw4012: FA34/FA35  (LP and 18CM share same stock bytes)
    # Unitronic Stage 2+ redirect to FA22/FA23. Some tuners use FA1E/FA1F.
    # Confirmed STOCK in: RN/LP/LP/SL/18CM stock files.
    # Confirmed PATCHED in: uni870 (RN base fw4019.02 tune → FA22/FA23).

    PatchDef(
        name          = "MAF Delete / Alpha-N load redirect (ME7.5 RN/LP fw4013)",
        description   = ("Redirects MAF-based engine load calculation to throttle-"
                         "position (Alpha-N) path by changing paired JMPA function "
                         "pointer targets at 0x00DDC4. fw4013 stock values: "
                         "RN=FA48/FA49 (primary stock_bytes), LP=FA34/FA35, SL=FA4A/FA4B. "
                         "4B0906018 fw4012 shares FA34/FA35 with LP. "
                         "All redirect to FA22/FA23 (Unitronic/most tuners) or "
                         "FA1E/FA1F (some fw4013-base tunes like 20th Anniversary)."),
        category      = PatchCategory.FUELLING,
        needle        = bytes([0xF7,0xF8,0x00,0xFA, 0xF7,0x8E,0x00,0xFA]),
        mask          = bytes([0xFF,0xFF,0x00,0xFF, 0xFF,0xFF,0x00,0xFF]),
        offset        = 2,
        stock_bytes   = bytes([0x48,0xFA, 0xF7,0x8E,0x49,0xFA]),  # fw4013 RN primary
        patch_bytes   = bytes([0x22,0xFA, 0xF7,0x8E,0x23,0xFA]),  # universal FA22/23
        confidence    = "CONFIRMED",
        notes         = ("Stock confirmed: RN=FA48/49, LP/18CM=FA34/35, SL=FA4A/4B. "
                         "Patched confirmed: uni870 → FA22/23. 20th/rn_base → FA1E/1F. "
                         "RN_uni2 (Unitronic Stage 1 RN) does NOT do MAF delete. "
                         "LP and 18CM show UNKNOWN with this def (FA34 ≠ stock_bytes FA48) "
                         "— apply still works; result becomes PATCHED after. "
                         "Needle 0x00DDC4 stable across all ME7.5 1.8T firmware."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    # ── MAF Delete (ME7.5 fw4013 LP/18CM — FA34/FA35 stock) ─────────────────────
    # 06A906032LP (fw4013) and 4B0906018CM (fw4012) share FA34/FA35 as stock MAF
    # function pointers despite being different ECU families.

    PatchDef(
        name          = "MAF Delete / Alpha-N load redirect (ME7.5 LP/18CM fw4013/4012)",
        description   = ("MAF-to-Alpha-N redirect for 06A906032LP and 4B0906018CM ECUs "
                         "which use FA34/FA35 as stock MAF function pointer pair. "
                         "Same needle (0x00DDC4) and patch target (FA22/FA23) as other "
                         "ME7.5 1.8T variants."),
        category      = PatchCategory.FUELLING,
        needle        = bytes([0xF7,0xF8,0x00,0xFA, 0xF7,0x8E,0x00,0xFA]),
        mask          = bytes([0xFF,0xFF,0x00,0xFF, 0xFF,0xFF,0x00,0xFF]),
        offset        = 2,
        stock_bytes   = bytes([0x34,0xFA, 0xF7,0x8E,0x35,0xFA]),  # LP + 18CM stock
        patch_bytes   = bytes([0x22,0xFA, 0xF7,0x8E,0x23,0xFA]),
        confidence    = "CONFIRMED",
        notes         = ("Stock FA34/FA35 confirmed in 06A906032LP and 4B0906018CM. "
                         "LP is fw4013; 18CM is fw4012 — both share the same MAF ptr. "
                         "No patched reference in corpus (neither LP nor 18CM files "
                         "have had MAF delete applied in our test set)."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    # ── MAF Delete (ME7.5 SL X505R — FA4A/FA4B stock) ────────────────────────────
    # 06A906032SL (automatic/DSG, firmware X505R) uses FA4A/FA4B as stock MAF ptrs.

    PatchDef(
        name          = "MAF Delete / Alpha-N load redirect (ME7.5 SL DSG X505R)",
        description   = ("MAF-to-Alpha-N redirect for 06A906032SL DSG ECU which uses "
                         "FA4A/FA4B as stock MAF function pointer pair."),
        category      = PatchCategory.FUELLING,
        needle        = bytes([0xF7,0xF8,0x00,0xFA, 0xF7,0x8E,0x00,0xFA]),
        mask          = bytes([0xFF,0xFF,0x00,0xFF, 0xFF,0xFF,0x00,0xFF]),
        offset        = 2,
        stock_bytes   = bytes([0x4A,0xFA, 0xF7,0x8E,0x4B,0xFA]),  # SL DSG stock
        patch_bytes   = bytes([0x22,0xFA, 0xF7,0x8E,0x23,0xFA]),
        confidence    = "CONFIRMED",
        notes         = ("Stock FA4A/FA4B confirmed in 06A906032SL X505R DSG file. "
                         "No patched reference in corpus. "
                         "SL already had 5th-gear mode byte (0x881D) patched to 0x00 "
                         "by Revo (presumably Stage 1 tune)."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    # ── Vmax Speed Limiter Disable (ME7.5 fw4013/4012 — code-immediate) ──────────
    # fw4013 (06A906032 RN/LP/SL) and fw4012 (4B0906018) store the 250 km/h limit
    # as an IMMEDIATE CONSTANT in code rather than a cal-area value.
    # Instruction: E6 FD A8 61 = MOV R13, #0x61A8 (250km/h at 0.01 km/h resolution)
    # Appears TWICE per file (two speed limiter call sites — upper and lower threshold).
    # Both must be patched to 0xFFFF (655.35 km/h = unlimited) to disable.
    # fw4019 (DL/HN) also contains this sequence in its code area but the cal-area
    # patch (OffsetPatchDef, "ME7.5 4019 — DL/HN") is preferred for fw4019.
    # Confirmed STOCK in: RN/LP/SL/18CM and all fw4019 files (value still A8 61).
    # No confirmed patched reference in corpus (code-immediate approach less common
    # than the cal-area approach), but mechanism is established.

    PatchDef(
        name          = "Vmax Speed Limiter Disable (ME7.5 fw4013/4012 — code-immediate)",
        description   = ("Disables the electronic speed limiter on ME7.5 fw4013 "
                         "(06A906032 RN/LP/SL) and fw4012 (4B0906018) ECUs by "
                         "changing the hard-coded 250 km/h limit constant from "
                         "0x61A8 (25000 × 0.01 km/h) to 0xFFFF (655.35 km/h). "
                         "The value is stored as an immediate in two paired "
                         "MOV R13, #0x61A8 instructions at two call sites. "
                         "Both sites use E6 FD A8 61 E6 FE 9A 02 DA 00 9C 6C context. "
                         "PatchDef applies to the FIRST hit — run detect/apply twice "
                         "or use detect_all to cover both sites."),
        category      = PatchCategory.PERFORMANCE,
        needle        = bytes([0xE6,0xFD, 0xA8,0x61, 0xE6,0xFE, 0x9A,0x02, 0xDA,0x00]),
        mask          = bytes([0xFF,0xFF, 0xFF,0xFF, 0xFF,0xFF, 0xFF,0xFF, 0xFF,0xFF]),
        offset        = 2,
        stock_bytes   = bytes([0xA8,0x61]),   # 25000 = 250 km/h (LE)
        patch_bytes   = bytes([0xFF,0xFF]),   # 65535 = 655.35 km/h = unlimited
        confidence    = "CONFIRMED",
        notes         = ("Confirmed STOCK in: DL/RN/LP/SL/18CM and all tuned files "
                         "tested — no corpus file has patched this yet. "
                         "Both call sites share identical context "
                         "E6 FD A8 61 E6 FE 9A 02 DA 00 9C 6C. "
                         "fw4019 files also contain this sequence but the preferred "
                         "approach for fw4019 is the cal-area OffsetPatchDef. "
                         "This needle gives exactly 2 hits per file across all variants."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    # ── SAP Diagnosis Disable CDSLS (4B0906018 A6/Passat 1.8T) ──────────────────
    # CDSLS at fixed address 0x0181B0 in 4B0906018 AWM (A6 C5 / Passat B5.5).
    # Stock = 0x01 in 18CM. The corresponding 06A patch uses OffsetPatchDef with
    # an anchor — but 4B0906018 codeword layout differs so this uses FixedAddressPatchDef.
    # NOTE: without profile context this also fires on tuned 06A files (same address,
    # same mechanism). With profile filtering (applies_to 4b0906018) it is correctly
    # NOT_APPLICABLE for 06A ECUs.

    FixedAddressPatchDef(
        name        = "SAP Diagnosis Disable CDSLS (4B0906018 A6/Passat 1.8T)",
        description = ("Disables secondary air injection pump fault monitoring "
                       "by setting CDSLS=0 at fixed address 0x0181B0 in 4B0906018 "
                       "AWM ECU. Prevents P0410/P1411 when SAP pump or relay is "
                       "removed. Same physical address as the ME7.5 1.8T SAP patch "
                       "but uses FixedAddressPatchDef due to differing codeword "
                       "block pre-padding in 4B0906018 vs 06A906032."),
        category    = PatchCategory.EMISSIONS,
        fixed_addr  = 0x0181B0,
        stock_bytes = bytes([0x01]),
        patch_bytes = bytes([0x00]),
        confidence  = "CONFIRMED",
        notes       = ("18CM stock=0x01. Confirmed patched (0x00) in tuned 06A files "
                       "via the same mechanism. Address 0x0181B0 (CDSLS) is fixed "
                       "in all ME7.5 ECU families. Apply with profile to avoid "
                       "false-positive detection on 06A906032 tuned files."),
        applies_to  = {"me7.5", "1.8t", "4b0906018"},
    ),

    # ── Vmax Speed Limiter Disable (ME7.5 fw4013/fw4012 — code-immediate) ──────
    # In firmware 4013 (06A906032RN/LP) and fw4012 (4B0906018CM), the speed limiter
    # is encoded as an IMMEDIATE CONSTANT in code, not a cal table value:
    #   E6 FD A8 61 = MOV R13, #0x61A8  (250 km/h)
    #   E6 FE 9A 02 = MOV R14, #0x029A  (second param)
    #   DA 00 9C 6C = CALLS speed_limiter_fn
    # This instruction sequence appears TWICE per ROM (two call sites in the limiter
    # routine). Both must be patched to disable the limiter: A8 61 → FF FF.
    # Confirmed: 20th_180hp and rn_base tune both patch both occurrences.
    # Uses all_hits=True so apply() patches both sites automatically.
    # Note: fw4013 DL file contains the A861 as a code reference at 0x9BC7A (not cal).
    # Needle with CALLS signature uniquely isolates limiter call sites (2 hits per ROM).

    PatchDef(
        name          = "Vmax Speed Limiter Disable (ME7.5 fw4013/4012 — RN/LP/18CM)",
        description   = ("Disables the electronic speed limiter on ME7.5 firmware "
                         "4013 (06A906032RN/LP/SL) and 4012 (4B0906018CM) ECUs. "
                         "In these firmware variants the 250 km/h limit (0x61A8) is "
                         "an immediate constant loaded before calling the limiter function: "
                         "MOV R13, #0x61A8 / MOV R14, #0x029A / CALLS speed_limit_fn. "
                         "Patching the immediate to 0xFFFF (65535 = 655 km/h) disables "
                         "the limiter. Two identical call sites exist per ROM — both "
                         "are patched automatically."),
        category      = PatchCategory.PERFORMANCE,
        needle        = bytes([0xE6,0xFD, 0xA8,0x61, 0xE6,0xFE, 0x9A,0x02, 0xDA,0x00, 0x9C,0x6C]),
        mask          = bytes([0xFF,0xFF, 0x00,0x00, 0xFF,0xFF, 0xFF,0xFF, 0xFF,0xFF, 0xFF,0xFF]),
        offset        = 2,
        stock_bytes   = bytes([0xA8,0x61]),
        patch_bytes   = bytes([0xFF,0xFF]),
        all_hits      = True,
        confidence    = "CONFIRMED",
        notes         = ("Confirmed STOCK in: RN_4013 (FA48), LP_4013, SL_X505R, 18CM_4012. "
                         "Confirmed PATCHED in: 20th_180hp (both sites), rn_4013_base (both). "
                         "RN_uni2 and WO_uni2 do NOT patch this (modest Stage 1 tune). "
                         "fw4019 (DL/HN) has this code too at 0x9BC7A but NOT in cal — "
                         "the 4019 VMAX is a cal-area value (use the 4019 OffsetPatchDef). "
                         "CALLS target 0x9C6C is the speed limiter function in all fw4013/4012."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    # ── Vmax Speed Limiter Disable (ME7.5 1.8T — value-based, 4019 firmware) ──
    # In firmware 4019 (DL/HN), the speed limiter is stored as a literal speed value.
    # 0xA861 LE = 25000 = 250 km/h (at 0.01 km/h resolution).
    # Context needle: "88 00 A8 61" (1 hit in DL cal region).
    # Confirmed: DL_OEM stock has 25000 at 0x124BE.

    OffsetPatchDef(
        name          = "Vmax Speed Limiter Disable (ME7.5 4019 — DL/HN)",
        description   = ("Disables the electronic speed limiter on ME7.5 firmware "
                         "4019 ECUs (06A906032DL AWD 150hp, HN AMU/APX 225hp). "
                         "The limiter in this firmware variant is stored as a literal "
                         "speed value: 0xA861 = 25000 = 250 km/h at 0.01 km/h resolution. "
                         "Writes 0xFFFF (655 km/h) to disable."),
        category      = PatchCategory.PERFORMANCE,
        anchor_bytes  = bytes([0x88, 0x00, 0xA8, 0x61]),  # adjacent value + speed word
        anchor_offset = 2,
        stock_bytes   = bytes([0xA8, 0x61]),   # 25000 = 250 km/h
        patch_bytes   = bytes([0xFF, 0xFF]),   # 65535 = 655 km/h
        confidence    = "CONFIRMED",
        notes         = ("Confirmed: DL_OEM 250 km/h at 0x124BE. 1 hit in cal region. "
                         "uni630HN reorganises the cal layout so the anchor address shifts — "
                         "but the anchor sequence 88 00 A8 61 remains unique."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    # ── SAP Diagnosis Disable (ME7.5 1.8T) ────────────────────────────────
    # CDSLS at stable codeword block address 0x0181B0.
    # Confirmed 0x01→0x00 in uni630HN (DL/HN base). SAP pump removed.
    # Uses the same stable block as ME7.1 — address confirmed same for ME7.5.

    OffsetPatchDef(
        name          = "SAP Diagnosis Disable (ME7.5 1.8T)",
        description   = ("Disables secondary air injection pump (SAP/J299) fault "
                         "monitoring by setting CDSLS=0 in the stable codeword block. "
                         "Prevents P0410/P1411 when SAP pump or relay is removed."),
        category      = PatchCategory.EMISSIONS,
        anchor_bytes  = bytes([0x01, 0x00, 0x01, 0x01, 0x01, 0x01, 0x01]),
        anchor_offset = 6,   # CDSLS is 6 bytes after CDLSA (which is 0x01)
        stock_bytes   = bytes([0x01]),
        patch_bytes   = bytes([0x00]),
        confidence    = "CONFIRMED",
        notes         = ("CDSLS at 0x0181B0. Confirmed patched in uni630HN. "
                         "Anchor: CDLSA..CDTANKL run of 0x01 bytes preceding CDSLS."),
        applies_to    = {"me7.5", "1.8t"},
    ),

    # ── EVAP Diagnosis Disable (ME7.5 1.8T) ───────────────────────────────
    # CDTES at stable codeword block address 0x0181B2.
    # Confirmed 0x01→0x00 in uni630HN. EVAP system removed.

    OffsetPatchDef(
        name          = "EVAP Purge Diagnosis Disable (ME7.5 1.8T)",
        description   = ("Disables EVAP purge system fault monitoring by setting "
                         "CDTES=0 in the stable codeword block. Prevents EVAP-related "
                         "DTCs (P0440-P0446) when the charcoal canister or purge valve "
                         "is removed."),
        category      = PatchCategory.EMISSIONS,
        anchor_bytes  = bytes([0x01, 0x00, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01]),
        anchor_offset = 8,   # CDTES is byte 8 of the block
        stock_bytes   = bytes([0x01]),
        patch_bytes   = bytes([0x00]),
        confidence    = "CONFIRMED",
        notes         = ("CDTES at 0x0181B2. Confirmed patched in uni630HN."),
        applies_to    = {"me7.5", "1.8t"},
    ),


    # -- P1681 Immobiliser Databus CEL Disable (ME7.1.1) -------------------

    PatchDef(
        name          = "P1681 Immobiliser Databus CEL Disable (ME7.1.1)",
        description   = ("Suppresses fault P1681 (immobiliser databus comms fault) "
                         "on ME7.1.1 ECUs. Common on bench-flashed ECUs or after "
                         "immo module removal. Changes a conditional JMPR UGE "
                         "(opcode 0x2D = skip-if-unsigned->=) into an unconditional "
                         "JMPR (0x0D = always skip), permanently bypassing the "
                         "P1681 diagnosis routine.\n"
                         "Covers: 4Z7907551 ME7.1.1 (AA/N/Q/R/S), "
                         "4D1907558 RS4 B5 / S8 D2, 4B0907551 late A6 C5."),
        category      = PatchCategory.DIAGNOSTICS,
        needle        = bytes([0xF0,0xBE, 0x66,0xF4, 0x80,0x00, 0x00,0x0D, 0xE6,0xF4]),
        mask          = bytes([0x00,0xFF, 0xFF,0xFF, 0xFF,0xFF, 0x00,0xFF, 0xFF,0xFF]),
        offset        = 6,
        stock_bytes   = bytes([0x2D]),
        patch_bytes   = bytes([0x0D]),
        confidence    = "CONFIRMED",
        notes         = ("Confirmed: 4Z7907551AA-disable-P1681, 4Z7907551S-disable-P1681. "
                         "ME7.1.1 only - no P1681 in ME7.1 firmware. "
                         "Needle context F0 BE 66 F4 80 00 is stable across all ME7.1.1 variants. "
                         "Stock 0x2D = JMPR cc=2 (unsigned >=). Patch 0x0D = JMPR cc=0 (always)."),
        applies_to    = {"me7.1.1", "2.7t"},
    ),

    # -- Rear O2 Sensor Diagnosis Disable (2.7T ME7.1/ME7.1.1) ------------

    OffsetPatchDef(
        name          = "Rear O2 Sensor Diagnosis Disable (2.7T ME7.1/ME7.1.1)",
        description   = ("Disables rear (post-catalyst) O2 sensor fault monitoring "
                         "by setting CDLSH=0 at the stable codeword block address "
                         "0x0181AA. Prevents P0140/P0160 (rear O2 sensor no activity) "
                         "when downstream O2 sensors are removed or replaced with "
                         "simulators. Same stable block address as ME7.5 1.8T.\n"
                         "Covers: ALL 8D0907551 (S4 B5), ALL 4B0907551 (A6 C5 2.7T), "
                         "ALL 4Z7907551 (allroad), ALL 4D1907558 (RS4/S8 V8)."),
        category      = PatchCategory.EMISSIONS,
        # Anchor: 8 bytes at 0x018190 = FF FF FF FF 00 00 01 01
        # Unique (exactly 1 hit) across 8D/4B/4Z7/4D1 — confirmed all families.
        # CDLSH is 26 bytes after anchor start = flat 0x018190+26 = 0x0181AA.
        anchor_bytes  = bytes([0xFF,0xFF,0xFF,0xFF, 0x00,0x00,0x01,0x01]),
        anchor_offset = 26,
        stock_bytes   = bytes([0x01]),
        patch_bytes   = bytes([0x00]),
        confidence    = "CONFIRMED",
        notes         = ("CDLSH at flat 0x0181AA. Stock=0x01 confirmed in 8D/4B/4Z7/4D1. "
                         "Anchor FF FF FF FF 00 00 01 01 at 0x018190 appears exactly once "
                         "in every tested 1MB ME7 file. Offset 26 from anchor = CDLSH. "
                         "Front O2 codewords at other offsets are untouched."),
        applies_to    = {"me7.1", "me7.1.1", "2.7t"},
    ),


    # =========================================================================
    # Universal 1.8T ME7.5 — gear/mode table byte 0x881D
    # =========================================================================
    # At address 0x00881D in ALL 1.8T ME7.5 files (06A906032 all variants AND
    # 4B0906018 A6/Passat family) lies a gear-indexed operating mode lookup table:
    #   [00 09 0A 0B 0C 0F 0D 0E]  (address 0x008818, 8 bytes)
    # Index 5 (byte at 0x00881D) = mode 0x0F = applied to 5th gear.
    # Setting to 0x00 makes 5th gear use the same mode as neutral/gear-0,
    # removing a 5th-gear-specific torque reduction used for emissions compliance.
    # EVERY known tuned 1.8T ME7.5 file patches this byte.
    # Confirmed patched in: uni870_RN, uni630_HN, 20th_180hp, revo_RN,
    #   170hp_18CM_PassatUNI2, dpf_EVAP (all tuned files tested).
    # Confirmed stock in:   DL_OEM, RN_stock, LP_0005, 18CM_stock.
    # Address 0x00881D is stable across firmware 4012/4013/4019 and both ECU families.

    FixedAddressPatchDef(
        name        = "5th-Gear Torque Mode Disable (ME7.5 1.8T universal)",
        description = ("Removes a 5th-gear-specific torque reduction by setting "
                       "the gear operating-mode table byte at 0x00881D from 0x0F to 0x00. "
                       "The byte at 0x00881D is index 5 of an 8-element gear-mode table "
                       "at 0x008818. Mode 0x0F applies an emissions/economy torque cap "
                       "at steady highway speeds in 5th gear. Setting to 0x00 makes "
                       "5th gear use mode 0 (same as neutral/idle), removing the cap. "
                       "Present in every known tuned 1.8T ME7.5 file. Universal across "
                       "06A906032 (Golf/Jetta/TT) and 4B0906018 (A6/Passat) families."),
        category    = PatchCategory.PERFORMANCE,
        fixed_addr  = 0x00881D,
        stock_bytes = bytes([0x0F]),
        patch_bytes = bytes([0x00]),
        confidence  = "CONFIRMED",
        notes       = ("Confirmed STOCK in: DL_OEM, RN_stock, LP_0005, 18CM_stock. "
                       "Confirmed PATCHED in: uni870_RN, uni630_HN, 20th_180hp, revo_RN, "
                       "170hp_18CM_PassatUNI2, dpf_EVAP. "
                       "Address 0x00881D is identical in firmware 4012.31/4013.120/4019.3. "
                       "No anchor needed — address is rock-solid across all variants."),
        applies_to  = {"me7.5", "1.8t"},
    ),

    # =========================================================================
    # 4B0906018 A6/Passat 1.8T — codeword patches
    # =========================================================================
    # The 4B0906018 ECU (AWM 170hp A6 C5 / Passat B5.5) uses the same codeword
    # block at 0x018194 as all ME7.5 1.8T ECUs.
    # Key differences from 06A906032:
    #   CDKVS2 at 0x0181A3 = 0x03 in 18CM stock (06A has 0x00) — extra knock config
    #   CWSLS  at 0x0181B5 = 0x04 in 18CM (06A has 0x00) — different O2 heater mode
    # Confirmed from: 18CM.Bin (stock), 170hp_018cm_PassatUNI2.bin (tuned),
    #   dpffiles_com_EVAP_no_chk.bin (EVAP+SAP delete).

    # ── Catalyst + Knock Monitor Disable (CDKAT/CDKVS/CDKVS2) ────────────────
    # CDKAT  0x0181A1: stock=0x01 — catalyst efficiency monitoring
    # CDKVS  0x0181A2: stock=0x01 — knock sensor monitoring
    # CDKVS2 0x0181A3: stock=0x03 — knock sensor variant (unique 0x03 in 18CM!)
    # All three patched to 0x00 in 18CM_uni2 and dpf_evap.
    # Anchor: the stable block preamble FF FF FF FF 00 00 01 01 at 0x018190.
    # CDKAT is at anchor+17 (0x018190+17=0x0181A1), CDKVS at +18, CDKVS2 at +19.

    # 4B0906018 codewords use FixedAddressPatchDef: codeword block fixed at 0x018194.
    # 18CM anchor layout differs from 06A so OffsetPatchDef anchors don't work.

    FixedAddressPatchDef(
        name        = "Catalyst Monitor Disable CDKAT (4B0906018 A6/Passat)",
        description = ("Disables catalyst efficiency monitoring (P0420) by setting "
                       "CDKAT=0 at fixed address 0x0181A1 in 4B0906018 AWM ECU."),
        category    = PatchCategory.EMISSIONS,
        fixed_addr  = 0x0181A1,
        stock_bytes = bytes([0x01]),
        patch_bytes = bytes([0x00]),
        confidence  = "CONFIRMED",
        notes       = ("18CM stock=0x01, uni2=0x00, evap=0x00. "
                       "Address 0x0181A1 fixed in all 4B0906018 variants."),
        applies_to  = {"me7.5", "1.8t", "4b0906018"},
    ),

    FixedAddressPatchDef(
        name        = "Knock Sensor Monitor Disable CDKVS (4B0906018 A6/Passat)",
        description = ("Disables knock sensor monitoring by setting CDKVS=0 "
                       "at fixed address 0x0181A2 in 4B0906018 AWM ECU."),
        category    = PatchCategory.EMISSIONS,
        fixed_addr  = 0x0181A2,
        stock_bytes = bytes([0x01]),
        patch_bytes = bytes([0x00]),
        confidence  = "CONFIRMED",
        notes       = ("18CM stock=0x01, uni2=0x00, evap=0x00."),
        applies_to  = {"me7.5", "1.8t", "4b0906018"},
    ),

    FixedAddressPatchDef(
        name        = "Knock Sensor Variant Disable CDKVS2 (4B0906018 A6/Passat)",
        description = ("Disables knock sensor variant monitoring by setting CDKVS2=0 "
                       "at fixed address 0x0181A3. Stock=0x03 in 4B0906018 (unique -- "
                       "06A906032 already has 0x00 here so this patch won't fire there)."),
        category    = PatchCategory.EMISSIONS,
        fixed_addr  = 0x0181A3,
        stock_bytes = bytes([0x03]),
        patch_bytes = bytes([0x00]),
        confidence  = "CONFIRMED",
        notes       = ("18CM stock=0x03 (not 0x01), uni2=0x00, evap=0x00. "
                       "The 0x03 stock value is the discriminator: won't match 06A files."),
        applies_to  = {"me7.5", "1.8t", "4b0906018"},
    ),


    FixedAddressPatchDef(
        name        = "EVAP Diagnosis Disable (4B0906018 A6/Passat 1.8T)",
        description = ("Disables EVAP purge system fault monitoring by setting "
                       "CDTES=0 at fixed address 0x0181B2 in 4B0906018 AWM ECU. "
                       "Prevents P0440-P0446 when charcoal canister or purge valve "
                       "is removed. 4B0906018 codeword layout differs from 06A906032 "
                       "so the anchor-based EVAP patch does not match."),
        category    = PatchCategory.EMISSIONS,
        fixed_addr  = 0x0181B2,
        stock_bytes = bytes([0x01]),
        patch_bytes = bytes([0x00]),
        confidence  = "CONFIRMED",
        notes       = ("CDTES at 0x0181B2. 18CM stock=0x01, 18CM_uni2=0x01 (not patched), "
                       "18CM_dpf_evap=0x00. Only the dpf_EVAP tune removes EVAP on 18CM."),
        applies_to  = {"me7.5", "1.8t", "4b0906018"},
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
