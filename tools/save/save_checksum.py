#!/usr/bin/env python3
"""
save_checksum.py -- recompute the two CRC32 fields in a PROF_SAVE header.
Every write tool here calls recompute_checksums() on the buffer just before
writing it.

Header layout:
    offset  0 (u64): magic "FBCHUNKS"
    offset  8 (u16): version
    offset 10 (u32): headerSize    (8 in every save seen)
    offset 14 (u32): bodySize      (file size - 26; fixed capacity)
    offset 18 (u32): headerHash  = crc(LE bytes of headerEntries)
    offset 22 (u32): headerEntries (section count; never changed by these tools)
    offset 26 (u32): bodyHash    = crc(data[30:EOF])
    offset 30      : sections begin (see docs/SAVE_FILE.md)

crc = standard CRC-32 table/polynomial, seeded with 0x12345678, i.e.
zlib.crc32(data, 0x12345678). No byte swap.

The game has not been seen rejecting a stale bodyHash, but keeping it correct
costs nothing.
"""
import struct
import zlib

CUSTOM_CRC32_SEED = 0x12345678


def custom_crc32(data: bytes) -> int:
    """The engine's CRC32 variant: standard table/polynomial, non-standard
    seed. zlib.crc32(data, value) treats `value` as the running CRC coming
    in, which is exactly the ~INITIAL / process / ~result pattern the
    game's own C = ~INITIAL; ...; return ~C implementation uses."""
    return zlib.crc32(data, CUSTOM_CRC32_SEED) & 0xFFFFFFFF


def recompute_checksums(data: bytearray) -> None:
    """Patches offsets 18 (headerHash) and 26 (bodyHash) in place so they
    match the current contents of `data`. Safe to call on any buffer that
    still has the standard 30-byte FBCHUNKS header described above."""
    header_entries = struct.unpack_from("<I", data, 22)[0]
    header_hash = custom_crc32(struct.pack("<I", header_entries))
    struct.pack_into("<I", data, 18, header_hash)

    body_hash = custom_crc32(bytes(data[30:]))
    struct.pack_into("<I", data, 26, body_hash)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("usage: python save_checksum.py PROF_SAVE   (checks, doesn't write)", file=sys.stderr)
        sys.exit(1)

    data = bytearray(open(sys.argv[1], "rb").read())
    stored_header_hash = struct.unpack_from("<I", data, 18)[0]
    stored_body_hash = struct.unpack_from("<I", data, 26)[0]

    check = bytearray(data)
    recompute_checksums(check)
    computed_header_hash = struct.unpack_from("<I", check, 18)[0]
    computed_body_hash = struct.unpack_from("<I", check, 26)[0]

    print(f"headerHash: stored 0x{stored_header_hash:08x}  computed 0x{computed_header_hash:08x}  "
          f"{'OK' if stored_header_hash == computed_header_hash else 'MISMATCH (stale)'}")
    print(f"bodyHash:   stored 0x{stored_body_hash:08x}  computed 0x{computed_body_hash:08x}  "
          f"{'OK' if stored_body_hash == computed_body_hash else 'MISMATCH (stale)'}")
