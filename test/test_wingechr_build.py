import logging
import os
import pathlib
import shutil
import tempfile
import unittest

from wingechr.build import BuildEnvironment

logging.basicConfig(
    format="[%(asctime)s %(levelname)7s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.DEBUG,
)


class TestBuild(unittest.TestCase):
    def test_build(self):
        with tempfile.TemporaryDirectory() as pwd:

            env = BuildEnvironment()

            def copy(src, dst):
                logging.info("Copying src to dst")
                shutil.copy(src, dst)

            logging.info("missing source")
            self.assertRaises(
                FileNotFoundError,
                env.build,
                copy,
                targets={"dst": f"{pwd}/t/t"},
                sources={"src": f"{pwd}/s"},
            )

            # create source
            pathlib.Path(f"{pwd}/s").touch()

            env.build(
                copy,
                targets={"dst": f"{pwd}/t/t"},
                sources={"src": f"{pwd}/s"},
            )
            self.assertTrue(os.path.isfile(f"{pwd}/t/t"))

            # try to update source fails now (cycle)
            self.assertRaises(
                Exception,
                env.build,
                copy,
                targets={"dst": f"{pwd}/s"},
                sources={"src": f"{pwd}/t/t"},
            )
