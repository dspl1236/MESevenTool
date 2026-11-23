"""Tests for meseventool.sgo — SGO flash-container import.

No real flash files are needed or redistributed: each test builds a minimal
in-memory SGO around a synthetic payload, using an inverse of each decode path.
"""
import struct

import pytest

from meseventool.sgo import (
    HEADER_MAGIC, FAMILIES, SGO, parse_sgo, extract_sgo, detect_family,
    record_decode, lfsr_decode, deinterleave,
)
from meseventool.rom import ROMImage


# ── encoders: inverses of each decode path, for building test payloads ──────

def _encode_record(payload: bytes, key: bytes) -> bytes:
    """Produce block data such that record_decode(data, key) == payload."""
    rec = bytearray()
    i = 0
    while i < len(payload):
        chunk = payload[i:i + 0x3FFF]        # literal record, count < 0x4000
        rec += len(chunk).to_bytes(2, "big") + chunk
        i += len(chunk)
    rec += b"\xC0\x00\x00\x00\x00"           # terminal: count >= 0xC000, + 3 bytes
    mask = bytes(key[j % len(key)] for j in range(len(rec)))
    wire = b"\x1a\x01" + bytes(a ^ b for a, b in zip(rec, mask))
    return bytes(c ^ 0xFF for c in wire)     # container XOR-FF layer


def _encode_plain(payload: bytes) -> bytes:
    """EDC15: block data is the XOR-FF of the image."""
    return bytes(c ^ 0xFF for c in payload)


def _encode_lfsr(payload: bytes) -> bytes:
    """EDC16: data such that lfsr_decode(data) == payload (keystream from zeros)."""
    keystream = lfsr_decode(bytes(len(payload)))
    return bytes(a ^ b for a, b in zip(payload, keystream))


# ── synthetic SGO container builder ─────────────────────────────────────────

def _build_sgo(blocks, name=b"SYNTH", version=b"0001") -> bytes:
    """blocks: list of (format, decomp_be, check_start, payload_bytes)."""
    ident = bytearray(269)
    nm = bytes(c ^ 0xFF for c in name)
    ident[:len(nm)] = nm                      # zero terminator already present
    ver = bytes(c ^ 0xFF for c in version)
    ident[260:260 + len(ver)] = ver

    i_ident = 0x31
    i_blocks = i_ident + 269
    nb = len(blocks)
    desc_area = i_blocks + 4 + nb * 4

    offsets, body, cursor = [], bytearray(), desc_area
    for fmt, decomp, check_start, payload in blocks:
        offsets.append(cursor)
        desc = bytearray(0x19)
        desc[4:7] = int(decomp).to_bytes(3, "big")
        desc[13:16] = int(check_start).to_bytes(3, "big")
        desc[3] = fmt
        struct.pack_into("<I", desc, 0x15, len(payload))
        chunk = bytes(desc) + payload
        body += chunk
        cursor += len(chunk)

    buf = bytearray(HEADER_MAGIC)
    buf += struct.pack("<8I", 2, 0, i_ident, 0, 0, 0, 0, i_blocks)
    assert len(buf) == 0x31
    buf += bytes(ident)
    assert len(buf) == i_blocks
    buf += struct.pack("<I", nb)
    buf += struct.pack(f"<{nb}I", *offsets)
    assert len(buf) == desc_area
    buf += body
    return bytes(buf)


# ── primitive round-trips ───────────────────────────────────────────────────

class TestPrimitives:
    def test_record_decode_roundtrip(self):
        payload = bytes((i * 37 + 11) & 0xFF for i in range(5000))
        data = _encode_record(payload, b"GEHEIM")
        assert record_decode(data, b"GEHEIM") == payload

    def test_record_decode_missing_sync_raises(self):
        with pytest.raises(ValueError, match="sync"):
            record_decode(bytes(64), b"GEHEIM")

    def test_lfsr_decode_roundtrip(self):
        payload = bytes((i * 5 + 1) & 0xFF for i in range(0x1000))
        assert lfsr_decode(_encode_lfsr(payload)) == payload

    def test_lfsr_decode_is_deterministic(self):
        assert lfsr_decode(bytes(16)) == lfsr_decode(bytes(16))

    def test_deinterleave_transpose(self):
        # Two 576-byte groups; byte value encodes group*9 + lane.
        data = bytearray()
        for group in range(2):
            for lane in range(9):
                data += bytes([group * 9 + lane]) * 0x40
        out = deinterleave(bytes(data))
        # Output order is lane-major: (g0 l0)(g1 l0)(g0 l1)(g1 l1)...
        expected = bytearray()
        for lane in range(9):
            for group in range(2):
                expected += bytes([group * 9 + lane]) * 0x40
        assert out == bytes(expected)

    def test_deinterleave_bad_length_raises(self):
        with pytest.raises(ValueError, match="576-byte"):
            deinterleave(bytes(100))


# ── container parsing ───────────────────────────────────────────────────────

class TestParser:
    def test_rejects_non_sgo(self):
        with pytest.raises(ValueError, match="not an SGML Object File"):
            parse_sgo(data=b"not an sgo file at all")

    def test_parses_name_and_blocks(self):
        payload = _encode_plain(bytes(0x400))
        sgo = parse_sgo(data=_build_sgo([(0x00, 0x400, 0, payload)], name=b"HELLO"))
        assert isinstance(sgo, SGO)
        assert sgo.name == "HELLO"
        assert len(sgo.blocks) == 1
        assert sgo.blocks[0]["format"] == 0x00
        assert sgo.blocks[0]["decomp_be"] == 0x400


# ── end-to-end extraction per family ────────────────────────────────────────

class TestExtract:
    def test_motronic7_auto_single_bank_flat(self):
        # Low bank: descriptor check-start 0x800000 maps flat to 0.
        payload = bytes((i * 29 + 7) & 0xFF for i in range(0x40000))  # 256 KB
        sgo = _build_sgo([(0x11, len(payload), 0x800000, _encode_record(payload, b"GEHEIM"))])
        result = extract_sgo(sgo)
        assert result.family == "motronic7"
        assert result.image == payload            # flat 256 KB at offset 0
        assert result.to_rom().size == 0x40000    # loads as a 256 KB ME7 ROM

    def test_motronic7_dual_bank_assembly(self):
        # Real ME7.1.1 layout: low bank at 0 (check 0x800000), high bank at
        # 0x100000 (check 0x0 -> +0x100000). Extent 0x101000 -> native 2 MiB.
        low = bytes((i * 7 + 1) & 0xFF for i in range(0x40000))
        high = bytes((i * 5 + 2) & 0xFF for i in range(0x1000))
        sgo = _build_sgo([
            (0x11, len(low), 0x800000, _encode_record(low, b"GEHEIM")),
            (0x11, len(high), 0x000000, _encode_record(high, b"GEHEIM")),
        ])
        result = extract_sgo(sgo)
        assert result.family == "motronic7"
        assert len(result.image) == 0x200000
        assert result.image[:0x40000] == low
        assert result.image[0x100000:0x100000 + 0x1000] == high

    def test_edc15_plain_auto(self):
        payload = bytes((i * 3 + 9) & 0xFF for i in range(0x80000))  # 512 KB
        sgo = _build_sgo([(0x00, len(payload), 0, _encode_plain(payload))])
        result = extract_sgo(sgo)
        assert result.family == "edc15"
        assert result.image == payload

    def test_edc16_requires_explicit_family(self):
        # Length-preserving LFSR is indistinguishable from table-ciphered DSG,
        # so EDC16 is never auto-detected — it must be requested by name.
        payload = bytes((i * 11 + 2) & 0xFF for i in range(0x1000))
        sgo = _build_sgo([(0x01, len(payload), 0, _encode_lfsr(payload))])
        with pytest.raises(ValueError, match="no automatic"):
            extract_sgo(sgo)
        result = extract_sgo(sgo, family="edc16-1m")
        assert result.family == "edc16-1m"
        assert len(result.image) == FAMILIES["edc16-1m"][2]   # 0x280000 floor
        assert result.image[:len(payload)] == payload

    def test_explicit_edc16_2m(self):
        payload = bytes((i * 11 + 2) & 0xFF for i in range(0x1000))
        sgo = _build_sgo([(0x01, len(payload), 0, _encode_lfsr(payload))])
        result = extract_sgo(sgo, family="edc16-2m")
        assert result.family == "edc16-2m"
        assert result.image[:len(payload)] == payload

    def test_unknown_format_auto_raises(self):
        sgo = _build_sgo([(0x05, 0x100, 0, bytes(0x100))])
        with pytest.raises(ValueError, match="no automatic"):
            extract_sgo(sgo)

    def test_unknown_family_name_raises(self):
        sgo = _build_sgo([(0x00, 0x100, 0, _encode_plain(bytes(0x100)))])
        with pytest.raises(ValueError, match="unknown family"):
            extract_sgo(sgo, family="med17")

    def test_detect_family_direct(self):
        payload = bytes((i * 29 + 7) & 0xFF for i in range(0x40000))
        sgo = parse_sgo(data=_build_sgo(
            [(0x11, len(payload), 0x800000, _encode_record(payload, b"GEHEIM"))]))
        assert detect_family(sgo) == "motronic7"

    def test_extracted_image_round_trips_through_rom(self):
        payload = bytes((i * 29 + 7) & 0xFF for i in range(0x40000))
        sgo = _build_sgo([(0x11, len(payload), 0x800000, _encode_record(payload, b"GEHEIM"))])
        rom = ROMImage.from_bytes(extract_sgo(sgo).image)
        assert rom.read(0x1000, 4) == payload[0x1000:0x1004]
