"""Tests del descargador de recursos, contra un servidor HTTP local (sin internet)."""
import hashlib
import http.server
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import assets as A  # noqa: E402
import omega_reader as R  # noqa: E402


def png(w, h):
    """PNG mínimo válido de w x h (gris)."""
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class FileServer:
    """Servidor HTTP con archivos en memoria: {ruta: bytes}."""

    def __init__(self, files):
        files_ = files

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = files_.get(self.path)
                if body is None:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.files = files
        self.srv = http.server.HTTPServer(("127.0.0.1", 0), H)
        self.base = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


BADGE = png(48, 48)
SHEET = png(384, 1152)


def manifest(base):
    return {"version": 1, "sources": {"x": {"name": "Fuente de prueba"}}, "files": [
        {"path": "badges/oras/1.png", "url": base + "/b1.png",
         "sha256": hashlib.sha256(BADGE).hexdigest(), "size": len(BADGE), "group": "oras"},
        {"path": "itemicons-sheet.png", "url": base + "/sheet.png",
         "sha256": hashlib.sha256(SHEET).hexdigest(), "size": len(SHEET),
         "allow_update": {"type": "png", "min_width": 384}},
    ]}


class TestAssetStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.server = FileServer({"/b1.png": BADGE, "/sheet.png": SHEET})
        self.store = A.AssetStore(cache_dir=os.path.join(self.tmp, "cache"), manifest=manifest(self.server.base),
                                  legacy_dir=os.path.join(self.tmp, "legacy"), timeout=3)

    def tearDown(self):
        self.server.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_initial_status(self):
        st = self.store.status()
        self.assertFalse(st["complete"])
        self.assertEqual(st["missing"], ["badges/oras/1.png", "itemicons-sheet.png"])
        self.assertEqual(st["bytes_missing"], len(BADGE) + len(SHEET))

    def test_download_all(self):
        self.assertEqual(self.store.download_missing(), [])
        st = self.store.status()
        self.assertTrue(st["complete"])
        with open(self.store.resolve("badges/oras/1.png"), "rb") as f:
            self.assertEqual(f.read(), BADGE)
        self.assertEqual(st["job"]["done"], 2)

    def test_second_run_downloads_nothing(self):
        self.store.download_missing()
        self.server.files.clear()            # si volviera a pedir algo, fallaría
        self.assertEqual(self.store.download_missing(), [])

    def test_bad_hash_rejected(self):
        self.server.files["/b1.png"] = png(10, 10)
        errors = self.store.download_missing()
        self.assertEqual(len(errors), 1)
        self.assertIn("badges/oras/1.png", errors[0])
        self.assertIsNone(self.store.resolve("badges/oras/1.png"))   # no deja archivos a medias
        self.assertIsNotNone(self.store.resolve("itemicons-sheet.png"))

    def test_sheet_updated_upstream_is_accepted(self):
        self.server.files["/sheet.png"] = png(384, 1200)               # Showdown añadió objetos
        self.assertEqual(self.store.download_missing(), [])

    def test_sheet_that_is_not_png_is_rejected(self):
        self.server.files["/sheet.png"] = b"<html>error</html>"
        self.assertEqual(len(self.store.download_missing()), 1)

    def test_network_error_reported(self):
        self.server.close()
        errors = self.store.download_missing()
        self.assertEqual(len(errors), 2)
        self.server = FileServer({})                                   # para tearDown

    def test_legacy_folder_is_used(self):
        os.makedirs(os.path.join(self.tmp, "legacy", "badges"))
        with open(os.path.join(self.tmp, "legacy", "badges", "1.png"), "wb") as f:
            f.write(BADGE)
        self.assertIsNotNone(self.store.resolve("badges/oras/1.png"))
        self.assertEqual(self.store.status()["missing"], ["itemicons-sheet.png"])

    def test_resolve_blocks_traversal(self):
        with open(os.path.join(self.tmp, "secret.txt"), "w") as f:
            f.write("x")
        for rel in ("../secret.txt", "badges/../../secret.txt", "/../secret.txt", "", "badges//1.png"):
            self.assertIsNone(self.store.resolve(rel), rel)

    def test_png_size(self):
        self.assertEqual(A.png_size(SHEET), (384, 1152))
        self.assertIsNone(A.png_size(b"GIF89a" + bytes(30)))


class TestRealManifest(unittest.TestCase):
    def test_manifest_is_consistent(self):
        m = A.load_manifest()
        paths = [e["path"] for e in m["files"]]
        self.assertEqual(len(paths), len(set(paths)))
        for e in m["files"]:
            self.assertTrue(e["url"].startswith("https://"), e["path"])
            self.assertEqual(len(e["sha256"]), 64)
            self.assertIn(e["source"], m["sources"])
        self.assertEqual(sum(p.startswith("badges/oras/") for p in paths), 8)


class TestAssetRoutes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.files = FileServer({"/b1.png": BADGE, "/sheet.png": SHEET})
        cls.old = R.ASSETS
        R.ASSETS = A.AssetStore(cache_dir=os.path.join(cls.tmp, "cache"), manifest=manifest(cls.files.base),
                                legacy_dir=None, timeout=3)
        cls.srv = R.Server(("127.0.0.1", 0), R.Handler)
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.files.close()
        R.ASSETS = cls.old
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_status_download_and_serve(self):
        st = json.loads(urllib.request.urlopen(self.base + "/assets/status.json", timeout=2).read())
        self.assertFalse(st["complete"])
        with self.assertRaises(urllib.error.HTTPError):
            urllib.request.urlopen(self.base + "/assets/badges/oras/1.png", timeout=2)
        req = urllib.request.Request(self.base + "/assets/download", data=b"", method="POST")
        json.loads(urllib.request.urlopen(req, timeout=2).read())
        for _ in range(50):
            st = json.loads(urllib.request.urlopen(self.base + "/assets/status.json", timeout=2).read())
            if st["complete"]:
                break
            threading.Event().wait(0.1)
        self.assertTrue(st["complete"])
        with urllib.request.urlopen(self.base + "/assets/badges/oras/1.png", timeout=2) as r:
            self.assertEqual(r.read(), BADGE)
            self.assertEqual(r.headers["Content-Type"], "image/png")

    def test_traversal_over_http(self):
        for path in ("/assets/../omega_reader.py", "/assets/%2e%2e/omega_reader.py", "/assets/..%5comega_reader.py"):
            with self.assertRaises(urllib.error.HTTPError, msg=path):
                urllib.request.urlopen(self.base + path, timeout=2)


if __name__ == "__main__":
    unittest.main()
