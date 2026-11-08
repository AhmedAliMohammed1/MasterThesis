"""Check stored-block random access without network or dataset downloads."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'tools/download_dur360_subset.py'
SPEC = importlib.util.spec_from_file_location('download_dur360_subset', SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StoredArchiveRanges(unittest.TestCase):
    def setUp(self):
        self.payload = bytes(range(256)) * 2048
        stored = bytearray(b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\x03')
        for base in range(0, len(self.payload), 131072):
            cursor = base
            for length in (65535, 65535, 2):
                stored.extend(struct.pack('<BHH', 0, length, length ^ 65535))
                stored.extend(self.payload[cursor:cursor + length])
                cursor += length
        self.stored = bytes(stored)

    def test_tiny_and_large_ranges_cross_block_and_cycle_boundaries(self):
        with patch.object(MODULE, 'compressed_range', side_effect=lambda a, b: self.stored[a:b + 1]):
            for offset, size in [(0, 512), (65500, 512), (131000, 512),
                                 (131071, 512), (0, 4096), (65500, 140000),
                                 (262140, 8000)]:
                with self.subTest(offset=offset, size=size):
                    self.assertEqual(MODULE.archive_range(offset, size),
                                     self.payload[offset:offset + size])

    def test_different_gzip_layout_is_rejected(self):
        damaged = bytearray(self.stored)
        damaged[10] = 2
        with patch.object(MODULE, 'compressed_range', side_effect=lambda a, b: bytes(damaged[a:b + 1])):
            with self.assertRaisesRegex(ValueError, 'gzip layout'):
                MODULE.archive_range(0, 4096)


if __name__ == '__main__':
    unittest.main()
