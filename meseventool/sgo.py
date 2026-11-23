"""
meseventool/sgo.py
==================
SGO (SGML Object File) flash-image import for MESevenTool.

Decodes ODIS SGO flash containers for the older Bosch 16-bit engine families
into flat flash images that :class:`meseventool.rom.ROMImage` can load:

  ============  ==========================  ==========================================
  family        ECU                         container coding
  ============  ==========================  ==========================================
  motronic7     Bosch Motronic ME7.x        GEHEIM record coding   (descriptor fmt 0x11)
  edc15         Bosch EDC15 diesel          plain XOR-FF           (descriptor fmt 0x00)
  edc16-1m      Bosch EDC16 diesel, 1 MiB   32-bit LFSR            (descriptor fmt 0x01/0x03)
  edc16-2m      Bosch EDC16 diesel, 2 MiB   32-bit LFSR            (descriptor fmt 0x01/0x03)
  ============  ==========================  ==========================================

Provenance
----------
The record / LFSR / de-interleave primitives and the SGO container parser are a
faithful port of ``lsdlsd88/TCU-FRF-SGO-UNPACKER`` (MIT) — ``sgo_legacy.py`` and
``sgo_unpack.py`` — which are in turn verified against the original
``SGO Extract.exe`` (2013) with Unicorn, and derived from calledit's
``SGML_Object_File_reader``.  See ``THIRD_PARTY_NOTICES.md``.  The descramble
word ``GEHEIM`` is interoperability material already published in that MIT
project; it is not immobiliser, component-protection or signature material.

Flat vs. device layout
-----------------------
The byte *decoding* is identical to lsdlsd88; only image assembly is
MESevenTool-specific.  The readable ME7/EDC15 flash is a single chip of at most
1 MiB (see ``rom.py`` VALID_SIZES): blocks are placed at the flat address their
descriptor maps to and the image is sized to that native flash (256K/512K/1M),
matching MESevenTool's flat addressing (XDF offsets, needle search; ``rom.py``:
"file[0x000000] = C167 flash base") rather than lsdlsd88's fixed 2 MiB device
buffer.  Some ME7.1.1 SGOs carry extra record blocks mapped above 1 MiB
(check-start < 0xD0000 -> +0x100000) into a *second logical section* ODIS
programs but which is not the ROM that gets read, edited or flashed; those are
dropped and counted in ``ExtractResult.extra_blocks``.  Confirmed against real
1 MiB reference bins and ``ecu_id.identify``: the 1 MiB main bank alone carries
the part number, version and maps.  EDC16 is a genuine flash+MCU device and
keeps its full mapped image.

Auto-detection only resolves the record-coded families (here ``motronic7`` via
its GEHEIM key) and plain containers, mirroring lsdlsd88's ``legacy_probe``: the
XOR-FF + 1A 01 sync + keyed records self-validate against each block's declared
size.  EDC16's LFSR and EDC15's XOR-FF are length-preserving, so they cannot be
told apart from table-ciphered DSG or other plain containers by content — EDC16
must therefore be selected explicitly.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Union

from .rom import ROMImage

HEADER_MAGIC = b"SGML Object File\x00"
MAX_IMAGE = 0x2000000  # 32 MiB assembly guard (upstream MAX_IMAGE)

# family: (legacy mode, label, device size floor, applicable descriptor formats)
FAMILIES = {
    "motronic7": (0, "Bosch Motronic ME7.x", 0x200000, frozenset({0x11})),
    "edc15":     (1, "Bosch EDC15 diesel",   0x200000, frozenset({0x00})),
    "edc16-1m":  (2, "Bosch EDC16 (1 MiB)",  0x280000, frozenset({0x01, 0x03})),
    "edc16-2m":  (4, "Bosch EDC16 (2 MiB)",  0x280000, frozenset({0x01, 0x03})),
}
# Only record-coded families carry a key; EDC15/EDC16 are keyless (fixed LFSR
# seed / plain XOR-FF).  The key is the sole evidence that identifies a
# record-coded family during auto-detection.
KEYS = {"motronic7": b"GEHEIM"}


# ── SGML Object File container parser ───────────────────────────────────────
# Port of lsdlsd88/TCU-FRF-SGO-UNPACKER sgo_unpack.py (MIT).
#
# Layout (all u32 little-endian):
#   0x00  "SGML Object File\0"     (17 bytes)
#   0x11  u32 compat (=2)
#   0x15  u32 checksum
#   0x19  u32 indexIDENT
#   0x1d  u32 indexBaudrate2000
#   0x21  u32 indexKwp2000Rei
#   0x25  u32 indexKwp2000Acp
#   0x29  u32 indexKwp2000Sa2
#   0x2d  u32 indexDataBlocks   (-> [count][u32 descriptor offsets...])
#   IDENT: 260-byte XOR-FF filename; 5-byte version; u32
#   Descriptor (0x19 bytes) at each offset:
#     +0x00 3B id/start, +0x03 1B format, +0x04 3B size_after_decomp,
#     +0x07 3B erase_start, +0x0a 3B erase_end, +0x0d 3B check_start,
#     +0x10 3B check_end, +0x13 2B checksum, +0x15 u32 data_size
#     then data_size bytes of payload.
# Three-byte addresses/sizes are big-endian (as in the PHP reader).


def be24(b: bytes) -> int:
    return (b[0] << 16) | (b[1] << 8) | b[2]


def le24(b: bytes) -> int:
    return b[0] | (b[1] << 8) | (b[2] << 16)


def _xorff_str(b: bytes) -> str:
    out = []
    for c in b:
        if c == 0:
            break
        out.append(c ^ 0xFF)
    return bytes(out).decode("latin1")


class SGO:
    """A parsed SGML Object File. Pass a path, or raw ``data`` to parse in memory."""

    def __init__(self, path=None, data=None):
        self.path = Path(path) if path is not None else None
        self.data = self.path.read_bytes() if data is None else bytes(data)
        d = self.data
        if not d.startswith(HEADER_MAGIC):
            raise ValueError("not an SGML Object File")
        self.require(0, 0x31, "header")
        (
            self.compat,
            self.checksum,
            self.i_ident,
            self.i_baud,
            self.i_rei,
            self.i_acp,
            self.i_sa2,
            self.i_blocks,
        ) = struct.unpack_from("<8I", d, 0x11)
        if self.compat != 2:
            raise ValueError(f"unsupported SGO compatibility {self.compat}")
        self.name = ""
        self.version = ""
        self.blocks: List[dict] = []
        self.block_offsets: Tuple[int, ...] = ()

    def require(self, offset: int, size: int, label: str) -> None:
        if offset < 0 or size < 0 or offset + size > len(self.data):
            raise ValueError(
                f"truncated {label}: need {size:#x} bytes at {offset:#x}, "
                f"file size is {len(self.data):#x}"
            )

    def parse(self) -> "SGO":
        d = self.data
        self.require(self.i_ident, 269, "IDENT")
        self.name = _xorff_str(d[self.i_ident:self.i_ident + 260])
        vpos = self.i_ident + 260
        self.version = _xorff_str(d[vpos:vpos + 5])

        self.blocks = []
        self.require(self.i_blocks, 4, "block index count")
        nb = struct.unpack_from("<I", d, self.i_blocks)[0]
        self.require(self.i_blocks + 4, nb * 4, "block index")
        self.block_offsets = struct.unpack_from(f"<{nb}I", d, self.i_blocks + 4)
        for bo in self.block_offsets:
            self.require(bo, 0x19, "block descriptor")
            raw = d[bo:bo + 0x19]
            blk = {
                "raw": raw,
                "id_le": le24(raw[0:3]),
                "id_be": be24(raw[0:3]),
                "format": raw[3],
                "decomp_be": be24(raw[4:7]),
                "erase": (be24(raw[7:10]), be24(raw[10:13])),
                "check": (be24(raw[13:16]), be24(raw[16:19])),
                "cksum": raw[19:21].hex(),
                "dsize": struct.unpack_from("<I", raw, 0x15)[0],
            }
            self.require(bo + 0x19, blk["dsize"], "block payload")
            blk["data"] = d[bo + 0x19:bo + 0x19 + blk["dsize"]]
            self.blocks.append(blk)
        return self

    def summary(self) -> str:
        lines = [
            f"file: {self.path.name if self.path else '<memory>'} ({len(self.data)} bytes)",
            f"name={self.name!r} version={self.version!r} blocks={len(self.blocks)}",
        ]
        for i, b in enumerate(self.blocks):
            lines.append(
                f"  [{i}] id(be)={b['id_be']:#x} fmt=0x{b['format']:02x} "
                f"decomp={b['decomp_be']:#x} dsize={b['dsize']:#x}"
            )
        return "\n".join(lines)


def parse_sgo(path=None, data=None) -> SGO:
    """Parse an SGO from a path or from raw bytes."""
    return SGO(path, data=data).parse()


# ── Verified legacy decode primitives ───────────────────────────────────────
# Faithful port of lsdlsd88/TCU-FRF-SGO-UNPACKER sgo_legacy.py (MIT), itself
# verified against SGO Extract.exe (2013) with Unicorn.

_XOR_FF = bytes(i ^ 0xFF for i in range(256))


def bitrev32(value: int) -> int:
    """Reverse the bits within each byte, preserving byte positions (as the EXE)."""
    return int.from_bytes(
        bytes(int(f"{b:08b}"[::-1], 2) for b in value.to_bytes(4, "little")),
        "little",
    )


def lfsr_decode(data: bytes) -> bytes:
    """EDC16 32-bit LFSR stream (seed 0xB38BFCE7, taps 31/21/1/0)."""
    state = bitrev32(0xB38BFCE7)
    out = bytearray()
    for pos in range(0, len(data), 4):
        key = bitrev32(state).to_bytes(4, "big")
        out.extend(c ^ 0xFF ^ k for c, k in zip(data[pos:pos + 4], key))
        for _ in range(3):
            feedback = ((state >> 31) ^ (state >> 21) ^ (state >> 1) ^ state) & 1
            state = ((state << 1) | feedback) & 0xFFFFFFFF
    return bytes(out)


def _xor_bytes(data: bytes, data_start: int, mask: bytes, mask_start: int, count: int) -> bytes:
    """data[data_start:+count] XOR mask[mask_start:+count], at C speed."""
    return (
        int.from_bytes(data[data_start:data_start + count], "big")
        ^ int.from_bytes(mask[mask_start:mask_start + count], "big")
    ).to_bytes(count, "big")


def record_decode(data: bytes, key: bytes) -> bytes:
    """XOR-FF, then a 1A 01 sync followed by keyed BE16 literal / RLE records."""
    wire = bytes(data).translate(_XOR_FF)
    pos = wire.find(b"\x1a\x01")
    if pos < 0:
        raise ValueError("legacy record sync 1A 01 is missing; wrong family or damaged data")
    pos += 2
    mask = key * (len(wire) // len(key) + 3)
    plain = wire[:pos] + _xor_bytes(wire, pos, mask, 0, len(wire) - pos)
    out = bytearray()

    def take(count: int) -> bytes:
        nonlocal pos
        if pos + count > len(plain):
            raise ValueError("truncated legacy record")
        result = plain[pos:pos + count]
        pos += count
        return result

    while pos < len(wire):
        count = int.from_bytes(take(2), "big")
        if count >= 0xC000:
            take(3)  # terminal 24-bit field; consumed but not emitted by the EXE
            return bytes(out)
        if count >= 0x4000:
            value = take(1)
            count -= 0x4000
            if len(out) + count > 0x1000000:
                raise ValueError("legacy record output exceeds 16 MiB")
            out.extend(value * count)
        else:
            if not count:
                raise ValueError("zero-length legacy literal record")
            if len(out) + count > 0x1000000:
                raise ValueError("legacy record output exceeds 16 MiB")
            out.extend(take(count))
    raise ValueError("legacy record terminator is missing")


def deinterleave(data: bytes) -> bytes:
    """EDC16 format 3: transpose nine 64-byte lanes per 576-byte group."""
    if len(data) % 0x240:
        raise ValueError("EDC16 format-3 data must contain complete 576-byte groups")
    return b"".join(
        data[group + lane:group + lane + 0x40]
        for lane in range(0, 0x240, 0x40)
        for group in range(0, len(data), 0x240)
    )


def decode_legacy(block: dict, family: str) -> Tuple[int, bytes]:
    """Decode one SGO block for ``family`` -> (device start address, image bytes).

    This mirrors lsdlsd88's ``decode_legacy`` for the four Bosch families
    MESevenTool carries (modes 0/1/2/4).  The returned ``start`` is the upstream
    *device* address; :func:`extract_sgo` re-places it into MESevenTool's flat
    flash layout.
    """
    mode = FAMILIES[family][0]
    start = block["check"][0]
    data = block["data"]
    if mode == 0:  # motronic7 — GEHEIM record coding
        start = start + 0x100000 if start < 0xD0000 else start - 0x800000
        result = record_decode(data, KEYS["motronic7"])
    elif mode in (2, 4):  # edc16 — 32-bit LFSR; format 3 adds de-interleave
        start = start - 0x700000 if start >= 0x800000 else (
            start - 0x200000 if start >= 0x400000 else start)
        result = lfsr_decode(data)
        if block["format"] == 3:
            result = deinterleave(result)
    else:  # mode 1 — edc15 plain XOR-FF
        if block["format"] != 0:
            raise ValueError("EDC15 supports verified plain format 0 only")
        start = block["id_be"]
        result = bytes(c ^ 0xFF for c in data)
    if start < 0:
        raise ValueError("negative legacy mapped address; wrong family")
    if len(result) != block["decomp_be"]:
        raise ValueError(
            f"legacy output size {len(result):#x} differs from declared "
            f"{block['decomp_be']:#x}; wrong family or unsupported data"
        )
    return start, result


# ── Auto-detection, assembly, public API ────────────────────────────────────


def detect_family(sgo: SGO) -> Optional[str]:
    """Family identifiable from content alone, or ``None`` if ambiguous.

    Only record-coded families (keyed) and plain containers self-identify:

    * a record key decodes every block to its declared size (XOR-FF + 1A 01
      sync + keyed records cannot pass by accident) -> that keyed family;
    * otherwise, all-plain (format 0x00, stored size == decoded size) -> edc15,
      the universal XOR-FF plaintext decode.

    EDC16 (format 0x01/0x03) uses a length-preserving LFSR, so "decodes to the
    declared size" is always true and cannot distinguish it from table-ciphered
    DSG or other format-1 containers.  It is therefore never auto-detected and
    must be passed explicitly.
    """
    if not sgo.blocks:
        return None
    for family, key in KEYS.items():
        try:
            if all(len(record_decode(b["data"], key)) == b["decomp_be"]
                   for b in sgo.blocks):
                return family
        except ValueError:
            pass
    if all(b["format"] == 0x00 and b["dsize"] == b["decomp_be"] for b in sgo.blocks):
        return "edc15"
    return None


# ME7 / EDC15 are single-chip ECUs whose readable flash is at most 1 MiB.  Some
# ME7.1.1 SGOs carry extra record blocks mapped above this into a second logical
# section (ODIS programs it, but it is not the ROM read/edited/flashed) -- the
# 1 MiB main bank alone is the ROM (verified via ecu_id.identify + 1 MiB refs).
_ME_FLASH_CEILING = 0x100000
_ME_FLASH_SIZES = (0x40000, 0x80000, 0x100000)  # 256K / 512K / 1M


def _flash_image(family: str, segments: List[Tuple[int, bytes]]) -> Tuple[bytes, int]:
    """Assemble the ROM flash image; return (image, dropped second-section blocks)."""
    if not segments:
        raise ValueError("SGO contains no data blocks")
    if family.startswith("edc16"):
        # EDC16 is a genuine flash+MCU device; keep the whole mapped image.
        kept, excluded = list(segments), 0
        extent = max(start + len(data) for start, data in kept)
        size = max(FAMILIES[family][2], (extent + 0xFFFF) & ~0xFFFF)
    else:
        kept, excluded = [], 0
        for start, data in segments:
            if start >= _ME_FLASH_CEILING:       # second logical section, not the ROM
                excluded += 1
                continue
            if start + len(data) > _ME_FLASH_CEILING:
                data = data[:_ME_FLASH_CEILING - start]
            kept.append((start, data))
        if not kept:
            raise ValueError("no flash-region blocks below the 1 MiB ME7 ceiling")
        extent = max(start + len(data) for start, data in kept)
        size = next((sz for sz in _ME_FLASH_SIZES if extent <= sz), None)
        if size is None:
            raise ValueError(f"ME7 flash extent {extent:#x} exceeds 1 MiB")
    if not 0 < size <= MAX_IMAGE:
        raise ValueError(f"flash size {size:#x} is out of range")
    image = bytearray([0xFF]) * size
    for start, data in sorted(kept):
        if start < 0 or start + len(data) > size:
            raise ValueError("decoded segment falls outside the flash image")
        image[start:start + len(data)] = data
    return bytes(image), excluded


@dataclass
class ExtractResult:
    """Outcome of :func:`extract_sgo`."""

    family: str
    image: bytes
    name: str = ""
    version: str = ""
    blocks: int = 0
    extra_blocks: int = 0  # record blocks dropped as a non-ROM second section

    def to_rom(self) -> ROMImage:
        """Wrap the extracted image as a :class:`ROMImage` (validates ME7 sizes)."""
        return ROMImage.from_bytes(self.image)


def extract_sgo(source: Union[str, Path, bytes, bytearray, SGO],
                family: str = "auto") -> ExtractResult:
    """Decode an SGO flash container into a flat image.

    ``source`` may be a path, raw SGO bytes, or an already-parsed :class:`SGO`.
    ``family`` is one of :data:`FAMILIES` or ``"auto"`` to detect it.
    """
    if isinstance(source, SGO):
        sgo = source if source.blocks else source.parse()
    elif isinstance(source, (bytes, bytearray)):
        sgo = parse_sgo(data=bytes(source))
    else:
        sgo = parse_sgo(path=source)

    if family == "auto":
        detected = detect_family(sgo)
        if detected is None:
            fmts = ", ".join(f"0x{v:02X}" for v in sorted({b["format"] for b in sgo.blocks}))
            raise ValueError(
                f"no automatic ME7/EDC family decoder for this SGO (block formats "
                f"{fmts}); pass family= explicitly, one of: {', '.join(FAMILIES)}"
            )
        family = detected
    elif family not in FAMILIES:
        raise ValueError(f"unknown family {family!r}; choose from {', '.join(FAMILIES)}")

    segments = [decode_legacy(b, family) for b in sgo.blocks]
    image, extra = _flash_image(family, segments)
    return ExtractResult(
        family=family, image=image, name=sgo.name, version=sgo.version,
        blocks=len(sgo.blocks), extra_blocks=extra,
    )
