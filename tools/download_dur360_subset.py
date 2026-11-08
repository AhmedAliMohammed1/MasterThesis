#!/usr/bin/env python3
"""Retrieve unchanged, publisher-checksummed Dur360BEV-Extended samples.

This is deliberately specific to the pinned archive revision below. Its gzip
stream consists of repeating stored DEFLATE blocks, permitting HTTP range reads
without downloading 159 GB. Tar checksums and publisher per-file MD5s validate
every selected payload. No pickle is executed and no labels are generated.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import pickletools
import re
import string
import struct
import tarfile
import time
import urllib.request

REVISION = '07f166e558d7e1987e9a554ce0a89494f8fb87b0'
BASE = f'https://huggingface.co/datasets/TomEeee/Dur360BEV-Extended/resolve/{REVISION}/'
PART_BYTES = 1992294400
POINT_START = 13174191616
POINT_BYTES = 9437184
MEMBER_BYTES = POINT_BYTES + 512
FRAME_COUNT = 15400
META_START = POINT_START - 24 * 1024 * 1024
PREFIX = 'Dur360BEV_Dataset_Extended/'


def compressed_range(start, end):
    chunks = []
    while start <= end:
        part, offset = divmod(start, PART_BYTES)
        last = min(end, (part + 1) * PART_BYTES - 1)
        suffix = string.ascii_lowercase[part // 26] + string.ascii_lowercase[part % 26]
        url = BASE + 'Dur360BEVext_dataset.tar' + suffix + '?download=true'
        local_end = last - part * PART_BYTES
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'Range': f'bytes={offset}-{local_end}'})
                with urllib.request.urlopen(req, timeout=60) as response:
                    expected = f'bytes {offset}-{local_end}/{PART_BYTES}'
                    # The final split part has a shorter total length.
                    received = response.headers.get('Content-Range', '')
                    if response.status != 206 or not received.startswith(expected.rsplit('/', 1)[0] + '/'):
                        raise ValueError('Server did not honor the requested HTTP byte range')
                    data = response.read(last - start + 2)
                if len(data) != last - start + 1:
                    raise ValueError('Incorrect HTTP range length')
                break
            except Exception:
                if attempt == 2:
                    raise
                time.sleep(attempt + 1)
        chunks.append(data)
        start = last + 1
    return b''.join(chunks)


def archive_range(offset, size):
    """Map stored-block gzip offsets; later tar/file checks reject layout drift."""
    end = offset + size
    if size < 4096:
        chunks = []
        while offset < end:
            cycle, within = divmod(offset, 131072)
            stop, overhead = ((65535, 5) if within < 65535 else
                              (131070, 10) if within < 131070 else (131072, 15))
            count = min(end - offset, stop - within)
            start = 10 + cycle * 131087 + within + overhead
            chunks.append(compressed_range(start, start + count - 1))
            offset += count
        return b''.join(chunks)
    cycle, within = divmod(offset, 131072)
    cycles = (within + size + 131071) // 131072
    start = 10 + cycle * 131087
    compressed = compressed_range(start, start + cycles * 131087 - 1)
    decoded = bytearray()
    cursor = 0
    for _ in range(cycles):
        for expected_length in (65535, 65535, 2):
            flag, length, complement = struct.unpack_from('<BHH', compressed, cursor)
            if flag != 0 or length != expected_length or length ^ complement != 65535:
                raise ValueError('Pinned archive no longer has the expected stored-block gzip layout')
            cursor += 5
            decoded.extend(compressed[cursor:cursor + length])
            cursor += length
    return bytes(decoded[within:within + size])


def members(blob, offset):
    for cursor in range((-offset) % 512, len(blob) - 511, 512):
        header = blob[cursor:cursor + 512]
        if header[257:262] != b'ustar':
            continue
        try:
            info = tarfile.TarInfo.frombuf(header, 'utf8', 'strict')
        except tarfile.HeaderError:
            continue
        if info.isfile() and cursor + 512 + info.size <= len(blob):
            yield info, blob[cursor + 512:cursor + 512 + info.size]


def split_indices(path):
    """Read only the two documented int64 byte arrays; never unpickle code."""
    result, key = {}, None
    for opcode, value, _ in pickletools.genops(path.read_bytes()):
        if opcode.name in ('SHORT_BINUNICODE', 'BINUNICODE') and value in ('train_indices', 'test_indices'):
            key = value
        if opcode.name in ('BINBYTES', 'SHORT_BINBYTES') and len(value) > 1000:
            if key in result or key is None or len(value) % 8:
                raise ValueError('Unexpected official split serialization')
            result[key] = list(struct.unpack('<' + 'q' * (len(value) // 8), value))
    if set(result) != {'train_indices', 'test_indices'}:
        raise ValueError('Missing published train/test lists')
    if set(result['train_indices']) & set(result['test_indices']):
        raise ValueError('Published train/test lists overlap')
    if set(result['train_indices'] + result['test_indices']) != set(range(FRAME_COUNT)):
        raise ValueError('Published split does not cover the expected frame indices')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frames-per-split', type=int, default=16)
    args = parser.parse_args()
    if not 1 <= args.frames_per_split <= 32:
        parser.error('--frames-per-split must be between 1 and 32')
    args.output.mkdir(parents=True, exist_ok=True)
    original = args.output / 'original'
    original.mkdir(exist_ok=True)
    metadata = archive_range(META_START, POINT_START - META_START)
    for info, payload in members(metadata, META_START):
        path = PurePosixPath(info.name)
        if not info.name.startswith(PREFIX) or '..' in path.parts or path.is_absolute():
            raise ValueError('Unsafe archive member path')
        destination = original.joinpath(*path.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    dataset = original / PREFIX.rstrip('/')
    checksums = {}
    for line in (dataset / 'md5sums.txt').read_text().splitlines():
        digest, name = line.split(maxsplit=1)
        checksums[name.removeprefix('./')] = digest
    splits = split_indices(dataset / 'metadata/dataset_ext_indices.pkl')
    test = set(splits['test_indices'])
    grid = [round(i * (FRAME_COUNT - 1) / 511) for i in range(512)]

    def identify(ordinal):
        offset = POINT_START + ordinal * MEMBER_BYTES
        info = tarfile.TarInfo.frombuf(archive_range(offset, 512), 'utf8', 'strict')
        stem = Path(info.name).stem
        if not re.fullmatch(r'10000\d{5}', stem) or info.size != POINT_BYTES:
            raise ValueError('Unexpected original point-cloud archive member')
        index = int(stem) - 1000000000
        if not 0 <= index < FRAME_COUNT:
            raise ValueError('Original frame index falls outside the published split')
        return {'stem': stem, 'sorted_index': index, 'tar_ordinal': ordinal,
                'header_offset': offset, 'split': 'test' if index in test else 'train'}

    with ThreadPoolExecutor(max_workers=12) as pool:
        candidates = list(pool.map(identify, grid))
    selection = []
    for split in ('train', 'test'):
        available = [item for item in candidates if item['split'] == split]
        count = args.frames_per_split
        if len(available) < count:
            raise ValueError('Insufficient candidate frames in a published split')
        selection.extend(available[round(i * (len(available) - 1) / max(count - 1, 1))] for i in range(count))
    manifest = {'dataset': 'TomEeee/Dur360BEV-Extended', 'revision': REVISION,
                'selection_method': '512 uniform archive-ordinal candidates; uniform candidates per published split; chosen without labels or inference outputs',
                'split_caveat': 'Published train/test indices are disjoint; drive independence is not established.',
                'frames': selection}
    manifest_path = args.output / 'frozen-selection-final.json'
    if manifest_path.exists() and json.loads(manifest_path.read_text()).get('frames') != selection:
        raise ValueError('Refusing to change an existing frozen frame selection')
    manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')

    def download(item):
        name = f'ouster_points/data/{item["stem"]}.bin'
        destination = dataset / name
        payload = destination.read_bytes() if destination.exists() else archive_range(item['header_offset'] + 512, POINT_BYTES)
        if hashlib.md5(payload).hexdigest() != checksums[name]:
            raise ValueError('Publisher checksum mismatch: ' + name)
        label = dataset / 'labels/data' / (item['stem'] + '.txt')
        if hashlib.md5(label.read_bytes()).hexdigest() != checksums[str(label.relative_to(dataset))]:
            raise ValueError('Publisher checksum mismatch: ' + str(label))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        return {**item, 'bytes': len(payload), 'publisher_md5': checksums[name],
                'sha256': hashlib.sha256(payload).hexdigest(),
                'label_sha256': hashlib.sha256(label.read_bytes()).hexdigest()}

    with ThreadPoolExecutor(max_workers=4) as pool:
        verified = list(pool.map(download, selection))
    manifest['frames'] = verified
    (args.output / 'download-verification.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(f'Verified {len(verified)} original point/label pairs against publisher MD5s in {dataset}')


if __name__ == '__main__':
    main()
