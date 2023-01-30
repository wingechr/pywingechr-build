import os
import pathlib
import shutil
import tempfile
import unittest
from functools import partial

from wingechr.build import BuildEnvironment


class TestBuild(unittest.TestCase):
    def test_build(self):
        with tempfile.TemporaryDirectory() as pwd:

            def create_t(env):
                def fun():
                    env.build(
                        shutil.copy,
                        targets={"dst": f"{pwd}/t"},
                        sources={"src": f"{pwd}/s"},
                    )

                return fun

            # missing source
            env = BuildEnvironment()
            self.assertRaises(FileNotFoundError, create_t(env))

            # create source
            pathlib.Path(f"{pwd}/s").touch()
            # still error, because env is older than source
            self.assertRaises(Exception, create_t(env))

            # use new environment: now it should work
            env = BuildEnvironment()
            create_t(env)()
            self.assertTrue(os.path.isfile(f"{pwd}/t"))

            # try to update source fails now (cycle)
            self.assertRaises(
                ValueError,
                partial(
                    env.build,
                    builder=shutil.copy,
                    targets={"dst": f"{pwd}/s"},
                    sources={"src": f"{pwd}/t"},
                ),
            )
