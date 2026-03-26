"""
MESevenTool — Bosch ME7.x ROM editor and analysis tool.

Supports ME7.1, ME7.5, ME7.5.5 variants across the VAG 1.8T/2.0T platform.
Primary target: 06A-906-032 (AWP/AUM/AUQ/BAM/AVC families).
"""

from .version   import __version__
from .rom       import ROMImage, VALID_SIZES
from .needle    import Searcher, SearchHit, NEEDLE_DPP, MASK_DPP, XXXX, MASK
from .dpp       import (DPPValues, DPPInfo, DPPExtractor, SEGMENT_SIZE,
                        extract_dpp)
from .checksum  import (ChecksumManager, ChecksumChecker, ChecksumResult,
                        MainChecksumResult, MultiChecksumResult, MultiBlock,
                        calc_sum_block, calc_crc32, verify_and_fix,
                        _le16, _le32, CAL_CKSUM_OFFSET)
from .maps      import (MapDef, AxisDef, MapFinder, make_awp_maps,
                        AXIS_RPM, AXIS_LOAD, AXIS_IGN_DEG,
                        U8, U16, S8, S16,
                        _rpm, _deg, _pct, _lambda)
from .patches   import (PatchDef, PatchResult, PatchState, PatchCategory,
                        FixedAddressPatchDef, OffsetPatchDef,
                        ScalarPatchDef, MultiOffsetPatchDef,
                        ALL_PATCHES, detect_all)
from .profiles  import (ROMProfile, PROFILE_AWP, PROFILE_UNKNOWN,
                        ALL_PROFILES, PROFILES, detect_profile, get_profile)
from .known_roms import (KnownROM, KNOWN_ROMS, lookup_rom, is_known_stock)
from .ecu_id    import (ECUIdentity, identify, identify_from_filename,
                        _clean_string)

__all__ = [
    "__version__",
    # ROM
    "ROMImage", "VALID_SIZES",
    # Needle
    "Searcher", "SearchHit", "NEEDLE_DPP", "MASK_DPP", "XXXX", "MASK",
    # DPP
    "DPPValues", "DPPInfo", "DPPExtractor", "SEGMENT_SIZE", "extract_dpp",
    # Checksum
    "ChecksumManager", "ChecksumChecker", "ChecksumResult",
    "MainChecksumResult", "MultiChecksumResult", "MultiBlock",
    "calc_sum_block", "calc_crc32", "verify_and_fix",
    "_le16", "_le32", "CAL_CKSUM_OFFSET",
    # Maps
    "MapDef", "AxisDef", "MapFinder", "make_awp_maps",
    "AXIS_RPM", "AXIS_LOAD", "AXIS_IGN_DEG",
    "U8", "U16", "S8", "S16", "_rpm", "_deg", "_pct", "_lambda",
    # Patches
    "PatchDef", "PatchResult", "PatchState", "PatchCategory",
    "FixedAddressPatchDef", "OffsetPatchDef",
    "ScalarPatchDef", "MultiOffsetPatchDef",
    "ALL_PATCHES", "detect_all",
    # Known ROMs
    "KnownROM", "KNOWN_ROMS", "lookup_rom", "is_known_stock",
    # Profiles
    "ROMProfile", "PROFILE_AWP", "PROFILE_UNKNOWN",
    "ALL_PROFILES", "PROFILES", "detect_profile", "get_profile",
    # ECU ID
    "ECUIdentity", "identify", "identify_from_filename", "_clean_string",
    # XDF
    "XDFLoader", "XDFTable", "XDFAxis",
    # KWP
    "KWPMonitor", "LiveValues", "kwpbridge_available", "kwpbridge_running",
]
from .xdf import XDFLoader, XDFTable, XDFAxis
from .kwp import KWPMonitor, LiveValues, kwpbridge_available, kwpbridge_running

