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
from functools import partial
from typing import Callable


class BuildEnvironment:
    __slots__ = ["__nodes", "__targets", "__now"]

    def __init__(self):
        self.__nodes = set()
        self.__targets = set()
        self.__now = self._get_cur_timestamp()
        logging.debug("NOW: %s", self.__now)

    def _get_cur_timestamp(self):
        """do not use datetime, because it can be
        different from file system time, which we want to use
        """
        with tempfile.NamedTemporaryFile(delete=True) as file:
            return self._get_timestamp(file.name, allow_future=True)

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

        dependencies = [self._add_node(d, allow_dir=True) for d in dependencies]
        sources = dict((k, self._add_node(v)) for k, v in sources.items())
        # add targets last so we can check for circular dependencies
        targets = dict(
            (k, self._add_node(v, is_target=True)) for k, v in targets.items()
        )

        # make sure no overlapping names exist
        fun_kwargs = targets | sources | kwargs
        assert len(fun_kwargs) == len(targets) + len(sources) + len(kwargs)

        # checks implicitly if sources exists
        if not all(
            self._check_target_ok(t, *dependencies, *sources.values())
            for t in targets.values()
        ):
            self._prepare_build(targets)
            fun = self._as_fun(builder)
            logging.info("Building %s", list(targets.values()))

            try:
                fun(**fun_kwargs)
            except Exception as exc:
                logging.error(exc)
                # delete failed target (if exist)
                for target in targets.values():
                    if os.path.isfile(target):
                        os.remove(target)

            for target in targets.values():
                if not os.path.isfile(target):
                    raise Exception("Build failed for %s" % target)

            # set timestamp
            for target in targets.values():
                os.utime(target, times=(self.__now, self.__now))

        else:
            logging.debug("Skipping %s", list(targets.values()))

        return targets

    def _as_fun(self, builder):
        if isinstance(builder, Callable):
            return builder
        else:
            return create_cmd(builder)

    def _check_target_ok(self, target, *dependencies):
        if dependencies:
            sources_depends_latest_ts = self._get_latest_ts(dependencies)
        else:
            sources_depends_latest_ts = None

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

    def _prepare_build(self, targets):
        for target in targets.values():
            # if os.path.isfile(target):
            #    os.remove(target)
            os.makedirs(os.path.dirname(target), exist_ok=True)

    def _add_node(self, path, is_target=False, allow_dir=False):        
        if allow_dir and os.path.isdir(path):
            for rt, _ds, fs in os.walk(path):
                for f in fs:
                    self._add_node(f'{rt}/{f}', is_target=is_target, allow_dir=False)
            return
        path = self._get_path(path)
        if is_target:
            if path in self.__nodes:
                raise ValueError(
                    "target path cannot be source for this or previous builds: %s"
                    % path
                )
            self.__targets.add(path)
        self.__nodes.add(path)
        return path

    @staticmethod
    def _get_path(path):
        path = os.path.realpath(path)
        return path

    def _get_timestamp(self, path, allow_future=False):
        ts = os.path.getmtime(path)
        if not allow_future and ts > self.__now:
            raise Exception("timestamp %s > now %s for %s" % (ts, self.__now, path))
        logging.debug("Timestap %s %s", ts, path)
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
                ValueError,
                partial(
                    env.build,
                    builder=shutil.copy,
                    targets={"dst": f"{pwd}/s"},
                    sources={"src": f"{pwd}/t"},
                ),
            )


if __name__ == "__main__":
    logging.basicConfig(
        format="[%(asctime)s %(levelname)7s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        level=logging.DEBUG,
    )
    unittest.main()
