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
from typing import Optional, Sequence

from .rom import ROMImage
from .needle import Searcher


# ── Enums ──────────────────────────────────────────────────────────────────────

class PatchState(Enum):
    STOCK   = auto()   # ROM contains stock bytes
    PATCHED = auto()   # ROM contains patch bytes
    UNKNOWN = auto()   # neither pattern matched
    MISSING = auto()   # needle not found in this ROM


class PatchCategory(Enum):
    EMISSIONS   = "Emissions"
    PERFORMANCE = "Performance"
    IMMOBILISER = "Immobiliser"
    COMFORT     = "Comfort"
    DIAGNOSTICS = "Diagnostics"
    # Aliases used in older code
    IMMO        = "Immobiliser"
    BOOST       = "Performance"
    SPEED       = "Performance"
    FUELLING    = "Performance"
    IGNITION    = "Performance"


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
    toggle.  offset is the byte offset from the needle hit start to the bytes
    that are modified (stock_bytes/patch_bytes start at needle_hit + offset).
    """
    name:        str
    description: str
    category:    PatchCategory | str
    needle:      Sequence[int]
    mask:        Sequence[int]
    offset:      int           # byte offset from needle hit to modifiable bytes
    stock_bytes: bytes
    patch_bytes: bytes
    warning:     str = ""
    confidence:  str = "UNCONFIRMED"
    notes:       str = ""

    def __post_init__(self):
        assert len(self.needle) == len(self.mask), \
            f"Patch '{self.name}': needle/mask length mismatch"
        assert len(self.stock_bytes) == len(self.patch_bytes), \
            f"Patch '{self.name}': stock/patch bytes length mismatch"

    def detect(self, rom: ROMImage,
               searcher: Optional[Searcher] = None) -> PatchResult:
        """Locate patch site and return current state."""
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
        if result.addr == 0 or result.state == PatchState.MISSING:
            return False
        rom.write(result.addr, self.patch_bytes)
        return True

    def revert(self, rom: ROMImage, result: PatchResult) -> bool:
        """Write stock_bytes at the discovered address."""
        if result.addr == 0 or result.state == PatchState.MISSING:
            return False
        rom.write(result.addr, self.stock_bytes)
        return True


# ── ScalarPatchDef ─────────────────────────────────────────────────────────────

@dataclass
class ScalarPatchDef:
    """
    A single numeric value that can be read and written at a needle-located site.

    Used for things like RPM limits, injector pulse widths, boost targets —
    values where you want to show the current number and let the user type a
    new one, rather than a simple stock/patched toggle.
    """
    name:       str
    description:str
    category:   PatchCategory | str
    needle:     Sequence[int]
    mask:       Sequence[int]
    offset:     int          # byte offset from needle hit to the value
    size:       int          # value size in bytes (1, 2, or 4)
    big_endian: bool  = True
    scale:      float = 1.0  # physical = raw * scale
    offset_val: float = 0.0  # physical = raw * scale + offset_val
    unit:       str   = ""
    min_val:    float = 0.0
    max_val:    float = 65535.0
    warning:    str   = ""
    confidence: str   = "UNCONFIRMED"
    notes:      str   = ""

    def _find_addr(self, rom: ROMImage,
                   searcher: Optional[Searcher] = None) -> int:
        """Return file offset of the value, 0 if needle not found."""
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
        """
        Write a physical value. Returns True on success.
        Rejects values outside [min_val, max_val].
        """
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


# ── C167 helper constants ──────────────────────────────────────────────────────
XX = 0x00   # wildcard in needle/mask
MM = 0xFF   # must-match


# ── Patch catalogue ────────────────────────────────────────────────────────────

ALL_PATCHES: list[PatchDef] = [

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
                       "P0141/P0140 when rear O2 is removed or a decat fitted. "
                       "Front O2 still controls closed-loop fuelling."),
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
        warning     = "Disables OBD-II rear O2 monitoring (P0140/P0141).",
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
        warning     = "Disables P0410/P0411.",
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
        warning     = "Disables P0400/P0401.",
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
               searcher: Optional[Searcher] = None) -> list[PatchResult]:
    """Run detection for every PatchDef and return results."""
    s = searcher or Searcher(rom)
    return [p.detect(rom, s) for p in ALL_PATCHES]
