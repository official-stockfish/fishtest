import os
import os.path
import subprocess
import sys
import unittest

import games
import updater

import worker


class workerTest(unittest.TestCase):
    def tearDown(self):
        if os.path.exists("foo.txt"):
            os.remove("foo.txt")
        if os.path.exists("README.md"):
            os.remove("README.md")

    def test_item_download(self):
        blob = None
        try:
            blob = games.download_from_github("README.md")
        except:
            pass
        self.assertFalse(blob is None)

    def test_config_setup(self):
        sys.argv = [sys.argv[0], "user", "pass", "--no_validation"]
        if os.path.exists("foo.txt"):
            os.remove("foo.txt")
        worker.CONFIGFILE = "foo.txt"
        worker.setup_parameters(".")
        from configparser import ConfigParser

        config = ConfigParser(inline_comment_prefixes=";", interpolation=None)
        config.read("foo.txt")
        self.assertTrue(config.has_section("login"))
        self.assertTrue(config.has_section("parameters"))
        self.assertTrue(config.has_option("login", "username"))
        self.assertTrue(config.has_option("login", "password"))
        self.assertTrue(config.has_option("parameters", "host"))
        self.assertTrue(config.has_option("parameters", "port"))
        self.assertTrue(config.has_option("parameters", "concurrency"))

    def test_worker_script_with_no_args(self):
        assert not os.path.exists("fishtest.cfg")
        with subprocess.Popen(
            ["python", "worker.py"],
            stdin=subprocess.PIPE,
        ) as p:
            p.communicate()
            self.assertEqual(p.returncode, 1)

    def test_setup_exception(self):
        cwd = os.getcwd()
        with self.assertRaises(Exception):
            games.setup_engine("foo", cwd, cwd, "https://foo", "foo", "https://foo", 1)

    def test_updater(self):
        file_list = updater.update(restart=False, test=True)
        print(file_list)
        self.assertTrue("worker.py" in file_list)

    def test_sri(self):
        self.assertTrue(worker.verify_sri("."))


if __name__ == "__main__":
    unittest.main()
