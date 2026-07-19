#!/usr/bin/env python3

import argparse
import hashlib
import mmap
import os
from pathlib import Path


SIGNATURES = {
    "ELF executable": b"\x7fELF",
    "gzip stream": b"\x1f\x8b\x08",
    "XZ stream": b"\xfd7zXZ\x00",
    "bzip2 stream": b"BZh",
    "ZIP archive": b"PK\x03\x04",
    "SquashFS little-endian": b"hsqs",
    "SquashFS big-endian": b"sqsh",
    "CPIO new ASCII": b"070701",
    "CPIO CRC ASCII": b"070702",
    "CPIO old ASCII": b"070707",
    "UBI image": b"UBI#",
    "UBIFS filesystem": b"\x31\x18\x10\x06",
    "Device tree/FIT": b"\xd0\x0d\xfe\xed",
    "Legacy U-Boot image": b"\x27\x05\x19\x56",
    "cramfs little-endian": b"\x45\x3d\xcd\x28",
    "cramfs big-endian": b"\x28\xcd\x3d\x45",
}

MAX_MATCHES = 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def find_offsets(data: mmap.mmap, signature: bytes) -> list[int]:
    offsets = []
    position = 0

    while len(offsets) < MAX_MATCHES:
        position = data.find(signature, position)

        if position < 0:
            break

        offsets.append(position)
        position += 1

    return offsets


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only signature scanner for QNAP firmware images."
    )
    parser.add_argument("image", type=Path)
    args = parser.parse_args()

    image = args.image.resolve()

    if not image.is_file():
        parser.error(f"Image not found: {image}")

    print("===== QNAP IMAGE SIGNATURE SCAN =====")
    print(f"Image:  {image}")
    print(f"Size:   {image.stat().st_size:,} bytes")
    print(f"SHA256: {sha256(image)}")
    print()

    with image.open("rb") as stream:
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            found_any = False

            for name, signature in SIGNATURES.items():
                offsets = find_offsets(data, signature)

                if not offsets:
                    continue

                found_any = True
                print(name)

                for offset in offsets:
                    print(f"  decimal={offset:<12} hex=0x{offset:08X}")

                if len(offsets) == MAX_MATCHES:
                    print("  Additional matches may exist.")

                print()

            # A tar archive stores "ustar" 257 bytes after its start.
            tar_offsets = find_offsets(data, b"ustar")

            if tar_offsets:
                found_any = True
                print("Possible tar archives")

                for marker in tar_offsets:
                    start = marker - 257
                    print(
                        f"  ustar marker=0x{marker:08X} "
                        f"possible start=0x{max(start, 0):08X}"
                    )

                print()

            if not found_any:
                print("No common embedded filesystem signatures found.")
                print("The image may be encrypted, signed, or use a vendor container.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
