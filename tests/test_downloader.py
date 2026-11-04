import hashlib
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from downloader import Downloader

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        routes = {
            '/robots.txt': ('text/plain', b'User-agent: *\nDisallow: /denied\n'),
            '/page': ('text/html', b'<a href="/file.pdf">PDF</a><img src="/image.png">'),
            '/file.pdf': ('application/pdf', b'%PDF-test'),
            '/image.png': ('image/png', b'PNG-test'),
            '/iiif': ('application/json', json.dumps({'items': [{'type': 'Image', 'id': '/image.png'}]}).encode()),
            '/big.pdf': ('application/pdf', b'x' * (1024 * 1024 + 1)),
        }
        if self.path == '/redirect':
            self.send_response(302)
            self.send_header('Location', '/denied.pdf')
            self.end_headers()
            return
        if self.path not in routes:
            self.send_error(404)
            return
        typ, body = routes[self.path]
        self.send_response(200)
        self.send_header('Content-Type', typ)
        self.end_headers()
        self.wfile.write(body)

class DownloaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.old = os.getcwd()
        self.temp = tempfile.TemporaryDirectory()
        os.chdir(self.temp.name)
        self.sleep = patch('downloader.time.sleep')
        self.sleep.start()
        self.d = Downloader(SimpleNamespace(max_files=2, max_pages=2, max_mb=1, depth=1))
        self.d.s.trust_env = False  # Local fixture only; production keeps proxy and TLS.

    def tearDown(self):
        self.d.s.close()
        self.sleep.stop()
        os.chdir(self.old)
        self.temp.cleanup()

    def test_page_downloads_and_manifest_hashes(self):
        self.d.crawl(self.base + '/page')
        self.d.finish()
        manifest = json.loads(Path('downloads/manifest.json').read_text())
        self.assertEqual(2, len(manifest))
        for entry in manifest:
            data = Path('downloads', entry['file']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])

    def test_iiif_relative_image_body(self):
        self.d.iiif(self.base + '/iiif')
        self.assertEqual(1, self.d.count)
        self.assertEqual(self.base + '/image.png', self.d.log[0]['url'])

    def test_redirect_checks_destination_robots(self):
        self.d.save(self.base + '/redirect')
        self.assertEqual(0, self.d.count)
        self.assertIn('robots denied', self.d.log[0]['error'])

    def test_failed_request_has_error(self):
        self.d.save(self.base + '/missing.pdf')
        self.assertEqual(0, self.d.count)
        self.assertIn('404', self.d.log[0]['error'])

    def test_size_limit_removes_partial_file(self):
        self.d.save(self.base + '/big.pdf')
        self.assertEqual(0, self.d.count)
        self.assertIn('size limit', self.d.log[0]['error'])
        self.assertFalse(list(Path('downloads').glob('*.part')))

    def test_max_files_and_duplicate(self):
        self.d.a.max_files = 1
        for path in ('/file.pdf', '/file.pdf', '/image.png'):
            self.d.save(self.base + path)
        self.assertEqual(1, self.d.count)

    def test_url_credentials_rejected(self):
        self.d.save('https://user:password@example.com/file.pdf')
        self.assertIn('Credentials in URLs', self.d.log[0]['error'])

    def test_cli_failure_exits_nonzero_and_writes_manifest(self):
        script = Path(__file__).resolve().parents[1] / 'downloader.py'
        result = subprocess.run([sys.executable, str(script), 'ftp://example.com/file', '--mode', 'file'], capture_output=True)
        self.assertEqual(1, result.returncode)
        self.assertIn('error', json.loads(Path('downloads/manifest.json').read_text())[0])
