"""Tests du système de mise à jour avec un faux serveur GitHub local.

Lancer : python -m unittest discover tests
"""
import hashlib
import importlib
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PAYLOAD = b"NOUVEL EXE " * 50000          # ~550 Ko
STATE = {"tag": "v0.2.0", "digest": "sha256:" + hashlib.sha256(PAYLOAD).hexdigest(),
         "size": len(PAYLOAD), "body": PAYLOAD, "asset": "AuraEdit.exe"}


class FakeGitHub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        port = self.server.server_address[1]
        if self.path == "/latest":
            data = json.dumps({
                "tag_name": STATE["tag"], "body": "- nouveautés", "html_url": "http://x/release",
                "assets": [{"name": STATE["asset"], "size": STATE["size"], "digest": STATE["digest"],
                            "browser_download_url": f"http://127.0.0.1:{port}/exe"}]}).encode()
        elif self.path == "/exe":
            data = STATE["body"]
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class UpdaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeGitHub)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        os.environ["AURAEDIT_UPDATE_URL"] = f"http://127.0.0.1:{cls.server.server_address[1]}/latest"
        import app.core.updater as up
        cls.up = importlib.reload(up)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        STATE.update(tag="v0.2.0", body=PAYLOAD, size=len(PAYLOAD), asset="AuraEdit.exe",
                     digest="sha256:" + hashlib.sha256(PAYLOAD).hexdigest())
        self.dir = Path(tempfile.mkdtemp())

    # --- versions
    def test_versions(self):
        up = self.up
        self.assertEqual(up.parse_version("v1.2.10"), (1, 2, 10))
        self.assertEqual(up.parse_version("2.0"), (2, 0, 0))
        self.assertTrue(up.is_newer("v0.10.0", "0.9.9"))     # 10 > 9 (pas un tri alphabétique)
        self.assertFalse(up.is_newer("v0.1.0", "0.1.0"))
        self.assertFalse(up.is_newer("n'importe quoi", "0.1.0"))

    # --- vérification
    def test_update_found(self):
        info = self.up.check_for_update("0.1.0")
        self.assertIsNotNone(info)
        self.assertEqual(info.version, "0.2.0")
        self.assertEqual(info.size, len(PAYLOAD))

    def test_already_up_to_date(self):
        self.assertIsNone(self.up.check_for_update("0.2.0"))
        self.assertIsNone(self.up.check_for_update("1.0.0"))

    def test_release_without_exe_is_ignored(self):
        STATE["asset"] = "autre.zip"
        self.assertIsNone(self.up.check_for_update("0.1.0"))

    def test_offline_returns_none(self):
        saved = self.up.API_URL
        self.up.API_URL = "http://127.0.0.1:9/latest"   # rien n'écoute ici
        try:
            self.assertIsNone(self.up.check_for_update("0.1.0"))
        finally:
            self.up.API_URL = saved

    # --- téléchargement
    def test_download_ok_with_progress(self):
        info = self.up.check_for_update("0.1.0")
        calls = []
        dest = self.up.download(info, self.dir / "AuraEdit.exe.download",
                                progress=lambda r, t: calls.append((r, t)))
        self.assertEqual(dest.read_bytes(), PAYLOAD)
        self.assertEqual(calls[-1], (len(PAYLOAD), len(PAYLOAD)))
        self.assertFalse((self.dir / "AuraEdit.exe.download.part").exists())

    def test_download_corrupted(self):
        info = self.up.check_for_update("0.1.0")
        STATE["body"] = PAYLOAD[:-1] + b"X"           # même taille, contenu différent
        with self.assertRaises(self.up.UpdateError):
            self.up.download(info, self.dir / "x.download")
        self.assertEqual(list(self.dir.iterdir()), [])  # rien ne traîne

    def test_download_incomplete(self):
        info = self.up.check_for_update("0.1.0")
        info.sha256 = None
        STATE["body"] = PAYLOAD[:1000]
        with self.assertRaises(self.up.UpdateError):
            self.up.download(info, self.dir / "x.download")

    def test_download_cancel(self):
        info = self.up.check_for_update("0.1.0")
        with self.assertRaises(self.up.UpdateError):
            self.up.download(info, self.dir / "x.download", is_cancelled=lambda: True)
        self.assertEqual(list(self.dir.iterdir()), [])

    # --- installation
    def test_install_and_cleanup(self):
        exe = self.dir / "AuraEdit.exe"
        exe.write_bytes(b"ANCIEN")
        new = self.dir / "AuraEdit.exe.download"
        new.write_bytes(b"NOUVEAU")
        self.up.install(new, exe)
        self.assertEqual(exe.read_bytes(), b"NOUVEAU")
        self.assertEqual((self.dir / "AuraEdit.exe.old").read_bytes(), b"ANCIEN")
        self.up.cleanup_leftovers(exe)
        self.assertEqual([p.name for p in self.dir.iterdir()], ["AuraEdit.exe"])

    def test_install_rollback(self):
        exe = self.dir / "AuraEdit.exe"
        exe.write_bytes(b"ANCIEN")
        with self.assertRaises(self.up.UpdateError):
            self.up.install(self.dir / "absent.download", exe)
        self.assertEqual(exe.read_bytes(), b"ANCIEN")    # le logiciel reste utilisable


class NotesTests(unittest.TestCase):
    def test_notes_without_github_links(self):
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        from app.core.updater import clean_notes
        body = ("## Nouveautés\r\n- Sons mieux reconnus\r\n\r\n"
                "**Full Changelog**: https://github.com/auragpro/AuraEdit/compare/v0.1.0...v0.2.0")
        self.assertEqual(clean_notes(body), "## Nouveautés\n- Sons mieux reconnus")


if __name__ == "__main__":
    unittest.main()
