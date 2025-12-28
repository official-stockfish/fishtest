import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from configparser import ConfigParser
from pathlib import Path

import games
import updater

import worker


class WorkerTest(unittest.TestCase):
    def setUp(self):
        self.worker_dir = Path(__file__).resolve().parents[1]
        self.tempdir_obj = tempfile.TemporaryDirectory()
        self.tempdir = Path(self.tempdir_obj.name)
        (self.tempdir / "testing").mkdir()

    def tearDown(self):
        try:
            self.tempdir_obj.cleanup()
        except PermissionError as e:
            if os.name == "nt":
                shutil.rmtree(self.tempdir, ignore_errors=True)
            else:
                raise e

    def test_item_download(self):
        blob = None
        try:
            blob = games.download_from_github("README.md")
        except Exception:
            pass
        self.assertIsNotNone(blob)

    def test_config_setup(self):
        sys.argv = [sys.argv[0], "user", "pass", "--no_validation"]
        worker.CONFIGFILE = str(self.tempdir / "foo.txt")
        worker.setup_parameters(self.tempdir)
        config = ConfigParser(inline_comment_prefixes=";", interpolation=None)
        config.read(worker.CONFIGFILE)
        self.assertTrue(config.has_section("login"))
        self.assertTrue(config.has_section("parameters"))
        self.assertTrue(config.has_option("login", "username"))
        self.assertTrue(config.has_option("login", "password"))
        self.assertTrue(config.has_option("login", "jwt"))
        self.assertTrue(config.has_option("parameters", "host"))
        self.assertTrue(config.has_option("parameters", "port"))
        self.assertTrue(config.has_option("parameters", "concurrency"))

    def test_worker_script_with_bad_args(self):
        self.assertFalse((self.worker_dir / "fishtest.cfg").exists())
        p = subprocess.run([sys.executable, "worker.py", "--no-validation"])
        self.assertEqual(p.returncode, 1)

    def test_setup_exception(self):
        cwd = self.tempdir
        with self.assertRaises(Exception):
            games.setup_engine("foo", cwd, cwd, "https://foo", "foo", "https://foo", 1)

    def test_updater(self):
        file_list = updater.update(restart=False, test=True)
        self.assertIn("worker.py", file_list)

    def test_sri(self):
        self.assertTrue(worker.verify_sri(self.worker_dir))

    def test_toolchain_verification(self):
        self.assertTrue(worker.verify_toolchain())

    def test_setup_fastchess(self):
        self.assertTrue(
            worker.setup_fastchess(
                self.tempdir, list(worker.detect_compilers())[0], 4, ""
            )
        )

    def test_memory_expression(self):
        mem = worker._memory(MAX=1024)
        expr, ret = mem("MAX/2")
        self.assertEqual(expr, "MAX/2")
        self.assertEqual(ret, 512)

        # Clamped to [0, MAX]
        _, ret2 = mem("-10")
        self.assertEqual(ret2, 0)
        _, ret3 = mem("MAX*2")
        self.assertEqual(ret3, 1024)

    def test_concurrency_expression(self):
        conc = worker._concurrency(MAX=8)
        expr, ret = conc("max(1,min(3,MAX-1))")
        self.assertEqual(expr, "max(1,min(3,MAX-1))")
        self.assertEqual(ret, 3)

        # Invalid: <= 0
        with self.assertRaises(ValueError):
            conc("0")

        # Invalid: over MAX without explicit MAX variable in expression
        with self.assertRaises(ValueError):
            conc("999")


if __name__ == "__main__":
    unittest.main()
