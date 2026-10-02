"""Exercise real HTTP range/resume protocol and interruption boundaries locally."""
import contextlib
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import io
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('kitti_demo', Path(__file__).resolve().parents[1] / 'tools/prepare_kitti_demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


@contextlib.contextmanager
def serve(payload, *, etag='"test-object"', ignore_range=False, truncate=False):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_HEAD(self):
            self.send_response(200)
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('ETag', etag)
            self.end_headers()

        def do_GET(self):
            requested = self.headers.get('Range')
            requests.append((requested, self.headers.get('If-Match')))
            if requested and not ignore_range:
                start, end = requested.removeprefix('bytes=').split('-')
                start, end = int(start), int(end) if end else len(payload) - 1
                part = payload[start:end + 1]
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{end}/{len(payload)}')
            else:
                self.send_response(200)
                part = payload
            if truncate:
                part = part[:-1]
            self.send_header('Content-Length', str(len(part)))
            self.end_headers()
            try:
                self.wfile.write(part)
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/sample.zip', requests
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


class DemoRecoveryTests(unittest.TestCase):
    def test_zip_member_read_skips_unneeded_data_and_pins_object(self):
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, 'w') as source:
            source.writestr('camera.png', b'camera payload')
            source.writestr('unneeded-lidar.bin', b'X' * 256_000)
            source.writestr('timestamps.txt', '2011-09-30 12:00:00.000000001\n')
        with serve(archive.getvalue()) as (url, requests):
            with demo.RemoteZip(url, '"test-object"') as remote:
                remote.block_size = 4096
                with zipfile.ZipFile(remote) as source:
                    self.assertEqual(source.read('camera.png'), b'camera payload')
                    self.assertIn(b'2011', source.read('timestamps.txt'))
                self.assertLess(remote.transferred, len(archive.getvalue()) / 4)
            self.assertTrue(requests)
            self.assertTrue(all(tag == '"test-object"' for _, tag in requests))

    def test_changed_object_fails_before_range_download(self):
        with serve(b'changed', etag='"changed"') as (url, requests):
            with self.assertRaisesRegex(ValueError, 'object changed'):
                demo.RemoteZip(url, '"old"')
            self.assertEqual(requests, [])

    def test_server_ignoring_range_is_rejected(self):
        with serve(b'0123456789', ignore_range=True) as (url, _):
            with demo.RemoteZip(url, '"test-object"') as remote:
                with self.assertRaisesRegex(ValueError, 'exact byte ranges'):
                    remote.read(2)

    def test_incomplete_range_is_not_accepted(self):
        with serve(b'0123456789', truncate=True) as (url, _):
            with demo.RemoteZip(url, '"test-object"') as remote:
                with self.assertRaisesRegex(ValueError, 'Incomplete ZIP range'):
                    remote.read(2)

    def test_partial_bag_download_resumes_and_verifies(self):
        payload = b'a test bag download' * 100
        with tempfile.TemporaryDirectory() as directory, serve(payload) as (url, requests):
            path = Path(directory) / 'bag.zip'
            path.with_suffix('.zip.part').write_bytes(payload[:127])
            with patch.multiple(demo, BAG_URL=url, BAG_BYTES=len(payload), BAG_SHA256=hashlib.sha256(payload).hexdigest()):
                demo.download_bag(path)
            self.assertEqual(path.read_bytes(), payload)
            self.assertEqual(requests[0][0], 'bytes=127-')
            self.assertFalse(path.with_suffix('.zip.part').exists())

    def test_completed_pending_download_is_promoted_without_network(self):
        payload = b'complete bag'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bag.zip'
            path.with_suffix('.zip.part').write_bytes(payload)
            with patch.multiple(demo, BAG_BYTES=len(payload), BAG_SHA256=hashlib.sha256(payload).hexdigest()), patch.object(demo, 'open_url', side_effect=AssertionError('network must not be needed')):
                demo.download_bag(path)
            self.assertEqual(path.read_bytes(), payload)

    def test_corrupt_final_archive_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bag.zip'
            path.write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'Checksum mismatch'):
                demo.download_bag(path)
            self.assertEqual(path.read_bytes(), b'corrupt')

    def test_camera_nanoseconds_are_retained(self):
        a = demo.timestamp_ns('2011-09-30 12:00:00.000000001')
        b = demo.timestamp_ns('2011-09-30 12:00:00.123456789')
        self.assertEqual(b - a, 123456788)


if __name__ == '__main__':
    unittest.main()
