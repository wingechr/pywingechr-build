"""
Example:


from build import BuildEnvironment
env = BuildEnvironment()

# use cmd string
env.build("copy %(src)s %(dst)s", targets={"dst": ...}, sources={"src": ...})

# use function
env.build(shutil.copy, targets={"dst": ...}, sources={"src": ...})

"""

import logging
import os
import pathlib
import shutil
import subprocess as sp
import tempfile
import unittest
from typing import Callable


class BuildEnvironment:
    __slots__ = ["__nodes", "__targets", "__now", "__folders"]

    def __init__(self):
        self.__nodes = set()
        self.__targets = set()
        self.__folders = set()
        self.__now = self._get_cur_timestamp()
        logging.debug("NOW: %s", self.__now)

    def _get_cur_timestamp(self):
        """do not use datetime, because it can be
        different from file system time, which we want to use
        """
        with tempfile.NamedTemporaryFile(delete=True) as file:
            return self._get_timestamp(file.name)

    def build(self, builder, targets, sources=None, dependencies=None, kwargs=None):
        """build the target with fun(target, **sources)
           if target doesnot exist or any source is newer

        Args:
            builder(Callable|str|list): callable(target, **sources)
              or str/list cor subprocess command with placeholders for TARGET
              and sources
            targets(dict): name -> node
            sources(dict, optional): name -> node
            dependencies(list, optional): [node]
            kwargs(dict, optional): name -> value

        """
        sources = sources or {}
        dependencies = dependencies or []
        kwargs = kwargs or {}

        # make sure no overlapping names exist
        fun_kwargs = targets | sources | kwargs
        assert len(fun_kwargs) == len(targets) + len(sources) + len(kwargs)

        # check dependencies/sources and get latest timestamp

        dependency_files = set()

        for d in dependencies:
            dependency_files = dependency_files | set(self._add_nodes(d))
        for s in sources.values():
            dependency_files = dependency_files | set(self._add_nodes(s))

        if dependency_files:
            dependency_files_latest_ts = self._get_latest_ts(dependency_files)
        else:
            dependency_files_latest_ts = None

        # add targets last so we can check for circular dependencies
        target_files = set()
        for t in targets.values():
            target_files = target_files | set(self._add_nodes(t, is_target=True))

        # checks implicitly if sources exists
        if not self._check_targets_ok(target_files, dependency_files_latest_ts):
            fun = self._as_fun(builder)
            logging.info("Building %s", list(targets.values()))

            try:
                fun(**fun_kwargs)
                if not self._check_targets_ok(target_files, dependency_files_latest_ts):
                    raise Exception("Build failed")

                # harmonize timestamp
                for target in target_files:
                    os.utime(target, times=(self.__now, self.__now))

            except Exception as exc:
                logging.error(exc)
                raise

        else:
            logging.debug("Skipping %s", list(target_files))

        return target_files

    def _as_fun(self, builder):
        if isinstance(builder, Callable):
            return builder
        else:
            return create_cmd(builder)

    def _check_target_ok(self, target, sources_depends_latest_ts):
        """target is ok if
        * it exists
        * newer than all sources (if they exist)
        """
        if os.path.isfile(target):
            target_latest_ts = self._get_timestamp(target)
        else:
            target_latest_ts = None

        return target_latest_ts and (  # target exists and is up to date
            not sources_depends_latest_ts
            or (
                sources_depends_latest_ts
                and target_latest_ts >= sources_depends_latest_ts
            )
        )

    def _check_targets_ok(self, targets, sources_depends_latest_ts):
        return all(self._check_target_ok(t, sources_depends_latest_ts) for t in targets)

    def _add_nodes(self, paths, is_target=False):
        if not isinstance(paths, list):
            paths = [paths]

        paths = [self._get_path(p) for p in paths]

        for path in paths:

            if is_target:
                logging.info(f"add target: {path}")
                if path in self.__nodes:
                    raise ValueError(
                        "target path cannot be source for this or previous builds: %s"
                        % path
                    )
                # assert folder exists
                os.makedirs(os.path.dirname(path), exist_ok=True)

                self.__targets.add(path)
            else:
                logging.info(f"add node: {path}")

        self.__nodes.add(path)
        return paths

    @staticmethod
    def _get_path(path):
        path = os.path.realpath(path)
        # make sure path is not a folder
        assert not os.path.isdir(path)
        return path

    def _get_timestamp(self, path):
        ts = os.path.getmtime(path)
        return ts

    def _get_latest_ts(self, paths):
        return max(self._get_timestamp(p) for p in paths)


def create_cmd(cmd_template):
    def fun(**kwargs):
        # prepare command
        logging.info(kwargs)
        if isinstance(cmd_template, str):
            logging.info(cmd_template)
            cmd = cmd_template % kwargs
            logging.debug(cmd)
        elif isinstance(cmd_template, list):
            cmd = [p % kwargs for p in cmd_template]
            logging.debug(" ".join(cmd))
        else:
            raise NotImplementedError(type(cmd_template))

        p = sp.Popen(cmd, shell=True, stdout=sp.PIPE, stderr=sp.PIPE)
        _, stderr = p.communicate()
        if p.returncode:
            stderr = stderr.decode()
            raise Exception(stderr)

    return fun


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
                Exception,
                env.build,
                builder=shutil.copy,
                targets={"dst": f"{pwd}/s"},
                sources={"src": f"{pwd}/t"},
            )


if __name__ == "__main__":
    logging.basicConfig(
        format="[%(asctime)s %(levelname)7s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.DEBUG,
    )
    unittest.main()
