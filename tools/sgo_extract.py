#!/usr/bin/env python3
"""
SGO Extract — Python reimplementation of SGO Extract.exe (2013)
Extracts Bosch ME7.x / EDC16 / Siemens PPD flash images from ODIS SGO files.

Algorithm reverse-engineered from SGO Extract.exe by disassembly:
  - SGO payload XOR-inverted (byte ^ 0xFF) before processing
  - State machine: sync(1A 01) → len_hi → len_lo → data/fill
  - Key "GEHEIM" (6 bytes) applied to length and data bytes
  - Literal records: length < 0x4000 → write length bytes
  - RLE records: 0x4000 <= length < 0xC000 → write (length-0x4000) copies of fill byte
  - Output: 1MB image, unwritten regions = 0xFF
"""

import sys, os

KEY         = b'GEHEIM'
FLASH_START = 0x01B7   # first data section offset in SGO header
FLASH_SIZE  = 0x100000  # 1MB output

def extract(sgo_path, out_path=None):
    raw = open(sgo_path, 'rb').read()
    if not raw.startswith(b'SGML Object File'):
        raise ValueError(f"Not a valid SGO file: {sgo_path}")

    output   = bytearray(b'\xff' * FLASH_SIZE)
    state    = 0
    key_pos  = 0
    prev     = 0
    rec_len  = 0
    rec_hi   = 0
    write_pos = 0

    for byte in raw[FLASH_START:]:
        inv = byte ^ 0xFF

        if state == 0:
            if prev == 0x1A and inv == 0x01:
                state = 1
            prev = inv

        elif state == 1:
            rec_hi   = inv ^ KEY[key_pos % 6]; key_pos += 1
            state    = 2

        elif state == 2:
            rec_lo      = inv ^ KEY[key_pos % 6]; key_pos += 1
            rec_len_raw = (rec_hi << 8) | rec_lo
            if rec_len_raw < 0x4000:
                rec_len = rec_len_raw
                state   = 3            # literal data
            elif rec_len_raw < 0xC000:
                rec_len = rec_len_raw - 0x4000
                state   = 4            # RLE fill
            else:
                state = 0              # invalid, resync

        elif state == 3:               # literal byte
            decoded = inv ^ KEY[key_pos % 6]; key_pos += 1
            if 0 <= write_pos < FLASH_SIZE:
                output[write_pos] = decoded
            write_pos += 1
            rec_len   -= 1
            if rec_len == 0:
                state = 1

        elif state == 4:               # RLE: read fill value, write N copies
            fill = inv ^ KEY[key_pos % 6]; key_pos += 1
            for _ in range(rec_len):
                if 0 <= write_pos < FLASH_SIZE:
                    output[write_pos] = fill
                write_pos += 1
            state = 1

    result = bytes(output[:FLASH_SIZE])
    if out_path is None:
        out_path = sgo_path.replace('.sgo', '.bin').replace('.SGO', '.bin')
    open(out_path, 'wb').write(result)
    written = sum(1 for b in result if b != 0xFF)
    print(f"  {os.path.basename(sgo_path)} -> {os.path.basename(out_path)} ({written//1024}KB written)")
    return out_path

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} file.sgo [file2.sgo ...]")
        sys.exit(1)
    for sgo in sys.argv[1:]:
        try:
            extract(sgo)
        except Exception as e:
            print(f"  ERROR {sgo}: {e}")
